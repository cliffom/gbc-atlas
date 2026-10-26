"""Index-exact synthetic reconstruction, including hardware 8x16 Y semantics."""

import contextlib
import io
import json
import random
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gbc_atlas import load_atlas, render_c, render_types, verify_approval
from gbc_atlas.cli import main
from gbc_atlas.project import load_project


def mirror(pixels, flags):
    rows = [list(row) for row in pixels]
    if flags & 0x40:
        rows.reverse()
    if flags & 0x20:
        rows = [row[::-1] for row in rows]
    return rows


def pattern(height, *, sprite=False):
    rng = random.Random(1234 + height)
    return [
        [rng.randrange(1 if sprite else 0, 4) for _ in range(8)] for _ in range(height)
    ]


class DeduplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "sample.atlas.json"
        self.m = {
            "version": 1,
            "id": "sample",
            "png": "atlas.png",
            "palettes": [[[0, 0, 0], [10, 10, 10], [20, 20, 20], [31, 31, 31]]],
        }

    def prepare(self, cols, rows, regions):
        self.image = Image.new("RGBA", (cols * 8, rows * 8), (0, 0, 0, 255))
        self.m.update(cell_palettes=[0] * (cols * rows), regions=regions)

    def paint(self, x, y, pixels, *, sprite=False):
        for py, row in enumerate(pixels):
            for px, index in enumerate(row):
                v = (0, 82, 165, 255)[index]
                self.image.putpixel(
                    (x + px, y + py), (v, v, v, 0 if sprite and index == 0 else 255)
                )

    def save(self, *, deduplicate=True):
        self.image.save(self.root / "atlas.png")
        self.path.write_text(json.dumps(self.m))
        return load_atlas(self.path, deduplicate=deduplicate)

    def assert_reconstruction(self, data):
        cols, _ = data.dimensions
        sprite_cells = set()
        for region in data.manifest["regions"]:
            if region["kind"] == "sprite":
                for y in range(region["y"] // 8, (region["y"] + region["height"]) // 8):
                    for x in range(
                        region["x"] // 8, (region["x"] + region["width"]) // 8
                    ):
                        sprite_cells.add(y * cols + x)
        for y in range(self.image.height):
            for x in range(self.image.width):
                cell = (y // 8) * cols + x // 8
                flags = data.cell_flags[cell]
                tile = data.cell_tiles[cell]
                # Sprite flags operate on the complete pair; Y exchanges halves.
                if cell in sprite_cells and flags & 0x40:
                    tile ^= 1
                px = 7 - x % 8 if flags & 0x20 else x % 8
                py = 7 - y % 8 if flags & 0x40 else y % 8
                offset = tile * 16 + py * 2
                index = ((data.tiles[offset] >> (7 - px)) & 1) | (
                    ((data.tiles[offset + 1] >> (7 - px)) & 1) << 1
                )
                source = self.image.getpixel((x, y))
                expected = 0 if source[3] == 0 else (0, 82, 165, 255).index(source[0])
                self.assertEqual(index, expected, (x, y))
                if cell in sprite_cells and index == 0:
                    self.assertEqual(source[3], 0)
                else:
                    palette = data.manifest["palettes"][
                        data.manifest["cell_palettes"][cell]
                    ]
                    rgb = tuple((v * 255 + 15) // 31 for v in palette[index])
                    self.assertEqual((*rgb, 255), source)

    def test_tiles_all_flips_exact_duplicates_and_local_palette_boundaries(self):
        self.prepare(
            7,
            1,
            [
                {
                    "name": "terrain",
                    "kind": "tile",
                    "x": 0,
                    "y": 0,
                    "width": 56,
                    "height": 8,
                }
            ],
        )
        base = pattern(8)
        for i, flag in enumerate((0, 0x20, 0x40, 0x60, 0, 0, 0)):
            self.paint(i * 8, 0, mirror(base, flag))
        # Equal RGB colors in different local palettes still cannot share tiles.
        self.m["palettes"].append(self.m["palettes"][0])
        self.m["cell_palettes"][5] = 1
        # Different 2bpp indices are never normalized to another palette ordering.
        self.paint(48, 0, [[(i + 1) % 4 for i in row] for row in base])
        data = self.save()
        self.assertEqual(data.cell_tiles, (0, 0, 0, 0, 0, 1, 2))
        self.assertEqual(data.cell_flags, (0, 0x20, 0x40, 0x60, 0, 0, 0))
        original = load_atlas(self.path)
        self.assertEqual(data.tiles[:16], original.tiles[:16])
        self.assertEqual(data.digest, original.digest)
        self.assertEqual(data.tiles_saved, 4)
        self.assert_reconstruction(data)
        self.assertEqual(data, load_atlas(self.path, deduplicate=True))

    def test_sprite_pairs_all_flips_no_half_reuse_and_palette_boundaries(self):
        self.prepare(
            7,
            2,
            [
                {
                    "name": "actor",
                    "kind": "sprite",
                    "x": 0,
                    "y": 0,
                    "width": 56,
                    "height": 16,
                }
            ],
        )
        base = pattern(16, sprite=True)
        base[0][0] = 0  # Transparency participates as index zero.
        for i, flag in enumerate((0, 0x20, 0x40, 0x60, 0, 0, 0)):
            self.paint(i * 8, 0, mirror(base, flag), sprite=True)
        # An otherwise new pair with an already present top half stays whole.
        changed = [row[:] for row in base]
        changed[15][7] = changed[15][7] % 3 + 1
        self.paint(40, 0, changed, sprite=True)
        self.m["palettes"].append(self.m["palettes"][0])
        self.m["cell_palettes"][6] = self.m["cell_palettes"][13] = 1
        data = self.save()
        self.assertEqual(data.cell_tiles, (0, 0, 0, 0, 0, 2, 4, 1, 1, 1, 1, 1, 3, 5))
        self.assertEqual(data.cell_flags, (0, 0x20, 0x40, 0x60, 0, 0, 0) * 2)
        self.assertEqual(data.tiles_saved, 8)
        self.assert_reconstruction(data)

    def test_mixed_atlas_keeps_kinds_regions_and_animations(self):
        self.prepare(
            4,
            3,
            [
                {
                    "name": "actor",
                    "kind": "sprite",
                    "x": 0,
                    "y": 0,
                    "width": 32,
                    "height": 16,
                    "duration_ms": 75,
                },
                {
                    "name": "terrain",
                    "kind": "tile",
                    "x": 0,
                    "y": 16,
                    "width": 32,
                    "height": 8,
                },
                {
                    "name": "corner",
                    "kind": "tile",
                    "x": 8,
                    "y": 16,
                    "width": 8,
                    "height": 8,
                },
            ],
        )
        self.m["animations"] = [{"name": "idle", "frames": [{"region": "actor"}]}]
        base = pattern(16, sprite=True)
        for i, flag in enumerate((0, 0x20, 0x40, 0x60)):
            self.paint(i * 8, 0, mirror(base, flag), sprite=True)
            # Tile bytes equal a sprite half, but remain a separate kind.
            self.paint(i * 8, 16, mirror(base[:8], flag))
        data = self.save()
        original = load_atlas(self.path)
        self.assertEqual(len(data.tiles) // 16, 3)
        self.assertEqual(data.cell_tiles[8:], (2, 2, 2, 2))
        self.assertEqual(data.regions, original.regions)
        self.assert_reconstruction(data)
        output = render_c(data)
        self.assertIn("#define SAMPLE_REGION_CORNER 2", output["sample.h"])
        self.assertIn("sample_idle_regions[1]", output["sample.c"])
        self.assertIn("#define SAMPLE_HAS_CELL_FLAGS 1", output["sample.h"])
        for name, text in output.items():
            (self.root / name).write_text(text)
        (self.root / "asset_types.h").write_text(render_types())
        subprocess.run(
            [
                "cc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-c",
                str(self.root / "sample.c"),
                "-o",
                str(self.root / "sample.o"),
            ],
            check=True,
            capture_output=True,
        )

    def test_symmetry_prefers_unflipped_and_first_occurrence_is_canonical(self):
        self.prepare(
            3,
            1,
            [
                {
                    "name": "terrain",
                    "kind": "tile",
                    "x": 0,
                    "y": 0,
                    "width": 24,
                    "height": 8,
                }
            ],
        )
        base = pattern(8)
        self.paint(0, 0, mirror(base, 0x60))
        self.paint(8, 0, base)
        data = self.save()
        self.assertEqual(data.cell_tiles, (0, 0, 1))
        self.assertEqual(data.cell_flags, (0, 0x60, 0))
        self.assertEqual(data.tiles[:16], load_atlas(self.path).tiles[:16])
        self.assert_reconstruction(data)
        self.image = Image.new("RGBA", (24, 8), (0, 0, 0, 255))
        data = self.save()
        self.assertEqual(data.cell_flags, (0, 0, 0))

    def test_configured_and_explicit_handoff_and_readonly_checks(self):
        self.prepare(
            2,
            1,
            [
                {
                    "name": "terrain",
                    "kind": "tile",
                    "x": 0,
                    "y": 0,
                    "width": 16,
                    "height": 8,
                }
            ],
        )
        data = self.save()
        self.m["approval"] = {
            "status": "approved",
            "digest": data.digest,
            "by": "fixture",
            "date": "2026-10-25",
            "evidence": "Synthetic test",
        }
        verify_approval(self.save())
        config = self.root / "pyproject.toml"
        config.write_text(
            '[tool.gbc-atlas]\nmanifests = ["*.atlas.json"]\noutput = "out"\nbank = "auto"\ndeduplicate = true\n'
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["validate", str(self.path), "--deduplicate"])
            main(["handoff", "--config", str(config)])
        self.assertIn("saved 1", out.getvalue())
        args = [
            "--input",
            str(self.path),
            "--output",
            str(self.root / "out"),
            "--deduplicate",
            "--bank",
            "auto",
        ]
        main(["check", *args])
        main(["generate", *args])
        main(["check", "--config", str(config)])
        flags = self.root / "out/sample.c"
        flags.write_text(
            flags.read_text().replace(
                "sample_cell_flags[2] = {\n    0, 0,",
                "sample_cell_flags[2] = {\n    32, 0,",
            )
        )
        before = {p.name: p.read_bytes() for p in flags.parent.iterdir()}
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["check", *args])
        self.assertEqual(
            before, {p.name: p.read_bytes() for p in flags.parent.iterdir()}
        )

    def test_options_are_strict_and_default_has_no_flags(self):
        self.prepare(
            1,
            1,
            [
                {
                    "name": "terrain",
                    "kind": "tile",
                    "x": 0,
                    "y": 0,
                    "width": 8,
                    "height": 8,
                }
            ],
        )
        data = self.save(deduplicate=False)
        self.assertIsNone(data.cell_flags)
        self.assertNotIn("cell_flags", render_c(data)["sample.c"])
        self.assertNotIn("HAS_CELL_FLAGS", render_c(data)["sample.h"])
        for value in (0, 1, "true", None, [], {}):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "boolean"),
            ):
                load_atlas(self.path, deduplicate=value)
        for value in ('"true"', "1"):
            config = self.root / "pyproject.toml"
            config.write_text(
                '[tool.gbc-atlas]\nmanifests = ["*.atlas.json"]\noutput = "out"\ndeduplicate = '
                + value
            )
            with self.assertRaisesRegex(ValueError, "boolean"):
                load_project(config)
