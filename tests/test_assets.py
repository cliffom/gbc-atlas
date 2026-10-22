"""Synthetic fixtures test conversion invariants, not production artwork."""

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gbc_atlas import load_atlas, render_c, verify_approval
from gbc_atlas.cli import main


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "assets/art/test"
        self.folder.mkdir(parents=True)
        self.path = self.folder / "test.atlas.json"
        # Only hashes are read from editable sources. These are test stand-ins.
        (self.folder / "atlas.aseprite").write_bytes(b"synthetic atlas source")
        (self.folder / "preview.aseprite").write_bytes(b"synthetic preview source")
        Image.new("RGBA", (160, 144), "white").save(self.folder / "scene.png")
        self.image = Image.new("RGBA", (16, 16), (0, 0, 0, 255))
        self.m = {
            "version": 1,
            "id": "test",
            "source": "atlas.aseprite",
            "png": "atlas.png",
            "preview": "preview.aseprite",
            "review_images": ["scene.png"],
            "palettes": [[[0, 0, 0], [10, 10, 10], [20, 20, 20], [31, 31, 31]]],
            "cell_palettes": [0] * 4,
            "regions": [
                {
                    "name": "object",
                    "kind": "tile",
                    "x": 0,
                    "y": 0,
                    "width": 16,
                    "height": 16,
                    "origin": [8, 15],
                    "placement": "Ground contact at origin",
                }
            ],
        }

    def save(self):
        self.image.save(self.folder / "atlas.png")
        self.path.write_text(json.dumps(self.m))

    def approve(self):
        self.save()
        self.m["approval"] = {
            "status": "approved",
            "digest": load_atlas(self.path).digest,
            "by": "test fixture",
            "date": "2026-10-21",
            "evidence": "Synthetic test only",
        }
        self.save()

    def run_cli(self, command):
        return main(
            [
                command,
                "--input",
                str(self.root / "assets/art"),
                "--output",
                str(self.root / "src/generated"),
            ]
        )

    def test_roundtrip_pixels_and_c_compile(self):
        for y in range(16):
            for x in range(16):
                v = [0, 82, 165, 255][(x + y) % 4]
                self.image.putpixel((x, y), (v, v, v, 255))
        self.approve()
        data = load_atlas(self.path)
        tiles, mapping = (data.tiles, data.cell_tiles)
        for y in range(16):
            for x in range(16):
                tile = mapping[(y // 8) * 2 + x // 8]
                offset = tile * 16 + (y % 8) * 2
                bit = 7 - x % 8
                index = ((tiles[offset] >> bit) & 1) | (
                    ((tiles[offset + 1] >> bit) & 1) << 1
                )
                self.assertEqual(index, (x + y) % 4)
        self.run_cli("generate")
        self.run_cli("check")
        include = self.root / "src/generated"
        subprocess.run(
            [
                "cc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(include),
                "-c",
                str(self.root / "src/generated/test.c"),
                "-o",
                str(self.root / "test.o"),
            ],
            check=True,
            capture_output=True,
        )
        file = self.root / "src/generated/test.c"
        file.write_text(file.read_text() + "/* drift */")
        with self.assertRaises(SystemExit):
            self.run_cli("check")

    def test_sprite_transparency_and_vertical_pairs(self):
        self.m["regions"][0]["kind"] = "sprite"
        self.image = Image.new("RGBA", (16, 16), (231, 93, 10, 0))
        self.image.putpixel((0, 0), (82, 82, 82, 255))
        self.image.putpixel((0, 8), (165, 165, 165, 255))
        self.save()
        data = load_atlas(self.path)
        self.assertEqual(list(data.cell_tiles), [0, 2, 1, 3])
        self.assertEqual(list(data.tiles)[:2], [128, 0])
        self.assertEqual(list(data.tiles)[16:18], [0, 128])
        self.assertEqual(list(data.tiles)[32:], [0] * 32)
        self.m["palettes"].append(copy.deepcopy(self.m["palettes"][0]))
        self.m["cell_palettes"][2] = 1
        self.save()
        with self.assertRaisesRegex(ValueError, "share a palette"):
            load_atlas(self.path)

    def test_reject_pixel_violations(self):
        for pixel, error in [
            ((0, 0, 0, 0), "Transparent background"),
            ((0, 0, 0, 128), "Partial alpha"),
            ((1, 2, 3, 255), "outside assigned"),
        ]:
            with self.subTest(pixel=pixel):
                self.image.putpixel((0, 0), pixel)
                self.save()
                with self.assertRaisesRegex(ValueError, error):
                    load_atlas(self.path)

    def test_approval_binds_sources_pixels_review_and_metadata(self):
        for field in ("source", "preview", "png", "review", "metadata"):
            with self.subTest(field=field):
                self.approve()
                if field == "metadata":
                    self.m["regions"][0]["placement"] += " updated"
                    self.save()
                else:
                    name = "scene.png" if field == "review" else self.m[field]
                    file = self.folder / name
                    file.write_bytes(file.read_bytes() + b"changed")
                with self.assertRaisesRegex(ValueError, "stale approval"):
                    verify_approval(load_atlas(self.path))

    def test_bounds_paths_and_animation(self):
        self.save()
        for changes, error in [
            ({"png": "../escape.png"}, "within"),
            ({"cell_palettes": [0]}, "every cell"),
            (
                {
                    "animations": [
                        {
                            "name": "idle",
                            "frames": [{"region": "missing", "duration_ms": 100}],
                        }
                    ]
                },
                "frame requires",
            ),
        ]:
            old = copy.deepcopy(self.m)
            self.m.update(changes)
            self.save()
            with self.assertRaisesRegex(ValueError, error):
                load_atlas(self.path)
            self.m = old
        self.m["animations"] = [
            {"name": "idle", "frames": [{"region": "object", "duration_ms": 125}]}
        ]
        self.save()
        output = render_c(load_atlas(self.path))
        self.assertIn("test_idle_duration_ms[1]", output["test.c"])
        self.assertIn("125", output["test.c"])

    def test_mixed_sheet_preserves_zero_and_pairs_after_odd_tile_count(self):
        # A leading BG cell in source order must not shift sprite tile IDs to odd.
        self.image = Image.new("RGBA", (16, 24), (0, 0, 0, 255))
        self.m["cell_palettes"] = [0] * 6
        self.m["regions"] = [
            {"name": "wall", "kind": "tile", "x": 0, "y": 0, "width": 8, "height": 24},
            {
                "name": "actor",
                "kind": "sprite",
                "x": 8,
                "y": 0,
                "width": 8,
                "height": 16,
                "duration_ms": 100,
            },
            {"name": "floor", "kind": "tile", "x": 8, "y": 16, "width": 8, "height": 8},
        ]
        self.m["animations"] = [{"name": "idle", "frames": [{"region": "actor"}]}]
        for y in range(16):
            for x in range(8, 16):
                self.image.putpixel((x, y), (99, 12, 23, 0))
        self.image.putpixel((8, 0), (82, 82, 82, 255))
        self.image.putpixel((8, 8), (165, 165, 165, 255))
        self.save()
        data = load_atlas(self.path)
        self.assertEqual(list(data.cell_tiles), [2, 0, 3, 1, 4, 5])
        self.assertEqual(list(data.tiles)[:2], [128, 0])
        self.assertEqual(list(data.tiles)[16:18], [0, 128])
        self.assertEqual(
            list(data.tiles)[32:], [0] * 64
        )  # BG index zero is still painted black.
        self.assertIn("100", render_c(data)["test.c"])
        self.image.putpixel((8, 0), (0, 0, 0, 255))
        self.save()
        with self.assertRaisesRegex(ValueError, "outside assigned"):
            load_atlas(self.path)  # Visible OBJ pixels cannot use palette index zero.

    def test_minimal_interchange_and_kind_conflict(self):
        for key in ("source", "preview", "review_images"):
            del self.m[key]
        self.save()
        load_atlas(self.path)
        conflict = copy.deepcopy(self.m["regions"][0])
        conflict.update(name="actor", kind="sprite")
        self.m["regions"].append(conflict)
        self.save()
        with self.assertRaisesRegex(ValueError, "Overlapping tile/sprite"):
            load_atlas(self.path)


if __name__ == "__main__":
    unittest.main()
