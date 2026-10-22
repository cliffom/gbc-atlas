---
name: create-atlas
description: Author or revise Game Boy Color tile and sprite atlases through Aseprite MCP, review exact atlas pixels in a second scene or animation document, and hand approved packs to gbc-atlas for C generation.
---

# Create Atlas

Read the consuming project's contributor instructions, art direction, asset paths,
and handoff commands. Read [the format contract](references/format.md) before
preparing a manifest or estimating encoding costs. Use the converter and this
skill from the same release. Project-specific choices belong in the consumer's
instructions; this skill does not select gameplay, perspective, or runtime slots.

## Establish the brief

Inspect the working tree, existing artwork, and relevant runtime allocations.
Resolve subject, intended placement, canvas and region dimensions, kinds,
connections, backing, palette roles, anchors, and animation facings/timing.
Reuse known choices. Ask only when a missing choice materially changes the art.
Explain cell counts and OAM costs; per-atlas converter ceilings do not allocate
scene resources. Budget BG/OBJ VRAM, palette slots, OAM and scanline occupancy,
upload work, and linked ROM capacity before runtime integration.

## Author and inspect

Discover the available Aseprite MCP tools and verify the connection with a
read-only call such as listing open documents. If disconnected, finish independent
work and report visual authoring/review blocked. Use MCP for drawing, revisions,
preview composition, and source/export saves. Preserve unrelated documents and
unsaved work; read-only image validation and deterministic conversion remain
independent of the editor.

Keep one static atlas and one scene/animation preview document per brief; reuse
them for revisions. Explicitly select the intended document and frame before each
related mutation/export batch because editor state is shared. Inspect uncertain
mutations before retrying. Build previews from the same atlas pixels; poses
occupy separate named atlas regions. Match timeline durations and stable anchors.

Inspect actual composites at native size and nearest-neighbor enlargement.
For repeating materials inspect horizontal/vertical joins and a repeated field;
for actors inspect contacts, overlaps, every facing, and motion. Review a 160×144
context composition and relevant neighbors/backing; label provisional context
honestly. Apply the project's art review criteria. Valid colors do not establish
visual quality. Fix defects in MCP and inspect the resulting revision.

## Review and generate

Save drafts to the project's draft area. Retain one editable atlas, one editable
preview, native atlas PNG, manifest, and minimal review evidence. Prefer preview
frames over redundant PNGs. Declare support files in the manifest so the digest
binds them. Verify export behavior: some editor commands export only one frame.
Confirm dimensions, frame counts, timing, and exact preview/atlas pixel reuse.

Run `gbc-atlas validate <manifest>` and inspect the PNG. Show the owner the concrete
atlas and relevant context/animation; state dimensions, cells, palettes, checks
completed, and checks pending. Obtain explicit approval of that revision before
production promotion and generation. Existing explicit approval of the shown
revision is sufficient; do not request it again. Validation never grants approval.

On approval, save/copy the unchanged pack to the project's production area and
record the actual owner evidence, date, and printed digest. Changes to bound
files or metadata invalidate the digest; review affected changes before updating
approval. A digest cannot establish that a PNG matches an editable document.
Do not paint, resize, quantize, or repair pixels in a conversion script, and never
hand-edit generated C.

Use the project's handoff wrapper when provided. Otherwise run:

```sh
gbc-atlas generate --input <production-directory> --output <generated-directory>
gbc-atlas check --input <production-directory> --output <generated-directory>
```

These commands enforce recorded approval and never move/delete artwork. Honor
the consuming project's retention policy and checks. Keep the shared C type
header aligned with the generator. Link final sources, manifest, generated files,
and relevant previews; report actual verification and pending work.

Art approval authorizes the approved asset handoff, not unrelated gameplay,
collision changes, commits, or pushes. Technical validation, human art approval,
emulator inspection, and physical-device testing are distinct. Only claim checks
that actually happened.
