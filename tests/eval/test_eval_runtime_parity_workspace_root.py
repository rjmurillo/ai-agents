"""Workspace-root isolation and review-fix coverage for `eval_runtime_parity` (#5404).

Split from `test_eval_runtime_parity_semantic_cli.py` to keep each test file
under the 500-line taste limit.
"""

from __future__ import annotations

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


def test_copilot_with_instruction_fixtures_is_refused_before_any_run(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path)
    runner = FixedResponseRunner("CONTINUE_PHASE_3")

    with pytest.raises(parity.ParityConfigError, match="need --harnesses claude"):
        parity.run_evaluation(
            fixtures_path=corpus,
            model=parity.DEFAULT_MODEL,
            output=tmp_path / "run" / "report.json",
            claude_bin="claude",
            copilot_bin="copilot",
            timeout=30,
            dry_run=True,
            runner=runner,
        )
    assert runner.calls == []


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
