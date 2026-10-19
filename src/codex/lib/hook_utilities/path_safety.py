"""Path safety helpers for plugin-distributed scripts."""

from __future__ import annotations

from pathlib import Path


def validate_path_no_traversal(path: Path, context: str = "path") -> Path:
    """Validate a path against CWE-22 traversal attacks.

    Relative paths must resolve inside the current working directory. Absolute
    paths are allowed because operating-system permissions decide access.
    """
    path_str = str(path)
    if ".." in path_str:
        raise PermissionError(
            f"Path traversal attempt detected in {context}: "
            f"'{path}' contains prohibited '..' sequence."
        )

    resolved = path.resolve()
    if not path.is_absolute():
        try:
            resolved.relative_to(Path.cwd().resolve())
        except ValueError as exc:
            raise PermissionError(
                f"Path traversal attempt detected in {context}: "
                f"'{path}' resolves outside the working directory."
            ) from exc

    return resolved
