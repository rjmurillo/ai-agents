"""Conformance of check_adr_lifecycle.py to the contracts it names (#5399).

The module no longer copies ADR-073's schema, the ADR filename pattern, or the
duplicate-key behavior. These tests hold each to its owner.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.validation import check_adr_lifecycle as gate
from scripts.validation import check_adr_uniqueness

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_073 = REPO_ROOT / ".project-toolkit" / "architecture" / "ADR-073-adr-lifecycle-frontmatter.md"
_STATUS_LINE = re.compile(r"^status:\s*([a-z]+(?:\s*\|\s*[a-z]+)+)\s*(?:#.*)?$", re.MULTILINE)


def test_lifecycle_statuses_conform_to_adr_073() -> None:
    match = _STATUS_LINE.search(ADR_073.read_text(encoding="utf-8"))

    assert match is not None, "ADR-073 no longer states a status enum line"
    declared = {word.strip() for word in match.group(1).split("|")}
    assert declared == set(gate.LIFECYCLE_STATUSES)


def test_adr_filename_pattern_is_the_uniqueness_gates_pattern() -> None:
    assert gate.ADR_FILENAME_RE is check_adr_uniqueness.ADR_FILENAME_RE


@pytest.mark.parametrize("name", ["ADR-073-x.md", "ADR-12-y.md"])
def test_adr_filename_pattern_accepts_adr_files(name: str) -> None:
    assert gate.ADR_FILENAME_RE.match(name)


@pytest.mark.parametrize("name", ["ADR-7-x.md", "README.md", "adr-073-x.md", "ADR-073-x.txt"])
def test_adr_filename_pattern_rejects_other_files(name: str) -> None:
    assert gate.ADR_FILENAME_RE.match(name) is None


def test_duplicate_frontmatter_key_is_rejected_with_the_key() -> None:
    import yaml

    with pytest.raises(gate._DuplicateKey) as excinfo:
        yaml.load("status: accepted\nstatus: proposed\n", Loader=gate._StrictLoader)

    assert excinfo.value.key == "status"


def test_unique_frontmatter_keys_load() -> None:
    import yaml

    loaded = yaml.load("status: accepted\ndate: 2026-01-01\n", Loader=gate._StrictLoader)

    assert loaded["status"] == "accepted"
