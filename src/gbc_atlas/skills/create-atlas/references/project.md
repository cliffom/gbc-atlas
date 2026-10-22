# Configured project handoff

Use `gbc-atlas` 0.2.0 or newer. Consumers normally need TOML configuration and
build/check commands, with no custom Python. A complete fresh-project walkthrough
and synthetic consumer example are linked from the repository README. Read the project's art direction
and runtime constraints independently of this configuration.

Add to the project's `pyproject.toml`:

```toml
[tool.gbc-atlas]
manifests = ["assets/art/*/*.atlas.json"]
output = "src/generated"
types-header = "include/asset_types.h"

[tool.gbc-atlas.retention]
roots = ["assets/art", "assets/review"]
retire-to = "build/review/retired"
```

`manifests` and `output` are required. `types-header` defaults to
`<output>/asset_types.h`; its filename must remain `asset_types.h`, as generated
arrays include that name. Pass both include directories to the C compiler if
using a separate header directory. Globs are deduplicated and sorted. No matching
manifests is an error, protecting artwork against mistaken discovery patterns.

Paths are relative to the TOML file, never the invocation directory. Configured
paths must remain inside that project. Unknown settings, symlinks, overlapping
managed/output/retirement directories, and orphan generated C/headers fail before
changes. Use dedicated generated and managed asset directories. Preserve unrelated
files by keeping them outside the configured retention roots.

From the project root:

```sh
gbc-atlas handoff
gbc-atlas check
```

From elsewhere, add `--config /path/to/project/pyproject.toml` to either command.
Poetry consumers prefix commands with `poetry run`; build tools and hooks can
invoke that same CLI directly. Never add a project-specific converter merely to
implement discovery, approval checks, type-header placement, or retirement.

The shared handoff validates every approved pack, its generated output inventory,
and destination paths before moving/writing any files. It writes generated arrays
and the shared type header. Handoff never grants artwork approval or promotes
drafts on its own: production inputs must already have approval evidence matching
their exact digest. Changes to project configuration do not invalidate pack
digests; changes to bound pack metadata or files do.

Retention is optional. Omit its table to leave all unreferenced artwork untouched.
When enabled, only the manifest and its declared PNG/source/preview/review files
are retained within the specified roots; `.gitkeep` files are also preserved.
Handoff moves other files into a unique `retire-to/handoff-*/` directory,
preserving their paths relative to the project root and their bytes. It prints
the recovery path before the first move. Inspect that path and protect unsaved
editor documents. Keep recovery storage ignored by Git. Removing it discards
the recoverable copies. Unreferenced directories are not recursively deleted.

`check` never writes, moves, or creates directories; it rejects unreferenced files
when retention is enabled and compares every generated file, including the type
header. `generate` can also use the project configuration, but never retires
artwork: if retirement is needed it fails with a handoff instruction. Existing
`generate/check --input ... --output ...` calls remain independent of project
configuration and do not retire artwork. Do not combine explicit input/output
arguments with `--config`.

Handoffs are preflighted, not filesystem transactions. Do not edit pack files
concurrently. If I/O is interrupted, use the printed retirement directory to
recover moved files and rerun after resolving the failure. The runtime still
owns resource allocation, loading, animation control, and scene tests.
