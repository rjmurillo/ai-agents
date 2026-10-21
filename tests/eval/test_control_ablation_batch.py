"""Tests for control-ablation batch bookkeeping: spend cap, env, redaction, provenance (#6814)."""

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
    HistoryRepo,
    history_tasks,
    live_args,
    make_history_repo,
    tool_use,
)
from tests.eval._control_ablation_test_support import (
    FakeClaudeRunner,
    ablation,
    ablation_tasks,
    claude_run,
    cli,
)

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _control_ablation_batch as batch  # noqa: E402

MINUS_VOICE = "minus:.claude/rules/voice.md"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HistoryRepo:
    built = make_history_repo(tmp_path / "repo")
    monkeypatch.setattr(
        ablation,
        "always_loaded",
        lambda _root, _exclusions: {"claude_code": {"files": sorted(CONTROL_FILES)}},
    )
    return built


@pytest.fixture
def live_repo(repo: HistoryRepo, monkeypatch: pytest.MonkeyPatch) -> HistoryRepo:
    monkeypatch.setattr(cli, "REPO_ROOT", repo.root)
    return repo


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
    events = [{"message": {"content": [tool_use("Read", file_path=f"{marker}\\x.py")]}}]

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
    runner = FakeClaudeRunner(history_tasks(live_repo))

    code = cli.main(live_args(live_repo, tmp_path, "--max-cost-usd", cap), runner=runner)

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


def test_secret_literals_include_the_claude_auth_runtime_env_forwards() -> None:
    environ = {"ANTHROPIC_API_KEY": "key-abcdefghijk", "CLAUDE_CODE_OAUTH_TOKEN": "oauth-1234567"}

    literals = batch.secret_literals([], environ)

    assert {"key-abcdefghijk", "oauth-1234567"} <= set(literals)


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
    fake = FakeClaudeRunner(history_tasks(live_repo), reply="I ran echo tok-SECRET-1234567890")
    args = live_args(live_repo, tmp_path, "--controls", "full", "--pass-env", "EVAL_TEST_LOGIN")

    assert cli.main(args, runner=fake) == cli.EXIT_OK

    out = tmp_path / "out"
    texts = [p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file()]
    assert texts and not any("tok-SECRET-1234567890" in text for text in texts)


def test_a_dry_run_leaves_no_base_tree_behind(live_repo: HistoryRepo, tmp_path: Path) -> None:
    code = cli.main(live_args(live_repo, tmp_path, "--dry-run"))

    assert code == cli.EXIT_OK
    assert not list((tmp_path / "ws").glob("_base-*"))
