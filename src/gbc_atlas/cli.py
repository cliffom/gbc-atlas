"""Explicit-input CLI; generation never retires or deletes project files."""

import argparse
from importlib.resources import files
from pathlib import Path

from . import load_atlas, render_c, render_types, verify_approval
from ._validation import require


def collect_outputs(manifests, *, generator_label="gbc-atlas"):
    """Validate all approved packs before returning their C outputs."""
    result = {}
    for path in sorted(manifests):
        data = load_atlas(path)
        verify_approval(data)
        generated = render_c(data, generator_label=generator_label)
        require(not result.keys() & generated.keys(), "Duplicate asset id")
        require("asset_types.h" not in generated, "asset_types is a reserved asset id")
        result.update(generated)
    return result


def check_inventory(target, expected):
    """Reject obsolete generated C/header files without deleting them."""
    existing = set(target.glob("*.c")) | set(target.glob("*.h"))
    require(
        not {p.name for p in existing} - set(expected),
        "Orphan generated files: inspect and remove obsolete outputs explicitly",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate a pack and print its digest")
    validate.add_argument("manifest", type=Path)
    for name in ("generate", "check"):
        command = sub.add_parser(
            name, help=f"{name.capitalize()} approved pack outputs"
        )
        command.add_argument(
            "--input",
            type=Path,
            required=True,
            help="One *.atlas.json manifest or a directory searched recursively",
        )
        command.add_argument("--output", type=Path, required=True)
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
        require(args.input.exists(), f"Missing input: {args.input}")
        manifests = (
            sorted(args.input.rglob("*.atlas.json"))
            if args.input.is_dir()
            else [args.input]
        )
        require(bool(manifests), "No atlas manifests found")
        result = collect_outputs(manifests)
        result["asset_types.h"] = render_types()
        target = args.output
        check_inventory(target, result)
        # Preflight every destination before any writes.
        require(not target.is_symlink(), "Output directory must not be a symlink")
        require(not target.exists() or target.is_dir(), "Output must be a directory")
        for name in result:
            path = target / name
            require(not path.is_symlink(), f"Output must not be a symlink: {path}")
            require(
                not path.exists() or path.is_file(), f"Output is not a file: {path}"
            )
        if args.command == "check":
            for name, content in result.items():
                path = target / name
                require(
                    path.is_file() and path.read_bytes() == content.encode(),
                    f"Stale generated file: {path}; run gbc-atlas generate",
                )
        else:
            target.mkdir(parents=True, exist_ok=True)
            for name, content in result.items():
                (target / name).write_bytes(content.encode())
        print(f"Assets {args.command}: {len(manifests)} approved atlases")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(1, f"Asset error: {error}\n")
