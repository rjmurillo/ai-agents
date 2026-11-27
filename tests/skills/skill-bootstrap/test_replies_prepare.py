"""prepare subcommand: window, limit, classification, sampling, privacy. Synthetic data only."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from replies_helpers import (
    BEFORE,
    CONTROL_TOKEN,
    LONG_PROMPT,
    api_error,
    assistant_text,
    assistant_tool,
    evidence_rows,
    plant_control,
    prepare_args,
    prepare_ok,
    replies_prepare,
    run_cli,
    simple_session,
    tool_result,
    ts,
    user,
    write_child,
    write_session,
)

NARRATION = "synthetic narration before the tool call"
FINAL = "synthetic final answer after the tool boundary"


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "proj-a"


def test_final_reply_follows_tool_boundary_and_narration_is_dropped(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recs = [user("synthetic opening prompt, unique wording beta", 1)]
    recs += [assistant_tool(2, narration=NARRATION), tool_result(3), assistant_text(FINAL, 4)]
    write_session(store, "main-a", recs)
    plant_control(store)
    run_dir = tmp_path / "run"
    payload, out = prepare_ok(capsys, store, run_dir)
    texts = [r["reply"] for r in evidence_rows(run_dir)]
    assert FINAL in texts
    assert not any(NARRATION in t for t in texts)
    assert payload["replies"]["by_kind"]["final_reply"]["total"] == 2
    assert FINAL not in out and CONTROL_TOKEN not in out


def test_window_before_is_exclusive_and_since_is_inclusive(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(
        store, "early", simple_session("synthetic early prompt wording gamma", ["EARLY reply"], 10)
    )
    write_session(
        store,
        "late",
        simple_session("synthetic late prompt wording delta", ["LATE reply"], 60 * 24 * 40),
    )
    plant_control(store, start=60)
    run_dir = tmp_path / "run"
    payload, _ = prepare_ok(capsys, store, run_dir, "--since", ts(30))
    texts = " ".join(r["reply"] for r in evidence_rows(run_dir))
    assert "EARLY" not in texts and "LATE" not in texts
    assert payload["population"]["excluded"]["outside_window"] == 2


def test_exclude_session_drops_parent_and_children(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(
        store,
        "skipme",
        simple_session("synthetic skip prompt wording epsilon", ["SKIPPED reply"], 10),
    )
    child = [user("synthetic delegated task", 11), assistant_text("SKIPPED child handback", 12)]
    write_child(store, "skipme", "agent-1", child)
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run", "--exclude-session", "skipme")
    assert payload["population"]["excluded"]["session_flag"] == 2
    assert "SKIPPED" not in " ".join(r["reply"] for r in evidence_rows(tmp_path / "run"))


def test_limit_counts_children_and_keeps_newest(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(
        store, "old", simple_session("synthetic old prompt wording zeta", ["OLD reply"], 10)
    )
    child = [user("synthetic delegated task", 11), assistant_text("OLD child handback", 12)]
    write_child(store, "old", "agent-1", child)
    plant_control(store, start=500)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run", "--limit", "1")
    assert payload["population"]["found"] == {"main": 2, "child": 1}
    assert payload["population"]["excluded"]["limit"] == 2
    assert payload["population"]["used"] == {"main": 1, "children": 0}


def test_subagent_handback_kind_and_meta_count(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(
        store, "main-a", simple_session("synthetic parent prompt wording eta", ["parent reply"], 10)
    )
    child = [
        user("synthetic delegated task", 11, isSidechain=True),
        assistant_text("HANDBACK text", 12, isSidechain=True),
    ]
    write_child(store, "main-a", "agent-1", child, meta="synthetic-type")
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    kinds = payload["replies"]["by_kind"]
    assert kinds["subagent_handback"]["total"] == 1
    assert payload["subagent_meta"] == {"synthetic-type": 1}
    assert payload["machine"]["delegated_prompt"] == 1


def test_errors_and_host_continues_are_counted_separately_from_replies(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recs = [
        user("synthetic prompt for error span wording theta", 1),
        assistant_tool(2),
        api_error(3),
    ]
    recs += [
        user("Continue where you left off.", 4),
        assistant_tool(5),
        tool_result(6, is_error=True),
    ]
    recs += [user("synthetic typed message after the tool failure", 7)]
    write_session(store, "main-a", recs)
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert payload["errors"] == {"api": 1, "tool": 1}
    assert payload["errors_then_host_continue"] == 1
    assert payload["host_continues"] == 1
    assert payload["replies"]["by_kind"]["final_reply"]["total"] == 1


def test_machine_turns_are_not_human(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recs = [user("synthetic prompt wording iota for machine test", 1)]
    recs += [user("<task-notification>x</task-notification>", 2), user("meta text", 3, isMeta=True)]
    recs += [user("summary text", 4, isCompactSummary=True), assistant_text("a reply", 5)]
    write_session(store, "main-a", recs)
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert payload["machine"] == {"notice": 1, "meta": 1, "compact_summary": 1}
    assert payload["turns"]["human"] == 2


def test_relayed_turns_are_machine_and_never_a_typed_followup(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recs = [user("synthetic prompt wording kappa for relay test", 1), assistant_text("one", 2)]
    recs += [user("<relay>status ping</relay>", 3), assistant_text("two", 4)]
    recs += [user("Relay note: synthetic update", 5), assistant_text("three", 6)]
    recs += [user("a typed synthetic follow-up", 7), assistant_text("four", 8)]
    write_session(store, "main-a", recs)
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run", "--machine-turn", "Relay note:")
    rows = evidence_rows(tmp_path / "run")
    assert payload["machine"] == {"relay": 2}
    assert payload["turns"]["typed_followup"] == 1
    assert payload["examined"] == 2
    texts = [row["next_human"] for row in rows if row["next_human"]]
    assert texts == ["a typed synthetic follow-up"]


def test_an_unlisted_relay_opener_stays_a_typed_followup(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recs = [user("synthetic prompt wording lambda for relay test", 1), assistant_text("one", 2)]
    recs += [user("Relay note: synthetic update", 3), assistant_text("two", 4)]
    write_session(store, "main-a", recs)
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert "relay" not in payload["machine"]
    assert payload["turns"]["typed_followup"] == 1


def test_bad_machine_turn_pattern_is_a_config_error(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plant_control(store)
    args = prepare_args(store, tmp_path / "run", "--machine-turn", "(")
    code, payload, _ = run_cli(capsys, args)
    assert (code, payload["message"]) == (2, "bad_machine_turn")
    assert not (tmp_path / "run").exists()


def test_eval_replay_sessions_and_children_are_excluded(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for number in range(3):
        write_session(
            store, f"replay-{number}", simple_session(LONG_PROMPT, ["REPLAY reply"], 10 + number)
        )
    write_child(
        store, "replay-0", "agent-1", [user("task", 11), assistant_text("REPLAY child", 12)]
    )
    write_session(
        store, "marked", simple_session("[eval] synthetic marked prompt", ["MARKED reply"], 20)
    )
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    excluded = payload["population"]["excluded"]
    assert excluded["eval_replay"] == 4 and excluded["eval_replay_children"] == 1
    assert "REPLAY" not in " ".join(r["reply"] for r in evidence_rows(tmp_path / "run"))


def test_prior_authority_is_distinct_from_generic_nudge(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recs = [user("synthetic prompt wording kappa for authority", 1), assistant_text("reply one", 2)]
    recs += [user("continue", 3), assistant_text("reply two", 4)]
    recs += [user("you already have my approval, go ahead", 5), assistant_text("reply three", 6)]
    write_session(store, "main-a", recs)
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert payload["authority"] == {"prior_authority": 1, "generic_nudge": 1}


def test_sampling_is_seeded_and_strata_are_capped(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for number in range(12):
        reply = (
            f"Want me to continue {number}? Let me know."
            if number % 2
            else f"Plain finished statement {number}."
        )
        write_session(
            store,
            f"s{number}",
            simple_session(f"synthetic unique prompt {number} lambda", [reply], 10 + number),
        )
    plant_control(store)
    small = ("--sample-per-kind", "3")
    first, _ = prepare_ok(capsys, store, tmp_path / "r1", *small, "--seed", "5", evidence=False)
    again, _ = prepare_ok(capsys, store, tmp_path / "r2", *small, "--seed", "5", evidence=False)
    other, _ = prepare_ok(capsys, store, tmp_path / "r3", *small, "--seed", "6", evidence=False)
    assert first["evidence_sha256"] == again["evidence_sha256"]
    assert first["evidence_sha256"] != other["evidence_sha256"]
    rows = evidence_rows(tmp_path / "r1")
    assert (
        sum(1 for r in rows if r["flagged"]) == 4 and sum(1 for r in rows if not r["flagged"]) == 3
    )
    strata = {(s["kind"], s["flagged"]): s["population"] for s in first["strata"]}
    assert strata == {("final_reply", True): 6, ("final_reply", False): 6}
    assert first["controls_sampled"] == 1


def test_multiple_explicit_stores_are_combined(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one, two = tmp_path / "projects" / "one", tmp_path / "projects" / "two"
    write_session(one, "a", simple_session("synthetic prompt wording mu one", ["reply a"], 10))
    write_session(two, "b", simple_session("synthetic prompt wording nu two", ["reply b"], 11))
    plant_control(two)
    payload, _ = prepare_ok(capsys, [one, two], tmp_path / "run")
    assert payload["population"]["stores"] == 2
    assert payload["population"]["used"]["main"] == 3


def test_run_dir_is_private_and_stdout_holds_no_text(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main-a", simple_session("synthetic prompt wording xi", [FINAL], 10))
    plant_control(store)
    run_dir = tmp_path / "run"
    _, out = prepare_ok(capsys, store, run_dir)
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    for name in os.listdir(run_dir):
        assert stat.S_IMODE((run_dir / name).stat().st_mode) == 0o600
    for fragment in (FINAL, CONTROL_TOKEN, "synthetic prompt wording", "main-a", str(store)):
        assert fragment not in out


def test_run_dir_refusals(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    plant_control(store)
    existing = tmp_path / "exists"
    existing.mkdir()
    code, payload, _ = run_cli(capsys, prepare_args(store, existing))
    assert (code, payload["message"]) == (2, "run_dir_exists")
    code, payload, _ = run_cli(capsys, prepare_args(store, store / "run"))
    assert (code, payload["message"]) == (2, "run_dir_inside_source_or_repo")
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    code, payload, _ = run_cli(capsys, prepare_args(store, repo / "run"))
    assert (code, payload["message"]) == (2, "run_dir_inside_source_or_repo")
    code, payload, _ = run_cli(capsys, prepare_args(store, tmp_path / "missing-parent" / "run"))
    assert (code, payload["message"]) == (2, "run_dir_parent_missing")
    code, _, _ = run_cli(capsys, prepare_args(store, tmp_path / "fine"))
    assert code == 0


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--since", "not-a-time"], "bad_since"),
        (["--since", BEFORE], "since_not_before_before"),
        (["--limit", "0"], "bad_numeric_option"),
        (["--replay-min", "1"], "bad_numeric_option"),
        (["--marker", "("], "bad_marker"),
    ],
)
def test_option_validation(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], message: str
) -> None:
    plant_control(store)
    code, payload, _ = run_cli(capsys, prepare_args(store, tmp_path / "run", *extra))
    assert (code, payload["message"]) == (2, message)
    assert not (tmp_path / "run").exists()
    prepare_ok(capsys, store, tmp_path / "control-run")


def test_store_validation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "projects"
    plant_control(root / "proj-a")
    empty = tmp_path / "empty"
    empty.mkdir()
    cases = [
        (root, "store_looks_like_root"),
        (empty, "store_has_no_sessions"),
        (tmp_path / "nope", "store_not_a_directory"),
    ]
    for target, message in cases:
        code, payload, _ = run_cli(capsys, prepare_args(target, tmp_path / f"run-{message}"))
        assert (code, payload["message"]) == (2, message)
    prepare_ok(capsys, root / "proj-a", tmp_path / "control-run")


def test_bad_lines_symlinks_and_oversize_are_counted_not_read(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    plant_control(store)
    broken = write_session(
        store, "broken", simple_session("synthetic prompt wording omicron", ["reply"], 10)
    )
    broken.write_text(
        broken.read_text(encoding="utf-8") + '{"type": "user", broken\n', encoding="utf-8"
    )
    link = store / "linked.jsonl"
    try:
        link.symlink_to(broken)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert payload["population"]["parse_errors"] == 1
    assert payload["population"]["found"]["main"] == 2
    monkeypatch.setattr(replies_prepare, "MAX_FILE_BYTES", 10)
    code, payload, _ = run_cli(capsys, prepare_args(store, tmp_path / "run2"))
    assert (code, payload["message"]) == (2, "no_replies_in_population")


def test_empty_population_is_a_config_error_and_creates_nothing(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main-a", [user("synthetic prompt wording pi, no reply", 10)])
    code, payload, _ = run_cli(capsys, prepare_args(store, tmp_path / "run"))
    assert (code, payload["message"]) == (2, "no_replies_in_population")
    assert not (tmp_path / "run").exists()
    plant_control(store)
    prepare_ok(capsys, store, tmp_path / "control-run")


def test_client_and_machine_opener_filters_exclude_children(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plant_control(store)
    write_session(
        store,
        "interactive",
        [user("ordinary work", 1, entrypoint="cli"), assistant_text("done", 2)],
    )
    write_session(
        store,
        "batch",
        [user("automated work", 3, entrypoint="sdk"), assistant_text("batch reply", 4)],
    )
    write_child(store, "batch", "agent-1", [user("work", 4), assistant_text("child reply", 5)])
    write_session(
        store, "probe", [user("Probe: fake", 6, entrypoint="cli"), assistant_text("probe reply", 7)]
    )
    payload, _ = prepare_ok(
        capsys,
        store,
        tmp_path / "run",
        "--entrypoint",
        "cli",
        "--entrypoint",
        "unknown",
        "--machine-first",
        "Probe:",
    )
    assert payload["population"]["used"] == {"main": 2, "children": 0}
    excluded = payload["population"]["excluded"]
    assert (
        excluded["entrypoint"] == excluded["entrypoint_children"] == excluded["machine_opener"] == 1
    )


def test_missing_control_refuses_run(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main", simple_session("ordinary work", ["plain reply"], 1))
    run_dir = tmp_path / "run"
    code, payload, _ = run_cli(capsys, prepare_args(store, run_dir))
    assert (code, payload["message"]) == (2, "control_not_found")
    assert not run_dir.exists()


def test_last_message_id_and_cutoff_limit_evidence(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plant_control(store)

    def fragment(text: str, at: int, mid: str) -> dict:
        record = assistant_text(text, at)
        record["message"]["id"] = mid
        return record

    records = [
        user("normal prompt", 1),
        fragment("Narration.", 2, "one"),
        fragment("Final.", 3, "two"),
        fragment("Next sentence.", 4, "two"),
        user("Not in the window.", 180),
    ]
    write_session(store, "main", records)
    run_dir = tmp_path / "run"
    prepare_ok(capsys, store, run_dir, "--before", ts(150))
    row = next(row for row in evidence_rows(run_dir) if "Final." in row["reply"])
    assert row["reply"] == "Final.\nNext sentence."
    assert row["next_human"] is None
