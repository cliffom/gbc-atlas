"""Configured handoffs preserve source packs and recoverable retired bytes."""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gbc_atlas import load_atlas
from gbc_atlas.cli import main
from gbc_atlas.project import load_project

FIXTURE = Path(__file__).parent / "fixtures/v1"


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / "assets/art/object"
        self.folder.mkdir(parents=True)
        for name in ("compat.atlas.json", "atlas.png"):
            shutil.copyfile(FIXTURE / name, self.folder / name)
        self.config = self.root / "pyproject.toml"
        self.text = """[tool.gbc-atlas]
manifests = ["assets/art/*/*.atlas.json"]
output = "src/generated"
types-header = "include/asset_types.h"

[tool.gbc-atlas.retention]
roots = ["assets/art", "assets/review"]
retire-to = "build/review/retired"
"""
        self.config.write_text(self.text)

    def run_cli(self, command):
        return main([command, "--config", str(self.config)])

    def expect_failure(self, command, message):
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit):
            self.run_cli(command)
        self.assertIn(message, error.getvalue())

    def test_cli_from_another_directory_and_native_c_compile(self):
        command = [
            sys.executable,
            "-m",
            "gbc_atlas",
            "handoff",
            "--config",
            str(self.config),
        ]
        subprocess.run(command, cwd=self.root.parent, check=True, capture_output=True)
        self.assertEqual(self.run_cli("check"), 0)
        self.assertTrue((self.root / "include/asset_types.h").is_file())
        self.assertFalse((self.root / "src/generated/asset_types.h").exists())
        subprocess.run(
            [
                "cc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(self.root / "include"),
                "-c",
                str(self.root / "src/generated/compat.c"),
                "-o",
                str(self.root / "test.o"),
            ],
            check=True,
            capture_output=True,
        )
        (self.root / "src/generated/compat.c").write_text("drift")
        self.expect_failure("check", "Stale generated file")

    def test_retirement_preserves_sources_and_is_repeatable(self):
        self.run_cli("handoff")
        originals = {p: p.read_bytes() for p in self.folder.iterdir()}
        expected = (self.root / "src/generated/compat.c").read_bytes()
        extras = [
            self.folder / "enlarged.png",
            self.root / "assets/review/old/source.aseprite",
        ]
        for path in extras:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"recoverable artifact")
        placeholder = self.root / "assets/review/.gitkeep"
        placeholder.touch()
        self.expect_failure("check", "Unreferenced asset artifacts")
        self.expect_failure("generate", "Unreferenced asset artifacts")
        self.assertFalse((self.root / "build").exists())
        self.assertTrue(all(p.exists() for p in extras))
        self.run_cli("handoff")
        destinations = list((self.root / "build/review/retired").iterdir())
        self.assertEqual(len(destinations), 1)
        for path in extras:
            self.assertFalse(path.exists())
            self.assertEqual(
                (destinations[0] / path.relative_to(self.root)).read_bytes(),
                b"recoverable artifact",
            )
        self.assertTrue(placeholder.exists())
        self.assertEqual(originals, {p: p.read_bytes() for p in self.folder.iterdir()})
        self.assertEqual(expected, (self.root / "src/generated/compat.c").read_bytes())
        self.run_cli("handoff")
        self.run_cli("check")
        self.assertEqual(
            list((self.root / "build/review/retired").iterdir()), destinations
        )

    def test_invalid_later_pack_prevents_retirement_and_generation(self):
        extra = self.folder / "old.png"
        extra.write_bytes(b"keep")
        folder = self.root / "assets/art/z_invalid"
        folder.mkdir()
        (folder / "invalid.atlas.json").write_text('{"version":0}')
        self.expect_failure("handoff", "Unsupported manifest version")
        self.assertTrue(extra.exists())
        self.assertFalse((self.root / "build").exists())
        self.assertFalse((self.root / "src").exists())

    def test_stale_approval_prevents_any_writes(self):
        path = self.folder / "compat.atlas.json"
        data = json.loads(path.read_text())
        data["custom_metadata"]["changed"] = True
        path.write_text(json.dumps(data))
        self.expect_failure("handoff", "stale approval")
        self.assertFalse((self.root / "src").exists())

    def test_orphan_output_prevents_retirement(self):
        target = self.root / "src/generated"
        target.mkdir(parents=True)
        (target / "orphan.c").write_text("keep")
        (self.folder / "old.png").write_bytes(b"keep")
        self.expect_failure("handoff", "Orphan generated files")
        self.assertTrue((self.folder / "old.png").exists())
        self.assertFalse((self.root / "build").exists())

    def test_symlink_in_retention_tree_stops_handoff(self):
        other = self.root / "unrelated.aseprite"
        other.write_bytes(b"unrelated")
        (self.folder / "old.aseprite").symlink_to(other)
        self.expect_failure("handoff", "symlink requires inspection")
        self.assertEqual(other.read_bytes(), b"unrelated")
        self.assertFalse((self.root / "build").exists())

    def test_symlink_ancestor_of_output_stops_handoff(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.root / "src").symlink_to(elsewhere, target_is_directory=True)
        self.expect_failure("handoff", "symlink requires inspection")
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_referenced_symlink_is_rejected_even_within_pack(self):
        original = self.folder / "atlas.png"
        original.rename(self.folder / "real.png")
        original.symlink_to("real.png")
        self.expect_failure("handoff", "symlink requires inspection")
        self.assertFalse((self.root / "src").exists())

    def test_invalid_output_parent_prevents_retirement(self):
        (self.root / "include").write_text("file instead of directory")
        (self.folder / "old.png").write_bytes(b"keep")
        self.expect_failure("handoff", "Output parent is not a directory")
        self.assertFalse((self.root / "build").exists())
        self.assertTrue((self.folder / "old.png").exists())

    def test_no_matching_manifests_cannot_retire_assets(self):
        self.config.write_text(
            self.text.replace("assets/art/*/*.atlas.json", "missing/*.atlas.json")
        )
        self.expect_failure("handoff", "No atlas manifests found")
        self.assertTrue((self.folder / "atlas.png").exists())
        self.assertFalse((self.root / "build").exists())

    def test_retirement_is_opt_in(self):
        self.config.write_text(self.text.split("[tool.gbc-atlas.retention]")[0])
        extra = self.folder / "unmanaged.png"
        extra.write_bytes(b"keep")
        self.run_cli("handoff")
        self.run_cli("check")
        self.assertTrue(extra.exists())
        self.assertFalse((self.root / "build").exists())

    def test_missing_types_header_is_stale_without_writes(self):
        self.expect_failure("check", "Stale generated file")
        self.assertFalse((self.root / "include").exists())
        self.run_cli("handoff")
        (self.root / "include/asset_types.h").unlink()
        self.expect_failure("check", "Stale generated file")
        self.assertFalse((self.root / "include/asset_types.h").exists())

    def test_duplicate_ids_across_packs_prevent_writes(self):
        shutil.copytree(self.folder, self.root / "assets/art/duplicate")
        self.expect_failure("handoff", "Duplicate asset id")
        self.assertFalse((self.root / "src").exists())

    def test_overlapping_globs_do_not_duplicate_packs(self):
        self.config.write_text(
            self.text.replace(
                '["assets/art/*/*.atlas.json"]',
                '["assets/art/*/*.atlas.json", "assets/art/**/*.atlas.json"]',
            )
        )
        self.run_cli("handoff")
        self.run_cli("check")

    def test_invalid_configurations_are_rejected(self):
        for old, new, message in [
            ('output = "src/generated"', 'output = "../outside"', "within the project"),
            ('output = "src/generated"', 'output = "."', "project"),
            (
                'output = "src/generated"',
                'output = "/tmp/outside"',
                "within the project",
            ),
            ('output = "src/generated"', 'output = "assets/art/generated"', "overlap"),
            (
                'retire-to = "build/review/retired"',
                'retire-to = "assets/art/retired"',
                "overlap",
            ),
            (
                'retire-to = "build/review/retired"',
                'retire-to = "src/generated/retired"',
                "overlap",
            ),
            (
                'roots = ["assets/art", "assets/review"]',
                'roots = ["assets", "assets/art"]',
                "overlap",
            ),
            ('output = "src/generated"', 'outpt = "src/generated"', "Unknown"),
            (
                'types-header = "include/asset_types.h"',
                'types-header = "include/other.h"',
                "asset_types.h",
            ),
            (
                'output = "src/generated"',
                'output = ".git/generated"',
                "within the project",
            ),
        ]:
            with self.subTest(new=new):
                self.config.write_text(self.text.replace(old, new))
                with self.assertRaisesRegex(ValueError, message):
                    load_project(self.config)
        self.assertFalse((self.root / "src").exists())

    def test_conflicting_cli_options_are_rejected(self):
        for args in (
            ["--input", str(self.folder)],
            [
                "--input",
                str(self.folder),
                "--output",
                str(self.root / "out"),
                "--config",
                str(self.config),
            ],
        ):
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                main(["generate", *args])

    def test_example_has_no_project_python_and_uses_the_installed_cli(self):
        example = Path(__file__).resolve().parents[1] / "examples/consumer"
        destination = self.root / "example"
        shutil.copytree(example, destination)
        self.assertFalse(list(destination.rglob("*.py")))
        executable = str(Path(sys.executable).parent / "gbc-atlas")
        for target in ("assets", "assets-check"):
            subprocess.run(
                ["make", target, f"GBC_ATLAS={executable}"],
                cwd=destination,
                check=True,
                capture_output=True,
            )
        manifest = destination / "assets/art/prop/prop.atlas.json"
        self.assertEqual(load_atlas(manifest).manifest["id"], "prop")
