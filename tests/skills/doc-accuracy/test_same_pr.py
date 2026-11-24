"""``--same-pr`` mode: doc claims that drift from code changed in the same diff.

Each evidence fixture is a trimmed copy of a real miss: a base commit, then a head
commit holding the wrong prose beside the code it describes. The wrong states are
PR #7451 (916946a57e), #7450 (d856c06b0e), #6584 (926ad8185c), #6852 (579642032f)
and #7379 (ef0ac7bed7).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import (
    Json,
    checklist_entry,
    edit_files_and_commit,
    line_of,
    make_repo,
    run_same_pr,
)


def test_closed_scope_list_checks_explicit_unchanged_script(tmp_path: Path) -> None:
    script = "scripts/scope.py"
    repo = make_repo(
        tmp_path,
        {
            script: 'SCOPE = ("src", "build", "packages")\n',
            "CONTRIBUTING.md": "Scope rules.\n",
        },
    )
    edit_files_and_commit(
        repo,
        {
            "CONTRIBUTING.md": f"`{script}` scans root scope `src/` or `build/`.\n",
        },
    )
    _code, findings, _checklist = run_same_pr(repo, tmp_path, "--phases", "1")
    assert any(
        f["rule"] == "R2" and f["evidence"]["missing"] == ["packages"] for f in findings["findings"]
    )


def test_literal_count_and_unchanged_option_reference(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "src.py": 'SECTIONS = ("one", "two", "three")\ndef _preflight():\n    return 0\n',
            "guide.md": "Run `--preflight` before publishing.\n",
        },
    )
    edit_files_and_commit(
        repo,
        {
            "src.py": 'SECTIONS = ("one", "two", "three")\ndef _preflight():\n    return 1\n',
            "counts.md": "The two `SECTIONS` are required.\n",
        },
    )
    _code, findings, checklist = run_same_pr(repo, tmp_path, "--phases", "1")
    assert any(f["rule"] == "R4" for f in findings["findings"])
    entry = checklist_entry(checklist, "guide.md", "--preflight")
    assert any(p["symbol"] == "_preflight" for p in entry["pairs"])


def test_local_collection_does_not_bind_to_unrelated_prose(tmp_path: Path) -> None:
    script = "scripts/tool.py"
    repo = make_repo(tmp_path, {script: "", "guide.md": "# Guide\n"})
    edit_files_and_commit(
        repo,
        {
            script: 'git = ["git", "-c", "user.name=smoke"]\nclaims = []\n',
            "guide.md": "Use the `git` CLI for checks.\nThe one `claims` record is sufficient.\n",
        },
    )

    code, findings, _ = run_same_pr(repo, tmp_path, "--phases", "1")

    assert code == 0
    assert _rule(findings, "R2") == _rule(findings, "R4") == []


def test_repo_cardinality_reaches_markdown_templates_and_json(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"guide.md": "No counts.\n"})
    edit_files_and_commit(
        repo,
        {
            "guide.md": (
                "Four records are proposed: ADR-001, ADR-002, ADR-003, ADR-004, plus ADR-005.\n"
            ),
            "guide.tmpl": "The three checks: alpha, beta, gamma, delta.\n",
            "data.json": '{"reason": "these two PRs", "pull_requests": [1, 2, 3]}\n',
        },
    )
    _code, findings, _checklist = run_same_pr(repo, tmp_path, "--phases", "1")
    assert {(f["prose"]["file"], f["rule"]) for f in findings["findings"]} >= {
        ("guide.md", "nl-cardinality"),
        ("guide.tmpl", "nl-cardinality"),
        ("data.json", "structured-cardinality"),
    }


TMPL = "templates/skills/code-qualities-assessment.SKILL.md.tmpl"
ASSESS = "src/claude/skills/code-qualities-assessment/scripts/assess.py"
CSHARP_DOC = "src/claude/skills/code-qualities-assessment/references/csharp-parser.md"


def _rule(findings: Json, rule: str) -> list[Json]:
    return [f for f in findings["findings"] if f["rule"] == rule]


# -- #7451: language enumeration names a subset of the closed set --------------

EXIT_ROW_WRONG = (
    "| 1 | Script error (invalid args, unresolvable base, file not found, missing C# or "
    "TypeScript parser package, parser startup failure, or C#, TypeScript, or JavaScript "
    "the pinned grammar cannot parse) |"
)
EXIT_ROW_RIGHT = EXIT_ROW_WRONG.replace(
    "missing C# or TypeScript parser package",
    "missing C#, TypeScript, or JavaScript parser package",
)
EXIT_TABLE = (
    "### Exit Codes\n\n| Code | Meaning |\n|------|---------|\n"
    "| 0 | Gate passed |\n| 10 | Regression |\n"
)

GRAMMARS_BASE = """\
from dataclasses import dataclass


class ParserError(Exception):
    pass


class CSharpParserError(ParserError):
    pass


class TypeScriptParserError(ParserError):
    pass


@dataclass(frozen=True)
class _DependencyGrammar:
    language_name: str
    packages: str
    error: type


_CSHARP = _DependencyGrammar(
    language_name="C#", packages="tree-sitter-c-sharp", error=CSharpParserError
)
_TYPESCRIPT = _DependencyGrammar(
    language_name="TypeScript", packages="tree-sitter-typescript", error=TypeScriptParserError
)


def _count_dependency_nodes(source: str, grammar: _DependencyGrammar) -> int:
    try:
        import tree_sitter

        return len(tree_sitter.parse(source))
    except ParserError:
        raise
    except ImportError as exc:
        raise grammar.error(
            f"{grammar.language_name} parser packages are missing: {exc}. "
            f"Install {grammar.packages}"
        ) from exc
    except Exception as exc:
        raise grammar.error(
            f"{grammar.language_name} parser failed to start or run: {exc}"
        ) from exc
"""
GRAMMARS_HEAD = GRAMMARS_BASE.replace(
    "class TypeScriptParserError(ParserError):\n    pass\n",
    "class TypeScriptParserError(ParserError):\n    pass\n\n\n"
    "class JavaScriptParserError(ParserError):\n"
    '    """JavaScript dependencies cannot be measured reliably."""\n',
).replace(
    "\n\ndef _count_dependency_nodes",
    "\n_JAVASCRIPT = _DependencyGrammar(\n"
    '    language_name="JavaScript", packages="tree-sitter-typescript",'
    " error=JavaScriptParserError\n)\n\n\ndef _count_dependency_nodes",
)


def _grammar_repo(tmp_path: Path, exit_row: str) -> tuple[Path, str]:
    base_row = "| 1 | Script error (invalid args, unresolvable base) |"
    repo = make_repo(tmp_path, {TMPL: EXIT_TABLE + base_row + "\n", ASSESS: GRAMMARS_BASE})
    edit_files_and_commit(repo, {TMPL: EXIT_TABLE + exit_row + "\n", ASSESS: GRAMMARS_HEAD})
    return repo, EXIT_TABLE + exit_row + "\n"


def test_r2_flags_subset_of_languages_for_a_shared_raise_site(tmp_path: Path) -> None:
    repo, tmpl_text = _grammar_repo(tmp_path, EXIT_ROW_WRONG)

    code, findings, _ = run_same_pr(repo, tmp_path)

    (hit,) = _rule(findings, "R2")
    assert code == 10
    assert hit["severity"] == "high"
    assert hit["prose"]["file"] == TMPL
    assert hit["prose"]["line"] == line_of(tmpl_text, "missing C# or TypeScript")
    assert hit["code"]["file"] == ASSESS
    assert hit["code"]["line"] == line_of(GRAMMARS_HEAD, "except ImportError") + 1
    assert hit["evidence"]["named"] == ["C#", "TypeScript"]
    assert hit["evidence"]["missing"] == ["JavaScript"]


def test_r2_stays_quiet_when_the_clause_names_every_language(tmp_path: Path) -> None:
    repo, _ = _grammar_repo(tmp_path, EXIT_ROW_RIGHT)

    code, findings, _ = run_same_pr(repo, tmp_path)

    assert _rule(findings, "R2") == []
    assert code == 0


def test_r2_stays_quiet_without_a_shared_raise_site(tmp_path: Path) -> None:
    no_raise = GRAMMARS_HEAD.split("def _count_dependency_nodes")[0]
    repo = make_repo(tmp_path, {TMPL: EXIT_TABLE, ASSESS: GRAMMARS_BASE})
    edit_files_and_commit(repo, {TMPL: EXIT_TABLE + EXIT_ROW_WRONG + "\n", ASSESS: no_raise})

    _, findings, _ = run_same_pr(repo, tmp_path)

    assert _rule(findings, "R2") == []


# -- #7450: JSON key holds something the code never assigns to it --------------

CSHARP_LINE = (
    "JSON retains the regression under `parser_dependency_admission` and records the "
    "scoped maintainer authorization."
)
COMPARISON_BASE = (
    "from dataclasses import dataclass\n\n\n@dataclass\nclass Comparison:\n"
    '    verdict: str = "pass"\n'
)
COMPARISON_HEAD = (
    COMPARISON_BASE
    + "    parser_dependency_admission: dict | None = None\n\n\n"
    + "def _admit(comparison: Comparison, admission: dict) -> None:\n"
    + "    comparison.parser_dependency_admission = dict(admission)\n"
)


def _admission_repo(tmp_path: Path, prose: str) -> Path:
    repo = make_repo(tmp_path, {CSHARP_DOC: "# C# parser\n", ASSESS: COMPARISON_BASE})
    edit_files_and_commit(repo, {CSHARP_DOC: f"# C# parser\n\n{prose}\n", ASSESS: COMPARISON_HEAD})
    return repo


def test_r3_flags_noun_the_assigned_value_never_mentions(tmp_path: Path) -> None:
    repo = _admission_repo(tmp_path, CSHARP_LINE)

    code, findings, _ = run_same_pr(repo, tmp_path)

    (hit,) = _rule(findings, "R3")
    assert code == 10
    assert hit["prose"] == {"file": CSHARP_DOC, "line": 3, "text": CSHARP_LINE}
    assert hit["code"]["file"] == ASSESS
    assert hit["code"]["line"] == line_of(COMPARISON_HEAD, "comparison.parser_dependency")
    assert hit["evidence"]["key"] == "parser_dependency_admission"
    assert hit["evidence"]["noun"] == "regression"


def test_r3_stays_quiet_when_the_assigned_value_shares_the_nouns_stem(tmp_path: Path) -> None:
    prose = "JSON retains the admission under `parser_dependency_admission`."
    repo = _admission_repo(tmp_path, prose)

    code, findings, _ = run_same_pr(repo, tmp_path)

    assert _rule(findings, "R3") == []
    assert code == 0


def test_r3_ignores_a_placeholder_key_in_prose_that_describes_the_pattern(tmp_path: Path) -> None:
    prose = 'A line like "noun under `key`" names a noun the code never assigns.'
    head = (
        COMPARISON_HEAD + '\n\ndef _put(box: dict, key: str, t: str) -> None:\n    box["key"] = t\n'
    )
    repo = make_repo(tmp_path, {CSHARP_DOC: "# C# parser\n", ASSESS: COMPARISON_BASE})
    edit_files_and_commit(repo, {CSHARP_DOC: f"# C# parser\n\n{prose}\n", ASSESS: head})

    code, findings, _ = run_same_pr(repo, tmp_path)

    assert _rule(findings, "R3") == []
    assert code == 0


def test_r3_without_an_assignment_goes_to_the_checklist(tmp_path: Path) -> None:
    prose = "JSON retains the regression under `unassigned_key`."
    repo = _admission_repo(tmp_path, prose)

    code, findings, checklist = run_same_pr(repo, tmp_path)

    assert _rule(findings, "R3") == []
    assert code == 0
    entry = checklist_entry(checklist, CSHARP_DOC, "unassigned_key")
    assert any("unassigned_key" in reason for reason in entry["reasons"])


@pytest.mark.parametrize(
    ("prose", "ambiguous"),
    [
        ("The regression is under `parser_dependency_admission`.", False),
        ("JSON `parser_dependency_admission` keeps only admitted dependencies.", False),
        ("JSON retains the regression under `parser_dependency_admission`.", True),
    ],
)
def test_r3_leaves_non_json_or_ambiguous_claims_to_the_checklist(
    tmp_path: Path, prose: str, ambiguous: bool
) -> None:
    repo = make_repo(tmp_path, {CSHARP_DOC: "# C# parser\n", ASSESS: COMPARISON_BASE})
    changes = {CSHARP_DOC: f"# C# parser\n\n{prose}\n", ASSESS: COMPARISON_HEAD}
    if ambiguous:
        changes["another_writer.py"] = COMPARISON_HEAD
    edit_files_and_commit(repo, changes)

    code, findings, checklist = run_same_pr(repo, tmp_path)

    assert code == 0
    assert _rule(findings, "R3") == []
    assert checklist_entry(checklist, CSHARP_DOC, "parser_dependency_admission")


# -- R1: Exit Codes table against literal exit integers ------------------------

TOOL = "scripts/tool.py"


def _tool_source(doc_codes: list[int], code_codes: list[int]) -> str:
    doc = "".join(f"    {n}: meaning {n}\n" for n in doc_codes)
    body = "".join(f"    if flag == {n}:\n        return {n}\n" for n in code_codes)
    return (
        f'"""Tool.\n\nExit Codes:\n{doc}"""\n\n\ndef main(flag: int) -> int:\n{body}    return 0\n'
    )


def test_r1_flags_code_missing_from_the_docstring_table(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {TOOL: _tool_source([0, 1], [1])})
    edit_files_and_commit(repo, {TOOL: _tool_source([0, 1, 2], [1, 3])})

    code, findings, _ = run_same_pr(repo, tmp_path)

    (hit,) = _rule(findings, "R1")
    assert code == 10
    assert hit["severity"] == "high"
    assert hit["prose"]["file"] == TOOL
    assert hit["evidence"]["code_only"] == [3]
    assert hit["evidence"]["doc_only"] == [2]


def test_r1_stays_quiet_when_docstring_and_code_agree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {TOOL: _tool_source([0, 1], [1])})
    edit_files_and_commit(repo, {TOOL: _tool_source([0, 1, 2], [1, 2])})

    code, findings, _ = run_same_pr(repo, tmp_path)

    assert _rule(findings, "R1") == []
    assert code == 0


def test_r1_reads_a_markdown_table_when_the_doc_names_the_script(tmp_path: Path) -> None:
    doc = "docs/tool.md"

    def table(rows: list[int]) -> str:
        lines = "".join(f"| {n} | meaning {n} |\n" for n in rows)
        return f"# Tool\n\nRun `{TOOL}`.\n\n## Exit Codes\n\n| Code | Meaning |\n|---|---|\n{lines}"

    repo = make_repo(tmp_path, {doc: table([0]), TOOL: _tool_source([0], [])})
    edit_files_and_commit(repo, {doc: table([0, 1]), TOOL: _tool_source([0], [1, 4])})

    code, findings, _ = run_same_pr(repo, tmp_path)

    (hit,) = _rule(findings, "R1")
    assert code == 10
    assert hit["prose"]["file"] == doc
    assert hit["code"]["file"] == TOOL
    assert hit["evidence"]["code_only"] == [4]


def test_r1_ignores_a_table_when_no_script_is_identifiable(tmp_path: Path) -> None:
    doc = "docs/tool.md"
    repo = make_repo(tmp_path, {doc: "# T\n", TOOL: _tool_source([0], [])})
    table = "# T\n\n## Exit Codes\n\n| Code | Meaning |\n|---|---|\n| 0 | ok |\n| 7 | odd |\n"
    edit_files_and_commit(repo, {doc: table, TOOL: _tool_source([0], [1])})

    _, findings, _ = run_same_pr(repo, tmp_path)

    assert _rule(findings, "R1") == []
