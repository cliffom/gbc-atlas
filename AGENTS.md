# gbc-atlas contributor instructions

This package converts explicit native PNG palettes and manifest v1 into GBC
2bpp and C arrays. Preserve exact pixels, palette indices, approval digest
compatibility, sprite even/odd pairs, cell maps, and the generated C interface.
Keep painting, quantization, and game-specific allocations out of the converter.
Project handoffs may perform opt-in recoverable retirement within configured
asset roots, after all approvals and paths validate. Approval verification does not grant human approval.

Read README.md and the bundled skill's references/format.md for the contract.
Keep skill guidance, packaged resources, CLI, and API aligned. Consumer projects
own art direction, handoff configuration, runtime integration, and ROM/emulator
tests. Provide standard handoffs through the CLI; consumers should not need
custom conversion or retirement scripts. Public examples must use synthetic
assets and must not identify private consumer projects.

Use Poetry with the committed lockfile. Run Ruff lint/format checks, unittest
discovery, poetry check --lock, and poetry build. Verify an installed wheel,
including its C header and skill resources. Use synthetic test images; do not
copy production artwork into fixtures. Never format generated expected C;
verify exact output and compile it instead. Record compatibility changes and
actual checks in the PR or handoff. Do not commit or push automatically.
