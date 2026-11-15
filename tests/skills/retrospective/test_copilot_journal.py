"""Tests for native Copilot journal evidence (issue #7357).

Every journal here is synthetic. Sentinel strings stand in for prompts and
results so a leak into the output is detectable.
"""

from __future__ import annotations

import importlib.util
import io
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


def context_event(kind: str, cwd: object = None, git_root: object = None) -> dict:
    context = {}
    if cwd is not None:
        context["cwd"] = str(cwd)
    if git_root is not None:
        context["gitRoot"] = str(git_root)
    return ev(kind, {"context": context})


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

    code = extract.main(["--project-dir", str(repo), "--journal", str(journal_path)])

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == 0
    assert payload["journal"]["available"] is True
    assert {r["call_id"] for r in payload["journal"]["receipts"]} == {"c1", "c2"}
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

    _assert_unavailable(report, "read cap")
    assert report["records_truncated"] is True
    assert report["records_read"] == 3


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
    doctor = journal_mod._load_doctor()
    assert doctor is not None
    parser = doctor[1]
    assert callable(parser._copilot_events)


# Side effects


def test_extraction_creates_no_toolkit_session_log(repo: Path, journal_path: Path) -> None:
    write_journal(journal_path, basic_rows(repo))

    extract.gather_evidence(repo, "2026-11-09", journal=journal_path)

    assert not (repo / ".project-toolkit").exists()
    assert list(repo.rglob("*session*")) == []


# Scope rule: a context event records one working directory, cwd else gitRoot.


def _available(report: dict) -> bool:
    return report["available"] is True and report["reason"] == ""


def test_cwd_inside_with_git_root_equal_to_the_repo_is_in_scope(
    repo: Path, journal_path: Path
) -> None:
    rows = [context_event("session.start", repo, repo), start("c1"), complete("c1")]
    write_journal(journal_path, rows)

    assert _available(journal_mod.extract_receipts(journal_path, repo))


def test_cwd_in_a_subdirectory_is_in_scope_when_project_dir_is_that_subdirectory(
    repo: Path, journal_path: Path
) -> None:
    sub = repo / "pkg"
    sub.mkdir()
    rows = [context_event("session.start", sub, repo), start("c1"), complete("c1")]
    write_journal(journal_path, rows)

    assert _available(journal_mod.extract_receipts(journal_path, sub))


def test_cwd_outside_is_out_of_scope_even_when_git_root_is_inside(
    repo: Path, tmp_path: Path, journal_path: Path
) -> None:
    rows = [context_event("session.start", tmp_path, repo), start("c1"), complete("c1")]
    write_journal(journal_path, rows)

    _assert_unavailable(journal_mod.extract_receipts(journal_path, repo), "outside the repository")


def test_git_root_elsewhere_does_not_override_a_cwd_inside(
    repo: Path, tmp_path: Path, journal_path: Path
) -> None:
    elsewhere = (tmp_path / "elsewhere").resolve()
    elsewhere.mkdir()
    rows = [context_event("session.start", repo, elsewhere), start("c1"), complete("c1")]
    write_journal(journal_path, rows)

    assert _available(journal_mod.extract_receipts(journal_path, repo))


def test_git_root_is_the_directory_only_when_cwd_is_absent(
    repo: Path, tmp_path: Path, journal_path: Path
) -> None:
    inside = write_journal(
        journal_path, [context_event("session.start", None, repo), start("c1"), complete("c1")]
    )
    outside = write_journal(
        tmp_path / "second" / "events.jsonl",
        [context_event("session.start", None, tmp_path), start("c1"), complete("c1")],
    )

    assert _available(journal_mod.extract_receipts(inside, repo))
    _assert_unavailable(journal_mod.extract_receipts(outside, repo), "outside the repository")


@pytest.mark.parametrize(
    "data",
    [
        {"context": {"cwd": "/a", "gitRoot": "/b"}},
        {"context": {"gitRoot": "/b"}},
        {"context": {"cwd": "", "gitRoot": "/b"}},
        {"context": {"cwd": 7, "gitRoot": "/b"}},
        {"context": {}},
        {"context": "not-a-dict"},
        {"cwd": "/a", "gitRoot": "/b"},
    ],
)
def test_recorded_cwd_matches_skill_doctor(data: dict) -> None:
    parser = journal_mod._load_doctor()[1]
    meta = {"cwd": None, "cwd_history": [], "started_at": None}

    parser._copilot_context(meta, data, None)

    assert journal_mod._recorded_cwd(data) == meta["cwd"]


# Call identity: matching uses the full id, display uses a bounded one.


def test_call_ids_sharing_a_long_prefix_stay_two_calls(repo: Path, journal_path: Path) -> None:
    prefix = "x" * (journal_mod._MAX_FIELD_CHARS + 10)
    first, second = prefix + "-first", prefix + "-second"
    rows = [
        session_start(repo),
        start(first),
        start(second),
        complete(first, True),
        complete(second, False),
    ]
    write_journal(journal_path, rows)

    report = journal_mod.extract_receipts(journal_path, repo)

    assert [r["outcome"] for r in report["receipts"]] == ["succeeded", "failed"]
    assert all(len(r["call_id"]) <= journal_mod._MAX_FIELD_CHARS for r in report["receipts"])
    assert report["completions_without_retained_start"] == 0


# Read budget: malformed, blank and oversized lines count before decoding.


def test_malformed_lines_count_against_the_line_budget(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal_mod, "MAX_LINES", 5)
    write_journal(journal_path, [session_start(repo), *["{bad"] * 20])

    report = journal_mod.extract_receipts(journal_path, repo)

    _assert_unavailable(report, "read cap")
    assert report["lines_read"] == 5
    assert report["records_truncated"] is True
    assert report["malformed_lines"] == 4


def test_a_journal_exactly_at_the_line_budget_is_not_truncated(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal_mod, "MAX_LINES", 3)
    write_journal(journal_path, [session_start(repo), start("c1"), complete("c1")])

    report = journal_mod.extract_receipts(journal_path, repo)

    assert _available(report)
    assert report["lines_read"] == 3
    assert report["records_truncated"] is False


def test_a_line_over_the_length_cap_is_skipped_and_reading_continues(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal_mod, "MAX_LINE_CHARS", 200)
    huge = json.dumps(start("huge", "bash", {"command": "y" * 5000}))
    write_journal(journal_path, [session_start(repo), huge, start("c1"), complete("c1")])

    report = journal_mod.extract_receipts(journal_path, repo)

    assert _available(report)
    assert report["oversized_lines"] == 1
    assert [r["call_id"] for r in report["receipts"]] == ["c1"]


def test_a_line_exactly_at_the_length_cap_is_still_parsed(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = start("c1", arguments={"pad": ""})
    pad = 300 - len(json.dumps(row))
    row = start("c1", arguments={"pad": "p" * pad})
    assert len(json.dumps(row)) == 300
    monkeypatch.setattr(journal_mod, "MAX_LINE_CHARS", 300)
    write_journal(journal_path, [session_start(repo), row, complete("c1")])

    report = journal_mod.extract_receipts(journal_path, repo)

    assert _available(report)
    assert report["oversized_lines"] == 0


def test_deeply_nested_json_is_counted_malformed_not_a_crash(
    repo: Path, journal_path: Path
) -> None:
    deep = "[" * 200_000 + "]" * 200_000
    write_journal(journal_path, [session_start(repo), deep, start("c1"), complete("c1")])

    report = journal_mod.extract_receipts(journal_path, repo)

    assert _available(report)
    assert report["malformed_lines"] == 1


# Truncation and read failures never read as complete.


def test_record_cap_before_an_outside_context_change_is_not_in_scope(
    repo: Path, tmp_path: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = context_event("session.context_changed", tmp_path)
    write_journal(journal_path, [session_start(repo), start("c1"), complete("c1"), moved])

    full = journal_mod.extract_receipts(journal_path, repo)
    monkeypatch.setattr(journal_mod, "MAX_RECORDS", 3)
    capped = journal_mod.extract_receipts(journal_path, repo)

    _assert_unavailable(full, "outside the repository")
    _assert_unavailable(capped, "read cap")


class _FailingStream(io.StringIO):
    """Serve the first lines, then fail the way a dropped disk or share does."""

    def readline(self, size: int = -1) -> str:
        line = super().readline(size)
        if not line:
            raise OSError(5, "Input/output error")
        return line


def test_read_failure_after_valid_events_is_unavailable(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_journal(journal_path, [session_start(repo), start("c1"), complete("c1")])
    real_open = Path.open
    target = journal_path.resolve()
    text = journal_path.read_text(encoding="utf-8")

    def flaky_open(self: Path, *args: object, **kwargs: object):
        if self == target:
            return _FailingStream(text)
        return real_open(self, *args, **kwargs)

    control = journal_mod.extract_receipts(journal_path, repo)
    monkeypatch.setattr(Path, "open", flaky_open)
    failed = journal_mod.extract_receipts(journal_path, repo)

    assert _available(control)
    _assert_unavailable(failed, "read failed: OSError")
    assert failed["records_read"] == 3
