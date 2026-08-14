"""Report contract tests for runtime parity review fixes."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import (
    FIXTURES,
    parity,
    runtime_parity,
)


def _single_fixture_corpus(tmp_path: Path, fixture_id: str) -> Path:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    payload["fixtures"] = [
        fixture for fixture in payload["fixtures"] if fixture["id"] == fixture_id
    ]
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _version_runner(argv, **kwargs):
    args = [str(value) for value in argv]
    executable = Path(args[0]).name.lower()
    return subprocess.CompletedProcess(args, 0, f"{executable} test-version\n", "")


def test_report_hashes_the_exact_installed_agent_bytes(tmp_path: Path) -> None:
    fixtures_path = _single_fixture_corpus(tmp_path, "resume-phase-3")
    report, code = parity.run_evaluation(
        fixtures_path=fixtures_path,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        runner=_version_runner,
    )
    fixture = parity.load_fixtures(fixtures_path)[0]
    claude_workspace = tmp_path / "claude"
    copilot_workspace = tmp_path / "copilot"
    parity.prepare_workspace(fixture, "claude", claude_workspace)
    parity.prepare_workspace(fixture, "copilot", copilot_workspace)
    record = report["fixtures"][0]

    assert code == parity.EXIT_OK
    assert record["claude_agent_sha256"] == hashlib.sha256(
        (claude_workspace / ".claude" / "agents" / "parity.md").read_bytes()
    ).hexdigest()
    assert record["copilot_agent_sha256"] == hashlib.sha256(
        (
            copilot_workspace / ".github" / "agents" / "parity.agent.md"
        ).read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    "tools",
    [
        [
            {
                "type": "tool_use",
                "name": "AskUserQuestion",
                "input": {
                    "questions": [
                        {
                            "question": "Choose deployment",
                            "options": [
                                {"label": "A) Canary deployment"},
                                {"label": "B) Immediate deployment"},
                            ],
                            "recommendation": "Recommendation: A",
                        }
                    ]
                },
            }
        ],
        [
            {
                "type": "tool.execution_start",
                "data": {
                    "toolName": "ask_user",
                    "arguments": json.dumps(
                        {
                            "question": "Choose deployment",
                            "choices": [
                                "A) Canary deployment",
                                "B) Immediate deployment",
                            ],
                            "recommendation": "Recommendation: A",
                        }
                    ),
                },
            }
        ],
    ],
)
def test_structured_question_payload_is_scoreable(tools) -> None:
    fixture = next(
        fixture
        for fixture in parity.load_fixtures(FIXTURES)
        if fixture.fixture_id == "consequential-choice"
    )

    results = parity.score_assertions(fixture, parity.question_payload(tools), {})

    assert all(result["passed"] for result in results)


def test_structured_question_without_prose_is_scored(
    tmp_path: Path,
) -> None:
    fixtures_path = _single_fixture_corpus(tmp_path, "consequential-choice")
    question = {
        "question": "Choose deployment",
        "options": [
            {"label": "A) Canary deployment"},
            {"label": "B) Immediate deployment"},
        ],
        "recommendation": "Recommendation: A",
    }

    def structured_question_runner(argv, **kwargs):
        args = [str(value) for value in argv]
        executable = Path(args[0]).name.lower()
        if "--version" in args:
            return _version_runner(args)
        if executable.startswith("claude"):
            events = [
                {
                    "type": "system",
                    "subtype": "init",
                    "model": parity.DEFAULT_MODEL,
                },
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "AskUserQuestion",
                                "input": {"questions": [question]},
                            }
                        ]
                    },
                },
                {"type": "result", "result": ""},
            ]
        else:
            events = [
                {
                    "type": "assistant.message",
                    "data": {"content": "", "model": parity.DEFAULT_MODEL},
                },
                {
                    "type": "tool.execution_start",
                    "data": {
                        "toolName": "ask_user",
                        "arguments": question,
                        "model": parity.DEFAULT_MODEL,
                    },
                },
            ]
        return subprocess.CompletedProcess(
            args,
            0,
            "\n".join(json.dumps(event) for event in events) + "\n",
            "",
        )

    report, code = parity.run_evaluation(
        fixtures_path=fixtures_path,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=structured_question_runner,
    )

    record = report["fixtures"][0]
    assert code == parity.EXIT_OK
    assert report["verdict"] == "PASS"
    assert record["claude"]["response"] == ""
    assert record["copilot"]["response"] == ""
    assert record["claude"]["question_mechanism"] == "structured_event"
    assert record["copilot"]["question_mechanism"] == "structured_event"
    assert all(item["passed"] for item in record["claude"]["assertions"])
    assert all(item["passed"] for item in record["copilot"]["assertions"])


def test_question_model_requires_attribution_on_the_question_event() -> None:
    events = [
        {
            "type": "assistant.message",
            "data": {"content": "", "model": parity.DEFAULT_MODEL},
        },
        {
            "type": "tool.execution_start",
            "data": {
                "toolName": "ask_user",
                "arguments": {"question": "Choose A or B"},
            },
        },
    ]

    assert parity.structured_tool_model(events) is None


def test_empty_success_explains_the_fail_closed_result(tmp_path: Path) -> None:
    fixtures_path = _single_fixture_corpus(tmp_path, "resume-phase-3")

    def empty_runner(argv, **kwargs):
        args = [str(value) for value in argv]
        if "--version" in args:
            return _version_runner(args)
        events = [
            {
                "type": "system",
                "subtype": "init",
                "model": parity.DEFAULT_MODEL,
            },
            {"type": "result", "result": ""},
        ]
        return subprocess.CompletedProcess(
            args,
            0,
            "\n".join(json.dumps(event) for event in events) + "\n",
            "",
        )

    report, code = parity.run_evaluation(
        fixtures_path=fixtures_path,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=empty_runner,
    )

    failure = report["fixtures"][0]["claude"]
    assert code == parity.EXIT_EXTERNAL
    assert failure["error"] == "runtime returned no answer"


def test_version_probes_use_isolated_harness_profiles(
    tmp_path: Path, monkeypatch
) -> None:
    fixtures_path = _single_fixture_corpus(tmp_path, "resume-phase-3")
    monkeypatch.setenv("HOME", "/operator/home")
    calls = []

    def recording_runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return _version_runner(argv)

    parity.run_evaluation(
        fixtures_path=fixtures_path,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        runner=recording_runner,
    )

    claude_argv, claude_kwargs = calls[0]
    copilot_argv, copilot_kwargs = calls[1]
    claude_env = claude_kwargs["env"]
    copilot_env = copilot_kwargs["env"]
    assert claude_argv == ["claude", "--version"]
    assert copilot_argv == ["copilot", "--no-auto-update", "--version"]
    assert claude_env["HOME"].startswith(str(tmp_path))
    assert copilot_env["HOME"].startswith(str(tmp_path))
    assert claude_env["CLAUDE_CONFIG_DIR"].startswith(str(tmp_path))
    assert copilot_env["COPILOT_HOME"].startswith(str(tmp_path))
    assert "/operator/home" not in claude_env.values()
    assert "/operator/home" not in copilot_env.values()


def test_git_init_failure_returns_external_exit(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixtures_path = _single_fixture_corpus(tmp_path, "resume-phase-3")

    def fail_git_init(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["git", "init"])

    monkeypatch.setattr(parity, "prepare_workspace", fail_git_init)

    code = parity.main(
        [
            "--fixtures",
            str(fixtures_path),
            "--output",
            str(tmp_path / "run" / "report.json"),
        ],
        runner=_version_runner,
    )

    assert code == parity.EXIT_EXTERNAL
    assert "Error:" in capsys.readouterr().err


def test_nested_frontmatter_name_is_not_rewritten(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "---\nmetadata:\n  name: nested\nname: original\n---\nbody\n",
        encoding="utf-8",
    )
    target = tmp_path / "target.md"

    runtime_parity._install_agent(source, target)

    installed = target.read_text(encoding="utf-8")
    assert "  name: nested" in installed
    assert "\nname: parity\n" in installed


def test_empty_version_probe_fails_closed(tmp_path: Path) -> None:
    def empty_version_runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "", "")

    with pytest.raises(RuntimeError, match="returned no version"):
        parity.probe_version(
            "copilot",
            "copilot",
            tmp_path / "probe",
            empty_version_runner,
            30,
        )


def test_main_rejects_a_different_current_worktree(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)

    code = parity.main(["--dry-run"], runner=_version_runner)

    assert code == parity.EXIT_CONFIG
    assert "current directory is not inside a git worktree" in capsys.readouterr().err


def test_worktree_identity_rejects_a_top_level_outside_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        runtime_parity.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, f"{runtime_parity.REPO_ROOT}\n", ""
        ),
    )

    with pytest.raises(
        runtime_parity.ParityConfigError,
        match="current directory is outside reported worktree",
    ):
        runtime_parity.verify_worktree_identity()


def test_git_init_drops_inherited_repository_context(
    tmp_path: Path, monkeypatch
) -> None:
    for name in runtime_parity.GIT_CONTEXT_VARIABLES:
        monkeypatch.setenv(name, str(runtime_parity.REPO_ROOT))
    calls = []

    def recording_run(argv, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(runtime_parity.subprocess, "run", recording_run)
    fixture = parity.load_fixtures(FIXTURES)[0]

    parity.prepare_workspace(fixture, "claude", tmp_path / "workspace")

    git_env = calls[0]["env"]
    assert all(name not in git_env for name in runtime_parity.GIT_CONTEXT_VARIABLES)


def test_resume_fixture_rejects_prose_before_exact_reply() -> None:
    fixture = parity.load_fixtures(FIXTURES)[0]

    results = parity.score_assertions(
        fixture,
        "Are phases 1 and 2 complete?\nCONTINUE_PHASE_3",
        {},
    )

    assert results[0]["passed"] is False
