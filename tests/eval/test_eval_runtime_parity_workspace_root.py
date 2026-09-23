"""Workspace-root isolation and review-fix coverage for `eval_runtime_parity` (#5404).

Split from `test_eval_runtime_parity_semantic_cli.py` to keep each test file
under the 500-line taste limit.
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


# --- Review fixes ------------------------------------------------------------


def test_existing_empty_workspace_root_is_accepted(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)
    root = tmp_path / "made-by-mktemp"
    root.mkdir()

    _, code = parity.run_evaluation(
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


def test_non_empty_workspace_root_is_refused(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)
    root = tmp_path / "used"
    root.mkdir()
    (root / "leftover").write_text("x", encoding="utf-8")

    with pytest.raises(parity.ParityConfigError, match="already contains"):
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
            workspace_root=root,
        )


def test_dry_run_both_harnesses_no_longer_refuses_instruction_fixtures(
    tmp_path: Path,
) -> None:
    """REQ-034 AC1: dry-run resolves both harnesses' instructions, no refusal."""
    corpus = corpus_with_instructions(tmp_path)
    runner = FixedResponseRunner("CONTINUE_PHASE_3")

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        runner=runner,
    )

    assert code == parity.EXIT_OK
    assert report["verdict"] == "DRY_RUN"
    record = report["fixtures"][0]
    assert record["copilot_instructions"][0]["path"] == (
        ".github/instructions/voice.instructions.md"
    )
    # dry-run still probes CLI versions but never installs a workspace or
    # calls the listing preflight (that needs a live workspace).
    assert all("--version" in call for call in runner.calls)


def test_unknown_grader_provider_is_a_config_error_even_in_dry_run(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False, semantic=True)

    code = parity.main(
        [
            "--fixtures",
            str(corpus),
            "--output",
            str(tmp_path / "run" / "report.json"),
            "--harnesses",
            "claude",
            "--grader-provider",
            "no-such-provider",
            "--dry-run",
        ],
        runner=FixedResponseRunner("CONTINUE_PHASE_3"),
    )

    assert code == parity.EXIT_CONFIG


def test_claude_only_run_never_probes_copilot(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)
    runner = FixedResponseRunner("CONTINUE_PHASE_3")

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot-not-installed",
        timeout=30,
        dry_run=True,
        runner=runner,
        harnesses="claude",
    )

    assert code == parity.EXIT_OK
    assert list(report["cli_versions"]) == ["claude"]
    assert all("copilot" not in call[0] for call in runner.calls)


def test_semantic_grader_receives_the_scored_assertion_text(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False, semantic=True)
    seen: list[str] = []

    class RecordingGrader:
        name = "recording"
        system_fingerprint = None
        calls = 0

        def complete(self, *, messages, **_kwargs):
            self.calls += 1
            seen.append(messages[0]["content"])
            verdict = "FAIL" if self.calls in (2, 3) else "PASS"
            return json.dumps({"verdict": verdict, "reason": "r"})

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
        grader=RecordingGrader(),
    )

    report = (tmp_path / "run" / "report.json").read_text(encoding="utf-8")
    assert '"assertion_text": "CONTINUE_PHASE_3"' in report
    assert seen[-1].endswith("CONTINUE_PHASE_3")
