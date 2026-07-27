"""Tests for build/scripts/validate_agent_matrix_refs.py.

Covers the parser, per-tree resolution, the anti-vacuous structural guards, and
the CLI exit contract from ADR-035.

Three tests deliberately read the real repository rather than a fixture:
``test_repository_is_clean``, ``test_every_tree_holding_agents_is_scanned``, and
``test_every_configured_tree_yields_agents``. Anchoring an expectation in the
filesystem instead of in the module's own constants is what keeps the suite from
adapting to a mutation of those constants. A test parametrized over
``AGENT_TREES`` would pass just as happily if someone shrank ``AGENT_TREES`` to
a single entry, or changed a suffix so a tree silently yielded no agents.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_agent_matrix_refs as vamr  # noqa: E402

CANONICAL = str(vamr.CANONICAL_TREE)

BOLD_MATRIX = """\
## Agent Capability Matrix

| Agent | Use For | Model | Avoid When |
|-------|---------|-------|-----------|
| **analyst** | Research | sonnet | Have context |
| **implementer** | Code | sonnet | Design open |
"""

PLAIN_MATRIX = """\
### Support Agents

| Agent | File | Role |
|-------|------|------|
| skillbook | `skillbook.md` | Skill management |
| explainer | `explainer.md` | Docs |
"""

BACKTICK_MATRIX = """\
### Coded Names

| Agent | Role |
|-------|------|
| `analyst` | Research |
"""

BOLD_HEADER_MATRIX = """\
### Bold Header

| **Agent** | Role |
|-----------|------|
| **analyst** | Research |
"""


def _suffix_for(tree: str) -> str:
    """Return the configured filename suffix for a tree, by path string."""
    for path, suffix in vamr.AGENT_TREES:
        if str(path) == tree:
            return suffix
    raise AssertionError(f"{tree} is not a configured agent tree")


def _repo(
    tmp_path: Path,
    files: dict[str, str],
    agents_by_tree: dict[str, list[str]],
) -> Path:
    """Build a throwaway repo.

    ``agents_by_tree`` maps a configured tree path to the agent names that tree
    ships. Each name is written using that tree's own suffix, because the
    suffix is what the validator strips to derive a name. A tree absent from
    the mapping is not created at all, which the validator skips.
    """
    for tree, names in agents_by_tree.items():
        suffix = _suffix_for(tree)
        directory = tmp_path / tree
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            (directory / f"{name}{suffix}").write_text(f"# {name}\n", encoding="utf-8")
    for relative, body in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path


def _canonical_file(name: str) -> str:
    """Return a path inside the canonical tree using its configured suffix."""
    return f"{CANONICAL}/{name}{_suffix_for(CANONICAL)}"


class TestParseMatrixRows:
    """Row extraction from markdown."""

    def test_bold_names_parse(self):
        rows, _ = vamr.parse_matrix_rows(BOLD_MATRIX)
        assert [name for name, _ in rows] == ["analyst", "implementer"]

    def test_plain_names_parse(self):
        rows, _ = vamr.parse_matrix_rows(PLAIN_MATRIX)
        assert [name for name, _ in rows] == ["skillbook", "explainer"]

    def test_backtick_wrapped_names_parse(self):
        """A code-formatted name is still a routing target, not a comment.

        Leaving it unparsed is how a phantom row hid from the first version of
        this validator: the file produced other rows, so no gap was visible.
        """
        rows, unparsed = vamr.parse_matrix_rows(BACKTICK_MATRIX)
        assert [name for name, _ in rows] == ["analyst"]
        assert unparsed == []

    def test_bold_header_is_recognized(self):
        """A bolded header must not drop the whole table out of the scan."""
        rows, _ = vamr.parse_matrix_rows(BOLD_HEADER_MATRIX)
        assert [name for name, _ in rows] == ["analyst"]

    def test_line_numbers_are_one_based(self):
        rows, _ = vamr.parse_matrix_rows(BOLD_MATRIX)
        assert rows[0][1] == 5
        assert BOLD_MATRIX.splitlines()[4].startswith("| **analyst**")

    def test_multiple_matrices_in_one_file_all_parse(self):
        rows, _ = vamr.parse_matrix_rows(BOLD_MATRIX + "\n" + PLAIN_MATRIX)
        assert [name for name, _ in rows] == [
            "analyst",
            "implementer",
            "skillbook",
            "explainer",
        ]

    def test_table_ends_at_first_non_pipe_line(self):
        text = BOLD_MATRIX + "\nSome prose.\n\n| notatable | x |\n"
        rows, _ = vamr.parse_matrix_rows(text)
        assert [name for name, _ in rows] == ["analyst", "implementer"]

    def test_rows_outside_a_matrix_are_ignored(self):
        text = "| Tool | Purpose |\n|------|---------|\n| ripgrep | search |\n"
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert rows == []
        assert unparsed == []

    def test_separator_row_is_not_treated_as_data(self):
        rows, unparsed = vamr.parse_matrix_rows(BOLD_MATRIX)
        assert len(rows) == 2
        assert unparsed == []

    def test_unparsed_data_row_is_reported_not_skipped(self):
        text = (
            "| Agent | Role |\n"
            "|-------|------|\n"
            "| **analyst** | Research |\n"
            "| TODO fill this in | Unknown |\n"
        )
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert [name for name, _ in rows] == ["analyst"]
        assert len(unparsed) == 1
        assert unparsed[0][0] == 4

    def test_dotted_and_underscored_names_parse(self):
        text = "| Agent | Role |\n|---|---|\n| pr-comment-responder.prompt | x |\n"
        rows, _ = vamr.parse_matrix_rows(text)
        assert [name for name, _ in rows] == ["pr-comment-responder.prompt"]

    @pytest.mark.parametrize("cell", ["|  |", "| \t |"])
    def test_blank_first_cells_do_not_yield_a_name(self, cell):
        text = f"| Agent | Role |\n|---|---|\n{cell} x |\n"
        rows, _ = vamr.parse_matrix_rows(text)
        assert rows == []


class TestKnownAgents:
    """Per-tree roster derivation."""

    def test_strips_the_configured_suffix(self, tmp_path):
        (tmp_path / "analyst.agent.md").write_text("x", encoding="utf-8")
        (tmp_path / "critic.agent.md").write_text("x", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".agent.md") == {"analyst", "critic"}

    def test_files_not_matching_the_suffix_are_excluded(self, tmp_path):
        """``copilot-instructions.md`` is not an agent in an ``.agent.md`` tree."""
        (tmp_path / "analyst.agent.md").write_text("x", encoding="utf-8")
        (tmp_path / "copilot-instructions.md").write_text("x", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".agent.md") == {"analyst"}

    def test_shared_suffix_is_stripped_whole(self, tmp_path):
        (tmp_path / "orchestrator.shared.md").write_text("x", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".shared.md") == {"orchestrator"}

    def test_uppercase_instruction_files_are_excluded(self, tmp_path):
        (tmp_path / "analyst.md").write_text("x", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("x", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    def test_empty_directory_returns_empty_set(self, tmp_path):
        assert vamr.known_agents(tmp_path, ".md") == set()


class TestPerTreeResolution:
    """Resolution is scoped to the tree that carries the citation.

    This is the defect an adversarial review found in the first version. A
    global roster answers "does this name exist anywhere", but the plugin roots
    install standalone, so the load-bearing question is whether the name exists
    in the install that publishes the table.
    """

    def test_name_shipped_in_its_own_tree_is_clean(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
        )
        assert vamr.violations(vamr.scan(repo)) == []

    def test_name_missing_from_its_own_tree_is_a_violation(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst"]},
        )
        bad = vamr.violations(vamr.scan(repo))
        assert [c.name for c in bad] == ["implementer"]

    def test_presence_in_a_sibling_tree_does_not_satisfy_a_citation(self, tmp_path):
        """The exact shape of the quality-auditor defect.

        One tree ships the agent, another cites it without shipping it. A
        repository-wide roster reports success here; a per-tree roster does not.
        """
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): BOLD_MATRIX,
                ".claude/agents/orchestrator.md": BOLD_MATRIX,
            },
            {
                CANONICAL: ["analyst", "implementer"],
                ".claude/agents": ["analyst"],
            },
        )
        bad = vamr.violations(vamr.scan(repo))
        assert len(bad) == 1
        assert bad[0].name == "implementer"
        assert str(bad[0].tree) == ".claude/agents"

    def test_violation_records_the_tree_that_lacks_the_agent(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst"]},
        )
        bad = vamr.violations(vamr.scan(repo))
        assert str(bad[0].tree) == CANONICAL

    def test_violation_reported_once_per_site(self, tmp_path):
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): BOLD_MATRIX,
                _canonical_file("planner"): BOLD_MATRIX,
            },
            {CANONICAL: ["analyst"]},
        )
        bad = vamr.violations(vamr.scan(repo))
        assert len(bad) == 2
        assert {str(c.path) for c in bad} == {
            _canonical_file("orchestrator"),
            _canonical_file("planner"),
        }

    def test_absent_tree_is_skipped_not_failed(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
        )
        result = vamr.scan(repo)
        assert [str(t) for t in result.trees_scanned] == [CANONICAL]
        assert vamr.violations(result) == []

    def test_files_without_a_matrix_are_not_counted(self, tmp_path):
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): BOLD_MATRIX,
                f"{CANONICAL}/notes.md": "# Notes\n\nNo table here.\n",
            },
            {CANONICAL: ["analyst", "implementer"]},
        )
        result = vamr.scan(repo)
        assert len(result.files_with_matrix) == 1


class TestAntiVacuousGuards:
    """A scan that silently finds nothing must fail, not pass."""

    def test_no_matrix_anywhere_is_degenerate(self, tmp_path):
        repo = _repo(
            tmp_path,
            {f"{CANONICAL}/notes.md": "# Notes\n"},
            {CANONICAL: ["analyst"]},
        )
        reasons = vamr.scan(repo).degeneracy()
        assert any("no capability matrix found in any" in r for r in reasons)

    def test_matrix_outside_the_canonical_tree_only_is_degenerate(self, tmp_path):
        repo = _repo(
            tmp_path,
            {".claude/agents/orchestrator.md": BOLD_MATRIX},
            {CANONICAL: ["analyst"], ".claude/agents": ["analyst", "implementer"]},
        )
        reasons = vamr.scan(repo).degeneracy()
        assert any(CANONICAL in r for r in reasons)

    def test_header_present_but_no_rows_is_a_parse_gap(self, tmp_path):
        text = "| Agent | Role |\n|-------|------|\n\nProse.\n"
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): text},
            {CANONICAL: ["analyst"]},
        )
        reasons = vamr.scan(repo).degeneracy()
        assert any("no rows parsed" in r for r in reasons)

    def test_unparsed_row_inside_a_matrix_is_degenerate(self, tmp_path):
        text = (
            "| Agent | Role |\n"
            "|-------|------|\n"
            "| **analyst** | Research |\n"
            "| TODO fill this in | Unknown |\n"
        )
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): text},
            {CANONICAL: ["analyst", "orchestrator"]},
        )
        reasons = vamr.scan(repo).degeneracy()
        assert any("does not parse as an agent name" in r for r in reasons)

    def test_tree_present_but_yielding_no_agents_is_degenerate(self, tmp_path):
        """A suffix that stops matching makes every citation resolve to nothing."""
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
        )
        (repo / ".claude" / "agents").mkdir(parents=True)
        (repo / ".claude" / "agents" / "README.rst").write_text("x", encoding="utf-8")
        reasons = vamr.scan(repo).degeneracy()
        assert any("yields no agent files" in r for r in reasons)

    def test_tree_holding_only_agent_files_is_not_degenerate(self, tmp_path):
        """A tree with definitions and no routing table is a valid state.

        An earlier version required every scanned tree to yield a matrix. That
        is not an invariant and fired on correct repositories, so the rule was
        narrowed to conditions that are unambiguously degenerate.
        """
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {
                CANONICAL: ["analyst", "implementer"],
                ".claude/agents": ["analyst", "implementer"],
            },
        )
        assert vamr.scan(repo).degeneracy() == []

    def test_no_matrix_anywhere_fails_the_cli(self, tmp_path, capsys):
        repo = _repo(
            tmp_path,
            {f"{CANONICAL}/notes.md": "# Notes\n"},
            {CANONICAL: ["analyst"]},
        )
        assert vamr.main(["--repo-root", str(repo)]) == 1
        assert "ERROR" in capsys.readouterr().out

    def test_canonical_degeneracy_fails_the_cli(self, tmp_path):
        repo = _repo(
            tmp_path,
            {".claude/agents/orchestrator.md": BOLD_MATRIX},
            {CANONICAL: ["analyst"], ".claude/agents": ["analyst", "implementer"]},
        )
        assert vamr.main(["--repo-root", str(repo)]) == 1

    def test_parse_gap_fails_the_cli_even_with_no_violations(self, tmp_path):
        text = "| Agent | Role |\n|-------|------|\n\nProse.\n"
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): BOLD_MATRIX,
                _canonical_file("planner"): text,
            },
            {CANONICAL: ["analyst", "implementer", "orchestrator", "planner"]},
        )
        result = vamr.scan(repo)
        assert vamr.violations(result) == []
        assert vamr.main(["--repo-root", str(repo)]) == 1

    def test_empty_tree_fails_the_cli_even_with_no_violations(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
        )
        (repo / ".claude" / "agents").mkdir(parents=True)
        (repo / ".claude" / "agents" / "README.rst").write_text("x", encoding="utf-8")
        assert vamr.violations(vamr.scan(repo)) == []
        assert vamr.main(["--repo-root", str(repo)]) == 1


class TestMainCli:
    """Exit contract from ADR-035."""

    def test_clean_repo_exits_zero(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
        )
        assert vamr.main(["--repo-root", str(repo)]) == 0

    def test_violation_exits_one(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst"]},
        )
        assert vamr.main(["--repo-root", str(repo)]) == 1

    def test_no_agents_anywhere_exits_two(self, tmp_path, capsys):
        """No roster at all is a configuration error, not a flood of violations."""
        repo = _repo(tmp_path, {f"{CANONICAL}/notes.md": "# Notes\n"}, {CANONICAL: []})
        assert vamr.main(["--repo-root", str(repo)]) == 2
        assert "CONFIG ERROR" in capsys.readouterr().err

    def test_violation_names_the_agent_the_site_and_the_tree(self, tmp_path, capsys):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst"]},
        )
        vamr.main(["--repo-root", str(repo)])
        out = capsys.readouterr().out
        assert "implementer" in out
        assert "orchestrator" in out
        assert CANONICAL in out

    def test_clean_run_names_what_it_looked_at(self, tmp_path, capsys):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
        )
        vamr.main(["--repo-root", str(repo)])
        out = capsys.readouterr().out
        assert "Rows cited:" in out
        assert "Trees scanned:" in out


class TestRealRepository:
    """Filesystem-anchored checks. These do not read the module's constants."""

    def test_repository_is_clean(self):
        assert vamr.main(["--repo-root", str(REPO_ROOT)]) == 0

    def test_every_tree_holding_agents_is_scanned(self):
        """Guard against a tree being dropped from ``AGENT_TREES``.

        The expectation is discovered on disk, not read from the constant under
        test. A test that iterated ``AGENT_TREES`` would pass just as happily
        after someone shrank it, which is the mutation this exists to kill.
        """
        expected = {
            "templates/agents",
            ".claude/agents",
            ".github/agents",
            "src/claude",
            "src/copilot-cli/agents",
            "src/vs-code-agents",
        }
        on_disk = {name for name in expected if (REPO_ROOT / name).is_dir()}
        assert on_disk, "no agent tree found on disk; the fixture list is stale"
        configured = {str(tree) for tree, _ in vamr.AGENT_TREES}
        assert on_disk <= configured

    def test_every_configured_tree_yields_agents(self):
        """Guard against a suffix that stops matching what a tree ships.

        A wrong suffix yields an empty roster, and an empty roster makes every
        citation in that tree look broken or, before the degeneracy guard, makes
        the tree silently contribute nothing.
        """
        result = vamr.scan(REPO_ROOT)
        assert result.trees_scanned, "no configured tree exists on disk"
        for tree in result.trees_scanned:
            assert result.agents_by_tree[tree], f"{tree} yielded no agent names"

    def test_orchestrator_matrix_is_scanned(self):
        """The matrix this validator was written for must be in the results."""
        result = vamr.scan(REPO_ROOT)
        names = {str(p) for p in result.files_with_matrix}
        assert any("orchestrator" in n for n in names)
