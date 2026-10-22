"""Exact 2bpp encoding of validated cells; no quantization or pixel changes."""

from ._validation import require


def encode_cells(image, colors, assignments, kinds, cols, rows):
    """Encode sprite pairs first, then BG cells, returning bytes and a cell map."""
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
    return bytes(tiles), tuple(cell_tiles)
