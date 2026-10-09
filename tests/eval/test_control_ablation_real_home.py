"""Tests for the ablation runner's real-HOME mode and its review-thread fixes (issue #5768).

The runner never copies, links, or reads a credential file. `--real-home`
keeps the operator's HOME so the CLI finds its own stored login, and the
report records the ambient-instruction confound.
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
    ablation,
    ablation_tasks,
    cli,
    load_tasks,
    write_tasks,
)

REAL_HOME_ENV = "EVAL_RUNTIME_REAL_HOME"


class EnvSpyRunner(FakeClaudeRunner):
    """Record the env each Claude call received."""

    def __init__(self, tasks: list[ablation_tasks.Task]) -> None:
        super().__init__(tasks)
        self.envs: list[dict[str, str]] = []

    def __call__(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
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


def test_isolated_run_sets_a_sibling_config_dir_and_records_no_confound(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(REAL_HOME_ENV, raising=False)
    runner = EnvSpyRunner(load_tasks(tmp_path))
    assert cli.main(_live_args(tmp_path), runner=runner) == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["real_home"] is False
    assert "confound" not in report
    assert runner.envs[0]["CLAUDE_CONFIG_DIR"].endswith(".claude-config")


def test_real_home_run_leaves_the_config_dir_unset_and_records_the_confound(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(REAL_HOME_ENV, raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    runner = EnvSpyRunner(load_tasks(tmp_path))
    try:
        code = cli.main(_live_args(tmp_path, "--real-home"), runner=runner)
    finally:
        os.environ.pop(REAL_HOME_ENV, None)
    assert code == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["real_home"] is True
    assert "~/.claude" in report["confound"]
    assert "CLAUDE_CONFIG_DIR" not in runner.envs[0]


def test_the_credential_file_flag_no_longer_exists(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(_live_args(tmp_path, "--claude-auth-file", str(tmp_path / "x")))
    assert exc.value.code == 2


def test_record_rows_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('\n{"task_id": "a", "repeat": 0}\n   \n', encoding="utf-8")
    assert list(cli._record_rows(path)) == [{"task_id": "a", "repeat": 0}]


def test_record_rows_refuses_malformed_json_with_the_line_number(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"task_id": "a"}\n{oops\n', encoding="utf-8")
    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="line 2"):
        list(cli._record_rows(path))


def test_full_control_context_bytes_counts_raw_file_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = b"ok\xff\xfe\r\n"
    (tmp_path / "AGENTS.md").write_bytes(raw)
    monkeypatch.setattr(
        ablation,
        "always_loaded",
        lambda _root, _exclusions: {"claude_code": {"files": ["AGENTS.md"]}},
    )
    control = ablation.resolve_full_control(tmp_path)
    assert control.context_bytes == len(raw)


def test_default_workspace_root_is_created_private_and_outside_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The default root comes from `tempfile.mkdtemp`, which follows TMPDIR.
    # Pin it so the result does not depend on where the operator's TMPDIR sits.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    root = cli._resolve_workspace_root(None)
    try:
        assert root.is_dir()
        assert root.stat().st_mode & 0o777 == 0o700
        assert cli.REPO_ROOT not in root.parents
    finally:
        root.rmdir()
