"""Verify replay scoring and cleanup independently of historical GitHub state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import docs_review_citation_freshness_replay as replay


def test_match_requires_file_class_and_line_tolerance() -> None:
    case = dict(file="guide.md", line=20, defect_class="stale-citation")
    finding = dict(citing_file="guide.md", citing_line=23, defect_class="stale-citation")
    assert replay.matches(case, finding)
    for change in (
        dict(citing_file="other.md"),
        dict(citing_line=24),
        dict(defect_class="other"),
    ):
        assert not replay.matches(case, finding | change)


def _rows() -> list[dict[str, Any]]:
    return [dict(id="P", kind="positive", scope="automatic", caught=True)] + [
        dict(id=f"N{i}", kind="negative", scope="automatic", false_positives=0) for i in range(12)
    ]


def test_score_requires_all_positives_and_all_twelve_clean_negatives() -> None:
    rows = _rows()
    assert replay.score(rows)["passed"]
    assert not replay.score(rows[:-1])["passed"]
    rows[0]["caught"] = False
    assert not replay.score(rows)["passed"]


def test_any_negative_finding_or_operational_error_fails() -> None:
    rows = _rows()
    rows[1]["false_positives"] = 1
    assert not replay.score(rows)["passed"]
    rows[1]["false_positives"] = 0
    rows[1]["error"] = "fetch failed"
    assert not replay.score(rows)["passed"]


def test_manual_reasons_are_reported_without_inflating_recall() -> None:
    rows = _rows() + [dict(id="M", kind="positive", scope="manual", why="Historical root.")]
    summary = replay.score(rows)
    assert summary["in_scope"] == 1
    assert summary["manual"] == [dict(id="M", why="Historical root.")]


def test_report_index_omits_bulk_fields_and_writes_a_case_file(tmp_path: Path) -> None:
    output = tmp_path / "2026-11-19.json"
    report = dict(
        schema_version=1,
        cases=[dict(id="C1-01", caught=True, findings=[dict(reason="moved")], output="log")],
    )
    replay.write_report(report, output)
    index = json.loads(output.read_text(encoding="utf-8"))
    assert "findings" not in index["cases"][0]
    assert "output" not in index["cases"][0]
    assert index["cases"][0]["record"] == "2026-11-19/C1-01.json"
    shard = json.loads((tmp_path / "2026-11-19" / "C1-01.json").read_text(encoding="utf-8"))
    assert shard["findings"] == [dict(reason="moved")]
    assert shard["output"] == "log"


def test_failed_check_removes_worktree_and_fetched_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def command(args: list[str], cwd: Path = replay.ROOT) -> str:
        commands.append(args)
        if args[0] == "gh":
            return '{"baseRefOid": "base", "headRefOid": "head"}'
        return "commit"

    def broken_check(root: Path, base: str) -> Any:
        raise RuntimeError("cannot read HEAD")

    monkeypatch.setattr(replay, "command", command)
    monkeypatch.setattr(replay, "check", broken_check)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(RuntimeError, match="cannot read HEAD"):
        replay.replay(dict(pr=1, sha="head"), "owner/repo", "unit")
    assert commands[-2][0:3] == ["git", "worktree", "remove"]
    assert commands[-1] == ["git", "update-ref", "-d", "refs/docs-citation-replay/unit/1"]
