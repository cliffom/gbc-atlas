# Manifest v1 and generated C interface v1

## Object pack and manifest version 1

Use a flat object folder. The runtime interchange format is exactly one native
`atlas.png` plus `<object>.atlas.json`. Keep `atlas.aseprite`, `preview.aseprite`,
and native review PNGs alongside these as authoring/review support. Filenames are
relative to that folder and cannot escape it. The CLI imports only `*.atlas.json` manifests. Review exports never enter the
importer on their own. Region names and atlas IDs use lowercase C identifiers.

This is a schema example, not approved art. Replace the descriptive placement
and approval evidence with actual decisions. The four RGB5 triplets form one
palette; `cell_palettes` is a row-major assignment for all atlas cells, including
unused cells. The example assumes a 16×16 atlas.

```json
{
  "version": 1,
  "id": "example_prop",
  "source": "atlas.aseprite",
  "png": "atlas.png",
  "preview": "preview.aseprite",
  "review_images": ["scene-native.png", "joins-native.png"],
  "palettes": [
    [[3, 3, 5], [9, 9, 12], [18, 17, 16], [29, 27, 22]]
  ],
  "cell_palettes": [0, 0, 0, 0],
  "regions": [
    {
      "name": "idle", "kind": "tile",
      "x": 0, "y": 0, "width": 16, "height": 16,
      "origin": [8, 15],
      "placement": "Ground contact at origin; opaque wall backing; no rotation."
    }
  ],
  "animations": [],
  "approval": {"status": "draft"}
}
```

Every region declares `kind: "tile"` or `kind: "sprite"`; a sheet may mix both.
Tile regions preserve all four opaque indices, including index zero. Sprite
regions always encode in 8×16 pairs: entry zero represents transparency and
visible pixels must match entries 1..3 exactly. Rectangles use pixels,
align to 8×8, and may overlap for intentionally shared parts of the same kind.
Overlapping tile and sprite kinds are rejected. Every cell must belong to a region;
name padding explicitly so its kind is unambiguous. Origins are optional pixel
coordinates inside their region (default `[0, 0]`). Document allowed connections,
facing, backing, and placement in each region's `placement` string. Sprite regions
align vertically to 16 pixels and each vertical pair shares a palette. The atlas
as a whole may have an odd number of rows if its final row
contains only tile regions.

For animation add named sequences referring to static regions:

```json
{"name": "walk_south", "frames": [
  {"region": "south_a", "duration_ms": 125},
  {"region": "south_b", "duration_ms": 125}
]}
```

A region can optionally declare `duration_ms`; a sequence frame can override
that duration. Frames in a sequence share kind, dimensions, and origin. Durations
are unsigned 16-bit milliseconds, not GBC frames; the runtime controller must convert
them to its tick rate. Save the same timing in the editable preview timeline.

After review, use the digest printed by `validate` in:

```json
"approval": {
  "status": "approved",
  "digest": "<printed SHA-256>",
  "by": "<owner>",
  "date": "<approval date>",
  "evidence": "<actual approval quote or conversation reference>"
}
```

Only `version`, `id`, `png`, `palettes`, `cell_palettes`, and `regions` are
required for technical conversion. `source`, `preview`, `review_images`, and
`animations` are optional interchange metadata. The shared skill’s authoring
workflow retains the editable sources and relevant review evidence and records
them in the manifest. Generation additionally requires `approval`.

The configured handoff can use these declared files as a retention list for
opt-in recoverable retirement. See [project configuration](project.md); the
project chooses managed roots and recovery storage.

The digest binds the manifest excluding `approval`, plus file hashes for the
atlas PNG and any declared editable sources and review images. It
detects drift; it cannot prove a human approved artwork or that a PNG matches an
editable file. The author must export from the exact reviewed document, confirm
dimensions/frame count through MCP, and record approval honestly. Do not use the
digest as a substitute for inspecting the images.

## Palette interpretation for scene consumers

Manifest v1 palette IDs are **local to one atlas**. `palettes[p][i]` is the
RGB5 triplet for encoded color index `i` in local palette `p`; preserve the
entry order. `cell_palettes` assigns one local ID to every 8×8 source cell,
including explicitly named padding. A region can use several local palettes.
There is no region-wide or animation-wide palette field.

To resolve a manifest region, let `columns = PNG_width / 8`. Iterate `cy` from
`region.y / 8` through `(region.y + region.height) / 8 - 1`, then `cx` from
`region.x / 8` through `(region.x + region.width) / 8 - 1`. For each cell:

```text
cell = cy * columns + cx
local_id = cell_palettes[cell]
ordered_rgb5 = palettes[local_id]
pool = BG if region.kind == "tile" else OBJ
comparison_key = (pool, ordered_rgb5 if pool == BG else ordered_rgb5[1:4])
```

The Python `Atlas.regions` and generated `AssetRegion` rectangles already use
cell coordinates and sizes; do not divide those by eight again. Manifest
rectangles use pixels. `Atlas.palettes` and generated `<id>_palettes` flatten
all four entries of every local palette as `r | (g << 5) | (b << 10)`, so entry
`i` of palette `p` is at offset `4*p + i`. This packing preserves RGB5 identity.

Read `cell_palettes` at the **source cell**, never at `cell_tiles[cell]`.
Mixed atlases encode sprite pairs first, so encoded tile IDs can differ from
source-cell positions. Optional deduplication changes tile/flip maps without
changing palette assignments. Same-kind overlapping regions refer to the same
cells and palette requirements; they do not create new identities. Palettes
that no selected cell references do not contribute to that selection, even
though they remain declared and count toward the bundle's local ceiling.

For sprite regions, each vertical 8×16 pair has one shared **local ID** in its
top and bottom cells; even equivalent palettes with different local IDs cannot
be assigned to opposite halves. Wider/taller sprite regions may use different
palettes in different pairs. Regions cannot mix kinds internally. Tile/sprite
overlap, incomplete or vertically misaligned sprite pairs, per-pixel palette
selection, and 8×8 sprite regions are unsupported. There are no external-atlas
region references in manifest v1.

An animation frame's `region` names a region in the same manifest. Resolve
that region exactly as above for each included frame; later frames may add
palettes absent from the first frame. Frames share kind, dimensions, and origin,
but need not share palette IDs or identities. Frame timing does not change
identity. The scene consumer chooses the animation-frame closure and residency
policy; the converter does not choose which animations or regions a scene uses.

For consumers preserving encoded pixel indices, compare palettes as follows:

| Pool | Identity within that pool | Consequence |
| --- | --- | --- |
| BG (tiles, including window/UI) | All four ordered RGB5 entries, indices 0–3 | Entry zero is opaque and participates in identity. |
| OBJ (sprites) | Ordered RGB5 entries 1–3 | Ignore entry zero: encoded index zero is transparent, regardless of its stored RGB. |

Equivalent identities can share a scene slot within the same pool, including
across atlases and repeated local declarations. BG and OBJ use separate pools;
a matching list does not merge those pools. Comparing unordered color sets is
incorrect: swapping visible entries changes encoded-index meaning and requires
explicit pixel-index remapping before the palettes can share a slot. These keys
compare all relevant entries even when particular pixels do not use every entry.
They do not authorize recoloring, sorting, remapping, or converter deduplication
across palette IDs. Sprite transparent PNG pixels may have arbitrary RGB;
visible pixels must match entries 1–3 exactly, and partial alpha is rejected.

The eight-local-palette ceiling counts **every declared palette**, including
unused and equivalent declarations, across both kinds in one bundle. It is
separate from the hardware's eight BG/window slots and eight OBJ slots
([Pan Docs — Palettes](https://github.com/gbdev/pandocs/blob/master/src/Palettes.md)).
Several valid bundles may exceed a scene pool when combined. Technical atlas
validation establishes neither whole-scene fit nor human artwork approval.
Scene tools own composition, selected regions/frames, target profiles,
reservations, diagnostics, and preflight; consuming builds own final runtime
allocation, streaming, and ROM/emulator checks.

The independent synthetic [palette conformance examples](../../../../../examples/palette-semantics/README.md)
provide native PNG/manifest v1 bundles, explicit cell/region/frame oracles, and
passing/over-budget multi-atlas selections for scene-tool tests. In an installed
wheel, obtain these repository examples from the matching source distribution
or repository checkout; the bundled format contract remains self-contained.
These examples require no new interchange format or runtime Python dependency.

## Generated interface and limits

`gbc-atlas generate --input <manifest-or-directory> --output <directory>` validates
all approved packs before writing arrays and `asset_types.h`.
`gbc-atlas check` accepts the same options and compares expected bytes without
writing. Stale approval, changed generated data, duplicate IDs, and orphan C or
headers fail. `asset_types` is reserved for the shared type header. Neither
command retires artwork. Configured projects can instead use
`gbc-atlas handoff` for generation and optional recoverable retirement.

Generated output contains:

- `<id>_tiles`: uncompressed 2bpp tile bytes, low plane then high plane per row.
- `<id>_cell_tiles` and `<id>_cell_palettes`: row-major cell-to-tile and
  cell-to-local-palette maps. Sprite cells are encoded first in vertical even/odd
  pairs; tile cells follow in row-major order. Always use the cell map for
  mixed atlases rather than assuming a region’s bytes are contiguous.
- With deduplication enabled, `<id>_cell_flags`: row-major X/Y flip bits, detailed
  below. Without this option the array and its marker macros are absent.
- `<id>_palettes`: packed GBC RGB15 values, four entries per local palette.
- `<id>_regions`: cell rectangles, kinds, pixel origins, and optional durations
  (zero means unspecified), with named region macros.
- Named animation arrays of region indices and durations, with frame counts.

No quantization, palette fitting, packing across VRAM banks, metasprite/OAM
placement, or collision generation occurs. ROM banking and tile deduplication
with flip reuse are opt-in as described below. The loader must allocate VRAM and
palette slots, remap local indices, and
assemble sprite regions through the cell map. Each 8×16 OAM entry uses the top
cell's even tile ID; enable GBDK's `SPRITES_8x16` mode when loading sprite regions.
Screen-space OAM coordinates also require the hardware
offsets; the source origin is an artistic anchor, not an OAM coordinate.

The current 256-cell, eight-palette per-atlas ceiling is a converter limit. There
is no whole-scene allocation or timing checker yet. Before integration, budget
combined BG/OBJ VRAM, palette slots, OAM entries, scanline occupancy, upload work,
and linked ROM capacity. Deduplication does not relax the source cell ceiling.
Technical converter tests use synthetic images;
they make no claims about art direction or editor connectivity.

RGB5 components expand to PNG RGB8 with `(value * 255 + 15) // 31`.
Colors must match that expansion exactly; the converter does not quantize.

## Optional GBDK ROM banking

Project configuration accepts `bank = "auto"` or an integer `0..255` in
`[tool.gbc-atlas]`; explicit `generate/check --input ... --output ...` accepts
`--bank auto` or `--bank N`. Python uses `render_c(atlas, bank="auto")` or
`plan_handoff(..., bank="auto")`. Bank `255` means autobank; `0` explicitly
selects fixed ROM. Banks above 255 and MBC5's 9-bit switching are not supported.
Use matching options for generation and checking. This output policy does not
change manifest v1, the digest, `AssetRegion`, or C interface v1.

Enabled sources start with `#pragma bank 255` (auto) or `#pragma bank N` and emit
one `BANKREF(<id>)`. Headers include `<gbdk/platform.h>`, declare
`BANKREF_EXTERN(<id>)`, and define `<ID>_BANKED 1`. For default output the marker
is absent (test with `#ifdef`), no GBDK header is included, and original bytes
are preserved. The single bank reference covers **all** atlas arrays: tiles,
cell maps, palettes, regions, and animation arrays. They are emitted in one
translation unit and share one bank. Compile/link with GBDK `-autobank` for auto
placement, a bank-capable cartridge, and sufficient ROM capacity. No atlas is
split across banks; an oversized atlas fails at link time.

Example fixed-ROM loader (replace `example_prop` with the atlas ID):

```c
#include <gb/gb.h>
#include "example_prop.h"

void load_prop(void) NONBANKED {
    uint8_t saved_bank = CURRENT_BANK;
    SWITCH_ROM(BANK(example_prop));
    set_bkg_data(0, EXAMPLE_PROP_TILE_COUNT, example_prop_tiles);
    /* Read/copy cell maps, palettes, regions and animations while banked in. */
    SWITCH_ROM(saved_bank);
}
```

The example assumes the consumer has allocated the destination VRAM slots.
Near pointers do not select banks: every later array access must select the
atlas bank again. Execute switching code in fixed ROM so it cannot switch itself
out. Interrupt handlers and other loaders must preserve/restore bank state.
Copy needed metadata to RAM when it must remain available across bank switches.

## Optional tile deduplication and flip reuse

Set `deduplicate = true` in `[tool.gbc-atlas]` or pass `--deduplicate` to explicit
`generate/check --input ... --output ...`. Technical `validate <manifest>
--deduplicate` reports the same encoding without requiring approval. Python uses
`load_atlas(path, deduplicate=True)` before rendering, or
`plan_handoff(..., deduplicate=True)`. Configured generation and checking use the
same options automatically. Validation/handoff/check report original and emitted
8×8 tile counts and tiles saved (a reused sprite pair saves two tiles).

This changes output policy only: manifest v1 and its approval digest algorithm
are unchanged, and approved packs need no digest replacement for these settings.
The shared C header and `AssetRegion` layout remain interface v1. The optional
extension emits `<ID>_HAS_CELL_FLAGS 1`, `<ID>_CELL_FLIP_X 0x20`,
`<ID>_CELL_FLIP_Y 0x40`, and `const uint8_t <id>_cell_flags[cell_count]`.
The array is present even when all flags are zero. Disabled output emits none
of these and remains byte-identical to the original interface. Loaders can test
`#ifdef <ID>_HAS_CELL_FLAGS`; absent flags mean zero. Banking independently adds
`<ID>_BANKED` as described above. Update generated headers and sources together.

Each reuse compares **exact 2bpp indices**, region kind, and local palette ID.
Even visually identical palettes with different local IDs do not share tiles.
Tile and sprite units never share. The canonical unit is the first occurrence in
the existing encode order: sprite pairs across each pair of rows first, then
tile cells row-major. Its bytes retain their original orientation. Reuse checks
no flip, X, Y, then XY; symmetric matches prefer that order. Results are
deterministic and repeat generation does not depend on hash iteration order.

For tile cells, `cell_tiles[cell]` selects the stored tile and `cell_flags[cell]`
transforms it back to the approved orientation. Bits 5/6 match CGB BG attributes
and OBJ flags directly; other bits are zero. Combine these with consumer-assigned
palette slots, VRAM bank, and priority as appropriate; `cell_palettes` remains a
local palette map, not a runtime allocation.

Sprite reuse compares an entire 8×16 pair, including transparent index zero.
Top cells always map to an even tile ID and bottom cells to its following odd ID;
both cells have the same flags and palette. Use the top cell's even ID and flags
for one 8×16 OAM entry. A Y flip reverses all 16 rows, **exchanging displayed
halves**, rather than flipping two 8×8 tiles independently. A pixel preview that
decodes one cell at a time must use the following rules:

```text
tile = cell_tiles[cell]
flags = cell_flags[cell]  (or zero if absent)
if cell belongs to a sprite region and flags & 0x40:
    tile = tile XOR 1          # select the other stored half
sx = 7 - pixel_x if flags & 0x20 else pixel_x
sy = 7 - pixel_y if flags & 0x40 else pixel_y
index = decode_2bpp(tiles[tile * 16 : tile * 16 + 16], sx, sy)
color = palettes[cell_palettes[cell]][index]
# index zero is transparent for sprites, opaque for tiles
```

For a named region, resolve source cell `(region.x + cx, region.y + cy)` as
`cell = (region.y + cy) * <ID>_COLUMNS + region.x + cx`, then read all three maps.
Region rectangles, origins, named macros, and animation region indices remain
unchanged. Neither deduplication nor mixed-atlas ordering guarantees contiguous
tile bytes for a region. Do not derive tile IDs from region positions or cache
generated indices as terrain bindings: bind to region names and resolve maps.
No VRAM, palette, OAM, or runtime bank allocation is introduced.
