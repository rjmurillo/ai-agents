"""Session validation artifact naming."""

from __future__ import annotations

from pathlib import Path


def artifact_name(session_file: str) -> str:
    """Return a name unique across directories, not just across file stems."""
    path = Path(session_file)
    return f"{path.parent.name}-{path.stem}"
