"""CLI, loader and pre-PR gate tests for check_required_context_conditions.py.

The analysis cases live in test_check_required_context_conditions.py. This module
covers the parts around them: parsing failures, exit codes, the advisory gate,
and one run against this repository's own workflows.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_required_context_conditions as lint_mod
import pytest
from check_required_context_conditions import (
    EXIT_CONFIG,
    EXIT_FINDINGS,
    EXIT_OK,
    WorkflowLoadError,
    lint,
    load_workflows,
    main,
    producing_jobs,
    validate_required_context_conditions,
)

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS
from tests.validation.required_context_helpers import (
    CONTEXT,
    FLAGGED_STEP,
    REPO_ROOT,
    job_body,
    write_workflow,
)


class TestLoadWorkflows:
    def test_missing_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(WorkflowLoadError, match="not found"):
            load_workflows(tmp_path / "absent")

    def test_invalid_yaml_raises_instead_of_reading_as_empty(self, tmp_path: Path) -> None:
        write_workflow(tmp_path, "bad.yml", "jobs: [unclosed\n")

        with pytest.raises(WorkflowLoadError, match="bad.yml"):
            load_workflows(tmp_path)

    @pytest.mark.parametrize(
        "body",
        [
            "when: 2001-13-45\n",
            "x: " + "[" * 4000 + "]" * 4000 + "\n",
        ],
    )
    def test_yaml_that_raises_outside_yaml_error_still_fails_closed(
        self, tmp_path: Path, body: str
    ) -> None:
        write_workflow(tmp_path, "odd.yml", body)

        with pytest.raises(WorkflowLoadError, match="odd.yml"):
            load_workflows(tmp_path)

    def test_a_non_mapping_top_level_raises(self, tmp_path: Path) -> None:
        write_workflow(tmp_path, "list.yml", "- a\n- b\n")

        with pytest.raises(WorkflowLoadError, match="not a mapping"):
            load_workflows(tmp_path)

    def test_an_empty_file_raises(self, tmp_path: Path) -> None:
        write_workflow(tmp_path, "empty.yml", "")

        with pytest.raises(WorkflowLoadError, match="not a mapping"):
            load_workflows(tmp_path)

    def test_yaml_and_yml_extensions_are_both_read(self, tmp_path: Path) -> None:
        write_workflow(tmp_path, "a.yml", "on: push\njobs: {}\n")
        write_workflow(tmp_path, "b.yaml", "on: push\njobs: {}\n")

        assert sorted(load_workflows(tmp_path)) == ["a.yml", "b.yaml"]

    def test_a_workflow_with_no_jobs_mapping_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        write_workflow(tmp_path, "nojobs.yml", "on: push\njobs: not-a-mapping\n")
        documents = load_workflows(tmp_path)

        assert producing_jobs(documents, (CONTEXT,)) == []

    def test_a_job_body_that_is_not_a_mapping_is_skipped(self, tmp_path: Path) -> None:
        write_workflow(tmp_path, "odd.yml", "on: push\njobs:\n  a: just-a-string\n")
        documents = load_workflows(tmp_path)

        assert producing_jobs(documents, (CONTEXT,)) == []


class TestMain:
    def _tree(self, tmp_path: Path, body: str) -> Path:
        workflows = tmp_path / "workflows"
        write_workflow(workflows, "wf.yml", body)
        return workflows

    def _flagged(self) -> str:
        return job_body(steps=FLAGGED_STEP)

    def test_findings_exit_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        workflows = self._tree(tmp_path, self._flagged())

        code = main(["--workflows-dir", str(workflows)])

        assert code == EXIT_FINDINGS
        assert "1 findings; examined 1 workflows, 1 pinned contexts, 1 producing jobs" in (
            capsys.readouterr().out
        )

    def test_advisory_reports_but_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        workflows = self._tree(tmp_path, self._flagged())

        code = main(["--workflows-dir", str(workflows), "--advisory"])

        assert code == EXIT_OK
        assert "[step-condition]" in capsys.readouterr().out

    def test_clean_tree_exits_zero_and_still_prints_the_examined_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        workflows = self._tree(tmp_path, job_body())

        code = main(["--workflows-dir", str(workflows)])

        assert code == EXIT_OK
        assert "0 findings; examined 1 workflows" in capsys.readouterr().out

    def test_verbose_lists_every_step(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        steps = "".join(
            f"      - name: s{i}\n        if: github.actor != 'bot'\n        run: echo {i}\n"
            for i in range(2)
        )
        workflows = self._tree(tmp_path, job_body(steps=steps))

        main(["--workflows-dir", str(workflows), "--verbose", "--advisory"])

        out = capsys.readouterr().out
        assert "wf.yml:gate:s0" in out
        assert "wf.yml:gate:s1" in out

    def test_unparseable_workflow_exits_two_even_when_advisory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        workflows = tmp_path / "workflows"
        write_workflow(workflows, "bad.yml", "jobs: [unclosed\n")

        code = main(["--workflows-dir", str(workflows), "--advisory"])

        assert code == EXIT_CONFIG
        assert "bad.yml" in capsys.readouterr().err

    def test_missing_directory_exits_two(self, tmp_path: Path) -> None:
        assert main(["--workflows-dir", str(tmp_path / "absent")]) == EXIT_CONFIG


class TestPrePrGate:
    def test_gate_prints_findings_and_returns_true(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        write_workflow(
            tmp_path / ".github" / "workflows",
            "wf.yml",
            job_body(steps=FLAGGED_STEP),
        )

        assert validate_required_context_conditions(tmp_path) is True

        out = capsys.readouterr().out
        assert "required-context-conditions: [step-condition]" in out
        assert "required-context-conditions: 1 findings" in out

    def test_gate_returns_true_and_reports_when_a_workflow_does_not_parse(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_workflow(tmp_path / ".github" / "workflows", "bad.yml", "jobs: [unclosed\n")

        assert validate_required_context_conditions(tmp_path) is True

        err = capsys.readouterr().err
        assert "bad.yml" in err
        assert "NOT EXAMINED" in err

    def test_gate_returns_true_when_there_is_no_workflow_directory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate_required_context_conditions(tmp_path) is True

        assert "not found" in capsys.readouterr().err


class TestRealCorpus:
    """Rule 13 (`.claude/rules/ci-scripts.md`): show the gate against the full corpus."""

    def test_every_pinned_context_has_a_producing_job_in_this_repository(self) -> None:
        documents = load_workflows(REPO_ROOT / ".github" / "workflows")
        producers = producing_jobs(documents, REQUIRED_CONTEXTS)

        produced = {p.context for p in producers}

        assert produced == set(REQUIRED_CONTEXTS)
        assert len(documents) > 20

    def test_the_real_corpus_runs_clean_of_config_errors_under_advisory(self) -> None:
        code = main(["--advisory"])

        assert code == EXIT_OK

    def test_the_known_relocations_the_adr_names_are_seen(self) -> None:
        """ADR-101 names the step-relocated required contexts; the lint must see them."""
        documents = load_workflows(REPO_ROOT / ".github" / "workflows")
        findings, _ = lint(documents, REQUIRED_CONTEXTS)

        flagged = {f.context for f in findings}

        assert {
            "Validate Path Normalization",
            "Validate Generated Files",
            "Validate PR",
            "Validate PR title",
            "Analyze (python)",
            "Analyze (actions)",
        } <= flagged
