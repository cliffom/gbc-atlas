# Consumer example

For a fresh game project, start with the [getting-started guide](../../docs/GETTING_STARTED.md).

A minimal project using the installed CLI, TOML configuration, and two Make
commands. There is no project-specific Python. The artwork is a synthetic
technical fixture; its approval record is explicitly a test stand-in.

After installing `gbc-atlas==0.2.0` in your environment, run from this directory:

```sh
make assets
make assets-check
```

Or test from a development checkout without installing a published release:

```sh
poetry run gbc-atlas handoff --config examples/consumer/pyproject.toml
poetry run gbc-atlas check --config examples/consumer/pyproject.toml
```

Run those development commands from the library repository root. Paths always
resolve relative to the configuration file, including from another directory.
Generated arrays go to `src/generated/` and their shared C header goes to
`include/asset_types.h`. A game would include both directories in its C build.

To exercise retirement, put an unreferenced file in `assets/art/prop/`.
`make assets-check` fails without moving it. `make assets` preserves it under
`build/review/retired/handoff-*/assets/art/prop/`; the pack's declared files remain
unchanged. Keep the retirement directory ignored and inspect the printed path.
Deleting `build/` discards those recovery copies.

The shared test suite copies this example to temporary storage, runs both Make
targets through the installed console script, and verifies the generated pack.
The project supplies art direction, actual human approval, runtime allocation,
and runtime tests; the package supplies the handoff implementation.
