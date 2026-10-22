"""CLI policy and compatibility with the pre-extraction converter."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

from gbc_atlas import load_atlas, render_c, render_types, verify_approval
from gbc_atlas.cli import main

FIXTURE = Path(__file__).parent / "fixtures/v1"


class CompatibilityTests(unittest.TestCase):
    def test_original_digest_and_c_bytes(self):
        data = load_atlas(FIXTURE / "compat.atlas.json")
        self.assertEqual(
            data.digest,
            "1b555b26485fbe7338af9408e9237f58ce0902100e89fd336c1bd8c308110a4b",
        )
        verify_approval(data)
        for name, content in render_c(data, generator_label="tools/assets.py").items():
            self.assertEqual(
                content.encode(), (FIXTURE / (name + ".expected")).read_bytes()
            )

    def test_packaged_resources(self):
        self.assertIn("GBC_ATLAS_ASSET_TYPES_H", render_types())
        skill = files("gbc_atlas").joinpath("skills/create-atlas")
        self.assertTrue(skill.joinpath("SKILL.md").is_file())
        self.assertTrue(skill.joinpath("references/format.md").is_file())
        self.assertTrue(skill.joinpath("references/project.md").is_file())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["skill-path"]), 0)
        self.assertTrue(Path(output.getvalue().strip(), "SKILL.md").is_file())

    def test_cli_checks_without_writes_and_rejects_stale_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input"
            shutil.copytree(FIXTURE, source)
            output = root / "generated"
            args = ["--input", str(source), "--output", str(output)]
            with self.assertRaises(SystemExit):
                main(["check", *args])
            self.assertFalse(output.exists())
            self.assertEqual(main(["generate", *args]), 0)
            self.assertEqual(main(["check", *args]), 0)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            path = source / "compat.atlas.json"
            m = json.loads(path.read_text())
            m["custom_metadata"]["changed"] = True
            path.write_text(json.dumps(m))
            with self.assertRaises(SystemExit):
                main(["generate", *args])
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
            self.assertTrue((source / "compat.c.expected").is_file())

    def test_invalid_second_pack_prevents_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(FIXTURE, root / "input")
            (root / "input/z.atlas.json").write_text('{"version":0}')
            with self.assertRaises(SystemExit):
                main(
                    [
                        "generate",
                        "--input",
                        str(root / "input"),
                        "--output",
                        str(root / "out"),
                    ]
                )
            self.assertFalse((root / "out").exists())

    def test_duplicate_ids_and_orphan_outputs_prevent_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input"
            shutil.copytree(FIXTURE, source)
            duplicate = source / "duplicate.atlas.json"
            shutil.copyfile(source / "compat.atlas.json", duplicate)
            args = ["--input", str(source), "--output", str(root / "out")]
            with self.assertRaises(SystemExit):
                main(["generate", *args])
            self.assertFalse((root / "out").exists())
            duplicate.unlink()
            (root / "out").mkdir()
            orphan = root / "out/obsolete.c"
            orphan.write_text("preserve for inspection")
            with self.assertRaises(SystemExit):
                main(["generate", *args])
            self.assertEqual(orphan.read_text(), "preserve for inspection")
            self.assertEqual(list((root / "out").iterdir()), [orphan])

    def test_empty_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(SystemExit):
                main(["generate", "--input", str(root), "--output", str(root / "out")])
            self.assertFalse((root / "out").exists())
