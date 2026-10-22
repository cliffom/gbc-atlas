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
