"""Named conversion results; coordinates and maps follow manifest v1."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Atlas:
    manifest: dict[str, Any]
    digest: str
    tiles: bytes
    cell_tiles: tuple[int, ...]
    palettes: tuple[int, ...]
    regions: tuple[tuple[int, ...], ...]
    dimensions: tuple[int, int]
    cell_flags: tuple[int, ...] | None = None

    @property
    def tiles_saved(self) -> int:
        return len(self.cell_tiles) - len(self.tiles) // 16
