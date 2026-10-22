# gbc-atlas

Deterministic native PNG + manifest → Game Boy Color 2bpp C arrays.
No painting, resizing, quantization, palette fitting, or editor connection is
needed for conversion. Authoring and visual review use Aseprite MCP through the
bundled skill.

Requires Python 3.10+. The generated code uses standard fixed-width C types and
is suitable for GBDK-2020. Pillow is the only runtime Python dependency.

## Install and use

Install a published release with `pip install gbc-atlas`, once releases are
published. Until then, install this repository at an explicit commit:

```sh
poetry add 'gbc-atlas @ git+https://github.com/cliffom/gbc-atlas.git@<commit>'
poetry run gbc-atlas validate assets/art/example/example.atlas.json
poetry run gbc-atlas generate --input assets/art --output src/generated
poetry run gbc-atlas check --input assets/art --output src/generated
```

`--input` accepts one manifest or a directory searched recursively. Generation
requires recorded approval of each exact pack revision. Validation prints the
digest without granting approval. All packs and the output inventory are checked
before writes. Check is read-only. Neither command moves or deletes artwork;
project-specific retention, promotion, and runtime integration belong to the
consumer. Use a dedicated generated directory; orphan C/headers cause failure.

## Python API

```python
from pathlib import Path
from gbc_atlas import load_atlas, render_c, render_types, verify_approval

atlas = load_atlas(Path("assets/art/example/example.atlas.json"))
verify_approval(atlas)
outputs = render_c(atlas)  # dict[str, str], no writes
outputs["asset_types.h"] = render_types()
```

`Atlas` exposes `manifest`, `digest`, `tiles`, `cell_tiles`, `palettes`, `regions`,
and `dimensions` (columns, rows). `load_atlas` performs technical validation and
encoding; it does not require approval. `render_c` is also available for technical
fixtures. Production workflows call `verify_approval` before rendering. The CLI
enforces that gate. Do not mutate a loaded result before verifying/rendering it;
reload after source or metadata changes. Invalid contracts raise `ValueError`.

The shared `asset_types.h` defines the C interface version 1. Generate or check it
with the same package release as the arrays; do not maintain a divergent copy.
Consumers with an existing type header may write `render_types()` to their include
directory instead. `render_c(..., generator_label="tools/assets.py")` lets
consumers preserve existing provenance comments when adopting the package.

## Authoring skill and format

Run `gbc-atlas skill-path` to locate the release's bundled `create-atlas` skill.
Copy that whole directory into your client's skill directory, or load its
`SKILL.md` directly if supported. Reinstall it when upgrading the converter.
A project-local adapter should identify art direction, paths, checks, budgets,
and handoff policy. No global skill installation is performed automatically.

- [Shared skill](src/gbc_atlas/skills/create-atlas/SKILL.md)
- [Manifest v1 and C interface](src/gbc_atlas/skills/create-atlas/references/format.md)

Package version, manifest version, and C interface version are separate contracts.
The initial extraction preserves manifest v1's digest algorithm and encoding,
including custom metadata and bound editable/review files. Digests detect drift;
they cannot prove human approval or that the PNG matches the editable document.
The converter currently limits each atlas to 256 cells and eight local palettes;
these are converter ceilings, not whole-scene VRAM, palette, or OAM allocations.

## Development

```sh
poetry install
poetry run ruff check .
poetry run ruff format --check .
poetry run python -m unittest discover -s tests -v
poetry build
```

Tests use synthetic artwork, exact 2bpp round trips, known digest/output fixtures,
and native C compilation. Game-specific ROM and emulator tests remain in the
consuming project. A C compiler is required for the compile test. Test an
installed wheel too, so the C header and skill resources are verified as shipped.

## Releases

Publishing a GitHub release runs `.github/workflows/publish.yml`. It validates the
tag and package version, runs the reusable check workflow on Python 3.10 and
3.14, and publishes the tested wheel and source distribution to PyPI. Draft
releases and tag pushes alone do not publish. A failed check blocks publishing.

Use [Semantic Versioning](https://semver.org/spec/v2.0.0.html): `vMAJOR.MINOR.PATCH`
tags must match `[project].version` in `pyproject.toml`. Increment major for
incompatible public API changes, minor for compatible features, and patch for
compatible fixes. While the major version is zero, signal breaking changes with
a minor bump. The public contract includes the documented Python API, CLI,
manifest/digest rules, and generated C interface; format versions remain separate.

Prerelease tags use `v1.2.3-alpha.1`, `v1.2.3-beta.1`, or `v1.2.3-rc.1` and must
be marked as prereleases in GitHub. Their Python versions are `1.2.3a1`,
`1.2.3b1`, and `1.2.3rc1`, respectively. This supported SemVer subset maps directly
to [Python package versions](https://packaging.python.org/en/latest/specifications/version-specifiers/).
Other prerelease labels, build metadata, and leading zeros are rejected.
Stable tags must not be marked as prereleases.

One-time setup before the first release:

1. Create a GitHub environment named `pypi` in `cliffom/gbc-atlas`.
2. Configure a [PyPI pending trusted publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
   for project `gbc-atlas`, owner `cliffom`, repository `gbc-atlas`, workflow
   `publish.yml`, and environment `pypi`. For an existing project, add the same
   configuration as a normal trusted publisher. Publishing uses OIDC, with no
   API-token secret. The separate publish job has `id-token: write` and receives
   only the already-tested distribution artifacts.

For each release, update the version (for example, `poetry version 0.1.0`), run
the development checks above, commit the change, and publish the GitHub release
for the matching tag (`v0.1.0`). For a release candidate use
`poetry version 0.2.0rc1` and a prerelease tagged `v0.2.0-rc.1`. Released versions
are immutable; fixes get a new version. The workflow validates consistency but
cannot determine whether a code change deserves a major, minor, or patch bump.
