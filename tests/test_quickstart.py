"""Execute the documented post-install quick start in an empty consumer."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUIDE = REPO / "docs/GETTING_STARTED.md"


def command_block(name):
    pattern = rf"<!-- smoke: {re.escape(name)} -->\s*```sh\n(.*?)\n```"
    blocks = re.findall(pattern, GUIDE.read_text(), re.DOTALL)
    if len(blocks) != 1:
        raise AssertionError(f"Expected one documented command block: {name}")
    return blocks[0]


class QuickStartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "my-game"
        self.project.mkdir()
        # CI supplies the checkout and installed wheel. Seed the same example
        # layout as the documented clone, without a network-dependent git clone.
        shutil.copytree(
            REPO / "examples/consumer", self.root / "gbc-atlas-demo/examples/consumer"
        )
        self.env = dict(os.environ)
        self.env["PATH"] = (
            str(Path(sys.executable).parent) + os.pathsep + self.env["PATH"]
        )

    def run_block(self, name, *, check=True):
        return subprocess.run(
            ["/bin/sh", "-eu", "-c", command_block(name)],
            cwd=self.project,
            env=self.env,
            check=check,
            capture_output=True,
            text=True,
        )

    def test_plain_c_project_walkthrough_and_recovery(self):
        self.run_block("setup")
        self.assertFalse(list(self.project.rglob("*.py")))
        pack = self.project / "assets/art/prop"
        originals = {p.name: p.read_bytes() for p in pack.iterdir()}
        generated = self.run_block("generate")
        self.assertIn("Technical validation passed", generated.stdout)
        for name in [
            "src/generated/prop.c",
            "src/generated/prop.h",
            "include/asset_types.h",
        ]:
            self.assertTrue((self.project / name).is_file(), name)
        self.run_block("compile")
        self.assertTrue((self.project / "build/asset-smoke").is_file())
        self.run_block("extra")
        extra = pack / "redundant-review.txt"
        payload = extra.read_bytes()
        rejected = self.run_block("reject-extra", check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("Unreferenced asset artifacts", rejected.stderr)
        self.assertEqual(extra.read_bytes(), payload)
        self.run_block("retire")
        self.assertFalse(extra.exists())
        recovered = list(
            (self.project / "build/review/retired").glob(
                "handoff-*/assets/art/prop/redundant-review.txt"
            )
        )
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].read_bytes(), payload)
        self.assertEqual(originals, {p.name: p.read_bytes() for p in pack.iterdir()})

    def test_example_configuration_preserves_existing_poetry_metadata(self):
        metadata = (
            '[project]\nname = "my-game"\nversion = "0.1.0"\n'
            'requires-python = ">=3.10"\n\n'
            "[tool.poetry]\npackage-mode = false\n"
        )
        path = self.project / "pyproject.toml"
        path.write_text(metadata)
        self.run_block("setup")
        self.assertTrue(path.read_text().startswith(metadata))
        self.run_block("generate")
