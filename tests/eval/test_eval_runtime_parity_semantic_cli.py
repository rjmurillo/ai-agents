"""End-to-end `run_evaluation`/`main` coverage for the semantic surface (#5404).

`test_eval_runtime_parity_semantic.py` covers the fixture loader, the
harness install/refusal, the ablation resolver, and the grader module in
isolation. This file drives the same features through `run_evaluation` and
`main`, the way a real invocation does: `--harnesses`, `--instructions-ref`,
and the injectable `grader`, exercising every exit code the new surface can
produce (spec-5404.md AC1-AC10, AC12).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import (
    FIXTURES,
    FixedResponseRunner,
    corpus_with_instructions,
    parity,
)

REPO_ROOT = parity.REPO_ROOT


class CalibratedFakeGrader:
    """Fails the fixture's own negative control and the automatic mutant.

    `calibrate` always issues exactly three calls in order (positive control,
    negative control, mutant) before `grade_semantic_assertions` issues a
    fourth for the actual runtime response, so dispatching on call order is
    simpler and more robust here than content matching: this test's positive
    control and the actual runtime response are the same literal text
    ("CONTINUE_PHASE_3", required by the stock fixture's exact-match regex
    assertion), so they are not distinguishable by content alone.
    """

    name = "fake-grader"
    system_fingerprint = "fake-fingerprint"

    def __init__(self, *, fail_response: bool = False, always: str | None = None) -> None:
        self.fail_response = fail_response
        self.always = always
        self.calls = 0

    def complete(self, *, messages, system="", model, **_kwargs):
        self.calls += 1
        if self.always:
            return json.dumps({"verdict": self.always, "reason": "forced"})
        if self.calls == 1:  # positive control
            verdict = "PASS"
        elif self.calls in (2, 3):  # negative control, then the mutant
            verdict = "FAIL"
        else:  # the actual runtime response
            verdict = "FAIL" if self.fail_response else "PASS"
        return json.dumps({"verdict": verdict, "reason": "test"})


# --- AC1, AC2: instruction install and Copilot refusal, end to end ----------


def test_default_both_harnesses_refuses_a_fixture_with_instructions(
    tmp_path: Path,
) -> None:
    corpus = corpus_with_instructions(tmp_path)

    with pytest.raises(parity.ParityConfigError, match="Copilot"):
        parity.run_evaluation(
            fixtures_path=corpus,
            model=parity.DEFAULT_MODEL,
            output=tmp_path / "run" / "report.json",
            claude_bin="claude",
            copilot_bin="copilot",
            timeout=30,
            dry_run=False,
            runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        )


def test_harnesses_claude_installs_instructions_and_passes(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path)
    output = tmp_path / "run" / "report.json"

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=output,
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        harnesses="claude",
    )

    assert code == parity.EXIT_OK
    assert report["verdict"] == "PASS"
    installed = (
        tmp_path
        / "run"
        / "workspaces"
        / "resume-phase-3"
        / "claude"
        / ".claude"
        / "rules"
        / "voice.md"
    )
    expected = (REPO_ROOT / ".claude" / "rules" / "voice.md").read_bytes()
    assert installed.read_bytes() == expected
    assert report["fixtures"][0]["instructions"][0]["path"] == ".claude/rules/voice.md"
    assert "copilot" not in report["fixtures"][0]


def test_single_harness_mode_emits_no_comparison_verdict(tmp_path: Path) -> None:
    """AC3: `--harnesses claude` runs only claude and skips FAIL_MODEL_MISMATCH."""
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        # A model mismatch would fail closed in dual-harness mode; in
        # single-harness mode there is nothing to compare it against.
        runner=FixedResponseRunner("CONTINUE_PHASE_3", model="a-different-model"),
        harnesses="claude",
    )

    assert code == parity.EXIT_OK
    assert report["verdict"] == "PASS"
    assert "copilot" not in report["fixtures"][0]


def test_single_harness_assertion_failure_exits_logic(tmp_path: Path) -> None:
    """A FAIL verdict in single-harness mode must not exit 0 (FAIL_BEHAVIOR)."""
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=FixedResponseRunner("RESTART_PHASE_1"),
        harnesses="claude",
    )

    assert report["verdict"] == "FAIL"
    assert code == parity.EXIT_LOGIC


# --- AC4, AC5: --instructions-ref ablation -----------------------------------


def test_instructions_ref_resolves_from_a_git_ref(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path)

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        harnesses="claude",
        instructions_ref="HEAD",
    )

    assert code == parity.EXIT_OK
    assert report["instructions_ref"] == "HEAD"
    assert len(report["instructions_ref_sha"]) == 40
    assert len(report["source_commit"]) == 40


def test_instructions_ref_bad_ref_is_a_config_error(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path)

    with pytest.raises(parity.ParityConfigError, match="not a resolvable ref"):
        parity.run_evaluation(
            fixtures_path=corpus,
            model=parity.DEFAULT_MODEL,
            output=tmp_path / "run" / "report.json",
            claude_bin="claude",
            copilot_bin="copilot",
            timeout=30,
            dry_run=False,
            runner=FixedResponseRunner("CONTINUE_PHASE_3"),
            harnesses="claude",
            instructions_ref="not-a-real-ref-5404",
        )


# --- AC7: dry-run validates without a model call -----------------------------


def test_dry_run_reports_semantic_as_not_run_and_calls_no_grader(
    tmp_path: Path,
) -> None:
    corpus = corpus_with_instructions(tmp_path, semantic=True)

    class ExplodingGrader:
        name = "must-not-be-called"
        system_fingerprint = None

        def complete(self, **_kwargs):
            raise AssertionError("dry-run must not call the grader")

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        grader=ExplodingGrader(),
    )

    assert code == parity.EXIT_OK
    assert report["verdict"] == "DRY_RUN"
    semantic = [
        a
        for a in report["fixtures"][0]["controls"]["positive"]
        if a["kind"] == "semantic"
    ]
    assert semantic == [
        {
            "kind": "semantic",
            "path": None,
            "expected": "FAIL on any continuation offer; PASS otherwise.",
            "passed": None,
            "status": "not_run",
        }
    ]


# --- AC8, AC9: calibration, INVALID_GRADER, UNAVAILABLE ----------------------


def test_semantic_assertion_passes_with_a_well_calibrated_grader(
    tmp_path: Path,
) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False, semantic=True)

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        harnesses="claude",
        grader=CalibratedFakeGrader(),
        grader_model="claude-sonnet-5",
    )

    assert code == parity.EXIT_OK
    assert report["verdict"] == "PASS"
    semantic = [
        a for a in report["fixtures"][0]["claude"]["assertions"] if a["kind"] == "semantic"
    ]
    assert semantic[0]["passed"] is True
    assert semantic[0]["status"] == "graded"
    assert semantic[0]["grader_provider"] == "fake-grader"
    assert semantic[0]["grader_model"] == "claude-sonnet-5"


def test_semantic_assertion_fails_the_run_when_the_response_fails(
    tmp_path: Path,
) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False, semantic=True)

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        harnesses="claude",
        grader=CalibratedFakeGrader(fail_response=True),
    )

    assert code == parity.EXIT_LOGIC
    assert report["verdict"] == "FAIL"
    assert report["fixtures"][0]["claude"]["passed"] is False


def test_miscalibrated_grader_yields_invalid_grader_and_exit_logic(
    tmp_path: Path,
) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False, semantic=True)

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        harnesses="claude",
        grader=CalibratedFakeGrader(always="PASS"),  # never fails: inverted control
    )

    assert code == parity.EXIT_LOGIC
    assert report["verdict"] == "INVALID_GRADER"


def test_unavailable_grader_yields_exit_external(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False, semantic=True)

    class RaisingGrader:
        name = "raising-grader"
        system_fingerprint = None

        def complete(self, **_kwargs):
            raise RuntimeError("grader transport is down")

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        harnesses="claude",
        grader=RaisingGrader(),
    )

    assert code == parity.EXIT_EXTERNAL
    assert report["verdict"] == "ERROR"


# --- CLI argument wiring ------------------------------------------------------


def test_parser_defaults_match_the_documented_contract() -> None:
    args = parity._parser().parse_args([])

    assert args.harnesses == "both"
    assert args.instructions_ref is None
    assert args.grader_provider == "anthropic"
    assert args.grader_model == "claude-opus-4-6"


def test_parser_accepts_every_harness_choice() -> None:
    for choice in ("both", "claude", "copilot"):
        args = parity._parser().parse_args(["--harnesses", choice])
        assert args.harnesses == choice


def test_main_rejects_an_unknown_harness_choice(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        parity.main(["--harnesses", "bogus"], runner=FixedResponseRunner("x"))

    assert excinfo.value.code == 2


def test_main_plumbs_instructions_ref_to_a_config_error(
    tmp_path: Path, capsys
) -> None:
    corpus = corpus_with_instructions(tmp_path)

    code = parity.main(
        [
            "--fixtures",
            str(corpus),
            "--output",
            str(tmp_path / "run" / "report.json"),
            "--harnesses",
            "claude",
            "--instructions-ref",
            "not-a-real-ref-5404",
        ],
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
    )

    assert code == parity.EXIT_CONFIG
    assert "not a resolvable ref" in capsys.readouterr().err


# --- Workspace ancestry isolation ---------------------------------------------


def test_live_run_refuses_a_workspace_root_under_instruction_files(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)
    parent = tmp_path / "contaminated"
    (parent / ".claude").mkdir(parents=True)
    (parent / ".claude" / "CLAUDE.md").write_text("leak", encoding="utf-8")

    with pytest.raises(parity.ParityConfigError, match="inherits instruction files"):
        parity.run_evaluation(
            fixtures_path=corpus,
            model=parity.DEFAULT_MODEL,
            output=tmp_path / "run" / "report.json",
            claude_bin="claude",
            copilot_bin="copilot",
            timeout=30,
            dry_run=False,
            runner=FixedResponseRunner("CONTINUE_PHASE_3"),
            harnesses="claude",
            workspace_root=parent / "workspaces",
        )


def test_dry_run_skips_the_workspace_ancestry_guard(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)
    parent = tmp_path / "contaminated"
    parent.mkdir()
    (parent / "AGENTS.md").write_text("leak", encoding="utf-8")

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        harnesses="claude",
        workspace_root=parent / "workspaces",
    )

    assert code == parity.EXIT_OK
    assert report["workspace_root"] == str(parent / "workspaces")


def test_live_run_uses_the_given_workspace_root(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)
    root = tmp_path / "isolated"

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
        harnesses="claude",
        workspace_root=root,
    )

    assert code == parity.EXIT_OK
    assert (root / "resume-phase-3" / "claude" / "PARITY_FIXTURE.md").is_file()
    assert report["workspace_root"] == str(root)


def test_main_exits_config_for_a_contaminated_workspace_root(tmp_path: Path) -> None:
    parent = tmp_path / "contaminated"
    parent.mkdir()
    (parent / "CLAUDE.md").write_text("leak", encoding="utf-8")

    code = parity.main(
        [
            "--fixtures",
            str(FIXTURES),
            "--output",
            str(tmp_path / "run" / "report.json"),
            "--harnesses",
            "claude",
            "--workspace-root",
            str(parent / "workspaces"),
        ],
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
    )

    assert code == parity.EXIT_CONFIG
