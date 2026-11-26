"""``--same-pr`` checklist entries: prose paired with changed code.

Split from ``test_same_pr.py`` so neither file crosses the 500-line taste limit.
The evidence fixtures are trimmed copies of PR #6584, #6852 and #7379.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diff_scope_helpers import (
    checklist_entry,
    edit_files_and_commit,
    line_of,
    make_repo,
    run_same_pr,
)

# -- checklist entries: #6584, #6852, #7379 ------------------------------------

ADR_SCRIPT = "src/claude/skills/adr-review/scripts/detect_adr_changes.py"
ADR_BASE = '''\
import yaml


def _has_duplicate_keys(frontmatter: str) -> bool:
    """Return True when the frontmatter repeats a mapping key."""
    try:
        yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return False
    return False
'''
ADR_HEAD = '''\
import yaml


def _has_duplicate_keys(frontmatter: str) -> bool:
    """Return True when the frontmatter repeats a mapping key.

    Stricter/looser/different than canonical: identical detection; this returns
    a bool because callers only branch on it.
    """

    class _Dup(yaml.YAMLError):
        pass

    class _Loader(yaml.SafeLoader):
        pass

    def _check(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[object, object]:
        seen: list[object] = []
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in seen:
                raise _Dup
            seen.append(key)
        return loader.construct_mapping(node, deep=True)

    try:
        yaml.load(frontmatter, Loader=_Loader)
    except _Dup:
        return True
    return False
'''


def test_checklist_pairs_a_docstring_claim_with_the_changed_nested_code(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {ADR_SCRIPT: ADR_BASE})
    edit_files_and_commit(repo, {ADR_SCRIPT: ADR_HEAD})

    code, findings, checklist = run_same_pr(repo, tmp_path)

    entry = checklist_entry(checklist, ADR_SCRIPT, "identical detection")
    assert code == 0 and findings["findings"] == []
    assert entry["prose_line"] == line_of(ADR_HEAD, "identical detection")
    assert "identical" in entry["reasons"]
    pairs = {p["symbol"]: p for p in entry["pairs"]}
    assert {"_check", "_Dup"} <= set(pairs)
    assert pairs["_check"]["file"] == ADR_SCRIPT
    assert pairs["_check"]["line"] == line_of(ADR_HEAD, "def _check")
    assert pairs["_Dup"]["line"] == line_of(ADR_HEAD, "class _Dup")


GROWTH = "tests/test_subprocess_text_encoding.py"
GROWTH_BASE = '''\
def _cpu_growth(run, small_input, large_input, tries: int = 3):
    """CPU time of ``run(large_input)`` over ``run(small_input)``."""
    return run(large_input) / run(small_input)
'''
GROWTH_HEAD = '''\
def _cpu_growth(run, small_input, large_input, tries: int = 3):
    """CPU time of ``run(large_input)`` over ``run(small_input)``, and the large result.

    The large result comes back so a caller can check it without a fifth run.
    """
    small_best = large_best = float("inf")
    large_result = None
    for _ in range(tries):
        small_best = min(small_best, run(small_input))
        large_result = run(large_input)
        large_best = min(large_best, large_result)
    return large_best / small_best, large_result
'''


def test_checklist_flags_ordinal_count_beside_changed_loop(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {GROWTH: GROWTH_BASE})
    edit_files_and_commit(repo, {GROWTH: GROWTH_HEAD})

    _, _, checklist = run_same_pr(repo, tmp_path)

    entry = checklist_entry(checklist, GROWTH, "fifth run")
    assert entry["prose_line"] == line_of(GROWTH_HEAD, "fifth run")
    assert "number" in entry["reasons"]
    (pair,) = [p for p in entry["pairs"] if p["symbol"] == "_cpu_growth"]
    assert pair["file"] == GROWTH
    assert pair["line"] > 0


SEVERITY_DOC = "src/claude/skills/review/resources/finding-severity.md"
SEVERITY_SCRIPT = "src/claude/skills/review/scripts/render_findings.py"
SEVERITY_LINE = (
    "- A label never claims more than its value can do to the axis verdict. "
    "Only `critical` and `high` move it, so `medium` is a SUGGESTION."
)
SEVERITY_BASE_DOC = "## Rules\n\n- Print the axis's own value after the label.\n"
SEVERITY_HEAD_DOC = SEVERITY_BASE_DOC + SEVERITY_LINE + "\n"
SEVERITY_BASE_PY = 'LABELS = {"critical": "CRITICAL", "high": "IMPORTANT"}\n'
SEVERITY_HEAD_PY = (
    'LABELS = {"critical": "CRITICAL", "high": "IMPORTANT", "medium": "SUGGESTION"}\n\n\n'
    'def label_for(value: str) -> str:\n    return LABELS.get(value, "UNSPECIFIED")\n'
)


def test_checklist_pairs_a_severity_claim_with_changed_review_code(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {SEVERITY_DOC: SEVERITY_BASE_DOC, SEVERITY_SCRIPT: SEVERITY_BASE_PY})
    edit_files_and_commit(
        repo, {SEVERITY_DOC: SEVERITY_HEAD_DOC, SEVERITY_SCRIPT: SEVERITY_HEAD_PY}
    )

    code, findings, checklist = run_same_pr(repo, tmp_path)

    entry = checklist_entry(checklist, SEVERITY_DOC, "Only `critical` and `high`")
    assert code == 0 and findings["findings"] == []
    assert entry["prose_line"] == line_of(SEVERITY_HEAD_DOC, "Only `critical`")
    assert {"only", "never"} <= set(entry["reasons"])
    assert {p["file"] for p in entry["pairs"]} == {SEVERITY_SCRIPT}
    assert all(p["line"] > 0 for p in entry["pairs"])
    # The contradicting rules live in unchanged files; the artifact says it cannot see them.
    assert any("unchanged" in limit for limit in checklist["limits"])
