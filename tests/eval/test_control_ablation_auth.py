"""Tests for `--claude-auth-file` and the live report's reply field (REQ-043)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tests.eval._control_ablation_test_support import (
    FakeClaudeRunner,
    ablation_tasks,
    cli,
    load_tasks,
    write_tasks,
)

# ---------------------------------------------------------------------------
# --claude-auth-file
# ---------------------------------------------------------------------------

FAR_FUTURE_MS = 4_102_444_800_000  # 2100-01-01
AUTH_SECRET = json.dumps(
    {"claudeAiOauth": {"accessToken": "fixture-secret-7731", "expiresAt": FAR_FUTURE_MS}}
)


class AuthObservingRunner(FakeClaudeRunner):
    """Record the auth copy's presence and mode while each Claude call runs."""

    def __init__(self, tasks: list[ablation_tasks.Task]) -> None:
        super().__init__(tasks)
        self.observed: list[tuple[bool, int | None, str | None]] = []

    def __call__(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "--print" in argv:
            env = kwargs["env"]
            assert isinstance(env, dict)
            target = Path(env["CLAUDE_CONFIG_DIR"]) / ".credentials.json"
            exists = target.is_file()
            mode = target.stat().st_mode & 0o777 if exists else None
            content = target.read_text(encoding="utf-8") if exists else None
            self.observed.append((exists, mode, content))
        return super().__call__(argv, **kwargs)


def _live_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--tasks",
        str(write_tasks(tmp_path)),
        "--controls",
        "reduced",
        "--workspace-root",
        str(tmp_path / "ws"),
        "--output-dir",
        str(tmp_path / "out"),
        *extra,
    ]


def test_auth_file_is_present_at_0600_only_during_each_claude_call(tmp_path: Path) -> None:
    auth = tmp_path / "credentials.json"
    auth.write_text(AUTH_SECRET, encoding="utf-8")
    runner = AuthObservingRunner(load_tasks(tmp_path))

    code = cli.main(_live_args(tmp_path, "--claude-auth-file", str(auth)), runner=runner)

    assert code == cli.EXIT_OK
    assert len(runner.observed) == 5
    assert all(item == (True, 0o600, AUTH_SECRET) for item in runner.observed)
    leftovers = list((tmp_path / "ws").rglob(".credentials.json"))
    assert leftovers == []


def test_auth_file_contents_never_reach_the_report(tmp_path: Path) -> None:
    auth = tmp_path / "credentials.json"
    auth.write_text(AUTH_SECRET, encoding="utf-8")

    code = cli.main(
        _live_args(tmp_path, "--claude-auth-file", str(auth)),
        runner=AuthObservingRunner(load_tasks(tmp_path)),
    )

    assert code == cli.EXIT_OK
    for path in (tmp_path / "out").iterdir():
        assert "fixture-secret-7731" not in path.read_text(encoding="utf-8")


def test_missing_auth_file_exits_config_before_any_model_call(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(
        _live_args(tmp_path, "--claude-auth-file", str(tmp_path / "absent.json")),
        runner=runner,
    )

    assert code == cli.EXIT_CONFIG
    assert runner.calls == []


def test_no_auth_file_leaves_the_profile_without_credentials(tmp_path: Path) -> None:
    runner = AuthObservingRunner(load_tasks(tmp_path))

    code = cli.main(_live_args(tmp_path), runner=runner)

    assert code == cli.EXIT_OK
    assert all(item == (False, None, None) for item in runner.observed)


def test_live_report_keeps_each_runs_reply(tmp_path: Path) -> None:
    tasks = load_tasks(tmp_path)

    code = cli.main(_live_args(tmp_path), runner=FakeClaudeRunner(tasks))

    assert code == cli.EXIT_OK
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    replies = {run["reply"] for run in report["runs"]}
    assert replies == {task.controls["known_good"].response for task in tasks}


def _print_calls(runner: FakeClaudeRunner) -> int:
    return sum(1 for call in runner.calls if "--print" in call)


def test_expiring_login_stops_the_batch_before_any_model_call(tmp_path: Path) -> None:
    auth = tmp_path / "credentials.json"
    soon_ms = 1_000  # 1970: already expired
    auth.write_text(json.dumps({"claudeAiOauth": {"expiresAt": soon_ms}}), encoding="utf-8")
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(_live_args(tmp_path, "--claude-auth-file", str(auth)), runner=runner)

    assert code == cli.EXIT_EXTERNAL
    assert _print_calls(runner) == 0
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert len(report["runs"]) == 1
    assert "expires in" in report["runs"][0]["harness_failure"]


def test_login_without_expiry_fails_closed(tmp_path: Path) -> None:
    auth = tmp_path / "credentials.json"
    auth.write_text(json.dumps({"claudeAiOauth": {}}), encoding="utf-8")
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(_live_args(tmp_path, "--claude-auth-file", str(auth)), runner=runner)

    assert code == cli.EXIT_EXTERNAL
    assert _print_calls(runner) == 0


def test_a_reply_that_echoes_the_token_is_redacted(tmp_path: Path) -> None:
    auth = tmp_path / "credentials.json"
    auth.write_text(AUTH_SECRET, encoding="utf-8")
    runner = FakeClaudeRunner(load_tasks(tmp_path), reply="token is fixture-secret-7731")

    code = cli.main(_live_args(tmp_path, "--claude-auth-file", str(auth)), runner=runner)

    assert code == cli.EXIT_OK
    report = (tmp_path / "out" / "report.json").read_text(encoding="utf-8")
    assert "fixture-secret-7731" not in report
    assert "[REDACTED]" in report
