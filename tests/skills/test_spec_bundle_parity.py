"""Parity tests for the spec skill's bundled helper scripts and data file.

Issue #2742: the spec skill (`src/copilot-cli/skills/spec/`) references helper
scripts (`redact_secrets.py`, `metrics_writer.py`) and a data file
(`spec-entity-aliases.json`) by toolkit-relative paths that do not exist when the
skill runs from an installed plugin in a consumer repo. The fix bundles
byte-identical copies inside the skill so a directory-copy install ships them.

These tests guard the byte-identity invariant: if the canonical source drifts
from the bundled copy, the BLOCKING redactor and the metrics tally would diverge
between toolkit-dev and installed-plugin runs. The build fails loudly on
divergence so the two never silently disagree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_DIR = _REPO_ROOT / "src" / "copilot-cli" / "skills" / "spec"

# (canonical source, bundled copy) pairs, both repo-relative.
_PARITY_PAIRS: tuple[tuple[Path, Path], ...] = (
    (
        _REPO_ROOT / "scripts" / "redact_secrets.py",
        _SKILL_DIR / "scripts" / "redact_secrets.py",
    ),
    (
        _REPO_ROOT / "scripts" / "metrics_writer.py",
        _SKILL_DIR / "scripts" / "metrics_writer.py",
    ),
    (
        _REPO_ROOT / ".agents" / "dictionaries" / "spec-entity-aliases.json",
        _SKILL_DIR / "data" / "spec-entity-aliases.json",
    ),
)


@pytest.mark.parametrize(
    ("source", "bundled"),
    _PARITY_PAIRS,
    ids=[bundled.name for _, bundled in _PARITY_PAIRS],
)
def test_bundled_copy_exists(source: Path, bundled: Path) -> None:
    # Arrange / Act / Assert: the bundle must ship the file the skill needs.
    assert source.is_file(), f"canonical source missing: {source}"
    assert bundled.is_file(), f"bundled copy missing: {bundled}"


@pytest.mark.parametrize(
    ("source", "bundled"),
    _PARITY_PAIRS,
    ids=[bundled.name for _, bundled in _PARITY_PAIRS],
)
def test_bundled_copy_is_byte_identical(source: Path, bundled: Path) -> None:
    # Arrange
    source_bytes = source.read_bytes()
    bundled_bytes = bundled.read_bytes()

    # Act / Assert: byte-for-byte equality so toolkit-dev and installed-plugin
    # runs invoke the same code and read the same data.
    assert bundled_bytes == source_bytes, (
        f"bundled copy {bundled} drifted from canonical source {source}; "
        f"re-copy the source into the skill bundle"
    )
