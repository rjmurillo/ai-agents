"""Negative controls and the CLI contract for ``--same-pr``.

Split from ``test_same_pr.py`` so neither file crosses the 500-line taste limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HELPERS_DIR = str(Path(__file__).resolve().parent)
_TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if _TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_SKILLS_DIR)
if _HELPERS_DIR not in sys.path:
    sys.path.insert(0, _HELPERS_DIR)

from claude_skills_import import import_skill_script
from diff_scope_helpers import edit_files_and_commit, make_repo, mod, run_same_pr
from test_same_pr import EXIT_ROW_RIGHT, EXIT_ROW_WRONG, TOOL, _grammar_repo, _tool_source

_SAME_PR = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/same_pr.py",
    module_name="same_pr_doc_contract",
)
_DIFF_SCOPING = (
    Path(__file__).resolve().parents[3]
    / "src/claude/skills/doc-accuracy/references/diff-scoping.md"
)
_COUNT_WORDS = {6: "six"}


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


def test_diff_scoping_matches_same_pr_read_limits() -> None:
    """The same-PR paragraph has to name the real suffix list, size cap, and pair cap."""
    section = _DIFF_SCOPING.read_text(encoding="utf-8")
    start = section.index("**What it reads.**")
    section = section[start : section.index("**Rules.**")]
    megabytes = _SAME_PR.MAX_FILE_BYTES / 1_000_000

    assert megabytes == int(megabytes)
    assert f"{int(megabytes)} MB" in section
    assert _COUNT_WORDS[_SAME_PR.MAX_PAIRS] in section
    for suffix in _SAME_PR.SCANNED_SUFFIXES:
        assert f"`{suffix}`" in section
    assert "every text file" not in section
    assert "nearest path first" not in section


def test_exit_literals_skip_returns_nested_under_main() -> None:
    """A return inside a helper nested in main is not a process exit."""
    source = (
        "def main() -> int:\n"
        "    def helper() -> int:\n"
        "        sys.exit(4)\n"
        "        return 7\n"
        "    async def inner() -> int:\n"
        "        return 8\n"
        "    if False:\n"
        "        return 3\n"
        "    return 0\n"
    )

    found = _SAME_PR.CodeIndex({"tool.py": source}).exit_literals("tool.py")

    assert set(found) == {0, 3, 4}


def test_same_pr_is_off_by_default(tmp_path: Path) -> None:
    repo, _ = _grammar_repo(tmp_path, EXIT_ROW_WRONG)
    out = tmp_path / "out"

    mod.main(["--target", str(repo), "--output-dir", str(out), "--diff-base", "HEAD~1"])

    assert not (out / "same-pr-findings.json").exists()


def test_count_beside_symbol_reads_only_the_adjacent_token() -> None:
    """A count counts only when it is the token touching the backticked name."""
    words = {"two": 2}
    count = _SAME_PR._count_beside_symbol
    assert count("The two `SECTIONS` are required.", "SECTIONS", words) == 2
    assert count("The 4 `SECTIONS` are required.", "sections", words) == 4
    assert count("The two extra `SECTIONS` are required.", "SECTIONS", words) is None
    assert count("   `SECTIONS` are required.", "SECTIONS", words) is None
    assert count("   `SECTIONS` and two `SECTIONS`.", "SECTIONS", words) == 2
