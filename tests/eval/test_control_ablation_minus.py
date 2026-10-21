"""Tests for the `minus:<path>` control, trajectory evidence, and batch bookkeeping (#6814)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval._control_ablation_history_support import (
    CONTROL_FILES,
    WITHHELD_PATH,
    HistoryRepo,
    make_historical_document,
    make_history_repo,
    write_document,
)
from tests.eval._control_ablation_test_support import (
    FakeClaudeRunner,
    ablation,
    ablation_tasks,
    claude_run,
    cli,
    outcome,
)

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _control_ablation_batch as batch  # noqa: E402
import _control_ablation_history as history  # noqa: E402

VOICE = ".claude/rules/voice.md"
MINUS_VOICE = f"minus:{VOICE}"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HistoryRepo:
    built = make_history_repo(tmp_path / "repo")
    monkeypatch.setattr(
        ablation,
        "always_loaded",
        lambda _root, _exclusions: {"claude_code": {"files": sorted(CONTROL_FILES)}},
    )
    return built


# ---------------------------------------------------------------------------
# minus:<path>
# ---------------------------------------------------------------------------


def test_minus_removes_exactly_the_named_file_and_its_bytes(repo: HistoryRepo) -> None:
    full = ablation.resolve_control("full", repo.root)

    minus = ablation.resolve_control(MINUS_VOICE, repo.root)

    assert set(full.files) - set(minus.files) == {VOICE}
    assert full.context_bytes - minus.context_bytes == len(CONTROL_FILES[VOICE])
    assert minus.name == MINUS_VOICE


@pytest.mark.parametrize(
    "path",
    [
        ".claude/rules/universal.md",
        ".claude/rules/security.md",
        "x/Secret-redaction.md",
        "AGENTS.md",
        "CLAUDE.md",
    ],
)
def test_minus_refuses_a_security_or_permission_file(repo: HistoryRepo, path: str) -> None:
    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="security or permission"):
        ablation.resolve_control(f"minus:{path}", repo.root)


def test_minus_refuses_a_file_the_full_control_does_not_load(repo: HistoryRepo) -> None:
    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="does not load"):
        ablation.resolve_control("minus:calc.py", repo.root)


@pytest.mark.parametrize(
    ("name", "known"),
    [("full", True), ("reduced", True), (MINUS_VOICE, True), ("minus:", False), ("half", False)],
)
def test_is_control_name(name: str, known: bool) -> None:
    assert ablation.is_control_name(name) is known


def test_the_cli_refuses_a_bare_minus_prefix_before_any_model_call(
    repo: HistoryRepo, tmp_path: Path
) -> None:
    runner = FakeClaudeRunner(_tasks(repo))

    code = cli.main(_live_args(repo, tmp_path, "--controls", "full,minus:"), runner=runner)

    assert code == cli.EXIT_CONFIG
    assert runner.calls == []


# ---------------------------------------------------------------------------
# Trajectory evidence
# ---------------------------------------------------------------------------


def _use(name: str, **tool_input: object) -> dict[str, object]:
    return {"type": "tool_use", "name": name, "input": tool_input}


def test_trajectory_separates_test_commands_and_counts_denials() -> None:
    events: list[dict[str, Any]] = [
        {"type": "assistant", "message": {"content": [_use("Bash", command="ls")]}},
        {"type": "assistant", "message": {"content": [_use("Bash", command="python3 -m pytest")]}},
        {"type": "assistant", "message": {"content": [_use("Read", file_path="a.py")]}},
        {"type": "result", "permission_denials": [{"tool_name": "WebFetch"}]},
    ]

    seen = claude_run.trajectory(events)

    assert seen["tool_calls"] == 3
    assert seen["bash_commands"] == ["ls", "python3 -m pytest"]
    assert seen["test_commands"] == ["python3 -m pytest"]
    assert seen["permission_denials"] == 1
    assert seen["withheld_marker_hits"] == []


def test_a_denied_test_command_is_attempted_not_executed() -> None:
    ran = {**_use("Bash", command="python3 -m pytest"), "id": "t1"}
    refused = {**_use("Bash", command="python -m pytest"), "id": "t2"}
    events: list[dict[str, Any]] = [
        {"type": "assistant", "message": {"content": [ran, refused]}},
        {"type": "result", "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t2"}]},
    ]

    seen = claude_run.trajectory(events)

    assert seen["test_commands"] == ["python3 -m pytest"]
    assert seen["denied_test_commands"] == ["python -m pytest"]


def test_trajectory_keeps_other_tool_inputs_clipped_for_a_leak_audit() -> None:
    events = [{"message": {"content": [_use("Write", file_path="a.py", content="x" * 500)]}}]

    inputs = claude_run.trajectory(events)["other_tool_inputs"]

    assert inputs[0]["input"]["file_path"] == "a.py"
    assert len(inputs[0]["input"]["content"]) == 203


def test_trajectory_reports_unknown_denials_as_null_not_zero() -> None:
    assert claude_run.trajectory([{"type": "result"}])["permission_denials"] is None


def test_trajectory_flags_a_tool_call_that_names_a_withheld_marker() -> None:
    events = [{"message": {"content": [_use("Read", file_path=f"/w/{WITHHELD_PATH}")]}}]

    hits = claude_run.trajectory(events, [WITHHELD_PATH, "abc123"])["withheld_marker_hits"]

    assert hits == [f"Read: {WITHHELD_PATH}"]


# ---------------------------------------------------------------------------
# Batch helpers
# ---------------------------------------------------------------------------


def test_records_filename_is_path_safe_for_a_minus_control() -> None:
    assert batch.records_filename(MINUS_VOICE) == "records-minus_.claude_rules_voice.md.jsonl"


def test_parse_pass_env_refuses_an_unset_name() -> None:
    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="MISSING"):
        batch.parse_pass_env("SET,MISSING", {"SET": "1"})


def test_parse_pass_env_without_the_flag_forwards_nothing() -> None:
    assert batch.parse_pass_env(None, {}) == []


def test_child_env_runner_adds_only_the_named_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WANTED", "w")
    monkeypatch.setenv("OTHER", "o")
    seen: dict[str, object] = {}

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    batch.child_env_runner(runner, ["WANTED"], "/venv/bin/python")(["x"], env={"PATH": "/bin"})

    assert seen["env"] == {"PATH": os.pathsep.join(["/venv/bin", "/bin"]), "WANTED": "w"}


def test_child_env_runner_puts_the_interpreter_first_once() -> None:
    seen: dict[str, object] = {}

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    path = os.pathsep.join(["/usr/bin", "/venv/bin"])
    batch.child_env_runner(runner, [], "/venv/bin/python")(["x"], env={"PATH": path})

    assert seen["env"] == {"PATH": os.pathsep.join(["/venv/bin", "/usr/bin"])}


@pytest.mark.parametrize(
    ("economics", "cost"),
    [({"model_cost_usd": 0.5}, 0.5), ({"model_cost_usd": None}, None), ({}, None), (None, None)],
)
def test_record_cost_is_null_when_unreported(economics: object, cost: float | None) -> None:
    assert batch.record_cost({"economics": economics}) == cost


def test_spend_guard_without_a_cap_never_blocks() -> None:
    guard = batch.SpendGuard(None)
    guard.add_failure(claude_run.HarnessFailureError("timed out"))

    assert guard.blocked_reason() is None
    assert guard.unmeasured


@pytest.mark.parametrize(
    "spend",
    [
        lambda g: g.add_failure(claude_run.HarnessFailureError("timed out")),
        lambda g: g.add_failure(OSError("seed failed")),
        lambda g: g.add_record({"economics": {}}),
    ],
)
def test_spend_guard_fails_closed_once_a_cost_is_unmeasured(spend: Any) -> None:
    guard = batch.SpendGuard(25.0)

    spend(guard)

    assert "unmeasured" in str(guard.blocked_reason())


def test_spend_guard_counts_a_failed_launchs_reported_cost() -> None:
    guard = batch.SpendGuard(1.0)

    guard.add_failure(claude_run.HarnessFailureError("exit 1", cost_usd=1.25))

    assert guard.spent == 1.25
    assert str(guard.blocked_reason()).startswith("spend cap reached")


@pytest.mark.parametrize("name", ["HOME", "CLAUDE_CONFIG_DIR", "PATH", "XDG_CONFIG_HOME"])
def test_parse_pass_env_refuses_a_harness_owned_name(name: str) -> None:
    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="harness-owned"):
        batch.parse_pass_env(name, {name: "x"})


def test_runner_state_reports_a_dirty_tree_and_hashes_its_diff(repo: HistoryRepo) -> None:
    clean = batch.runner_state(repo.root)
    (repo.root / "calc.py").write_text("changed\n", encoding="utf-8")

    dirty = batch.runner_state(repo.root)

    assert clean == {
        "runner_commit": repo.fix_sha,
        "runner_tree_dirty": False,
        "runner_diff_sha256": None,
    }
    assert dirty["runner_tree_dirty"] is True
    assert isinstance(dirty["runner_diff_sha256"], str)


def test_runner_state_is_null_outside_a_repository(tmp_path: Path) -> None:
    assert batch.runner_state(tmp_path) == {
        "runner_commit": None,
        "runner_tree_dirty": None,
        "runner_diff_sha256": None,
    }


def test_remove_cell_deletes_the_workspace_and_its_siblings(tmp_path: Path) -> None:
    cell = tmp_path / "cell"
    for path in (cell, tmp_path / "cell.review", tmp_path / "cell.claude-config"):
        (path / "f").mkdir(parents=True)

    batch.remove_cell(cell)

    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Live CLI on a historical task (fake Claude)
# ---------------------------------------------------------------------------


def _tasks(repo: HistoryRepo) -> list[ablation_tasks.Task]:
    document = make_historical_document(repo)
    return history.load_historical_tasks(document, repo.root, sys.executable).tasks


def _live_args(repo: HistoryRepo, tmp_path: Path, *extra: str) -> list[str]:
    tasks_file = write_document(tmp_path / "tasks.json", make_historical_document(repo))
    return [
        "--tasks",
        str(tasks_file),
        "--workspace-root",
        str(tmp_path / "ws"),
        "--output-dir",
        str(tmp_path / "out"),
        *extra,
    ]


@pytest.fixture
def live_repo(repo: HistoryRepo, monkeypatch: pytest.MonkeyPatch) -> HistoryRepo:
    monkeypatch.setattr(cli, "REPO_ROOT", repo.root)
    return repo


def test_a_historical_live_run_records_both_arms_with_checks_and_provenance(
    live_repo: HistoryRepo, tmp_path: Path
) -> None:
    runner = FakeClaudeRunner(_tasks(live_repo), kind="known_good")

    code = cli.main(
        _live_args(live_repo, tmp_path, "--controls", f"full,{MINUS_VOICE}"), runner=runner
    )

    assert code == cli.EXIT_OK
    out = tmp_path / "out"
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    for name in ("full", MINUS_VOICE):
        lines = (out / batch.records_filename(name)).read_text(encoding="utf-8").splitlines()
        assert [outcome.parse_record(json.loads(line)).config.control for line in lines] == [name]
    run = report["runs"][0]
    assert run["checks"]["followup"]["exit_code"] == 0
    assert run["checks"]["acceptance"]["argv"][0] == sys.executable
    assert run["trajectory"]["test_commands"]
    assert run["trajectory"]["withheld_marker_hits"] == []
    provenance = report["provenance"]
    assert provenance["sources"]["half-odd"]["base_sha"] == live_repo.base_sha
    assert VOICE in provenance["controls"]["full"]["files"]
    assert VOICE not in provenance["controls"][MINUS_VOICE]["files"]
    assert provenance["pass_env"] == []
    assert provenance["agent_path_first"] == str(Path(sys.executable).parent)


def test_no_graded_cell_or_base_tree_is_left_for_a_later_agent_to_read(
    live_repo: HistoryRepo, tmp_path: Path
) -> None:
    listings: list[list[str]] = []
    fake = FakeClaudeRunner(_tasks(live_repo))

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "--version" not in argv:
            listings.append(sorted(p.name for p in (tmp_path / "ws").iterdir()))
        return fake(argv, **kwargs)

    args = _live_args(live_repo, tmp_path, "--controls", f"full,{MINUS_VOICE}", "--repeats", "2")
    assert cli.main(args, runner=runner) == cli.EXIT_OK

    assert len(listings) == 4
    for listing in listings:
        cells = [name for name in listing if name.startswith("half-odd")]
        assert len(cells) <= 2  # the launching cell and its .claude-config profile
        assert not any(name.startswith("_base-") for name in listing)
    assert not [p for p in (tmp_path / "ws").iterdir() if p.name.startswith("half-odd")]


def test_the_known_bad_fix_fails_only_the_withheld_check_in_a_live_run(
    live_repo: HistoryRepo, tmp_path: Path
) -> None:
    runner = FakeClaudeRunner(_tasks(live_repo), kind="known_bad")

    code = cli.main(_live_args(live_repo, tmp_path, "--controls", "full"), runner=runner)

    assert code == cli.EXIT_OK
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    checks = report["runs"][0]["checks"]
    assert checks["acceptance"]["exit_code"] == 0
    assert checks["followup"]["exit_code"] != 0


def test_a_cell_launches_while_spend_is_still_under_the_cap(
    live_repo: HistoryRepo, tmp_path: Path
) -> None:
    runner = FakeClaudeRunner(_tasks(live_repo), cost=0.6)
    args = _live_args(live_repo, tmp_path, "--repeats", "2", "--max-cost-usd", "1.0")

    code = cli.main([*args, "--controls", "full"], runner=runner)

    assert code == cli.EXIT_OK
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert [("skipped" in run) for run in report["runs"]] == [False, False]
    assert report["spent_usd"] == pytest.approx(1.2)


def test_the_spend_cap_skips_the_cell_after_the_cap_is_reached(
    live_repo: HistoryRepo, tmp_path: Path
) -> None:
    runner = FakeClaudeRunner(_tasks(live_repo), cost=1.5)
    args = _live_args(live_repo, tmp_path, "--repeats", "2", "--max-cost-usd", "1.0")

    code = cli.main([*args, "--controls", "full"], runner=runner)

    assert code == cli.EXIT_EXTERNAL
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert "skipped" not in report["runs"][0]
    assert report["runs"][1]["skipped"].startswith("spend cap reached")
    assert report["spent_usd"] == 1.5


def test_a_non_positive_spend_cap_refuses_before_any_model_call(
    live_repo: HistoryRepo, tmp_path: Path
) -> None:
    runner = FakeClaudeRunner(_tasks(live_repo))

    code = cli.main(_live_args(live_repo, tmp_path, "--max-cost-usd", "0"), runner=runner)

    assert code == cli.EXIT_CONFIG
    assert runner.calls == []


def test_pass_env_reaches_the_claude_child_and_only_its_name_reaches_the_report(
    live_repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_TEST_LOGIN", "secret-value")
    envs: list[dict[str, str]] = []
    fake = FakeClaudeRunner(_tasks(live_repo))

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        envs.append(dict(kwargs.get("env") or {}))
        return fake(argv, **kwargs)

    args = _live_args(live_repo, tmp_path, "--controls", "full", "--pass-env", "EVAL_TEST_LOGIN")
    code = cli.main(args, runner=runner)

    assert code == cli.EXIT_OK
    assert all(env.get("EVAL_TEST_LOGIN") == "secret-value" for env in envs)
    python_dir = str(Path(sys.executable).parent)
    assert all(env["PATH"].split(os.pathsep)[0] == python_dir for env in envs)
    text = (tmp_path / "out" / "report.json").read_text(encoding="utf-8")
    assert "EVAL_TEST_LOGIN" in text
    assert "secret-value" not in text


def test_an_unset_pass_env_name_refuses_before_any_model_call(
    live_repo: HistoryRepo, tmp_path: Path
) -> None:
    runner = FakeClaudeRunner(_tasks(live_repo))
    args = _live_args(live_repo, tmp_path, "--pass-env", "EVAL_TEST_UNSET_NAME")

    assert cli.main(args, runner=runner) == cli.EXIT_CONFIG
    assert runner.calls == []


def test_provenance_hashes_the_task_file_as_loaded_not_as_edited_mid_batch(
    live_repo: HistoryRepo, tmp_path: Path
) -> None:
    args = _live_args(live_repo, tmp_path, "--controls", "full")
    tasks_file = Path(args[1])
    loaded = batch.sha256_text(tasks_file.read_text(encoding="utf-8"))
    fake = FakeClaudeRunner(_tasks(live_repo))

    def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        tasks_file.write_text("{}", encoding="utf-8")  # an edit while the batch runs
        return fake(argv, **kwargs)

    assert cli.main(args, runner=runner) == cli.EXIT_OK
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert report["provenance"]["tasks_file_sha256"] == loaded


# ---------------------------------------------------------------------------
# PR #6819 review fixes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "runs_tests"),
    [
        ("python3 -m pytest tests -q", True),
        ("cd w && python -m unittest tests.test_calc", True),
        ("uv run --frozen pytest a.py", True),
        ("python3 - <<'E'\nopen('t.py', 'w').write('import pytest')\nE", False),
        ("python3 - <<'E'\nx = 1\nE\npython3 -m pytest t.py", True),
        ("grep -n pytest tests/eval/t.py", False),
    ],
)
def test_only_a_test_invocation_counts_as_a_test_command(command: str, runs_tests: bool) -> None:
    assert claude_run.is_test_invocation(command) is runs_tests


def test_a_withheld_marker_matches_a_raw_string_json_would_escape() -> None:
    marker = "C:\\repo\\ai-agents"
    events = [{"message": {"content": [_use("Read", file_path=f"{marker}\\x.py")]}}]

    hits = claude_run.trajectory(events, [marker])["withheld_marker_hits"]

    assert hits == [f"Read: {marker}"]


def test_a_resumed_guard_starts_from_the_earlier_spend(tmp_path: Path) -> None:
    (tmp_path / "records-full.jsonl").write_text(
        json.dumps({"economics": {"model_cost_usd": 0.8}}) + "\n", encoding="utf-8"
    )

    guard = batch.SpendGuard.resumed(1.0, tmp_path)

    assert guard.spent == 0.8
    guard.add_record({"economics": {"model_cost_usd": 0.3}})
    assert str(guard.blocked_reason()).startswith("spend cap reached")


def test_a_resumed_guard_keeps_failed_launch_spend_from_the_earlier_report(
    tmp_path: Path,
) -> None:
    (tmp_path / "report.json").write_text(
        json.dumps({"spent_usd": 1.5, "spend_unmeasured": False}), encoding="utf-8"
    )

    assert batch.SpendGuard.resumed(1.0, tmp_path).spent == 1.5


@pytest.mark.parametrize(
    "report", ['{"spent_usd": 0.1, "spend_unmeasured": true}', "{not json", "[]"]
)
def test_a_resumed_guard_stays_blocked_on_unknown_earlier_spend(
    tmp_path: Path, report: str
) -> None:
    (tmp_path / "report.json").write_text(report, encoding="utf-8")

    assert "unmeasured" in str(batch.SpendGuard.resumed(25.0, tmp_path).blocked_reason())


@pytest.mark.parametrize("cap", ["nan", "inf", "-1"])
def test_a_non_finite_or_negative_spend_cap_refuses(
    live_repo: HistoryRepo, tmp_path: Path, cap: str
) -> None:
    runner = FakeClaudeRunner(_tasks(live_repo))

    code = cli.main(_live_args(live_repo, tmp_path, "--max-cost-usd", cap), runner=runner)

    assert code == cli.EXIT_CONFIG
    assert runner.calls == []


def test_runner_state_counts_an_untracked_file_as_dirty(repo: HistoryRepo) -> None:
    (repo.root / "new_module.py").write_text("x = 1\n", encoding="utf-8")

    state = batch.runner_state(repo.root)

    assert state["runner_tree_dirty"] is True
    assert isinstance(state["runner_diff_sha256"], str)


def test_secret_literals_include_a_forwarded_token_files_content(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("tok-SECRET-1234567890\n", encoding="utf-8")

    literals = batch.secret_literals(["TOKEN_FILE"], {"TOKEN_FILE": str(token)})

    assert "tok-SECRET-1234567890" in literals
    assert str(token) in literals


def test_redact_scrubs_literals_everywhere_and_keeps_commit_shas() -> None:
    sha = "a" * 40
    entry = {"reply": "cat tok-SECRET-1234567890", "t": {"cmds": [f"git show {sha}"]}}

    scrubbed = batch.redact(entry, ["tok-SECRET-1234567890"])

    assert "tok-SECRET" not in json.dumps(scrubbed)
    assert sha in json.dumps(scrubbed)


def test_a_forwarded_secret_echoed_by_the_agent_never_reaches_the_report(
    live_repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EVAL_TEST_LOGIN", "tok-SECRET-1234567890")
    fake = FakeClaudeRunner(_tasks(live_repo), reply="I ran echo tok-SECRET-1234567890")
    args = _live_args(live_repo, tmp_path, "--controls", "full", "--pass-env", "EVAL_TEST_LOGIN")

    assert cli.main(args, runner=fake) == cli.EXIT_OK

    out = tmp_path / "out"
    texts = [p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file()]
    assert texts and not any("tok-SECRET-1234567890" in text for text in texts)


def test_a_dry_run_leaves_no_base_tree_behind(live_repo: HistoryRepo, tmp_path: Path) -> None:
    code = cli.main(_live_args(live_repo, tmp_path, "--dry-run"))

    assert code == cli.EXIT_OK
    assert not list((tmp_path / "ws").glob("_base-*"))
