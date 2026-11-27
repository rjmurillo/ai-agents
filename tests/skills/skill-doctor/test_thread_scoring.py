"""The session type (top_level or subagent) flows from the inventory to the report."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import assemble_report
import audit_batches as ab
import audit_scores
import pytest
from audit_batch_helpers import Row, _inventory, _row
from render_report import render_page
from session_sampling import sample_sessions
from session_threads import cap_advice, summarize_threads

INPUTS = Path(__file__).resolve().parent / "fixtures" / "audit" / "reproduction"


def load(name: str) -> Any:
    return json.loads((INPUTS / name).read_text(encoding="utf-8"))


def scored_with_threads() -> list[dict[str, Any]]:
    """The reproduction scores with the first two sessions marked as subagent work."""
    sessions: list[dict[str, Any]] = copy.deepcopy(load("scores.json")["sessions"])
    for index, record in enumerate(sessions):
        record["thread"] = "subagent" if index < 2 else "top_level"
    return sessions


def test_thread_enum_is_checked_when_present() -> None:
    sessions = scored_with_threads()
    sessions[0]["thread"] = "background"
    errors = audit_scores.validate_sessions(sessions, audit_scores.load_label_tables())
    assert any("thread must be one of top_level, subagent" in e for e in errors)


def test_missing_thread_is_valid() -> None:
    sessions = load("scores.json")["sessions"]
    assert audit_scores.validate_sessions(sessions, audit_scores.load_label_tables()) == []


def test_artifact_groups_by_thread_alongside_strata_and_harness() -> None:
    artifact = audit_scores.build_artifact(scored_with_threads())
    assert set(artifact["per_thread"]) == {"subagent", "top_level"}
    assert artifact["per_thread"]["subagent"]["sessions_scored"] == 2
    assert artifact["per_thread"]["top_level"]["sessions_scored"] == 4
    assert "per_harness" in artifact


def test_artifact_without_thread_records_has_no_per_thread() -> None:
    artifact = audit_scores.build_artifact(load("scores.json")["sessions"])
    assert "per_thread" not in artifact


def test_assemble_writes_per_thread_overall(tmp_path: Path) -> None:
    sessions = scored_with_threads()
    report = assemble_report.assemble(load("draft.json"), {"sessions": sessions})
    per_thread = report["sampling"]["per_thread"]
    artifact = audit_scores.build_artifact(sessions)
    assert per_thread["subagent"]["overall"] == artifact["per_thread"]["subagent"]["overall"]
    assert per_thread["top_level"]["overall"] == artifact["per_thread"]["top_level"]["overall"]


def test_assemble_drops_stale_per_thread_overall() -> None:
    draft = load("draft.json")
    draft["sampling"]["per_thread"] = {"subagent": {"scoreable": 1, "overall": 0.1}}
    sessions = scored_with_threads()
    for record in sessions:
        record["thread"] = "top_level"
    report = assemble_report.assemble(draft, {"sessions": sessions})
    assert "overall" not in report["sampling"]["per_thread"]["subagent"]


def test_assemble_without_threads_adds_no_per_thread() -> None:
    report = assemble_report.assemble(load("draft.json"), load("scores.json"))
    assert "per_thread" not in report["sampling"]


def sampling_report() -> dict[str, Any]:
    return {
        "scores": {"overall": 0.8},
        "sampling": {
            "per_harness": {"claude": {"scoreable": 3, "skill_candidates": 1, "sampled": 2}},
            "per_thread": {
                "top_level": {"scoreable": 1, "sampled": 1, "overall": 0.9},
                "subagent": {"scoreable": 2, "sampled": 1},
            },
        },
    }


def test_report_renders_sampling_by_session_type() -> None:
    page = render_page(sampling_report())
    assert "Sampling by session type" in page
    assert "<td>Top-level</td><td>1</td><td>1</td><td>90</td>" in page
    assert "<td>Subagent</td><td>2</td><td>1</td><td>-</td>" in page


def test_report_without_per_thread_has_no_session_type_table() -> None:
    report = sampling_report()
    del report["sampling"]["per_thread"]
    assert "Sampling by session type" not in render_page(report)


def test_report_renders_session_type_table_without_harness_table() -> None:
    report = sampling_report()
    report["sampling"]["per_harness"] = {}
    page = render_page(report)
    assert "Sampling by session type" in page
    assert "Sampling by harness" not in page


def threaded_inventory() -> Row:
    inventory = _inventory(4)
    inventory["sessions"][0]["thread"] = "subagent"
    inventory["sessions"][1]["thread"] = "top_level"
    return inventory


def test_assignment_carries_script_supplied_threads() -> None:
    manifest = ab.build_assignment(threaded_inventory(), 10)
    threads = manifest["batches"][0]["session_threads"]
    assert threads["copilot:s0"] == "subagent"
    assert threads["copilot:s1"] == "top_level"
    assert threads["copilot:s2"] == "top_level"
    assert "copilot:unsampled" not in threads


def test_import_stamps_thread_from_the_assignment(tmp_path: Path) -> None:
    manifest = ab.build_assignment(threaded_inventory(), 10)
    batch = manifest["batches"][0]
    rows = [_row(batch, sid) for sid in batch["session_ids"]]
    path = tmp_path / "accepted.json"
    ab.import_scores(batch, path, rows)
    stored = {r["session_id"]: r for r in json.loads(path.read_text(encoding="utf-8"))["sessions"]}
    assert stored["copilot:s0"]["thread"] == "subagent"
    assert stored["copilot:s1"]["thread"] == "top_level"
    assert all("thread" not in row for row in rows)


def test_import_rejects_a_thread_that_contradicts_the_assignment(tmp_path: Path) -> None:
    manifest = ab.build_assignment(threaded_inventory(), 10)
    batch = manifest["batches"][0]
    rows = [_row(batch, sid) for sid in batch["session_ids"]]
    rows[0]["thread"] = "top_level"
    with pytest.raises(ab.ImportRejectedError) as raised:
        ab.import_scores(batch, tmp_path / "accepted.json", rows)
    assert any("thread 'top_level' is not 'subagent'" in e for e in raised.value.errors)


def test_malformed_session_threads_are_rejected() -> None:
    manifest = ab.build_assignment(threaded_inventory(), 10)
    batch = copy.deepcopy(manifest["batches"][0])
    batch["session_threads"] = {"copilot:s0": "orbital"}
    errors = ab.validate_rows(batch, [])
    assert any("session_threads" in e for e in errors)


def test_assignment_without_session_threads_still_imports(tmp_path: Path) -> None:
    manifest = ab.build_assignment(_inventory(2), 10)
    batch = copy.deepcopy(manifest["batches"][0])
    del batch["session_threads"]
    rows = [_row(batch, sid) for sid in batch["session_ids"]]
    ab.import_scores(batch, tmp_path / "accepted.json", rows)
    stored = json.loads((tmp_path / "accepted.json").read_text(encoding="utf-8"))["sessions"]
    assert all("thread" not in row for row in stored)


def test_legacy_inventory_reads_the_subagent_tag_from_session_meta() -> None:
    inventory = _inventory(3)
    inventory["sessions"][0]["meta"]["thread_source"] = "subagent"
    threads = ab.build_assignment(inventory, 10)["batches"][0]["session_threads"]
    assert threads["copilot:s0"] == "subagent"
    assert threads["copilot:s2"] == "top_level"


def test_explicit_thread_field_wins_over_session_meta() -> None:
    inventory = _inventory(2)
    inventory["sessions"][0]["thread"] = "top_level"
    inventory["sessions"][0]["meta"]["thread_source"] = "subagent"
    threads = ab.build_assignment(inventory, 10)["batches"][0]["session_threads"]
    assert threads["copilot:s0"] == "top_level"


def test_legacy_subagent_score_without_thread_imports_as_subagent(tmp_path: Path) -> None:
    inventory = _inventory(2)
    inventory["sessions"][0]["meta"]["thread_source"] = "subagent"
    batch = ab.build_assignment(inventory, 10)["batches"][0]
    rows = [_row(batch, sid) for sid in batch["session_ids"]]
    ab.import_scores(batch, tmp_path / "accepted.json", rows)
    stored = json.loads((tmp_path / "accepted.json").read_text(encoding="utf-8"))["sessions"]
    assert {r["session_id"]: r["thread"] for r in stored}["copilot:s0"] == "subagent"


def test_assemble_fills_missing_per_type_sampled_counts() -> None:
    draft = load("draft.json")
    draft["sampling"]["per_thread"] = {"subagent": {"scoreable": 5}, "top_level": {}}
    report = assemble_report.assemble(draft, {"sessions": scored_with_threads()})
    per_thread = report["sampling"]["per_thread"]
    assert per_thread["subagent"]["sampled"] == 2
    assert per_thread["top_level"]["sampled"] == 4
    assert per_thread["subagent"]["scoreable"] == 5
    assert "scoreable" not in per_thread["top_level"]
    assert "<td>Subagent</td><td>5</td><td>2</td>" in render_page(report)


def test_assemble_rejects_a_per_type_sampled_count_the_scores_do_not_match() -> None:
    draft = load("draft.json")
    draft["sampling"]["per_thread"] = {"subagent": {"sampled": 3}}
    with pytest.raises(assemble_report.AssemblyError) as raised:
        assemble_report.assemble(draft, {"sessions": scored_with_threads()})
    assert any("session type 'subagent': 2 of 3" in e for e in raised.value.errors)


def test_assemble_keeps_a_matching_per_type_sampled_count() -> None:
    draft = load("draft.json")
    draft["sampling"]["per_thread"] = {"subagent": {"sampled": 2, "scoreable": 2}}
    report = assemble_report.assemble(draft, {"sessions": scored_with_threads()})
    assert report["sampling"]["per_thread"]["subagent"]["sampled"] == 2


def test_report_renders_the_top_level_gap_notice_and_opens_sampling() -> None:
    report = sampling_report()
    report["sampling"]["top_level_notice"] = "the sample holds no <b>top-level</b> sessions"
    page = render_page(report)
    assert '<p class="notice">the sample holds no &lt;b&gt;top-level&lt;/b&gt; sessions</p>' in page
    assert '<details class="section" open><summary>Sampling</summary>' in page


def test_report_without_either_notice_leaves_sampling_closed() -> None:
    page = render_page(sampling_report())
    assert 'class="notice"' not in page
    assert '<details class="section"><summary>Sampling</summary>' in page


def _session(harness: str, thread: str, name: str, skills: list[str]) -> dict[str, Any]:
    return {
        "harness": harness,
        "thread": thread,
        "_key": f"{harness}:{name}",
        "skills_used": skills,
    }


def _gap_notice(sessions: list[dict[str, Any]], max_sessions: int = 12) -> str:
    args = SimpleNamespace(max_sessions=max_sessions, per_skill=3, no_skill=4)
    sampled, per_harness, sampling = sample_sessions(sessions, ["s"], args)
    summarize_threads(sessions, sampled, per_harness, sampling)
    notice: str = sampling["top_level_notice"]
    return notice


def test_gap_notice_names_no_skill_cap_when_it_excludes_top_level_work() -> None:
    sessions = [_session("claude", "subagent", f"c{i}", []) for i in range(5)]
    sessions += [_session("claude", "top_level", f"t{i}", []) for i in range(2)]
    notice = _gap_notice(sessions)
    assert "--no-skill" in notice
    assert "--max-sessions" not in notice


def test_gap_notice_names_per_skill_cap_when_it_excludes_top_level_work() -> None:
    sessions = [_session("claude", "subagent", f"c{i}", ["s"]) for i in range(3)]
    sessions.append(_session("claude", "top_level", "t0", ["s"]))
    notice = _gap_notice(sessions)
    assert "--per-skill" in notice
    assert "--max-sessions" not in notice


def test_gap_notice_names_max_sessions_when_the_overall_cap_binds() -> None:
    sessions = [_session("claude", "subagent", f"c{i}", []) for i in range(2)]
    sessions += [_session("claude", "top_level", f"t{i}", []) for i in range(2)]
    notice = _gap_notice(sessions, max_sessions=2)
    assert "--max-sessions" in notice
    assert "--per-skill" not in notice


def test_gap_advice_names_every_cap_when_harnesses_are_held_back_differently() -> None:
    sessions = [
        _session("claude", "top_level", "t", []),
        _session("codex", "top_level", "t", []),
    ]
    per_harness = {"claude": {"sampled": 1, "quota": 1}, "codex": {"sampled": 0, "quota": 2}}
    assert "--max-sessions, --per-skill, or --no-skill" in cap_advice(sessions, set(), per_harness)
