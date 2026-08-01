"""Semantic version parsing, formatting, and bumping utilities for prompt versioning."""

import re


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse a version string into a ``(major, minor, patch)`` tuple.

    Accepts ``"v1.2.3"`` or ``"1.2.3"``. Raises ``ValueError``
    if the string does not match the expected ``X.Y.Z`` pattern.
    """
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version_str)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def format_version(major: int, minor: int, patch: int) -> str:
    """Format a ``(major, minor, patch)`` tuple into a version string.

    Example: ``"v1.2.3"``.
    """
    return f"v{major}.{minor}.{patch}"


def get_next_version(existing_versions: list[str], change_type: str = "patch") -> str:
    """Compute the next version based on existing versions and the desired bump type.

    If no valid existing versions are found, returns ``"v1.0.0"``.

    Args:
        existing_versions: List of version strings already in use.
        change_type: One of ``"major"``, ``"minor"``, or ``"patch"`` (default).

    Returns:
        The next version string.
    """
    if not existing_versions:
        return "v1.0.0"

    versions = []
    for v in existing_versions:
        try:
            parsed = parse_version(v)
            versions.append(parsed)
        except ValueError:
            continue

    if not versions:
        return "v1.0.0"

    latest = max(versions, key=lambda x: (x[0], x[1], x[2]))
    major, minor, patch = latest

    if change_type == "major":
        return format_version(major + 1, 0, 0)
    elif change_type == "minor":
        return format_version(major, minor + 1, 0)
    else:
        return format_version(major, minor, patch + 1)
