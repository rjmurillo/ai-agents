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
# ADR-064 (issue #5632) made spec a skill on the Claude side too. Until then the
# bundle existed only in the Copilot tree and was hand-maintained, so a Claude
# plugin consumer installed `/spec` with none of the helpers it names. The
# Claude copy is now the source the directory-copy generator mirrors from, which
# is why both trees are pinned here rather than just the Copilot one.
_CLAUDE_SKILL_DIR = _REPO_ROOT / ".claude" / "skills" / "spec"

_CANONICAL_BUNDLE: tuple[tuple[Path, str], ...] = (
    (_REPO_ROOT / "scripts" / "redact_secrets.py", "scripts/redact_secrets.py"),
    (_REPO_ROOT / "scripts" / "metrics_writer.py", "scripts/metrics_writer.py"),
    (
        _REPO_ROOT / ".agents" / "dictionaries" / "spec-entity-aliases.json",
        "data/spec-entity-aliases.json",
    ),
)

# (canonical source, bundled copy) pairs, both repo-relative, for both trees.
_PARITY_PAIRS: tuple[tuple[Path, Path], ...] = tuple(
    (source, skill_dir / relative)
    for source, relative in _CANONICAL_BUNDLE
    for skill_dir in (_SKILL_DIR, _CLAUDE_SKILL_DIR)
)


@pytest.mark.parametrize(
    ("source", "bundled"),
    _PARITY_PAIRS,
    ids=[f"{bundled.parts[-4]}-{bundled.name}" for _, bundled in _PARITY_PAIRS],
)
def test_bundled_copy_exists(source: Path, bundled: Path) -> None:
    # Arrange / Act / Assert: the bundle must ship the file the skill needs.
    assert source.is_file(), f"canonical source missing: {source}"
    assert bundled.is_file(), f"bundled copy missing: {bundled}"


@pytest.mark.parametrize(
    ("source", "bundled"),
    _PARITY_PAIRS,
    ids=[f"{bundled.parts[-4]}-{bundled.name}" for _, bundled in _PARITY_PAIRS],
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
