"""Version rollback checks that ask git whether the ref is a real commit."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import rollback_checks


def _head_commit() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        cwd=Path(__file__).resolve().parent,
    )
    return out.stdout.strip()


def test_version_with_a_real_commit_passes() -> None:
    assert rollback_checks.version_reasons({"kind": "version", "ref": _head_commit()}) == []


def test_version_with_an_uppercase_commit_id_passes() -> None:
    rollback = {"kind": "version", "ref": _head_commit().upper()}
    assert rollback_checks.version_reasons(rollback) == []


def test_version_commit_unknown_to_git_blocks() -> None:
    reasons = rollback_checks.version_reasons({"kind": "version", "ref": "0" * 40})
    assert reasons == ["rollback version ref is not a commit in this repository"]


def test_version_blocks_when_git_cannot_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("git")

    monkeypatch.setattr(rollback_checks.subprocess, "run", boom)
    reasons = rollback_checks.version_reasons({"kind": "version", "ref": "a" * 40})
    assert reasons == ["rollback version ref could not be checked: git did not run"]


def test_every_referenced_kind_has_a_check() -> None:
    assert set(rollback_checks.KIND_CHECKS) == {"backup", "snapshot", "version"}
