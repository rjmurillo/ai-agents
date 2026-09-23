"""Tests for the semantic grader, instruction install, and ablation (#5404).

Covers spec-5404.md acceptance criteria 1-10: instruction install and the
Copilot refusal, `--harnesses` single-harness mode, `--instructions-ref`
ablation (good and bad ref), the `semantic` assertion loader rules, grader
PASS/FAIL/raise/malformed handling, calibration (control inversion and the
automatic mutant), and every exit code the new surface can produce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import (
    FIXTURES,
    parity,
    runtime_grader,
    runtime_parity,
)

# --- Fixtures and helpers ----------------------------------------------------

# The stock "resume-phase-3" fixture's own control responses (its deterministic
# assertions require these exact strings, see
# scripts/eval/examples/runtime-parity-fixtures.json). Reused here so a
# semantic assertion can be layered on without breaking that fixture's
# existing regex controls.
POSITIVE_RESPONSE = "CONTINUE_PHASE_3"
NEGATIVE_RESPONSE = "RESTART_PHASE_1"


def _semantic_corpus(
    tmp_path: Path,
    *,
    instructions: list[str] | None = None,
    extra_assertions: list[dict] | None = None,
    only_semantic: bool = False,
) -> Path:
    """Build a one-fixture corpus with a semantic assertion for these tests."""
    source = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture = dict(source["fixtures"][0])
    semantic_assertion = {
        "kind": "semantic",
        "rubric": "FAIL if the response invites further work; PASS otherwise.",
    }
    if only_semantic:
        fixture["assertions"] = [semantic_assertion]
    else:
        fixture["assertions"] = [*fixture["assertions"], semantic_assertion]
    if extra_assertions:
        fixture["assertions"] = [*fixture["assertions"], *extra_assertions]
    if instructions is not None:
        fixture["instructions"] = instructions
    path = tmp_path / "fixtures.json"
    path.write_text(
        json.dumps({"schema_version": 1, "fixtures": [fixture]}), encoding="utf-8"
    )
    return path


class FakeGrader:
    """Dispatch PASS/FAIL/malformed/raise from message content."""

    name = "fake-grader"

    def __init__(
        self,
        *,
        raise_on: str | None = None,
        malformed_on: str | None = None,
        fail_on: tuple[str, ...] = (),
        always: str | None = None,
    ) -> None:
        self.raise_on = raise_on
        self.malformed_on = malformed_on
        self.fail_on = fail_on
        self.always = always
        self.system_fingerprint = "fake-fingerprint"
        self.calls: list[str] = []

    def complete(self, *, messages, system="", model, **_kwargs):
        content = messages[0]["content"]
        self.calls.append(content)
        if self.raise_on and self.raise_on in content:
            raise RuntimeError("fake grader transport failure")
        if self.malformed_on and self.malformed_on in content:
            return "not json at all"
        if self.always:
            return json.dumps({"verdict": self.always, "reason": "forced"})
        verdict = "FAIL" if any(needle in content for needle in self.fail_on) else "PASS"
        return json.dumps({"verdict": verdict, "reason": "test"})


def _well_calibrated_grader(**kwargs) -> FakeGrader:
    """A grader that fails the negative control and the automatic mutant."""
    return FakeGrader(
        fail_on=(NEGATIVE_RESPONSE, runtime_grader.MUTANT_TAIL.strip()),
        **kwargs,
    )


# --- T1: fixture loader (AC1, AC5, AC6) --------------------------------------


def test_fixture_loads_instructions_field(tmp_path: Path) -> None:
    corpus = _semantic_corpus(
        tmp_path, instructions=[".claude/rules/voice.md", ".claude/rules/builder-ethos.md"]
    )

    fixtures = runtime_parity.load_fixtures(corpus)

    assert fixtures[0].instructions == (
        ".claude/rules/voice.md",
        ".claude/rules/builder-ethos.md",
    )


def test_instructions_field_rejects_path_escape(tmp_path: Path) -> None:
    corpus = _semantic_corpus(tmp_path, instructions=["../outside.md"])

    with pytest.raises(runtime_parity.ParityConfigError, match="escapes"):
        runtime_parity.load_fixtures(corpus)


def test_semantic_assertion_requires_nonempty_rubric(tmp_path: Path) -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    payload["fixtures"][0]["assertions"].append({"kind": "semantic", "rubric": ""})
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(runtime_parity.ParityConfigError, match="rubric"):
        runtime_parity.load_fixtures(path)


def test_semantic_assertion_requires_a_deterministic_sibling(tmp_path: Path) -> None:
    corpus = _semantic_corpus(tmp_path, only_semantic=True)

    with pytest.raises(runtime_parity.ParityConfigError, match="deterministic"):
        runtime_parity.load_fixtures(corpus)


def test_semantic_assertion_alongside_a_deterministic_control_loads(
    tmp_path: Path,
) -> None:
    corpus = _semantic_corpus(tmp_path)

    fixtures = runtime_parity.load_fixtures(corpus)

    kinds = {spec.kind for spec in fixtures[0].assertions}
    assert "semantic" in kinds
    assert kinds - {"semantic"}


def test_score_assertions_reports_semantic_as_not_run(tmp_path: Path) -> None:
    fixture = runtime_parity.load_fixtures(_semantic_corpus(tmp_path))[0]

    results = runtime_parity.score_assertions(fixture, "any response", {})

    semantic = [r for r in results if r["kind"] == "semantic"]
    assert semantic == [
        {
            "kind": "semantic",
            "path": None,
            "expected": fixture.assertions[-1].rubric,
            "passed": None,
            "status": "not_run",
        }
    ]


def test_control_validation_ignores_semantic_entries(tmp_path: Path) -> None:
    """A fixture whose deterministic assertions discriminate still loads.

    The positive control here does not literally contain the rubric text, so
    if `_validate_controls` folded the semantic `passed: None` into `all()`
    this fixture would fail to load even though its real (deterministic)
    controls behave correctly.
    """
    fixtures = runtime_parity.load_fixtures(_semantic_corpus(tmp_path))

    assert len(fixtures) == 1


# --- T2/T3: instruction install, Copilot refusal, ref resolution ------------


def _any_semantic_fixture(tmp_path: Path, **kwargs):  # returns _runtime_parity.Fixture
    return runtime_parity.load_fixtures(_semantic_corpus(tmp_path, **kwargs))[0]


def test_prepare_workspace_installs_instructions_for_claude(tmp_path: Path) -> None:
    fixture = _any_semantic_fixture(tmp_path)
    workspace = tmp_path / "ws"

    parity.prepare_workspace(
        fixture,
        "claude",
        workspace,
        instructions={"a/b/voice.md": b"voice rule bytes"},
    )

    installed = workspace / ".claude" / "rules" / "voice.md"
    assert installed.read_bytes() == b"voice rule bytes"


def test_prepare_workspace_refuses_copilot_with_instructions(tmp_path: Path) -> None:
    fixture = _any_semantic_fixture(tmp_path)

    with pytest.raises(parity.ParityConfigError, match="Copilot"):
        parity.prepare_workspace(
            fixture,
            "copilot",
            tmp_path / "ws",
            instructions={"voice.md": b"x"},
        )


def test_prepare_workspace_without_instructions_is_unchanged(tmp_path: Path) -> None:
    """No `instructions` kwarg preserves the pre-#5404 call shape and behavior."""
    fixture = runtime_parity.load_fixtures(FIXTURES)[0]

    parity.prepare_workspace(fixture, "copilot", tmp_path / "ws")

    assert not (tmp_path / "ws" / ".claude").exists()


def test_resolve_instructions_reads_the_working_tree(tmp_path: Path) -> None:
    target = runtime_parity.REPO_ROOT / ".claude" / "rules" / "voice.md"
    assert target.is_file()

    resolved = runtime_parity.resolve_instructions([".claude/rules/voice.md"], None)

    assert resolved[".claude/rules/voice.md"] == target.read_bytes()


def test_resolve_instructions_missing_working_tree_file_is_a_config_error() -> None:
    with pytest.raises(runtime_parity.ParityConfigError, match="does not exist"):
        runtime_parity.resolve_instructions(["does/not/exist.md"], None)


def test_resolve_instructions_reads_a_git_ref() -> None:
    resolved = runtime_parity.resolve_instructions(
        [".claude/rules/voice.md"], "HEAD"
    )

    target = runtime_parity.REPO_ROOT / ".claude" / "rules" / "voice.md"
    assert resolved[".claude/rules/voice.md"] == target.read_bytes()


def test_resolve_instructions_rejects_an_unresolvable_ref() -> None:
    with pytest.raises(runtime_parity.ParityConfigError, match="not a resolvable ref"):
        runtime_parity.resolve_ref_sha("this-ref-does-not-exist-5404")


def test_resolve_instructions_rejects_a_path_missing_at_a_good_ref() -> None:
    with pytest.raises(runtime_parity.ParityConfigError, match="could not resolve"):
        runtime_parity.resolve_instructions(["does/not/exist/at/head.md"], "HEAD")


def test_resolve_source_commit_returns_a_sha() -> None:
    sha = runtime_parity.resolve_source_commit()

    assert len(sha) == 40
    assert all(char in "0123456789abcdef" for char in sha)


# --- T4/T5: the grader itself -------------------------------------------------


def test_grade_returns_pass_on_a_pass_verdict() -> None:
    result = runtime_grader.grade(FakeGrader(), "m", "rubric", "prompt", "clean response")

    assert result.verdict == "PASS"
    assert result.provider == "fake-grader"
    assert result.model == "m"


def test_grade_returns_fail_on_a_fail_verdict() -> None:
    result = runtime_grader.grade(
        FakeGrader(fail_on=("bad",)), "m", "rubric", "prompt", "a bad response"
    )

    assert result.verdict == "FAIL"


def test_grade_returns_unavailable_when_the_provider_raises() -> None:
    result = runtime_grader.grade(
        FakeGrader(raise_on="prompt"), "m", "rubric", "prompt", "response"
    )

    assert result.verdict == "UNAVAILABLE"
    assert "fake grader transport failure" in result.reason


def test_grade_returns_unavailable_on_malformed_output() -> None:
    result = runtime_grader.grade(
        FakeGrader(malformed_on="prompt"), "m", "rubric", "prompt", "response"
    )

    assert result.verdict == "UNAVAILABLE"


def test_grade_returns_unavailable_when_verdict_is_not_pass_or_fail() -> None:
    grader = FakeGrader(always="MAYBE")

    result = runtime_grader.grade(grader, "m", "rubric", "prompt", "response")

    assert result.verdict == "UNAVAILABLE"


def test_grade_parses_the_first_json_object_out_of_surrounding_prose() -> None:
    class ProseGrader:
        name = "prose-grader"
        system_fingerprint = None

        def complete(self, *, messages, system="", model, **_kwargs):
            return 'Sure, here it is:\n```json\n{"verdict": "PASS", "reason": "ok"}\n```'

    result = runtime_grader.grade(ProseGrader(), "m", "rubric", "prompt", "response")

    assert result.verdict == "PASS"
    assert result.reason == "ok"


def test_calibrate_grades_positive_negative_and_mutant() -> None:
    fixture = runtime_parity.Fixture(
        fixture_id="f",
        claude_agent=Path(__file__),
        copilot_agent=Path(__file__),
        prompt="prompt",
        setup_files={},
        tools=(),
        assertions=(),
        positive=runtime_parity.Control(response=POSITIVE_RESPONSE, files={}),
        negative=runtime_parity.Control(response=NEGATIVE_RESPONSE, files={}),
    )
    grader = _well_calibrated_grader()

    calibration = runtime_grader.calibrate(grader, "m", "rubric", fixture)

    assert calibration.positive.verdict == "PASS"
    assert calibration.negative.verdict == "FAIL"
    assert calibration.mutant.verdict == "FAIL"
    assert not calibration.unavailable
    assert not calibration.miscalibrated


def test_calibrate_flags_miscalibration_when_negative_control_passes() -> None:
    fixture = runtime_parity.Fixture(
        fixture_id="f",
        claude_agent=Path(__file__),
        copilot_agent=Path(__file__),
        prompt="prompt",
        setup_files={},
        tools=(),
        assertions=(),
        positive=runtime_parity.Control(response=POSITIVE_RESPONSE, files={}),
        negative=runtime_parity.Control(response=NEGATIVE_RESPONSE, files={}),
    )
    always_pass = FakeGrader()  # never fails anything: inverted control

    calibration = runtime_grader.calibrate(always_pass, "m", "rubric", fixture)

    assert calibration.miscalibrated


def test_grade_semantic_assertions_grades_the_runtime_response(
    tmp_path: Path,
) -> None:
    fixture = _any_semantic_fixture(tmp_path)
    grader = _well_calibrated_grader()

    results, override, calibration = runtime_grader.grade_semantic_assertions(
        fixture, "a clean completion response", grader, "m"
    )

    assert override is None
    assert calibration is None
    assert results[0]["passed"] is True
    assert results[0]["status"] == "graded"


def test_grade_semantic_assertions_fails_closed_when_the_response_fails(
    tmp_path: Path,
) -> None:
    fixture = _any_semantic_fixture(tmp_path)
    grader = FakeGrader(
        fail_on=(
            NEGATIVE_RESPONSE,
            runtime_grader.MUTANT_TAIL.strip(),
            "bad tail",
        )
    )

    results, override, _calibration = runtime_grader.grade_semantic_assertions(
        fixture, "response with a bad tail", grader, "m"
    )

    assert override is None
    assert results[0]["passed"] is False


def test_grade_semantic_assertions_reports_unavailable_on_calibration_failure(
    tmp_path: Path,
) -> None:
    fixture = _any_semantic_fixture(tmp_path)
    grader = FakeGrader(raise_on=POSITIVE_RESPONSE)

    results, override, calibration = runtime_grader.grade_semantic_assertions(
        fixture, "response", grader, "m"
    )

    assert results == []
    assert override == "UNAVAILABLE"
    assert calibration["positive"]["verdict"] == "UNAVAILABLE"


def test_grade_semantic_assertions_reports_invalid_grader_on_miscalibration(
    tmp_path: Path,
) -> None:
    fixture = _any_semantic_fixture(tmp_path)
    always_pass = FakeGrader()

    results, override, calibration = runtime_grader.grade_semantic_assertions(
        fixture, "response", always_pass, "m"
    )

    assert results == []
    assert override == "INVALID_GRADER"
    assert calibration["negative"]["verdict"] == "PASS"


def test_grade_semantic_assertions_reports_unavailable_when_the_final_grade_fails(
    tmp_path: Path,
) -> None:
    fixture = _any_semantic_fixture(tmp_path)
    grader = _well_calibrated_grader(raise_on="a clean completion response")

    results, override, _calibration = runtime_grader.grade_semantic_assertions(
        fixture, "a clean completion response", grader, "m"
    )

    assert results == []
    assert override == "UNAVAILABLE"


def test_resolve_ref_sha_refuses_an_option_shaped_ref() -> None:
    with pytest.raises(runtime_parity.ParityConfigError, match="must not start with"):
        runtime_parity.resolve_ref_sha("--output=/tmp/x")


def test_duplicate_instruction_basenames_are_refused(tmp_path: Path) -> None:
    with pytest.raises(runtime_parity.ParityConfigError, match="duplicate file names"):
        _any_semantic_fixture(
            tmp_path,
            instructions=[".claude/rules/voice.md", "templates/rules/voice.md"],
        )
