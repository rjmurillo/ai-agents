"""Tests for native Copilot journal evidence (issue #7357).

Every journal here is synthetic. Sentinel strings stand in for prompts and
results so a leak into the output is detectable.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from hashlib import sha1
from pathlib import Path

import pytest

_SCRIPT_DIR = (
    Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "retrospective" / "scripts"
)


def _load(filename: str):
    path = _SCRIPT_DIR / filename
    name = f"retro_{path.stem}_{sha1(str(path).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extract = _load("extract_evidence.py")
journal_mod = _load("copilot_journal.py")

PROMPT = "SENTINEL-PROMPT-do-not-leak"
REASONING = "SENTINEL-REASONING-do-not-leak"
RESULT = "SENTINEL-RESULT-do-not-leak"
ARG_VALUE = "SENTINEL-ARGUMENT-do-not-leak"


def ev(kind: str, data: dict, **extra) -> dict:
    return {"type": kind, "timestamp": "2026-11-09T12:00:00Z", "data": data, **extra}


def start(call: object, tool: object = "bash", arguments: object = None, **extra) -> dict:
    data = {"toolCallId": call, "toolName": tool}
    if arguments is not None:
        data["arguments"] = arguments
    return ev("tool.execution_start", data, **extra)


def complete(call: object, success: object = True, **fields) -> dict:
    return ev("tool.execution_complete", {"toolCallId": call, "success": success, **fields})


def session_start(cwd: Path | None) -> dict:
    context = {"cwd": str(cwd)} if cwd is not None else {}
    return ev("session.start", {"context": context})


def write_journal(path: Path, rows: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [row if isinstance(row, str) else json.dumps(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    return root


@pytest.fixture
def journal_path(tmp_path: Path) -> Path:
    # Real journals live outside the repository, under ~/.copilot/session-state.
    return tmp_path / "copilot-home" / "session-state" / "s1" / "events.jsonl"


def basic_rows(repo: Path) -> list:
    return [
        session_start(repo),
        ev("user.message", {"content": PROMPT}),
        ev("assistant.message", {"content": REASONING}),
        start("c1", "bash", {"command": ARG_VALUE}),
        complete(
            "c1", False, result={"content": RESULT}, error={"code": "EXIT_1", "message": RESULT}
        ),
        start("c2", "view", {"path": "a.py"}),
        complete("c2", True, result={"content": RESULT}),
    ]


def receipts_by_id(report: dict) -> dict:
    return {r["call_id"]: r for r in report["receipts"]}


# Reproduction of the issue: without the new input there is nothing to read.


def test_without_journal_flag_no_receipts_are_gathered(repo: Path, journal_path: Path) -> None:
    write_journal(journal_path, basic_rows(repo))
    evidence = extract.gather_evidence(repo, "2026-11-09")
    assert evidence.journal is None
    assert evidence.session_log_available is False


# Positive


def test_journal_without_toolkit_log_yields_execution_receipts(
    repo: Path, journal_path: Path
) -> None:
    write_journal(journal_path, basic_rows(repo))

    evidence = extract.gather_evidence(repo, "2026-11-09", journal=journal_path)

    assert evidence.session_log_available is False
    report = evidence.journal
    assert report["available"] is True
    assert report["source"] == journal_mod.SOURCE_LABEL
    by_id = receipts_by_id(report)
    assert by_id["c1"]["outcome"] == "failed"
    assert by_id["c1"]["success"] is False
    assert by_id["c1"]["error_code"] == "EXIT_1"
    assert by_id["c1"]["tool"] == "bash"
    assert by_id["c2"]["outcome"] == "succeeded"
    assert report["tool_starts"] == 2


def test_cli_prints_receipts_and_exits_zero(
    repo: Path, journal_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_journal(journal_path, basic_rows(repo))

    code = extract.main(["--project-dir", str(repo), "--journal", str(journal_path)])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["journal"]["available"] is True
    assert len(payload["journal"]["receipts"]) == 2


def test_journal_outside_repository_is_read_when_recorded_cwd_is_inside(
    repo: Path, journal_path: Path
) -> None:
    write_journal(journal_path, basic_rows(repo / "sub"))
    (repo / "sub").mkdir()

    report = journal_mod.extract_receipts(journal_path, repo)

    assert report["available"] is True


def test_incomplete_call_reports_no_completion(repo: Path, journal_path: Path) -> None:
    write_journal(journal_path, [session_start(repo), start("c1")])

    report = journal_mod.extract_receipts(journal_path, repo)

    assert receipts_by_id(report)["c1"]["outcome"] == "no_completion"


# Privacy: only allowlisted fields leave the journal.


def test_no_prompt_reasoning_argument_or_result_text_in_output(
    repo: Path, journal_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_journal(journal_path, basic_rows(repo))

    extract.main(["--project-dir", str(repo), "--journal", str(journal_path)])

    out = capsys.readouterr().out
    for sentinel in (PROMPT, REASONING, RESULT, ARG_VALUE):
        assert sentinel not in out


# Typed argument variants


@pytest.mark.parametrize(
    ("arguments", "kind"),
    [
        ({"command": "x"}, "object"),
        ('{"command": "x"}', "string"),
        ("not json at all {", "string"),
        (["a", "b"], "array"),
        (7, "scalar"),
        (True, "scalar"),
        (1.5, "scalar"),
        (None, "none"),
    ],
)
def test_argument_variants_parse_whether_or_not_json_strings(
    repo: Path, journal_path: Path, arguments: object, kind: str
) -> None:
    rows = [session_start(repo), start("c1", "bash", arguments), complete("c1")]
    write_journal(journal_path, rows)

    report = journal_mod.extract_receipts(journal_path, repo)

    assert report["available"] is True
    assert receipts_by_id(report)["c1"]["argument_kind"] == kind


def test_non_bool_success_is_unknown_not_success(repo: Path, journal_path: Path) -> None:
    rows = [session_start(repo), start("c1"), complete("c1", "true")]
    write_journal(journal_path, rows)

    receipt = receipts_by_id(journal_mod.extract_receipts(journal_path, repo))["c1"]

    assert receipt["success"] is None
    assert receipt["outcome"] == "unknown"


def test_non_string_fields_are_bounded_and_sanitized(repo: Path, journal_path: Path) -> None:
    long_tool = "t" * 500 + "\x1b[31m"
    rows = [session_start(repo), start(42, long_tool), complete(42, True, error=["bad"])]
    write_journal(journal_path, rows)

    receipt = receipts_by_id(journal_mod.extract_receipts(journal_path, repo))["42"]

    assert len(receipt["tool"]) == 120
    assert "\x1b" not in receipt["tool"]
    assert receipt["error_code"] is None


# Unavailable cases


def _assert_unavailable(report: dict, fragment: str) -> None:
    assert report["available"] is False
    assert fragment in report["reason"]
    assert report["receipts"] == []


def test_missing_journal_is_unavailable(repo: Path, tmp_path: Path) -> None:
    report = journal_mod.extract_receipts(tmp_path / "nope.jsonl", repo)
    _assert_unavailable(report, "not readable")


def test_directory_is_unavailable(repo: Path, tmp_path: Path) -> None:
    report = journal_mod.extract_receipts(tmp_path, repo)
    _assert_unavailable(report, "not a regular file")


def test_all_malformed_lines_are_unavailable_and_counted(repo: Path, journal_path: Path) -> None:
    write_journal(journal_path, ["{not json", "[1, 2]", "also bad"])
    report = journal_mod.extract_receipts(journal_path, repo)
    _assert_unavailable(report, "no working directory")
    assert report["malformed_lines"] == 3
    assert report["records_read"] == 0


def test_binary_garbage_is_unavailable_not_success(repo: Path, journal_path: Path) -> None:
    journal_path.parent.mkdir(parents=True)
    journal_path.write_bytes(bytes(range(256)) * 4)
    assert journal_mod.extract_receipts(journal_path, repo)["available"] is False


def test_journal_without_tool_events_is_unavailable(repo: Path, journal_path: Path) -> None:
    write_journal(journal_path, [session_start(repo), ev("user.message", {"content": PROMPT})])
    _assert_unavailable(journal_mod.extract_receipts(journal_path, repo), "no tool execution")


def test_journal_without_recorded_cwd_fails_closed(repo: Path, journal_path: Path) -> None:
    write_journal(journal_path, [session_start(None), start("c1"), complete("c1")])
    _assert_unavailable(journal_mod.extract_receipts(journal_path, repo), "scope not confirmed")


def test_journal_from_another_repository_is_unavailable(
    repo: Path, tmp_path: Path, journal_path: Path
) -> None:
    other = (tmp_path / "other").resolve()
    other.mkdir()
    write_journal(journal_path, [session_start(other), start("c1"), complete("c1")])
    _assert_unavailable(journal_mod.extract_receipts(journal_path, repo), "outside the repository")


def test_later_cwd_change_outside_repository_is_unavailable(
    repo: Path, tmp_path: Path, journal_path: Path
) -> None:
    moved = ev("session.context_changed", {"context": {"cwd": str(tmp_path)}})
    write_journal(journal_path, [session_start(repo), start("c1"), complete("c1"), moved])
    _assert_unavailable(journal_mod.extract_receipts(journal_path, repo), "outside the repository")


def test_sibling_directory_sharing_a_name_prefix_is_outside(
    repo: Path, tmp_path: Path, journal_path: Path
) -> None:
    sibling = (tmp_path / "repo-evil").resolve()
    sibling.mkdir()
    write_journal(journal_path, [session_start(sibling), start("c1"), complete("c1")])
    assert journal_mod.extract_receipts(journal_path, repo)["available"] is False


def test_unavailable_journal_adds_note_and_exit_stays_zero(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = extract.main(["--project-dir", str(repo), "--journal", str(tmp_path / "missing")])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["journal"]["available"] is False
    assert any("Copilot journal unavailable" in note for note in payload["notes"])


def test_missing_skill_doctor_sibling_degrades_to_unavailable(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_journal(journal_path, basic_rows(repo))
    monkeypatch.setattr(journal_mod, "_doctor_scripts_dir", lambda: repo / "absent")
    _assert_unavailable(
        journal_mod.extract_receipts(journal_path, repo), "skill-doctor parser unavailable"
    )


# Caps and skipped records


def test_receipt_cap_is_reported(repo: Path, journal_path: Path) -> None:
    extra = journal_mod.MAX_RECEIPTS + 5
    rows = [session_start(repo), *[start(f"c{i}") for i in range(extra)]]
    write_journal(journal_path, rows)

    report = journal_mod.extract_receipts(journal_path, repo)

    assert len(report["receipts"]) == journal_mod.MAX_RECEIPTS
    assert report["receipts_truncated"] is True
    assert report["receipts_cap"] == journal_mod.MAX_RECEIPTS
    assert report["tool_starts"] == extra


def test_record_cap_is_reported(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal_mod, "MAX_RECORDS", 3)
    rows = [session_start(repo), start("c1"), complete("c1"), start("c2"), complete("c2")]
    write_journal(journal_path, rows)

    report = journal_mod.extract_receipts(journal_path, repo)

    assert report["records_truncated"] is True
    assert report["records_read"] == 3
    assert "c2" not in receipts_by_id(report)


def test_skipped_records_are_counted(repo: Path, journal_path: Path) -> None:
    rows = [
        session_start(repo),
        "{broken",
        start("c1"),
        start("c1"),  # same id, no event id: kept, merged by call id
        ev("tool.execution_start", {"toolCallId": "e1", "toolName": "x"}, id="dup"),
        ev("tool.execution_start", {"toolCallId": "e2", "toolName": "x"}, id="dup"),
        ev("tool.execution_start", {"toolCallId": "z"}, checkpoint=True),
        ev("tool.execution_start", {"toolCallId": "z2"}, ephemeral=True),
        ev("tool.execution_start", {"toolCallId": "sub1"}, agentId="child"),
        {"type": "tool.execution_start", "data": "not-a-dict"},
        start(None),
        complete("ghost"),
    ]
    write_journal(journal_path, rows)

    report = journal_mod.extract_receipts(journal_path, repo)

    assert report["malformed_lines"] == 1
    assert report["starts_without_call_id"] == 1
    assert report["completions_without_retained_start"] == 1
    assert report["records_filtered"] == 5  # dup id, checkpoint, ephemeral, subagent, non-dict data
    assert set(receipts_by_id(report)) == {"c1", "e1"}


def test_reuses_skill_doctor_event_filter() -> None:
    _, _, parser = journal_mod._load_doctor()
    assert callable(parser._copilot_events)


# Side effects


def test_extraction_creates_no_toolkit_session_log(repo: Path, journal_path: Path) -> None:
    write_journal(journal_path, basic_rows(repo))

    extract.gather_evidence(repo, "2026-11-09", journal=journal_path)

    assert not (repo / ".project-toolkit").exists()
    assert list(repo.rglob("*session*")) == []
