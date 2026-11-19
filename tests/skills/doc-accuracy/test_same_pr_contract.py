"""Negative controls and the CLI contract for ``--same-pr``.

Split from ``test_same_pr.py`` so neither file crosses the 500-line taste limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import edit_files_and_commit, make_repo, mod, run_same_pr
from test_same_pr import EXIT_ROW_RIGHT, EXIT_ROW_WRONG, TOOL, _grammar_repo, _tool_source


def test_accurate_prose_beside_changed_code_yields_no_finding_and_no_entry(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path, {"docs/tool.md": "# Tool\n", TOOL: _tool_source([0], [])})
    edit_files_and_commit(
        repo,
        {"docs/tool.md": "# Tool\n\nThis tool prints a report.\n", TOOL: _tool_source([0], [])},
    )

    code, findings, checklist = run_same_pr(repo, tmp_path)

    assert code == 0
    assert findings["findings"] == []
    assert checklist["entries"] == []


def test_findings_artifact_reports_what_was_examined(tmp_path: Path) -> None:
    repo, _ = _grammar_repo(tmp_path, EXIT_ROW_RIGHT)

    _, findings, _ = run_same_pr(repo, tmp_path)

    assert findings["examined"]["changed_files"] == 2
    assert findings["examined"]["prose_lines"] > 0
    assert findings["examined"]["code_lines"] > 0


def test_same_pr_without_diff_base_is_a_config_error(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"a.md": "# A\n"})

    code = mod.main(["--target", str(repo), "--output-dir", str(tmp_path / "o"), "--same-pr"])

    assert code == 2


def test_same_pr_is_off_by_default(tmp_path: Path) -> None:
    repo, _ = _grammar_repo(tmp_path, EXIT_ROW_WRONG)
    out = tmp_path / "out"

    mod.main(["--target", str(repo), "--output-dir", str(out), "--diff-base", "HEAD~1"])

    assert not (out / "same-pr-findings.json").exists()
