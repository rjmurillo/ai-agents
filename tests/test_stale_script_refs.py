"""Tests for stale script reference validation."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.validation.stale_script_refs as stale_script_refs
from scripts.validation.stale_script_refs import (
    Finding,
    find_stale_refs,
    main,
)


def test_existing_tracked_script_ref_passes(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "runbook.md"
    doc.parent.mkdir()
    doc.write_text("```bash\nscripts/Live.ps1 --check\n```\n", encoding="utf-8")

    findings = find_stale_refs(
        tmp_path,
        docs={"docs/runbook.md"},
        tracked={"docs/runbook.md", "scripts/Live.ps1"},
        allowlist=set(),
    )

    assert findings == []


def test_missing_script_ref_fails_with_file_line_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    doc = tmp_path / "docs" / "runbook.md"
    doc.parent.mkdir()
    doc.write_text("Use this command:\n```bash\npwsh scripts/Missing.ps1\n```\n", encoding="utf-8")

    def fake_git_ls_files(repo_root: Path, patterns: tuple[str, ...] | None = None) -> set[str]:
        if patterns:
            return {"docs/runbook.md"}
        return {"docs/runbook.md"}

    monkeypatch.setattr(stale_script_refs, "git_ls_files", fake_git_ls_files)

    result = main(["--repo-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert result == 1
    assert "docs/runbook.md:3:scripts/Missing.ps1" in captured.out


def test_historical_directory_is_skipped(tmp_path: Path) -> None:
    doc = tmp_path / ".agents" / "sessions" / "old.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("```bash\npwsh scripts/Missing.ps1\n```\n", encoding="utf-8")

    findings = find_stale_refs(
        tmp_path,
        docs={".agents/sessions/old.md"},
        tracked={".agents/sessions/old.md"},
        allowlist=set(),
    )

    assert findings == []


def test_allowlist_entry_is_honored(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "history.md"
    doc.parent.mkdir()
    doc.write_text("```bash\npwsh scripts/Missing.ps1\n```\n", encoding="utf-8")

    findings = find_stale_refs(
        tmp_path,
        docs={"docs/history.md"},
        tracked={"docs/history.md"},
        allowlist={"docs/history.md:2:scripts/Missing.ps1"},
    )

    assert findings == []


def test_file_allowlist_entry_is_honored(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "history.md"
    doc.parent.mkdir()
    doc.write_text("```bash\npwsh scripts/Missing.ps1\n```\n", encoding="utf-8")

    findings = find_stale_refs(
        tmp_path,
        docs={"docs/history.md"},
        tracked={"docs/history.md"},
        allowlist={"docs/history.md"},
    )

    assert findings == []


def test_finding_format() -> None:
    assert Finding("docs/runbook.md", 2, "scripts/Missing.ps1").format() == (
        "docs/runbook.md:2:scripts/Missing.ps1"
    )
