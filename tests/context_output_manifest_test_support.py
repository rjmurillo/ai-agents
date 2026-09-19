"""Shared manifest fixtures for context output tests."""

import json
from pathlib import Path


def write_manifest(
    path: Path,
    entries: list[dict[str, str]],
    output_root: str = ".",
) -> None:
    """Write a compact manifest fixture."""
    path.write_text(
        json.dumps({"output_root": output_root, "entries": entries}),
        encoding="utf-8",
    )
