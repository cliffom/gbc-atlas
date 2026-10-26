"""Exact 2bpp encoding of validated cells; no quantization or pixel changes."""

from ._validation import require


def encode_cells(image, colors, assignments, kinds, cols, rows, *, deduplicate=False):
    """Encode sprite pairs then BG cells, returning bytes, map, and optional flags."""
    # Encode sprite cells first, preserving even/odd vertical pairs, then tile cells.
    # This prevents an odd number of BG cells from shifting OBJ pairs onto odd IDs.
    order = []
    for y in range(0, rows, 2):
        for x in range(cols):
            cell = y * cols + x
            if kinds[cell] == "sprite":
                require(
                    y + 1 < rows and kinds[cell + cols] == "sprite",
                    "Incomplete sprite pair",
                )
                require(
                    assignments[cell] == assignments[cell + cols],
                    "8x16 pairs must share a palette",
                )
                order.extend((cell, cell + cols))
    order.extend(i for i, kind in enumerate(kinds) if kind == "tile")
    require(len(order) == cols * rows, "Incomplete cell encoding")
    tiles = []
    cell_tiles = [0] * (cols * rows)
    for tile_id, cell in enumerate(order):
        cell_tiles[cell] = tile_id
        cx, cy = cell % cols * 8, cell // cols * 8
        palette = colors[assignments[cell]]
        candidates = palette if kinds[cell] == "tile" else palette[1:]
        offset = 0 if kinds[cell] == "tile" else 1
        require(
            len(set(candidates)) == len(candidates), "Duplicate visible palette colors"
        )
        for y in range(8):
            low = high = 0
            for x in range(8):
                r, g, b, alpha = image.getpixel((cx + x, cy + y))
                require(alpha in (0, 255), f"Partial alpha at {cx + x},{cy + y}")
                if kinds[cell] == "tile":
                    require(
                        alpha == 255, f"Transparent background at {cx + x},{cy + y}"
                    )
                if alpha == 0:
                    color = 0
                else:
                    require(
                        (r, g, b) in candidates,
                        f"Pixel {cx + x},{cy + y} is outside assigned RGB5 palette",
                    )
                    color = candidates.index((r, g, b)) + offset
                low = (low << 1) | (color & 1)
                high = (high << 1) | (color >> 1)
            tiles.extend((low, high))
    if not deduplicate:
        return bytes(tiles), tuple(cell_tiles), None
    return reuse_units(bytes(tiles), order, kinds, assignments)


def flipped(unit, flags):
    """Transform one 8x8 tile or complete 8x16 pair of 2bpp indices."""
    lines = [unit[i : i + 2] for i in range(0, len(unit), 2)]
    if flags & 0x40:
        lines.reverse()
    if flags & 0x20:
        lines = [bytes(int(f"{plane:08b}"[::-1], 2) for plane in row) for row in lines]
    return b"".join(lines)


def reuse_units(tiles, order, kinds, assignments):
    """Reuse first canonical units, keeping palette/kind and sprite pairs intact."""
    unique = bytearray()
    cell_tiles = [0] * len(order)
    cell_flags = [0] * len(order)
    matches = {}
    index = 0
    while index < len(order):
        cell = order[index]
        size = 2 if kinds[cell] == "sprite" else 1
        unit = tiles[index * 16 : (index + size) * 16]
        prefix = (kinds[cell], assignments[cell])
        key = (*prefix, unit)
        if key not in matches:
            tile_id = len(unique) // 16
            unique.extend(unit)
            # Preserve earliest canonical units. Symmetries prefer 0, X, Y, XY.
            for flags in (0, 0x20, 0x40, 0x60):
                matches.setdefault((*prefix, flipped(unit, flags)), (tile_id, flags))
        tile_id, flags = matches[key]
        for half in range(size):
            target = order[index + half]
            # Keep even top / odd bottom IDs. For Y reuse, reconstruction swaps
            # displayed halves exactly as hardware 8x16 OBJ does.
            cell_tiles[target] = tile_id + half
            cell_flags[target] = flags
        index += size
    return bytes(unique), tuple(cell_tiles), tuple(cell_flags)
