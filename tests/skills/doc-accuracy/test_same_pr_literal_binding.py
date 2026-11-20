"""``--same-pr`` R2: a path list binds only to a collection its line names.

Issue #7484: a long ADR-109 table row named two members of `AGENT_PATTERNS`
and the word "prefix". R2 bound it to that unrelated collection and failed
the gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import Json, edit_files_and_commit, make_repo, run_same_pr


def _rule(findings: Json, rule: str) -> list[Json]:
    return [f for f in findings["findings"] if f["rule"] == rule]


EVAL_SUITE = "scripts/eval/eval-suite.py"
AGENT_PATTERNS_SOURCE = (
    "AGENT_PATTERNS = [\n"
    '    ".claude/agents/",\n'
    '    "src/claude/",\n'
    '    "src/copilot-cli/agents/",\n'
    '    "src/vs-code-agents/",\n'
    "]\n"
)
# A trimmed copy of the ADR-109 B1 rollout row that issue #7484 reported.
ADR_ROW = (
    "| B1 | Agents: compile renders `src/claude/` and `src/copilot-cli/agents/`; "
    "rewrite the pattern at `build/scripts/validate_install_parity.py:141`; widen "
    "`OWNED_PREFIXES` in `build/scripts/build_all.py` | tests |"
)


def _agent_patterns_repo(tmp_path: Path, prose: str, *, change_code: bool) -> Path:
    head = AGENT_PATTERNS_SOURCE + ("\n\ndef run():\n    return 1\n" if change_code else "")
    repo = make_repo(tmp_path, {EVAL_SUITE: AGENT_PATTERNS_SOURCE, "adr.md": "# ADR\n"})
    edit_files_and_commit(repo, {EVAL_SUITE: head, "adr.md": f"# ADR\n\n{prose}\n"})
    return repo


def test_r2_ignores_paths_from_a_collection_the_line_never_names(tmp_path: Path) -> None:
    repo = _agent_patterns_repo(tmp_path, ADR_ROW, change_code=True)

    code, findings, _ = run_same_pr(repo, tmp_path, "--phases", "1")

    assert _rule(findings, "R2") == []
    assert code == 0


def test_r2_ignores_a_collection_another_line_pulled_in(tmp_path: Path) -> None:
    prose = f"{ADR_ROW}\n\nThe eval runner lives in `{EVAL_SUITE}`."
    repo = _agent_patterns_repo(tmp_path, prose, change_code=False)

    code, findings, _ = run_same_pr(repo, tmp_path, "--phases", "1")

    assert _rule(findings, "R2") == []
    assert code == 0


def test_r2_binds_paths_when_the_line_names_the_collection_file(tmp_path: Path) -> None:
    prose = ADR_ROW.replace("| tests |", f"| `{EVAL_SUITE}` scans these roots |")
    repo = _agent_patterns_repo(tmp_path, prose, change_code=True)

    code, findings, _ = run_same_pr(repo, tmp_path, "--phases", "1")

    (hit,) = _rule(findings, "R2")
    assert hit["code"]["symbol"] == "AGENT_PATTERNS"
    assert hit["evidence"]["missing"] == [".claude/agents", "src/vs-code-agents"]
    assert code == 10


def test_r2_binds_paths_when_the_line_names_the_collection_symbol(tmp_path: Path) -> None:
    prose = "`AGENT_PATTERNS` covers `src/claude/` and `src/copilot-cli/agents/`."
    repo = _agent_patterns_repo(tmp_path, prose, change_code=True)

    code, findings, _ = run_same_pr(repo, tmp_path, "--phases", "1")

    (hit,) = _rule(findings, "R2")
    assert hit["code"]["symbol"] == "AGENT_PATTERNS"
    assert hit["evidence"]["missing"] == [".claude/agents", "src/vs-code-agents"]
    assert code == 10


def test_r2_binds_paths_when_the_line_names_the_bare_script_name(tmp_path: Path) -> None:
    prose = ADR_ROW.replace("| tests |", "| `./eval-suite.py` scans these roots |")
    repo = _agent_patterns_repo(tmp_path, prose, change_code=True)

    code, findings, _ = run_same_pr(repo, tmp_path, "--phases", "1")

    (hit,) = _rule(findings, "R2")
    assert hit["code"]["symbol"] == "AGENT_PATTERNS"
    assert code == 10


def test_r2_binds_a_comment_inside_the_collection_file(tmp_path: Path) -> None:
    comment = "# Scope roots: `src/claude/` and `src/copilot-cli/agents/`.\n"
    repo = make_repo(tmp_path, {EVAL_SUITE: AGENT_PATTERNS_SOURCE})
    edit_files_and_commit(repo, {EVAL_SUITE: comment + AGENT_PATTERNS_SOURCE})

    code, findings, _ = run_same_pr(repo, tmp_path, "--phases", "1")

    (hit,) = _rule(findings, "R2")
    assert hit["prose"]["file"] == EVAL_SUITE
    assert hit["evidence"]["missing"] == [".claude/agents", "src/vs-code-agents"]
    assert code == 10


def test_r2_needs_a_scope_word_when_the_line_names_only_the_file(tmp_path: Path) -> None:
    prose = f"`{EVAL_SUITE}` reads `src/claude/` and `src/copilot-cli/agents/`."
    repo = _agent_patterns_repo(tmp_path, prose, change_code=True)

    code, findings, _ = run_same_pr(repo, tmp_path, "--phases", "1")

    assert _rule(findings, "R2") == []
    assert code == 0
