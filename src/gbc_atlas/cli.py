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
    validate.add_argument(
        "--deduplicate", action="store_true", help="Reuse exact tiles and flips"
    )
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
            command.add_argument(
                "--bank", help='GBDK ROM bank: "auto" or 0..255 (explicit input only)'
            )
            command.add_argument(
                "--deduplicate",
                action="store_true",
                help="Reuse exact tiles and flips (explicit input only)",
            )
    sub.add_parser("skill-path", help="Print the bundled create-atlas skill directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "skill-path":
            print(files("gbc_atlas").joinpath("skills/create-atlas"))
            return 0
        if args.command == "validate":
            data = load_atlas(args.manifest, deduplicate=args.deduplicate)
            print(f"Technical validation passed; approval digest: {data.digest}")
            if args.deduplicate:
                print(
                    f"Tiles: {len(data.cell_tiles)} -> {len(data.tiles) // 16}; saved {data.tiles_saved}"
                )
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
            bank = args.bank
            if bank is not None and bank != "auto":
                try:
                    bank = int(bank)
                except ValueError:
                    raise ValueError(
                        'bank must be "auto" or an integer 0..255'
                    ) from None
            plan = plan_handoff(
                manifests, target, bank=bank, deduplicate=args.deduplicate
            )
        else:
            require(
                getattr(args, "bank", None) is None
                and not getattr(args, "deduplicate", False),
                "--bank/--deduplicate require --input/--output; use project configuration",
            )
            project = load_project(args.config or Path("pyproject.toml"))
            plan = plan_project(project)
        apply_handoff(plan, args.command)
        for name, before, after in plan.tile_counts:
            print(f"{name}: tiles {before} -> {after}; saved {before - after}")
        print(f"Assets {args.command}: {plan.atlas_count} approved atlases")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Asset error: {error}\n")
