# Getting started

This guide targets **gbc-atlas 0.3.1 or newer** and a POSIX shell on macOS or Linux.
You need Python 3.10+, Git, and Make. A native C compiler is needed only for the
optional compilation check. No GBDK installation or live editor is needed to try
the synthetic example. You can author real packs directly in Aseprite without an
agent. Agent-assisted drawing and editor review use the bundled skill and require
Aseprite MCP; file validation and conversion work independently of either route.

The result is a game project with one TOML configuration and shared CLI calls:
no custom asset-conversion Python. Start with a new empty directory:

```sh
mkdir my-game
cd my-game
```

## Install in the game project

Choose one installation method. For a C project without Python packaging, use a
virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
printf 'gbc-atlas==0.3.1\n' > requirements-assets.txt
python -m pip install -r requirements-assets.txt
```

Keep that environment activated for the commands below. Your game does not need
a Python package or a `[project]` table; `pyproject.toml` can contain only tool
configuration.

Alternatively, if you use Poetry, initialize its metadata in this empty project:

```sh
poetry init --name my-game --python '>=3.10' --no-interaction
```

Add the following to `pyproject.toml` so Poetry manages dependencies without
trying to install your C game as a Python package:

```toml
[tool.poetry]
package-mode = false
```

Then install:

```sh
poetry add gbc-atlas==0.3.1
```

For an existing Poetry project, keep its metadata and skip initialization.
With Poetry, prefix the following `gbc-atlas` commands with `poetry run`, and run
Make with `GBC_ATLAS='poetry run gbc-atlas'`.

## Try a complete synthetic pack

Download the matching release's example once:

```sh
git clone --depth 1 --branch v0.3.1 https://github.com/cliffom/gbc-atlas.git ../gbc-atlas-demo
```

Copy its assets, configuration, and Make targets into your **empty** project.
These commands append the tool configuration without replacing Poetry metadata:

<!-- smoke: setup -->
```sh
cp -R ../gbc-atlas-demo/examples/consumer/assets .
cat ../gbc-atlas-demo/examples/consumer/pyproject.toml >> pyproject.toml
cat > Makefile <<'MAKE'
GBC_ATLAS ?= gbc-atlas

.PHONY: assets assets-check
assets:
	$(GBC_ATLAS) handoff

assets-check:
	$(GBC_ATLAS) check
MAKE
```

For an existing game, merge the example's TOML table and Make targets into your
files instead of copying over them. The demo checkout supplies only this sample;
normal conversion uses the installed package and does not require that checkout.

The copied configuration discovers `assets/art/*/*.atlas.json`, writes arrays to
`src/generated/`, and puts the shared type header in `include/asset_types.h`.
It also enables recoverable retirement within `assets/art/` and `assets/review/`.
[The configuration reference](../src/gbc_atlas/skills/create-atlas/references/project.md)
explains other layouts and how to disable retirement. Every path is relative to
the configuration file, not the command's working directory.

Validate and generate:

<!-- smoke: generate -->
```sh
gbc-atlas validate assets/art/prop/prop.atlas.json
make assets
make assets-check
```

Validation prints a SHA-256 digest. Handoff reports one approved atlas; check
passes without modifying any files. The sample's approval is explicitly a
synthetic test stand-in, not evidence of human approval for your artwork.

You now have:

```text
assets/art/prop/atlas.png
assets/art/prop/prop.atlas.json
src/generated/prop.c
src/generated/prop.h
include/asset_types.h
```

`make assets` calls `gbc-atlas handoff`; `make assets-check` calls
`gbc-atlas check`. Those two Make targets are the complete asset handoff code.

## Verify C compilation

This optional native check proves that the generated arrays and shared header
compile and link together. It does not test GBC display or allocate VRAM:

<!-- smoke: compile -->
```sh
mkdir -p build
cat > build/asset-smoke.c <<'C'
#include "prop.h"

int main(void) {
    return PROP_TILE_COUNT == 4 && prop_cell_tiles[0] == 0 ? 0 : 1;
}
C
cc -std=c99 -Wall -Wextra -Werror -Iinclude -Isrc/generated \
    build/asset-smoke.c src/generated/prop.c -o build/asset-smoke
./build/asset-smoke
```

For your GBDK build, add `-Iinclude -Isrc/generated` to compiler flags and compile
`src/generated/*.c` alongside your existing runtime sources. Include the generated
asset header from runtime code. Your game still owns VRAM/palette allocation,
loading, OAM placement, and animation control. Budget scene resources before
integration; [the format reference](../src/gbc_atlas/skills/create-atlas/references/format.md)
describes cell maps, sprite pairs, and generated data. Avoid formatting or
hand-editing generated C.

## Understand retirement before using real artwork

The retention roots are dedicated managed directories. Keep unrelated artwork,
drafts, and unsaved editor work outside them. Add a disposable unreferenced file:

<!-- smoke: extra -->
```sh
printf 'Disposable review fixture\n' > assets/art/prop/redundant-review.txt
```

This next command **should fail**, reporting an unreferenced asset without moving
it or writing anything:

<!-- smoke: reject-extra -->
```sh
make assets-check
```

Perform the handoff and check again:

<!-- smoke: retire -->
```sh
make assets
make assets-check
```

The handoff prints a unique `build/review/retired/handoff-…` directory. Inside it,
`assets/art/prop/redundant-review.txt` retains its original bytes. Declared pack
files remain unchanged. Inspect the printed path; removing `build/` discards
these recoverable copies. If a handoff is interrupted, inspect that directory
before retrying. Handoffs are preflighted, not filesystem transactions.

## Replace the example with your first real pack

Choose an authoring route:

- **Without an agent:** author/export the atlas and a separate scene/animation
  preview directly in Aseprite, inspect them yourself, and follow your project's
  review process. Use the [manifest reference](../src/gbc_atlas/skills/create-atlas/references/format.md)
  to prepare metadata. You do not need to install a skill or configure MCP.
- **With an agent:** run `gbc-atlas skill-path` (or `poetry run gbc-atlas skill-path`).
  Have the agent read that directory's `SKILL.md` and referenced documents, or copy
  the entire skill directory into your client's skill location. Supply art
  direction, an asset brief, draft location, and runtime constraints. The agent
  must use Aseprite MCP for drawing/export/editor review and preserve open work.

Both routes then follow the same pack contract and handoff:

1. Save drafts outside the managed roots, for example `build/review/<object>/`.
   Prepare the native PNG and `<object>.atlas.json`; declare editable atlas,
   preview, and relevant evidence files. Start with `approval.status` set to
   `draft`. The [manifest reference](../src/gbc_atlas/skills/create-atlas/references/format.md)
   contains the complete format, RGB5 expansion, and palette/alignment rules.
2. Run `gbc-atlas validate <draft-manifest>`. This confirms technical validity
   and prints the revision digest; it does not approve the art. Inspect the actual
   atlas/context/animation and approve that exact revision through your project's
   human review process.
3. Record the real approver, date, evidence, and printed digest in the manifest's
   `approval` object as documented in the format reference. Copy the unchanged
   declared pack into `assets/art/<object>/`. The approval object itself is
   excluded from the digest; editing any bound file or metadata changes it.
4. Run `make assets`, `make assets-check`, and your game's build/tests. The CLI
   rejects missing or stale approval. Keep human approval, technical validation,
   emulator inspection, and device testing distinct.

When removing the synthetic pack, also inspect and remove its obsolete generated
`prop.c` and `prop.h`. The orphan-output guard deliberately refuses to delete
those for you. Update runtime includes to your real asset's generated header.
Never reuse the sample's technical approval as approval of new artwork.

## Add checks and decide what to commit

Use the same release for the package, bundled skill, and shared
[pre-commit](https://pre-commit.com/) hook. Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/cliffom/gbc-atlas
    rev: v0.3.1
    hooks:
      - id: gbc-atlas-check
```

The hook installs its own Python environment and runs the configured read-only
check on every commit. It does not depend on an activated game environment or
convert your game into a Python package. In the activated virtual environment, install and enable pre-commit:

```sh
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

For Poetry use `poetry add --group dev pre-commit`, then
`poetry run pre-commit install` and `poetry run pre-commit run --all-files`. For CI, install the
pinned package and run the same `gbc-atlas check` or `make assets-check` command.

Commit `requirements-assets.txt` for the virtual-environment setup, or
`pyproject.toml` and `poetry.lock` for Poetry. Commit the tool configuration,
Make/hook changes, approved packs and declared sources, generated C/headers, and
the generated shared type header together. Add `/.venv/` and `/build/` to your `.gitignore`; keep drafts, recovery
copies, native-check executables, and ROM binaries out of Git. The disposable
example ignores its own generated files; do not copy that example `.gitignore`
into a real game that commits generated assets.

## Common first-run failures

| Message or symptom | What to do |
| --- | --- |
| `No atlas manifests found` | Check the configured glob and pack location; an empty project cannot hand off yet. |
| Missing or stale approval | Validate the current revision, review affected changes, and record actual approval; do not bypass the gate. |
| Unreferenced asset artifacts | Inspect the listed files; use handoff to retire them or declare relevant evidence before reviewing the changed pack. |
| Stale generated file | Run `make assets`, review the changes, then rerun check. |
| Orphan generated files | Inspect/remove obsolete C/headers explicitly, such as the removed demo pack's outputs. |
| Pixel outside RGB5 palette | Compare against the exact expansion in the format reference; correct/export the artwork through the authoring workflow. |
| Missing `asset_types.h` during compilation | Add both include directories and run handoff; the type header must match the generator. |
| Retired files seem lost | Inspect the printed recovery path; handoff preserved project-relative paths there unless recovery storage was removed. |

The automated quick-start test runs the marked setup, validation, generation,
read-only rejection, retirement, and native-compile commands verbatim in a fresh
temporary consumer using the installed CLI. Installation and the source/example
checkout are supplied by the test environment rather than contacting a release
server during tests.
