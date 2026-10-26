"""Manifest v1, exact RGB5 conversion, and approval digest compatibility."""

import hashlib
import json
from pathlib import Path

from PIL import Image

from ._validation import (
    identifier,
    integer,
    relative_file,
    require,
    validate_deduplicate,
)
from .encoding import encode_cells
from .model import Atlas


def source_files(path, m):
    """The manifest is the retention list as well as the approval contract."""
    files = {"png": relative_file(path.parent, m["png"])}
    require(files["png"].suffix.lower() == ".png", "Atlas must be one native PNG")
    for key in ("source", "preview"):
        if key in m:
            files[key] = relative_file(path.parent, m[key])
            require(
                files[key].suffix == ".aseprite", f"{key} must be editable .aseprite"
            )
    if "source" in files and "preview" in files:
        require(
            files["source"] != files["preview"],
            "Atlas and preview must be separate documents",
        )
    for index, name in enumerate(m.get("review_images", [])):
        files[f"review_{index}"] = relative_file(path.parent, name)
    return files


def load_atlas(path: Path, *, deduplicate: bool = False) -> Atlas:
    """Validate/encode a native pack; optional deduplication does not alter its digest."""
    path = Path(path)
    validate_deduplicate(deduplicate)
    m = json.loads(path.read_text())
    require(isinstance(m, dict), "Manifest must be a JSON object")
    require(m.get("version") == 1, "Unsupported manifest version")
    require(identifier(m.get("id")), "id must be a lowercase C identifier")
    require(path.name.endswith(".atlas.json"), "Manifest must be named *.atlas.json")
    files = source_files(path, m)
    with Image.open(files["png"]) as source:
        image = source.convert("RGBA")
    w, h = image.size
    require(
        w % 8 == h % 8 == 0 and 8 <= w <= 256 and 8 <= h <= 256,
        "Atlas dimensions must be multiples of eight, 8..256",
    )
    cols, rows = w // 8, h // 8
    count = cols * rows
    require(count <= 256, "Converter supports at most 256 atlas cells")
    palettes = m.get("palettes", [])
    require(1 <= len(palettes) <= 8, "Use 1..8 local palettes")
    colors = []
    for palette in palettes:
        require(
            len(palette) == 4
            and all(len(c) == 3 and all(integer(v, 0, 31) for v in c) for c in palette),
            "Palettes require four RGB5 triplets",
        )
        rgb = [tuple((v * 255 + 15) // 31 for v in c) for c in palette]
        colors.append(rgb)
    assignments = m.get("cell_palettes", [])
    require(
        len(assignments) == count
        and all(integer(v, 0, len(palettes) - 1) for v in assignments),
        "cell_palettes must assign every cell in row-major order",
    )
    regions = m.get("regions", [])
    require(1 <= len(regions) <= 255, "Declare 1..255 named regions")
    names = set()
    region_values = []
    kinds = [None] * count
    for r in regions:
        name = r.get("name")
        require(
            identifier(name) and name not in names, "Invalid or duplicate region name"
        )
        names.add(name)
        kind = r.get("kind")
        require(kind in ("tile", "sprite"), "Each region requires kind: tile or sprite")
        rect = [r.get(k) for k in ("x", "y", "width", "height")]
        require(
            all(integer(v, 0, 256) and v % 8 == 0 for v in rect),
            "Regions use aligned pixel rectangles",
        )
        x, y, rw, rh = rect
        require(
            rw > 0 and rh > 0 and x + rw <= w and y + rh <= h, "Region outside atlas"
        )
        require(
            kind != "sprite" or (y % 16 == 0 and rh % 16 == 0),
            "Sprite regions must align vertically to 8x16 pairs",
        )
        origin = r.get("origin", [0, 0])
        require(
            isinstance(origin, list)
            and len(origin) == 2
            and integer(origin[0], 0, rw - 1)
            and integer(origin[1], 0, rh - 1),
            "Region origin must be a pixel coordinate within the region",
        )
        duration = r.get("duration_ms", 0)
        require(
            "duration_ms" not in r or integer(duration, 1, 65535),
            "Invalid region duration_ms",
        )
        region_values.append(
            [
                x // 8,
                y // 8,
                rw // 8,
                rh // 8,
                *origin,
                1 if kind == "sprite" else 0,
                duration,
            ]
        )
        for cy in range(y // 8, (y + rh) // 8):
            for cx in range(x // 8, (x + rw) // 8):
                cell = cy * cols + cx
                require(
                    kinds[cell] in (None, kind),
                    "Overlapping tile/sprite kinds in one cell",
                )
                kinds[cell] = kind
    require(
        all(kinds), "Every atlas cell must belong to a region; name padding explicitly"
    )
    tiles, cell_tiles, cell_flags = encode_cells(
        image, colors, assignments, kinds, cols, rows, deduplicate=deduplicate
    )
    animations = m.get("animations", [])
    anim_names = set()
    region_names = [r["name"] for r in regions]
    for a in animations:
        require(
            identifier(a.get("name")) and a["name"] not in anim_names,
            "Invalid animation name",
        )
        anim_names.add(a["name"])
        frames = a.get("frames", [])
        require(1 <= len(frames) <= 255, "Animation requires 1..255 frames")
        for frame in frames:
            require(
                frame.get("region") in names, "Animation frame requires a named region"
            )
            region = regions[region_names.index(frame["region"])]
            require(
                integer(frame.get("duration_ms", region.get("duration_ms")), 1, 65535),
                "Animation frame requires duration_ms on frame or region",
            )
        shapes = [region_values[region_names.index(f["region"])][2:7] for f in frames]
        require(
            all(shape == shapes[0] for shape in shapes),
            "Animation frames must share dimensions and origin",
        )
    # Bind approval to all metadata, editable documents, atlas pixels and review evidence.
    contract = {k: v for k, v in m.items() if k != "approval"}
    hashes = {
        key: hashlib.sha256(file.read_bytes()).hexdigest()
        for key, file in files.items()
    }
    digest = hashlib.sha256(
        json.dumps([contract, hashes], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    packed = [r | (g << 5) | (b << 10) for p in palettes for r, g, b in p]
    return Atlas(
        m,
        digest,
        bytes(tiles),
        tuple(cell_tiles),
        tuple(packed),
        tuple(tuple(r) for r in region_values),
        (cols, rows),
        cell_flags,
    )
