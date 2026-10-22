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
- `<id>_palettes`: packed GBC RGB15 values, four entries per local palette.
- `<id>_regions`: cell rectangles, kinds, pixel origins, and optional durations
  (zero means unspecified), with named region macros.
- Named animation arrays of region indices and durations, with frame counts.

No quantization, palette fitting, deduplication, tile flips, packing across VRAM
banks, metasprite/OAM placement, collision generation, or automatic ROM banking
occurs. The loader must allocate VRAM and palette slots, remap local indices, and
assemble sprite regions through the cell map. Each 8×16 OAM entry uses the top
cell's even tile ID; enable GBDK's `SPRITES_8x16` mode when loading sprite regions.
Screen-space OAM coordinates also require the hardware
offsets; the source origin is an artistic anchor, not an OAM coordinate.

The current 256-tile, eight-palette per-atlas ceiling is a converter limit. There
is no whole-scene allocation or timing checker yet. Before integration, budget
combined BG/OBJ VRAM, palette slots, OAM entries, scanline occupancy, upload work,
and linked ROM capacity. The current ROM-only baseline must evolve deliberately
if generated assets exhaust it. Technical converter tests use synthetic images;
they make no claims about art direction or editor connectivity.

RGB5 components expand to PNG RGB8 with `(value * 255 + 15) // 31`.
Colors must match that expansion exactly; the converter does not quantize.
