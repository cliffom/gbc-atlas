"""Independent manifest-v1 consumer oracles; no scene allocator is tested here."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from gbc_atlas import load_atlas, verify_approval

FIXTURES = Path(__file__).resolve().parents[1] / "examples/palette-semantics"


class PaletteSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads((FIXTURES / "expected.json").read_text())

    def test_cell_region_and_frame_identities(self):
        for name, expected in self.expected["atlases"].items():
            for deduplicate in (False, True):
                with self.subTest(atlas=name, deduplicate=deduplicate):
                    atlas = load_atlas(
                        FIXTURES / name / f"{name}.atlas.json", deduplicate=deduplicate
                    )
                    m = atlas.manifest
                    self.assertEqual(list(atlas.dimensions), expected["dimensions"])
                    self.assertEqual(m["cell_palettes"], expected["cell_palettes"])
                    if not deduplicate:
                        self.assertEqual(list(atlas.cell_tiles), expected["cell_tiles"])
                    for pool, labels in expected["palette_identities"].items():
                        for palette, label in zip(m["palettes"], labels, strict=True):
                            key = palette if pool == "BG" else palette[1:]
                            self.assertEqual(
                                key, self.expected["identities"][pool][label]
                            )
                    cols, _ = atlas.dimensions
                    for r, encoded in zip(m["regions"], atlas.regions, strict=True):
                        oracle = expected["regions"][r["name"]]
                        # Manifest pixels and generated C/API cell rectangles agree.
                        x, y, width, height = encoded[:4]
                        self.assertEqual(
                            [x * 8, y * 8, width * 8, height * 8],
                            [r[k] for k in ("x", "y", "width", "height")],
                        )
                        cells = [
                            cy * cols + cx
                            for cy in range(y, y + height)
                            for cx in range(x, x + width)
                        ]
                        self.assertEqual(cells, oracle["cells"])
                        local_ids = [m["cell_palettes"][cell] for cell in cells]
                        self.assertEqual(local_ids, oracle["local_palettes"])
                        pool = "OBJ" if r["kind"] == "sprite" else "BG"
                        self.assertEqual(pool, oracle["pool"])
                        labels = expected["palette_identities"][pool]
                        self.assertEqual(
                            sorted({labels[i] for i in local_ids}),
                            sorted(oracle["identities"]),
                        )
                        for cell in cells:
                            if pool == "OBJ" and cell // cols % 2 == 0:
                                self.assertEqual(atlas.cell_tiles[cell] % 2, 0)
                                self.assertEqual(
                                    atlas.cell_tiles[cell + cols],
                                    atlas.cell_tiles[cell] + 1,
                                )
                    self.assertEqual(
                        {
                            a["name"]: [f["region"] for f in a["frames"]]
                            for a in m["animations"]
                        },
                        expected["animations"],
                    )
                    # A frame resolves through the same region oracle; no palette
                    # is attached directly to an animation or inherited from frame 0.
                    for frames in expected["animations"].values():
                        self.assertEqual(
                            [expected["regions"][f]["identities"] for f in frames],
                            [["A"], ["C"]],
                        )
                    with self.assertRaisesRegex(ValueError, "approval"):
                        verify_approval(atlas)

    def test_exact_indices_survive_mixed_encoding(self):
        for name in self.expected["atlases"]:
            atlas = load_atlas(FIXTURES / name / f"{name}.atlas.json")
            cols, rows = atlas.dimensions
            for y in range(rows * 8):
                for x in range(cols * 8):
                    cell = y // 8 * cols + x // 8
                    offset = atlas.cell_tiles[cell] * 16 + y % 8 * 2
                    bit = 7 - x % 8
                    index = ((atlas.tiles[offset] >> bit) & 1) | (
                        ((atlas.tiles[offset + 1] >> bit) & 1) << 1
                    )
                    self.assertEqual(index, (x + y) % 4)
            self.assertEqual(
                list(atlas.palettes),
                [
                    r | g << 5 | b << 10
                    for palette in atlas.manifest["palettes"]
                    for r, g, b in palette
                ],
            )

    def test_fixture_mutations_keep_existing_validation(self):
        cases = [
            ("local_count", "1..8 local palettes"),
            ("pair", "share a palette"),
            ("color", "outside assigned"),
            ("bg_transparent", "Transparent background"),
            ("partial_alpha", "Partial alpha"),
            ("obj_zero", "outside assigned"),
            ("duplicate_visible", "Duplicate visible"),
            ("overlap", "Overlapping tile/sprite"),
            ("sprite_alignment", "align vertically"),
            ("frame", "named region"),
        ]
        for case, error in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp) / "mixed"
                shutil.copytree(FIXTURES / "mixed", folder)
                path = folder / "mixed.atlas.json"
                m = copy.deepcopy(json.loads(path.read_text()))
                with Image.open(folder / "atlas.png") as source:
                    image = source.copy()
                if case == "local_count":
                    m["palettes"] *= 2
                elif case == "pair":
                    # Semantically identical OBJ keys still need the SAME local ID.
                    m["cell_palettes"][6] = 0
                elif case == "color":
                    image.putpixel((0, 0), (1, 2, 3, 255))
                elif case == "bg_transparent":
                    image.putpixel((0, 0), (0, 0, 0, 0))
                elif case == "partial_alpha":
                    image.putpixel((16, 0), (0, 0, 0, 128))
                elif case == "obj_zero":
                    image.putpixel((16, 0), (8, 16, 25, 255))
                elif case == "duplicate_visible":
                    m["palettes"][2][2] = m["palettes"][2][1]
                elif case == "overlap":
                    m["regions"][0]["width"] = 24
                elif case == "sprite_alignment":
                    m["regions"][1]["height"] = 8
                elif case == "frame":
                    m["animations"][0]["frames"][1]["region"] = "missing"
                image.save(folder / "atlas.png")
                path.write_text(json.dumps(m))
                with self.assertRaisesRegex(ValueError, error):
                    load_atlas(path)
