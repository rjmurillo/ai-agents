"""Report contract tests for runtime parity review fixes."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import FIXTURES, parity


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
