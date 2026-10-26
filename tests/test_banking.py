"""Opt-in banking stays shared between API, CLI, and project handoffs."""

import contextlib
import io
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gbc_atlas import load_atlas, render_c, render_types
from gbc_atlas.cli import main
from gbc_atlas.project import load_project

FIXTURE = Path(__file__).parent / "fixtures/v1/compat.atlas.json"


class BankingTests(unittest.TestCase):
    def test_banked_metadata_and_native_compile(self):
        atlas = load_atlas(FIXTURE)
        for bank, pragma in (("auto", 255), (0, 0), (7, 7), (254, 254), (255, 255)):
            with self.subTest(bank=bank), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                output = render_c(atlas, bank=bank)
                self.assertTrue(
                    output["compat.c"].startswith(f"#pragma bank {pragma}\n")
                )
                self.assertEqual(output["compat.c"].count("BANKREF(compat)"), 1)
                self.assertIn("BANKREF_EXTERN(compat)", output["compat.h"])
                self.assertIn("#define COMPAT_BANKED 1", output["compat.h"])
                self.assertIn("#include <gbdk/platform.h>", output["compat.h"])
                for name, text in output.items():
                    (root / name).write_text(text)
                (root / "asset_types.h").write_text(render_types())
                (root / "gbdk").mkdir()
                (root / "gbdk/platform.h").write_text(
                    "#define BANKREF(n)\n#define BANKREF_EXTERN(n)\n"
                )
                subprocess.run(
                    [
                        "cc",
                        "-std=c99",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        "-Wno-unknown-pragmas",
                        "-I",
                        str(root),
                        "-c",
                        str(root / "compat.c"),
                        "-o",
                        str(root / "compat.o"),
                    ],
                    check=True,
                    capture_output=True,
                )

    def test_invalid_bank_values(self):
        atlas = load_atlas(FIXTURE)
        for bank in (True, False, -1, 256, 1.0, "7", "AUTO", [], {}):
            with (
                self.subTest(bank=bank),
                self.assertRaisesRegex(ValueError, "bank must"),
            ):
                render_c(atlas, bank=bank)

    def test_cli_and_project_check_the_same_banked_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "pyproject.toml"
            shutil.copytree(FIXTURE.parent, root / "input")
            for bank in ("auto", 9):
                value = '"auto"' if bank == "auto" else str(bank)
                config.write_text(
                    '[tool.gbc-atlas]\nmanifests = ["input/*.atlas.json"]\n'
                    f'output = "out"\nbank = {value}\n'
                )
                self.assertEqual(load_project(config).bank, bank)
                main(["handoff", "--config", str(config)])
                args = ["--input", str(root / "input"), "--output", str(root / "out")]
                main(["check", *args, "--bank", str(bank)])
                before = {p.name: p.read_bytes() for p in (root / "out").iterdir()}
                with (
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    main(["check", *args])
                self.assertEqual(
                    before, {p.name: p.read_bytes() for p in (root / "out").iterdir()}
                )
                main(["generate", *args, "--bank", str(bank)])
                main(["check", "--config", str(config)])

    def test_gbdk_compile_link(self):
        lcc = os.environ.get("GBDK_LCC") or shutil.which("lcc")
        if not lcc:
            self.skipTest("Set GBDK_LCC to run GBDK autobank compile/link")
        for bank, deduplicate in (("auto", False), ("auto", True), (7, True)):
            with self.subTest(bank=bank, deduplicate=deduplicate):
                self.check_gbdk(lcc, bank, deduplicate)

    def check_gbdk(self, lcc, selected_bank, deduplicate):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            atlas = load_atlas(FIXTURE, deduplicate=deduplicate)
            for name, text in render_c(atlas, bank=selected_bank).items():
                (root / name).write_text(text)
            (root / "asset_types.h").write_text(render_types())
            (root / "main.c").write_text(
                '#include <gb/gb.h>\n#include "compat.h"\n'
                "volatile uint8_t result;\nvoid main(void) {\n"
                "uint8_t saved = CURRENT_BANK;\nSWITCH_ROM(BANK(compat));\n"
                "result = compat_tiles[0] + compat_cell_tiles[0] + "
                "compat_cell_palettes[0] + compat_palettes[0] + compat_regions[0].x;\n"
                "#ifdef COMPAT_HAS_CELL_FLAGS\nresult += compat_cell_flags[0];\n#endif\n"
                "SWITCH_ROM(saved);\n}\n"
            )
            subprocess.run(
                [
                    lcc,
                    "-autobank",
                    "-Wm-yC",
                    "-Wm-yt0x19",
                    "-Wm-yoA",
                    "-Wl-m",
                    "-Wl-w",
                    "-o",
                    str(root / "smoke.gb"),
                    str(root / "main.c"),
                    str(root / "compat.c"),
                ],
                cwd=root,
                check=True,
                capture_output=True,
            )
            mapping = (root / "smoke.map").read_text()
            # bankpack resolves the single atlas BANKREF outside fixed bank 0.
            match = re.search(r"([0-9A-Fa-f]+)\s+___bank_compat\b", mapping)
            self.assertIsNotNone(match, mapping)
            self.assertGreater(int(match[1], 16), 0)
            self.assertLess(int(match[1], 16), 255)
            bank = int(match[1], 16)
            if selected_bank != "auto":
                self.assertEqual(bank, selected_bank)
            for suffix in (
                "tiles",
                "cell_tiles",
                "cell_palettes",
                "palettes",
                "regions",
                "idle_regions",
                "idle_duration_ms",
            ) + (("cell_flags",) if deduplicate else ()):
                symbol = re.search(rf"([0-9A-Fa-f]+)\s+_compat_{suffix}\b", mapping)
                self.assertIsNotNone(symbol)
                self.assertEqual(int(symbol[1], 16) >> 16, bank)
