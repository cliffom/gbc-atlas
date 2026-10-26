"""Project configuration; every configured path is relative to its TOML file."""

import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from ._validation import require, validate_bank, validate_deduplicate


def reject_symlinks(path: Path, root: Path | None = None) -> None:
    """Inspect lexical project paths before resolving away any symlinks."""
    paths = [path]
    if root is not None:
        require(path.is_relative_to(root), f"Path escapes project: {path}")
        paths.extend(parent for parent in path.parents if parent.is_relative_to(root))
    for item in paths:
        require(not item.is_symlink(), f"Asset symlink requires inspection: {item}")


def relative_path(root: Path, value, label: str) -> Path:
    require(isinstance(value, str) and value.strip(), f"{label} requires a path")
    path = Path(value)
    require(
        not path.is_absolute()
        and ".." not in path.parts
        and ".git" not in path.parts
        and path.parts,
        f"{label} must stay within the project and cannot name its root",
    )
    target = root / path
    reject_symlinks(target, root)
    return target


def overlaps(left: Path, right: Path) -> bool:
    return left.is_relative_to(right) or right.is_relative_to(left)


@dataclass(frozen=True)
class Retention:
    roots: tuple[Path, ...]
    retire_to: Path


@dataclass(frozen=True)
class Project:
    root: Path
    patterns: tuple[str, ...]
    output: Path
    types_header: Path
    retention: Retention | None = None
    bank: str | int | None = None
    deduplicate: bool = False

    def manifests(self) -> list[Path]:
        paths = sorted(
            {p for pattern in self.patterns for p in self.root.glob(pattern)}
        )
        require(bool(paths), "No atlas manifests found; check configured patterns")
        for path in paths:
            reject_symlinks(path, self.root)
            require(path.is_file(), f"Manifest is not a file: {path}")
        return paths


def string_list(value, label):
    require(
        isinstance(value, list) and value and all(isinstance(v, str) for v in value),
        f"{label} requires a nonempty list of strings",
    )
    return value


def load_project(path: Path = Path("pyproject.toml")) -> Project:
    """Load explicit project policy; reject unknown keys and overlapping paths."""
    path = Path(path).resolve()
    root = path.parent
    with path.open("rb") as stream:
        document = tomllib.load(stream)
    tool = document.get("tool", {})
    require(isinstance(tool, dict), "tool must be a TOML table")
    table = tool.get("gbc-atlas")
    require(isinstance(table, dict), f"Missing [tool.gbc-atlas] in {path}")
    require(
        not set(table)
        - {"manifests", "output", "types-header", "retention", "bank", "deduplicate"},
        "Unknown [tool.gbc-atlas] setting",
    )
    patterns = string_list(table.get("manifests"), "manifests")
    for pattern in patterns:
        relative_path(root, pattern, "manifest pattern")
        require(pattern.endswith(".atlas.json"), "Patterns must match *.atlas.json")
    output = relative_path(root, table.get("output"), "output")
    types = relative_path(
        root,
        table.get("types-header", str(output.relative_to(root) / "asset_types.h")),
        "types-header",
    )
    require(types.name == "asset_types.h", "types-header must be named asset_types.h")
    retention = None
    if "retention" in table:
        policy = table["retention"]
        require(isinstance(policy, dict), "retention requires a table")
        require(not set(policy) - {"roots", "retire-to"}, "Unknown retention setting")
        roots = tuple(
            relative_path(root, v, "retention root")
            for v in string_list(policy.get("roots"), "retention roots")
        )
        retired = relative_path(root, policy.get("retire-to"), "retire-to")
        validate_retention(roots, retired, output, types)
        retention = Retention(roots, retired)
    return Project(
        root,
        tuple(patterns),
        output,
        types,
        retention,
        validate_bank(table.get("bank")),
        validate_deduplicate(table.get("deduplicate", False)),
    )


def validate_retention(roots, retired, output, types):
    for index, folder in enumerate(roots):
        require(
            not any(overlaps(folder, other) for other in roots[:index]),
            "Retention roots must not overlap",
        )
        require(
            not overlaps(folder, output) and not overlaps(folder, types),
            "Retention roots must not overlap generated outputs",
        )
        require(
            not overlaps(folder, retired),
            "Retirement destination must not overlap retention roots",
        )
    require(
        not overlaps(retired, output) and not overlaps(retired, types),
        "Retirement destination must not overlap generated outputs",
    )
