"""An isolated control-ablation run gets the stored Claude login as a token.

Mirrors `test_eval_runtime_parity_isolated_login.py` for the ablation runner:
the login resolves through `_cli_credentials`, `runtime_env` stays login-free,
a missing login stops the run with exit 4 before any workspace exists, and the
token never reaches a recorded reply or patch.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.eval._control_ablation_test_support import (
    FakeClaudeRunner,
    ablation_tasks,
    cli,
    load_tasks,
    write_tasks,
)
from tests.eval._credential_test_support import set_sources
from tests.eval._runtime_parity_test_support import runtime_harness

TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
REAL_HOME_ENV = "EVAL_RUNTIME_REAL_HOME"
DISK_TOKEN = "disk-token-for-ablation-test"


@pytest.fixture(autouse=True)
def _parity_runs_have_a_token() -> None:
    """Override the conftest stub: these tests exercise real resolution."""


@pytest.fixture(autouse=True)
def _isolated_runs_start_without_ambient_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (TOKEN_ENV, "ANTHROPIC_API_KEY", REAL_HOME_ENV):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _disk_login(monkeypatch: pytest.MonkeyPatch) -> None:
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: DISK_TOKEN)


class SpyRunner(FakeClaudeRunner):
    """Record each Claude call's env."""

    def __init__(self, tasks: list[ablation_tasks.Task]) -> None:
        super().__init__(tasks)
        self.envs: list[dict[str, str]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--version" not in [str(a) for a in argv]:
            env = kwargs["env"]
            assert isinstance(env, dict)
            self.envs.append({str(k): str(v) for k, v in env.items()})
        return super().__call__(argv, **kwargs)


def _live_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--tasks",
        str(write_tasks(tmp_path)),
        "--controls",
        "reduced",
        "--only-tasks",
        load_tasks(tmp_path)[0].id,
        "--workspace-root",
        str(tmp_path / "ws"),
        "--output-dir",
        str(tmp_path / "out"),
        *extra,
    ]


def test_isolated_run_carries_the_stored_login_as_a_token(tmp_path: Path) -> None:
    runner = SpyRunner(load_tasks(tmp_path))

    assert cli.main(_live_args(tmp_path), runner=runner) == cli.EXIT_OK

    assert runner.envs[0][TOKEN_ENV] == DISK_TOKEN
    assert runner.envs[0]["CLAUDE_CONFIG_DIR"].endswith(".claude-config")


def test_runtime_env_itself_stays_login_free(tmp_path: Path) -> None:
    assert TOKEN_ENV not in runtime_harness.runtime_env(tmp_path, "claude")


def test_real_home_run_gets_no_token(tmp_path: Path) -> None:
    runner = SpyRunner(load_tasks(tmp_path))
    try:
        code = cli.main(_live_args(tmp_path, "--real-home"), runner=runner)
    finally:
        os.environ.pop(REAL_HOME_ENV, None)

    assert code == cli.EXIT_OK
    assert TOKEN_ENV not in runner.envs[0]


def test_an_exported_api_key_is_left_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-operator-key")
    runner = SpyRunner(load_tasks(tmp_path))

    assert cli.main(_live_args(tmp_path), runner=runner) == cli.EXIT_OK

    assert runner.envs[0]["ANTHROPIC_API_KEY"] == "sk-ant-operator-key"
    assert TOKEN_ENV not in runner.envs[0]


@pytest.mark.parametrize("probe", [True, False])
def test_no_reachable_login_exits_4_before_any_workspace_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], probe: bool
) -> None:
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: None, probe=probe)
    runner = SpyRunner(load_tasks(tmp_path))

    code = cli.main(_live_args(tmp_path), runner=runner)

    assert code == cli.EXIT_AUTH == 4
    assert runner.calls == []
    assert not (tmp_path / "ws").exists()
    assert not (tmp_path / "out").exists()
    assert "Error:" in capsys.readouterr().err


def test_a_missing_login_is_not_needed_for_a_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: None, probe=True)
    # Without --workspace-root the default root is built under `tempfile.gettempdir()`,
    # which can sit under `$HOME` and outside the pytest base temp. The conftest scan
    # cutoff only covers roots inside the base temp, so a global `~/.claude/CLAUDE.md`
    # would fail the run. Put the default root under `tmp_path`, which the cutoff covers.
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    assert cli.main(["--dry-run", "--tasks", str(write_tasks(tmp_path))]) == cli.EXIT_OK


def test_a_missing_login_is_not_needed_under_real_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: None, probe=True)
    runner = SpyRunner(load_tasks(tmp_path))
    try:
        code = cli.main(_live_args(tmp_path, "--real-home"), runner=runner)
    finally:
        os.environ.pop(REAL_HOME_ENV, None)

    assert code == cli.EXIT_OK


def test_invoke_claude_masks_the_token_in_the_reply(tmp_path: Path) -> None:
    task = load_tasks(tmp_path)[0]
    workspace = tmp_path / "w"
    workspace.mkdir()
    runner = FakeClaudeRunner([task], reply=f"env shows {DISK_TOKEN}")

    _events, reply, _cost, _wall, _argv = cli.claude_run.invoke_claude(
        workspace, task, cli.DEFAULT_MODEL, 5.0, runner
    )

    assert DISK_TOKEN not in reply
    assert runtime_harness.TOKEN_MASK in reply


def test_a_token_the_agent_wrote_into_a_file_never_reaches_the_records(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), extra_files={"leak.txt": DISK_TOKEN})

    assert cli.main(_live_args(tmp_path), runner=runner) == cli.EXIT_OK

    written = "".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (tmp_path / "out").rglob("*")
        if path.is_file()
    )
    assert written
    assert DISK_TOKEN not in written
    assert json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
