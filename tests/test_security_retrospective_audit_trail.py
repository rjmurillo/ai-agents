"""Tests for the security retrospective's local audit trail.

Coverage for `_write_audit_trail`, which had none. The method was renamed
from a name that promised a write to a semantic memory backend retired in
issue #5574, and the rename is only safe if the write it actually performs
is pinned. These tests pin it.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.security.invoke_security_retrospective import (
    ExternalReviewSource,
    FalseNegative,
    SecurityRetrospective,
)

_FALLBACK = Path(".agents") / "security" / "false-negatives.json"


def _retrospective(tmp_path: Path, dry_run: bool = False) -> SecurityRetrospective:
    with patch.object(SecurityRetrospective, "_find_repo_root", return_value=tmp_path):
        return SecurityRetrospective(
            7, ExternalReviewSource.MANUAL, dry_run=dry_run
        )


def _false_negative(cwe_id: str = "CWE-78") -> FalseNegative:
    return FalseNegative(
        cwe_id=cwe_id,
        file_path="scripts/run.py",
        line_number=42,
        description="unsanitised argument reaches a shell",
        severity="HIGH",
        external_reviewer="Manual",
        remediation="pass a list, never shell=True",
        pr_number=7,
    )


def test_writes_record_for_each_false_negative(tmp_path: Path) -> None:
    """Positive path: the audit trail lands on disk with the finding's fields."""
    retro = _retrospective(tmp_path)
    retro.false_negatives = [_false_negative()]

    assert retro._write_audit_trail() is True

    entries = json.loads((tmp_path / _FALLBACK).read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["cwe_id"] == "CWE-78"
    assert entries[0]["pr_number"] == 7
    assert entries[0]["file_path"] == "scripts/run.py"
    assert entries[0]["severity"] == "HIGH"
    assert entries[0]["memory_data"]["importance"] == 10


def test_appends_rather_than_overwrites(tmp_path: Path) -> None:
    """Edge: a second run must not discard the first run's record.

    The audit trail is the only durable record of a missed vulnerability now
    that the second backend is gone, so a clobbering write would lose it.
    """
    retro = _retrospective(tmp_path)
    retro.false_negatives = [_false_negative("CWE-22")]
    retro._write_audit_trail()
    retro.false_negatives = [_false_negative("CWE-89")]
    retro._write_audit_trail()

    entries = json.loads((tmp_path / _FALLBACK).read_text(encoding="utf-8"))
    assert [entry["cwe_id"] for entry in entries] == ["CWE-22", "CWE-89"]


def test_corrupt_existing_trail_does_not_raise(tmp_path: Path) -> None:
    """Edge: unparseable existing content is replaced, not propagated."""
    target = tmp_path / _FALLBACK
    target.parent.mkdir(parents=True)
    target.write_text("{not json", encoding="utf-8")

    retro = _retrospective(tmp_path)
    retro.false_negatives = [_false_negative()]

    assert retro._write_audit_trail() is True
    entries = json.loads(target.read_text(encoding="utf-8"))
    assert len(entries) == 1


def test_no_findings_writes_nothing(tmp_path: Path) -> None:
    """Negative: an empty finding list must not create the file."""
    retro = _retrospective(tmp_path)
    retro.false_negatives = []

    assert retro._write_audit_trail() is True
    assert not (tmp_path / _FALLBACK).exists()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    """Negative: dry run reports intent without touching the tree."""
    retro = _retrospective(tmp_path, dry_run=True)
    retro.false_negatives = [_false_negative()]

    assert retro._write_audit_trail() is True
    assert not (tmp_path / _FALLBACK).exists()
