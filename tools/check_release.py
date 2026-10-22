"""Validate the project's SemVer release tags against Python package versions."""

import argparse
import re

NUMBER = r"(?:0|[1-9][0-9]*)"
TAG = re.compile(
    rf"v(?P<base>{NUMBER}\.{NUMBER}\.{NUMBER})"
    rf"(?:-(?P<phase>alpha|beta|rc)\.(?P<number>{NUMBER}))?"
)


def validate_release(tag: str, version: str, prerelease: bool) -> None:
    """Require canonical SemVer tags and their matching PEP 440 versions.

    Restrict prereleases to alpha.N, beta.N and rc.N so their meaning maps
    directly to Python packaging. Build metadata is not published to PyPI.
    """
    match = TAG.fullmatch(tag)
    if match is None:
        raise ValueError(
            "Release tag must be vMAJOR.MINOR.PATCH, optionally followed by "
            "-alpha.N, -beta.N or -rc.N; no leading zeros or build metadata"
        )
    phase = match["phase"]
    expected = match["base"]
    if phase:
        expected += {"alpha": "a", "beta": "b", "rc": "rc"}[phase] + match["number"]
    if version != expected:
        raise ValueError(
            f"Tag {tag} requires package version {expected}, got {version}"
        )
    if prerelease != bool(phase):
        raise ValueError("GitHub prerelease flag must match the release tag")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--prerelease", choices=("true", "false"), required=True)
    args = parser.parse_args()
    try:
        validate_release(args.tag, args.version, args.prerelease == "true")
    except ValueError as error:
        parser.exit(1, f"Release error: {error}\n")
    print(f"Release {args.tag} matches package version {args.version}")


if __name__ == "__main__":
    main()
