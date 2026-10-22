"""Read-only handoff planning and opt-in recoverable artifact retirement."""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ._validation import require
from .approval import verify_approval
from .c_output import render_c, render_types
from .manifest import load_atlas, source_files
from .project import Project, Retention, reject_symlinks, validate_retention


@dataclass(frozen=True)
class HandoffPlan:
    outputs: dict[Path, bytes]
    extras: tuple[Path, ...]
    atlas_count: int
    root: Path | None
    retention: Retention | None


def check_inventory(target, expected):
    existing = set(target.glob("*.c")) | set(target.glob("*.h"))
    require(
        not {p.name for p in existing} - set(expected),
        "Orphan generated files: inspect and remove obsolete outputs explicitly",
    )


def plan_handoff(
    manifests,
    output: Path,
    *,
    types_header: Path | None = None,
    root: Path | None = None,
    retention: Retention | None = None,
) -> HandoffPlan:
    """Validate every pack and path before retirement or output writes."""
    manifests = sorted(set(manifests))
    require(bool(manifests), "No atlas manifests found")
    types_header = (
        types_header if types_header is not None else output / "asset_types.h"
    )
    require(
        types_header.name == "asset_types.h", "types-header must be named asset_types.h"
    )
    require(retention is None or root is not None, "Retention requires a project root")
    if retention is not None:
        validate_retention(retention.roots, retention.retire_to, output, types_header)
    reject_symlinks(output, root)
    require(not output.exists() or output.is_dir(), "Output must be a directory")
    generated = {}
    retained = set()
    for path in manifests:
        reject_symlinks(path, root)
        atlas = load_atlas(path)
        verify_approval(atlas)
        sources = source_files(path, atlas.manifest)
        # source_files resolves containment; inspect the original paths for symlinks.
        names = [
            atlas.manifest[k]
            for k in ("png", "source", "preview")
            if k in atlas.manifest
        ] + atlas.manifest.get("review_images", [])
        for name in names:
            reject_symlinks(path.parent / name, root)
        retained.add(path.resolve())
        retained.update(sources.values())
        result = render_c(atlas)
        require("asset_types.h" not in result, "asset_types is a reserved asset id")
        require(not generated.keys() & result.keys(), "Duplicate asset id")
        generated.update(result)
    outputs = {output / name: text.encode() for name, text in generated.items()}
    outputs[types_header] = render_types().encode()
    expected = {p.name for p in outputs if p.parent == output}
    check_inventory(output, expected)
    require(
        not any(
            left != right and left.is_relative_to(right)
            for left in outputs
            for right in outputs
        ),
        "Generated file paths must not contain one another",
    )
    for path in outputs:
        reject_symlinks(path, root)
        require(not path.exists() or path.is_file(), f"Output is not a file: {path}")
        require(
            path.resolve() not in retained, f"Output would overwrite source: {path}"
        )
        for parent in path.parents:
            require(
                not parent.exists() or parent.is_dir(),
                f"Output parent is not a directory: {parent}",
            )
    require(
        not any(p.is_relative_to(output.resolve()) for p in retained),
        "Generated output directory must not contain asset sources",
    )
    extras = []
    if retention is not None:
        reject_symlinks(retention.retire_to, root)
        for parent in (retention.retire_to, *retention.retire_to.parents):
            require(
                not parent.exists() or parent.is_dir(),
                f"Retirement destination is not a directory: {parent}",
            )
        for folder in retention.roots:
            reject_symlinks(folder, root)
            require(
                not folder.exists() or folder.is_dir(),
                f"Retention root is not a directory: {folder}",
            )
            for path in sorted(folder.rglob("*")):
                reject_symlinks(path, root)
                require(
                    path.is_dir() or path.is_file(), f"Unsupported asset file: {path}"
                )
                if (
                    path.is_file()
                    and path.name != ".gitkeep"
                    and path.resolve() not in retained
                ):
                    extras.append(path)
    return HandoffPlan(outputs, tuple(extras), len(manifests), root, retention)


def plan_project(project: Project) -> HandoffPlan:
    """Plan a loaded project's complete handoff with no consumer-side wiring."""
    return plan_handoff(
        project.manifests(),
        project.output,
        types_header=project.types_header,
        root=project.root,
        retention=project.retention,
    )


def apply_handoff(plan: HandoffPlan, command: str) -> Path | None:
    """Apply a validated plan, or check it without any writes or moves.

    Plans describe a filesystem snapshot. Apply immediately after planning and do
    not mutate sources/configuration between calls. This is not a filesystem
    transaction: interrupted I/O can leave a partial handoff; retired files remain
    recoverable at the printed destination.
    """
    require(command in ("generate", "handoff", "check"), "Unknown handoff command")
    require(
        not plan.extras or command == "handoff",
        "Unreferenced asset artifacts: "
        + ", ".join(map(str, plan.extras))
        + "; run gbc-atlas handoff to retire them",
    )
    if command == "check":
        for path, content in plan.outputs.items():
            require(
                path.is_file() and path.read_bytes() == content,
                f"Stale generated file: {path}; run gbc-atlas handoff or generate",
            )
        return None
    destination = None
    if plan.extras:
        assert plan.retention is not None and plan.root is not None
        plan.retention.retire_to.mkdir(parents=True, exist_ok=True)
        destination = Path(
            tempfile.mkdtemp(prefix="handoff-", dir=plan.retention.retire_to)
        )
        # Print before the first move so interrupted handoffs retain a recovery path.
        print(f"Retiring {len(plan.extras)} unreferenced asset files to {destination}")
        for path in plan.extras:
            target = destination / path.relative_to(plan.root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), target)
    for path, content in plan.outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return destination
