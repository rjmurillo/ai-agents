"""Tests for scripts/eval/eval_control_ablation.py (REQ-043 AC-2, AC-3, AC-8, AC-11).

The Claude CLI is never invoked for real; `FakeClaudeRunner` plays its part
by applying a task's known control and emitting canned stream-json, the
same shape `tests/eval/test_eval_runtime_parity.py::FakeRunner` uses for
Claude's `--print --output-format stream-json` events. Grading commands
(`git`, `python3`) run for real against `tmp_path`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._control_ablation_test_support import ablation, cli, make_task_document, outcome

DEFAULT_MODEL = cli.DEFAULT_MODEL


class FakeClaudeRunner:
    """Apply one task control's files and emit a matching stream-json result."""

    def __init__(
        self,
        tasks: list[ablation.Task],
        *,
        kind: str = "known_good",
        model: str = DEFAULT_MODEL,
        resolved_model: str | None = None,
        cost: float = 0.01,
        omit_cost: bool = False,
    ) -> None:
        self.by_prompt = {task.prompt: task for task in tasks}
        self.kind = kind
        self.model = model
        self.resolved_model = model if resolved_model is None else resolved_model
        self.cost = cost
        self.omit_cost = omit_cost
        self.calls: list[list[str]] = []

    def __call__(
        self, argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        self.calls.append(args)
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, stdout="2.3.1\n", stderr="")
        prompt = args[args.index("--print") + 1]
        task = self.by_prompt[prompt]
        control = task.controls[self.kind]
        workspace = Path(str(kwargs["cwd"]))
        for relative, content in control.files.items():
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        events: list[dict[str, object]] = [
            {"type": "system", "subtype": "init", "model": self.resolved_model},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": " ".join(task.acceptance)},
                        }
                    ]
                },
            },
        ]
        result_event: dict[str, object] = {
            "type": "result",
            "subtype": "success",
            "result": control.response,
        }
        if not self.omit_cost:
            result_event["total_cost_usd"] = self.cost
        events.append(result_event)
        stdout = "\n".join(json.dumps(event) for event in events) + "\n"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


def _write_tasks(tmp_path: Path) -> Path:
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(make_task_document()), encoding="utf-8")
    return path


def _load(tmp_path: Path) -> list[ablation.Task]:
    return ablation.load_tasks_file(_write_tasks(tmp_path))


# ---------------------------------------------------------------------------
# --dry-run (AC-2)
# ---------------------------------------------------------------------------


def test_dry_run_exits_zero_on_the_valid_five_case_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks_path = _write_tasks(tmp_path)
    code = cli.main(
        [
            "--tasks",
            str(tasks_path),
            "--dry-run",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    assert report["known_good_accepted_durable"] == report["known_good_total"] == 5
    assert report["known_bad_accepted_durable"] == 0


def test_dry_run_exits_one_when_a_known_bad_control_would_be_accepted_durable(
    tmp_path: Path,
) -> None:
    # Break discrimination: known_bad's follow-up file now asserts the same
    # value known_bad itself returns, so it wrongly passes follow-up too.
    document = make_task_document()
    task = document["tasks"][0]
    task["controls"]["known_bad"]["files"] = dict(task["controls"]["known_good"]["files"])
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    code = cli.main(
        [
            "--tasks",
            str(path),
            "--dry-run",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == cli.EXIT_LOGIC


def test_dry_run_does_not_write_records_files(tmp_path: Path) -> None:
    tasks_path = _write_tasks(tmp_path)
    out_dir = tmp_path / "out"
    cli.main(
        [
            "--tasks",
            str(tasks_path),
            "--dry-run",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(out_dir),
        ]
    )
    # AC-11 scopes records-<control>.jsonl to live runs.
    assert not list(out_dir.glob("records-*.jsonl"))
    assert (out_dir / "report.json").is_file()


# ---------------------------------------------------------------------------
# --max-runs (AC-3)
# ---------------------------------------------------------------------------


def test_live_run_refuses_before_any_model_call_when_max_runs_exceeded(tmp_path: Path) -> None:
    tasks = _load(tmp_path)
    runner = FakeClaudeRunner(tasks)
    code = cli.main(
        [
            "--tasks",
            str(_write_tasks(tmp_path)),
            "--controls",
            "full,reduced",
            "--repeats",
            "1",
            "--max-runs",
            "2",  # 5 tasks x 2 controls x 1 repeat = 10 > 2
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        runner=runner,
    )
    assert code == cli.EXIT_CONFIG
    assert runner.calls == []


def test_live_run_proceeds_when_within_max_runs(tmp_path: Path) -> None:
    tasks = _load(tmp_path)
    runner = FakeClaudeRunner(tasks)
    code = cli.main(
        [
            "--tasks",
            str(_write_tasks(tmp_path)),
            "--controls",
            "reduced",
            "--repeats",
            "1",
            "--max-runs",
            "30",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        runner=runner,
    )
    assert code == cli.EXIT_OK
    # One --version probe, plus 5 tasks x 1 control x 1 repeat.
    version_calls = sum(1 for call in runner.calls if "--version" in call)
    assert version_calls == 1
    assert len(runner.calls) - version_calls == 5


# ---------------------------------------------------------------------------
# Live run happy path and AC-11
# ---------------------------------------------------------------------------


def test_live_run_writes_one_valid_record_per_control_file(tmp_path: Path) -> None:
    tasks = _load(tmp_path)
    runner = FakeClaudeRunner(tasks)
    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--tasks",
            str(_write_tasks(tmp_path)),
            "--controls",
            "full,reduced",
            "--repeats",
            "1",
            "--max-runs",
            "30",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(out_dir),
        ],
        runner=runner,
    )
    assert code == cli.EXIT_OK
    for control_name in ("full", "reduced"):
        lines = (out_dir / f"records-{control_name}.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 5
        for line in lines:
            record = outcome.parse_record(json.loads(line))
            assert record.config.control == control_name
            assert record.config.harness == "claude"


def test_live_run_argv_is_redacted_in_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tasks = _load(tmp_path)
    runner = FakeClaudeRunner(tasks)
    code = cli.main(
        [
            "--tasks",
            str(_write_tasks(tmp_path)),
            "--controls",
            "reduced",
            "--repeats",
            "1",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        runner=runner,
    )
    assert code == cli.EXIT_OK
    report = json.loads(capsys.readouterr().out)
    for run in report["runs"]:
        argv = run["argv"]
        assert argv[argv.index("--print") + 1] == "<fixture-prompt>"


# ---------------------------------------------------------------------------
# AC-8: harness failures
# ---------------------------------------------------------------------------


def test_live_run_exits_external_when_stream_lacks_total_cost_usd(tmp_path: Path) -> None:
    tasks = _load(tmp_path)
    runner = FakeClaudeRunner(tasks, omit_cost=True)
    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--tasks",
            str(_write_tasks(tmp_path)),
            "--controls",
            "reduced",
            "--repeats",
            "1",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(out_dir),
        ],
        runner=runner,
    )
    assert code == cli.EXIT_EXTERNAL
    records_path = out_dir / "records-reduced.jsonl"
    assert records_path.read_text(encoding="utf-8") == ""


def test_live_run_exits_external_when_resolved_model_differs(tmp_path: Path) -> None:
    tasks = _load(tmp_path)
    runner = FakeClaudeRunner(tasks, resolved_model="claude-opus-5-5")
    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--tasks",
            str(_write_tasks(tmp_path)),
            "--controls",
            "reduced",
            "--repeats",
            "1",
            "--model",
            "claude-sonnet-5",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(out_dir),
        ],
        runner=runner,
    )
    assert code == cli.EXIT_EXTERNAL
    records_path = out_dir / "records-reduced.jsonl"
    assert records_path.read_text(encoding="utf-8") == ""


def test_live_run_harness_failure_on_one_task_does_not_block_the_rest(tmp_path: Path) -> None:
    # Only the first task's prompt triggers a missing-cost failure; the
    # other four should still produce valid records (AC-8 is per run).
    tasks = _load(tmp_path)
    good_runner = FakeClaudeRunner(tasks)
    failing_prompt = tasks[0].prompt

    def mixed_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        if "--print" in args and args[args.index("--print") + 1] == failing_prompt:
            broken = FakeClaudeRunner(tasks, omit_cost=True)
            return broken(argv, **kwargs)
        return good_runner(argv, **kwargs)

    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--tasks",
            str(_write_tasks(tmp_path)),
            "--controls",
            "reduced",
            "--repeats",
            "1",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(out_dir),
        ],
        runner=mixed_runner,
    )
    assert code == cli.EXIT_EXTERNAL
    lines = (out_dir / "records-reduced.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4


# ---------------------------------------------------------------------------
# Config refusals
# ---------------------------------------------------------------------------


def test_main_refuses_an_unknown_control_name(tmp_path: Path) -> None:
    tasks_path = _write_tasks(tmp_path)
    code = cli.main(
        [
            "--tasks",
            str(tasks_path),
            "--controls",
            "bogus",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == cli.EXIT_CONFIG


def test_main_refuses_a_malformed_task_file(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    path.write_text("not json", encoding="utf-8")
    code = cli.main(
        [
            "--tasks",
            str(path),
            "--dry-run",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == cli.EXIT_CONFIG


# ---------------------------------------------------------------------------
# --claude-auth-file
# ---------------------------------------------------------------------------

AUTH_SECRET = '{"claudeAiOauth": {"accessToken": "fixture-secret-7731"}}'


class AuthObservingRunner(FakeClaudeRunner):
    """Record the auth copy's presence and mode while each Claude call runs."""

    def __init__(self, tasks: list[ablation.Task]) -> None:
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
        str(_write_tasks(tmp_path)),
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
    runner = AuthObservingRunner(_load(tmp_path))

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
        runner=AuthObservingRunner(_load(tmp_path)),
    )

    assert code == cli.EXIT_OK
    for path in (tmp_path / "out").iterdir():
        assert "fixture-secret-7731" not in path.read_text(encoding="utf-8")


def test_missing_auth_file_exits_config_before_any_model_call(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(_load(tmp_path))

    code = cli.main(
        _live_args(tmp_path, "--claude-auth-file", str(tmp_path / "absent.json")),
        runner=runner,
    )

    assert code == cli.EXIT_CONFIG
    assert runner.calls == []


def test_no_auth_file_leaves_the_profile_without_credentials(tmp_path: Path) -> None:
    runner = AuthObservingRunner(_load(tmp_path))

    code = cli.main(_live_args(tmp_path), runner=runner)

    assert code == cli.EXIT_OK
    assert all(item == (False, None, None) for item in runner.observed)


def test_live_report_keeps_each_runs_reply(tmp_path: Path) -> None:
    tasks = _load(tmp_path)

    code = cli.main(_live_args(tmp_path), runner=FakeClaudeRunner(tasks))

    assert code == cli.EXIT_OK
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    replies = {run["reply"] for run in report["runs"]}
    assert replies == {task.controls["known_good"].response for task in tasks}
