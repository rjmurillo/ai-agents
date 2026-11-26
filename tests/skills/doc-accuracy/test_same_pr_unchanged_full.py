"""``--same-pr`` unchanged-reference scan: a changed file with no hunk is changed in full.

``doc_accuracy._get_changed_diff`` documents that a changed file with no parsed
hunk (binary, mode-only) counts as changed in full. The unchanged-reference scan
must agree: none of that file's lines are "unchanged prose".
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import Json, commit, git, make_repo, run_same_pr

SYMBOL = "compute_total_amount"
CODE = "src/calc.py"
CODE_BASE = f"def {SYMBOL}(items):\n    return sum(items)\n"
CODE_HEAD = f"def {SYMBOL}(items):\n    return sum(items) + 0\n"
SENTENCE = f"The {SYMBOL} helper sums its items.\n"


def _unchanged_entries(checklist: Json, path: str) -> list[Json]:
    return [
        entry
        for entry in checklist["entries"]
        if entry["prose_file"] == path
        and any(reason.startswith("unchanged reference") for reason in entry["reasons"])
    ]


def _diff(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "diff", "--unified=0", "--no-renames", "HEAD~1", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return done.stdout


def test_mode_only_change_counts_as_changed_in_full(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {CODE: CODE_BASE, "docs/untouched.md": SENTENCE, "docs/mode_only.md": SENTENCE},
    )
    git(repo, "config", "core.fileMode", "true")
    (repo / CODE).write_text(CODE_HEAD, encoding="utf-8")
    (repo / "docs" / "mode_only.md").chmod(0o755)
    commit(repo)
    # Arrange check: the mode-only file really has no hunk in the diff doc_accuracy reads.
    mode_diff = _diff(repo, "--", "docs/mode_only.md")
    assert "new mode 100755" in mode_diff
    assert "@@" not in mode_diff

    code, _findings, checklist = run_same_pr(repo, tmp_path)

    assert code == 0
    # Control: an untouched file naming the changed symbol is still reported.
    assert len(_unchanged_entries(checklist, "docs/untouched.md")) == 1
    # A mode-only file is changed in full, so it has no unchanged lines to report.
    assert _unchanged_entries(checklist, "docs/mode_only.md") == []


def test_changed_file_keeps_lines_outside_its_hunk_as_unchanged(tmp_path: Path) -> None:
    doc = "docs/partly_edited.md"
    repo = make_repo(tmp_path, {CODE: CODE_BASE, doc: SENTENCE + "Second line.\n"})
    (repo / CODE).write_text(CODE_HEAD, encoding="utf-8")
    (repo / doc).write_text(SENTENCE + "Second line, edited.\n", encoding="utf-8")
    commit(repo)

    code, _findings, checklist = run_same_pr(repo, tmp_path)

    assert code == 0
    entries = _unchanged_entries(checklist, doc)
    assert [entry["prose_line"] for entry in entries] == [1]
