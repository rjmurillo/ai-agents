from __future__ import annotations

from pathlib import Path

from scripts.ci import validate_ai_review_budgets as budgets


def _write_workflow(root: Path, text: str) -> Path:
    path = root / ".github" / "workflows" / "ai.yml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_required_job_timeout_uses_retry_worst_case():
    assert budgets.required_job_timeout([2, 3, 2, 8]) == 56


def test_under_budget_workflow_fails(tmp_path, capsys):
    _write_workflow(
        tmp_path,
        """
name: AI
jobs:
  triage:
    timeout-minutes: 10
    steps:
      - uses: ./.github/actions/ai-review
        with:
          timeout-minutes: 8
""",
    )
    rc = budgets.main(["--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == budgets.EXIT_REGRESSION
    assert "required=31" in captured.err


def test_sufficient_budget_workflow_passes(tmp_path, capsys):
    _write_workflow(
        tmp_path,
        """
name: AI
jobs:
  triage:
    timeout-minutes: 31
    steps:
      - uses: ./.github/actions/ai-review
        with:
          timeout-minutes: 8
""",
    )
    rc = budgets.main(["--repo-root", str(tmp_path)])
    assert rc == budgets.EXIT_OK
    assert "budgets OK" in capsys.readouterr().out


def test_missing_job_timeout_fails(tmp_path, capsys):
    _write_workflow(
        tmp_path,
        """
name: AI
jobs:
  triage:
    steps:
      - uses: ./.github/actions/ai-review
        with:
          timeout-minutes: 1
""",
    )
    rc = budgets.main(["--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == budgets.EXIT_REGRESSION
    assert "timeout-minutes=0" in captured.err
