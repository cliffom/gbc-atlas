"""Explicit-input conversion and configuration-based project handoffs."""

import argparse
from importlib.resources import files
from pathlib import Path

from ._validation import require
from .handoff import apply_handoff, plan_handoff, plan_project
from .manifest import load_atlas
from .project import load_project


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate a pack and print its digest")
    validate.add_argument("manifest", type=Path)
    for name in ("generate", "check", "handoff"):
        command = sub.add_parser(
            name, help=f"{name.capitalize()} approved pack outputs"
        )
        command.add_argument(
            "--config", type=Path, help="Project TOML file (default: ./pyproject.toml)"
        )
        if name != "handoff":
            command.add_argument(
                "--input",
                type=Path,
                help="One *.atlas.json manifest or a directory searched recursively",
            )
            command.add_argument("--output", type=Path)
    sub.add_parser("skill-path", help="Print the bundled create-atlas skill directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "skill-path":
            print(files("gbc_atlas").joinpath("skills/create-atlas"))
            return 0
        if args.command == "validate":
            data = load_atlas(args.manifest)
            print(f"Technical validation passed; approval digest: {data.digest}")
            return 0
        source = getattr(args, "input", None)
        target = getattr(args, "output", None)
        if source is not None or target is not None:
            require(
                source is not None and target is not None,
                "--input and --output must be supplied together",
            )
            require(
                args.config is None, "Do not combine --config with --input/--output"
            )
            require(source.exists(), f"Missing input: {source}")
            manifests = (
                sorted(source.rglob("*.atlas.json")) if source.is_dir() else [source]
            )
            plan = plan_handoff(manifests, target)
        else:
            project = load_project(args.config or Path("pyproject.toml"))
            plan = plan_project(project)
        apply_handoff(plan, args.command)
        print(f"Assets {args.command}: {plan.atlas_count} approved atlases")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Asset error: {error}\n")
