"""``--same-pr`` mode: doc claims that drift from code changed in the same diff.

Each evidence fixture is a trimmed copy of a real miss: a base commit, then a head
commit holding the wrong prose beside the code it describes. The wrong states are
PR #7451 (916946a57e), #7450 (d856c06b0e), #6584 (926ad8185c), #6852 (579642032f)
and #7379 (ef0ac7bed7).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import Json, edit_files_and_commit, make_repo, run_same_pr


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


# -- #7484: two path members and "prefix" do not bind an unnamed collection -----

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
    entry = _entry(checklist, "guide.md", "--preflight")
    assert any(p["symbol"] == "_preflight" for p in entry["pairs"])


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


def _line_of(text: str, needle: str) -> int:
    """1-based line of the first line containing ``needle``."""
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not in fixture")


def _rule(findings: Json, rule: str) -> list[Json]:
    return [f for f in findings["findings"] if f["rule"] == rule]


def _entry(checklist: Json, path: str, needle: str) -> Json:
    hits = [e for e in checklist["entries"] if e["prose_file"] == path and needle in e["text"]]
    assert len(hits) == 1, [e["text"] for e in checklist["entries"]]
    return cast(Json, hits[0])


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
    assert hit["prose"]["line"] == _line_of(tmpl_text, "missing C# or TypeScript")
    assert hit["code"]["file"] == ASSESS
    assert hit["code"]["line"] == _line_of(GRAMMARS_HEAD, "except ImportError") + 1
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
    assert hit["code"]["line"] == _line_of(COMPARISON_HEAD, "comparison.parser_dependency")
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
    entry = _entry(checklist, CSHARP_DOC, "unassigned_key")
    assert any("unassigned_key" in reason for reason in entry["reasons"])


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

    entry = _entry(checklist, ADR_SCRIPT, "identical detection")
    assert code == 0 and findings["findings"] == []
    assert entry["prose_line"] == _line_of(ADR_HEAD, "identical detection")
    assert "identical" in entry["reasons"]
    pairs = {p["symbol"]: p for p in entry["pairs"]}
    assert {"_check", "_Dup"} <= set(pairs)
    assert pairs["_check"]["file"] == ADR_SCRIPT
    assert pairs["_check"]["line"] == _line_of(ADR_HEAD, "def _check")
    assert pairs["_Dup"]["line"] == _line_of(ADR_HEAD, "class _Dup")


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

    entry = _entry(checklist, GROWTH, "fifth run")
    assert entry["prose_line"] == _line_of(GROWTH_HEAD, "fifth run")
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

    entry = _entry(checklist, SEVERITY_DOC, "Only `critical` and `high`")
    assert code == 0 and findings["findings"] == []
    assert entry["prose_line"] == _line_of(SEVERITY_HEAD_DOC, "Only `critical`")
    assert {"only", "never"} <= set(entry["reasons"])
    assert {p["file"] for p in entry["pairs"]} == {SEVERITY_SCRIPT}
    assert all(p["line"] > 0 for p in entry["pairs"])
    # The contradicting rules live in unchanged files; the artifact says it cannot see them.
    assert any("unchanged" in limit for limit in checklist["limits"])
