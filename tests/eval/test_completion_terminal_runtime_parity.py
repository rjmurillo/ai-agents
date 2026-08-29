"""Runtime parity contracts for terminal task completion."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
FIXTURES = REPO_ROOT / "tests" / "evals" / "completion-terminal-runtime-fixtures.json"
SCRIPT = EVAL_DIR / "eval_runtime_parity.py"

spec = importlib.util.spec_from_file_location("completion_runtime_parity", SCRIPT)
assert spec and spec.loader
parity = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = parity
sys.path.insert(0, str(EVAL_DIR))
try:
    spec.loader.exec_module(parity)
finally:
    sys.path.remove(str(EVAL_DIR))
runtime_grader = sys.modules["_runtime_parity_grader"]


def test_controls_discriminate_semantic_tail() -> None:
    for fixture in parity.load_fixtures(FIXTURES):
        positive = parity.score_assertions(
            fixture, fixture.positive.response, fixture.positive.files
        )
        negative = parity.score_assertions(
            fixture, fixture.negative.response, fixture.negative.files
        )

        assert all(result["passed"] for result in positive)
        assert not all(result["passed"] for result in negative)


def test_appended_continuation_tail_mutation_fails() -> None:
    fixture = parity.load_fixtures(FIXTURES)[1]
    response = "Updated the documentation. Checks pass. Should I continue?"

    results = parity.score_assertions(fixture, response, {})

    assert results[0]["actual"] == "reopened"
    assert results[0]["passed"] is False


@pytest.mark.parametrize("harness", ["claude", "copilot"])
def test_instruction_artifact_is_installed_through_project_surface(
    tmp_path: Path,
    harness: str,
) -> None:
    fixture = parity.load_fixtures(FIXTURES)[0]
    workspace = tmp_path / harness

    parity.prepare_workspace(fixture, harness, workspace)

    if harness == "claude":
        installed = workspace / ".claude" / "rules" / "completion-terminal.md"
        source = fixture.claude_instruction
    else:
        installed = (
            workspace
            / ".github"
            / "instructions"
            / "completion-terminal.instructions.md"
        )
        source = fixture.copilot_instruction
        assert not (workspace / ".github" / "copilot-instructions.md").exists()
    assert source is not None
    assert installed.read_bytes() == source.read_bytes()


def test_copilot_enables_custom_instructions_for_instruction_fixture() -> None:
    fixture = parity.load_fixtures(FIXTURES)[0]

    argv = parity.build_argv("copilot", "copilot", parity.DEFAULT_MODEL, fixture)

    assert "--no-custom-instructions" not in argv


def test_dry_run_records_grader_and_instruction_provenance(tmp_path: Path) -> None:
    def version_runner(argv, **kwargs):
        import subprocess

        return subprocess.CompletedProcess(argv, 0, "test-version\n", "")

    report, code = parity.run_evaluation(
        fixtures_path=FIXTURES,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        grader_provider="copilot-cli",
        grader_model="judge-model",
        runner=version_runner,
    )

    assert code == parity.EXIT_OK
    assert report["grader_provider"] == "copilot-cli"
    assert report["grader_model"] == "judge-model"
    fixture = parity.load_fixtures(FIXTURES)[0]
    record = report["fixtures"][0]
    assert record["claude_instruction_sha256"] == hashlib.sha256(
        fixture.claude_instruction.read_bytes()
    ).hexdigest()
    assert record["copilot_instruction_sha256"] == hashlib.sha256(
        fixture.copilot_instruction.read_bytes()
    ).hexdigest()


def test_malformed_semantic_assertion_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    payload["fixtures"][0]["assertions"][0]["value"] = "maybe"
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(parity.ParityConfigError, match="terminal.*reopened"):
        parity.load_fixtures(path)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"verdict":"terminal"}',
        '{"verdict":"unknown","reason":"bad label"}',
    ],
)
def test_malformed_grader_output_fails_closed(raw: str) -> None:
    with pytest.raises(runtime_grader.SemanticGraderError):
        runtime_grader._parse_grade(raw)


def test_unavailable_grader_fails_explicitly(monkeypatch) -> None:
    def unavailable(_name: str):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(runtime_grader, "resolve_provider", unavailable)

    with pytest.raises(
        runtime_grader.SemanticGraderError,
        match="provider unavailable",
    ):
        runtime_grader.make_semantic_tail_grader("missing", "judge-model")
