"""Fixture tree primitives shared by the routing scenario loader and hygiene checks (issue #5425).

Split out so `_routing_scenario.py` and `_routing_hygiene.py` can both use
them without importing each other.
"""

from __future__ import annotations

from pathlib import Path

FIXTURE_SUFFIX = ".fixture"


class RoutingCorpusError(ValueError):
    """A scenario, fixture, or corpus is invalid. Never degrades to a default."""


def fixture_files(directory: Path) -> dict[str, Path]:
    """Map logical relative posix path to file for one fixture directory.

    The `.fixture` suffix is stripped from the logical path. A file without
    the suffix raises, so live source cannot hide inside a fixture tree. A
    symlink raises too, so a fixture cannot pull in a file from outside it.
    """
    files: dict[str, Path] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise RoutingCorpusError(f"{path}: fixture trees may not contain symlinks")
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        if not relative.endswith(FIXTURE_SUFFIX):
            raise RoutingCorpusError(f"{path}: fixture file must end with {FIXTURE_SUFFIX}")
        files[relative[: -len(FIXTURE_SUFFIX)]] = path
    return files


def read_fixture_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RoutingCorpusError(f"{path}: cannot read fixture as UTF-8: {exc}") from exc
