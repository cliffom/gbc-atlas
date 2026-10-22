"""Shared contract validation helpers."""

import re
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]*", value)


def relative_file(folder, value):
    require(isinstance(value, str), "Expected a relative file path")
    path = (folder / value).resolve()
    require(
        not Path(value).is_absolute() and path.is_relative_to(folder.resolve()),
        "Asset files must stay within the object folder",
    )
    require(path.is_file(), f"Missing file: {path}")
    return path
