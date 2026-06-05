"""Path helpers for quality-gate workflow adapters."""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def resolve_workspace_path(path: Path, label: str) -> Path:
    """Resolve ``path`` under the repository root and reject traversal."""

    workspace = REPOSITORY_ROOT.resolve()
    candidate = path if path.is_absolute() else workspace / path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(f"{label} must stay within the repository workspace") from exc
    return resolved
