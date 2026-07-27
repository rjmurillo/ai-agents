"""Tests for build/scripts/validate_agent_matrix_refs.py.

Covers the parser, the resolution check, the anti-vacuous structural guards,
and the CLI exit contract from ADR-035.

Two tests deliberately read the real repository rather than a fixture:
``test_repository_is_clean`` and ``test_every_tree_holding_agents_is_scanned``.
Anchoring an expectation in the filesystem instead of in the module's own
constants is what keeps the suite from adapting to a mutation of those
constants. A test parametrized over ``MATRIX_TREES`` would pass just as happily
if someone shrank ``MATRIX_TREES`` to a single entry.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_agent_matrix_refs as vamr  # noqa: E402

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


def _repo(tmp_path: Path, files: dict[str, str], agents: list[str]) -> Path:
    """Build a throwaway repo with the given matrix files and agent files."""
    agents_dir = tmp_path / "template_agents_placeholder"
    agents_dir.mkdir(exist_ok=True)
    name_source = tmp_path / vamr.AGENT_NAME_SOURCE
    name_source.mkdir(parents=True, exist_ok=True)
    for agent in agents:
        (name_source / f"{agent}.md").write_text(f"# {agent}\n", encoding="utf-8")
    for relative, body in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path


class TestParseMatrixRows:
    """Row extraction from markdown."""

    def test_bold_names_parse(self):
        rows = vamr.parse_matrix_rows(BOLD_MATRIX)
        assert [name for name, _ in rows] == ["analyst", "implementer"]

    def test_plain_names_parse(self):
        rows = vamr.parse_matrix_rows(PLAIN_MATRIX)
        assert [name for name, _ in rows] == ["skillbook", "explainer"]

    def test_line_numbers_are_one_based(self):
        rows = vamr.parse_matrix_rows(BOLD_MATRIX)
        assert rows[0][1] == 5
        assert BOLD_MATRIX.splitlines()[4].startswith("| **analyst**")

    def test_multiple_matrices_in_one_file_all_parse(self):
        rows = vamr.parse_matrix_rows(BOLD_MATRIX + "\n" + PLAIN_MATRIX)
        assert [name for name, _ in rows] == [
            "analyst",
            "implementer",
            "skillbook",
            "explainer",
        ]

    def test_table_without_agent_header_is_ignored(self):
        other = (
            "| Skill | Use For |\n"
            "|-------|---------|\n"
            "| **memory** | Recall |\n"
        )
        assert vamr.parse_matrix_rows(other) == []

    def test_matrix_ends_at_first_non_pipe_line(self):
        text = BOLD_MATRIX + "\nSome prose.\n\n| **stray** | not a row |\n"
        assert [name for name, _ in vamr.parse_matrix_rows(text)] == [
            "analyst",
            "implementer",
        ]

    def test_missing_separator_row_still_parses(self):
        text = "| Agent | Role |\n| **analyst** | Research |\n"
        assert [name for name, _ in vamr.parse_matrix_rows(text)] == ["analyst"]

    def test_header_at_end_of_file_yields_nothing(self):
        assert vamr.parse_matrix_rows("| Agent | Role |") == []

    def test_empty_text_yields_nothing(self):
        assert vamr.parse_matrix_rows("") == []

    @pytest.mark.parametrize(
        "cell",
        ["| **Analyst** |", "| Analyst |", "| _analyst_ |", "| 	 |", "|  |"],
    )
    def test_non_kebab_first_cells_do_not_parse(self, cell):
        text = f"| Agent | Role |\n|---|---|\n{cell} x |\n"
        assert vamr.parse_matrix_rows(text) == []

    def test_dotted_and_underscored_names_parse(self):
        text = "| Agent | Role |\n|---|---|\n| review-pr.prompt | x |\n"
        assert [name for name, _ in vamr.parse_matrix_rows(text)] == [
            "review-pr.prompt"
        ]


class TestHasMatrixHeader:
    """Header detection used to separate parse gaps from ordinary files."""

    def test_detects_header(self):
        assert vamr.has_matrix_header(BOLD_MATRIX)

    def test_rejects_file_without_header(self):
        assert not vamr.has_matrix_header("# Title\n\nSome prose.\n")

    def test_rejects_similar_header(self):
        assert not vamr.has_matrix_header("| Agents | Role |\n")


class TestKnownAgents:
    """Resolution of the agent name source."""

    def test_reads_stems(self, tmp_path):
        _repo(tmp_path, {}, ["analyst", "qa"])
        assert vamr.known_agents(tmp_path) == {"analyst", "qa"}

    def test_uppercase_instruction_files_are_excluded(self, tmp_path):
        _repo(tmp_path, {}, ["analyst"])
        (tmp_path / vamr.AGENT_NAME_SOURCE / "AGENTS.md").write_text("x", "utf-8")
        (tmp_path / vamr.AGENT_NAME_SOURCE / "CLAUDE.md").write_text("x", "utf-8")
        assert vamr.known_agents(tmp_path) == {"analyst"}

    def test_missing_source_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            vamr.known_agents(tmp_path)

    def test_empty_source_returns_empty_set(self, tmp_path):
        (tmp_path / vamr.AGENT_NAME_SOURCE).mkdir(parents=True)
        assert vamr.known_agents(tmp_path) == set()


class TestScanAndViolations:
    """End-to-end resolution over a synthetic repo."""

    def test_resolved_names_produce_no_violations(self, tmp_path):
        root = _repo(
            tmp_path,
            {"templates/agents/orchestrator.shared.md": BOLD_MATRIX},
            ["analyst", "implementer"],
        )
        result = vamr.scan(root)
        assert len(result.citations) == 2
        assert vamr.violations(result, vamr.known_agents(root)) == []

    def test_unresolved_name_is_a_violation(self, tmp_path):
        root = _repo(
            tmp_path,
            {"templates/agents/orchestrator.shared.md": BOLD_MATRIX},
            ["analyst"],
        )
        bad = vamr.violations(root and vamr.scan(root), vamr.known_agents(root))
        assert [c.name for c in bad] == ["implementer"]
        assert bad[0].path == Path("templates/agents/orchestrator.shared.md")
        assert bad[0].line == 6

    def test_violation_reported_once_per_site(self, tmp_path):
        root = _repo(
            tmp_path,
            {
                "templates/agents/orchestrator.shared.md": BOLD_MATRIX,
                ".github/agents/orchestrator.agent.md": BOLD_MATRIX,
            },
            ["analyst"],
        )
        bad = vamr.violations(vamr.scan(root), vamr.known_agents(root))
        assert len(bad) == 2
        assert {str(c.path) for c in bad} == {
            "templates/agents/orchestrator.shared.md",
            ".github/agents/orchestrator.agent.md",
        }

    def test_absent_tree_is_skipped_not_failed(self, tmp_path):
        root = _repo(
            tmp_path,
            {"templates/agents/orchestrator.shared.md": BOLD_MATRIX},
            ["analyst", "implementer"],
        )
        result = vamr.scan(root)
        assert Path("src/vs-code-agents") not in result.trees_scanned
        assert result.degeneracy() == []

    def test_files_without_a_matrix_are_not_counted(self, tmp_path):
        root = _repo(
            tmp_path,
            {
                "templates/agents/orchestrator.shared.md": BOLD_MATRIX,
                "templates/agents/analyst.shared.md": "# analyst\n\nprose\n",
            },
            ["analyst", "implementer"],
        )
        result = vamr.scan(root)
        assert result.files_with_matrix == [
            Path("templates/agents/orchestrator.shared.md")
        ]


class TestAntiVacuousGuards:
    """A scan that finds nothing must not report success."""

    def test_tree_holding_only_agent_files_is_not_degenerate(self, tmp_path):
        """A tree with no routing table is valid, not a failure."""
        root = _repo(
            tmp_path,
            {
                "templates/agents/orchestrator.shared.md": BOLD_MATRIX,
                ".github/agents/analyst.agent.md": "# analyst\n\nprose\n",
            },
            ["analyst", "implementer"],
        )
        assert vamr.scan(root).degeneracy() == []

    def test_no_matrix_anywhere_is_degenerate(self, tmp_path):
        root = _repo(
            tmp_path,
            {"templates/agents/analyst.shared.md": "# analyst\n\nprose\n"},
            ["analyst"],
        )
        reasons = vamr.scan(root).degeneracy()
        assert len(reasons) == 1
        assert "no capability matrix found in any scanned tree" in reasons[0]

    def test_matrix_outside_the_canonical_tree_only_is_degenerate(self, tmp_path):
        """Copies without a canonical source mean the scan lost the source."""
        root = _repo(
            tmp_path,
            {".github/agents/orchestrator.agent.md": BOLD_MATRIX},
            ["analyst", "implementer"],
        )
        reasons = vamr.scan(root).degeneracy()
        assert len(reasons) == 1
        assert str(vamr.CANONICAL_TREE) in reasons[0]

    def test_canonical_degeneracy_fails_the_cli(self, tmp_path):
        _repo(
            tmp_path,
            {".github/agents/orchestrator.agent.md": BOLD_MATRIX},
            ["analyst", "implementer"],
        )
        assert vamr.main(["--repo-root", str(tmp_path)]) == 1

    def test_header_present_but_no_rows_is_a_parse_gap(self, tmp_path):
        root = _repo(
            tmp_path,
            {"templates/agents/x.shared.md": "| Agent | Role |\n|---|---|\n"},
            ["analyst"],
        )
        result = vamr.scan(root)
        assert result.parse_gaps == [Path("templates/agents/x.shared.md")]

    def test_parse_gap_fails_the_cli_even_with_no_violations(self, tmp_path):
        _repo(
            tmp_path,
            {"templates/agents/x.shared.md": "| Agent | Role |\n|---|---|\n"},
            ["analyst"],
        )
        assert vamr.main(["--repo-root", str(tmp_path)]) == 1

    def test_no_matrix_anywhere_fails_the_cli(self, tmp_path):
        _repo(
            tmp_path,
            {"templates/agents/analyst.shared.md": "prose only\n"},
            ["analyst"],
        )
        assert vamr.main(["--repo-root", str(tmp_path)]) == 1


class TestMainCli:
    """ADR-035 exit contract."""

    def test_clean_repo_exits_zero(self, tmp_path):
        _repo(
            tmp_path,
            {"templates/agents/orchestrator.shared.md": BOLD_MATRIX},
            ["analyst", "implementer"],
        )
        assert vamr.main(["--repo-root", str(tmp_path)]) == 0

    def test_violation_exits_one(self, tmp_path):
        _repo(
            tmp_path,
            {"templates/agents/orchestrator.shared.md": BOLD_MATRIX},
            ["analyst"],
        )
        assert vamr.main(["--repo-root", str(tmp_path)]) == 1

    def test_missing_name_source_exits_two(self, tmp_path):
        (tmp_path / "templates" / "agents").mkdir(parents=True)
        assert vamr.main(["--repo-root", str(tmp_path)]) == 2

    def test_violation_names_the_agent_and_site(self, tmp_path, capsys):
        _repo(
            tmp_path,
            {"templates/agents/orchestrator.shared.md": BOLD_MATRIX},
            ["analyst"],
        )
        vamr.main(["--repo-root", str(tmp_path)])
        out = capsys.readouterr().out
        assert "unknown agent 'implementer'" in out
        assert "templates/agents/orchestrator.shared.md:6" in out

    def test_clean_run_names_what_it_looked_at(self, tmp_path, capsys):
        _repo(
            tmp_path,
            {"templates/agents/orchestrator.shared.md": BOLD_MATRIX},
            ["analyst", "implementer"],
        )
        vamr.main(["--repo-root", str(tmp_path)])
        out = capsys.readouterr().out
        assert "Rows cited:             2" in out
        assert "Files carrying matrix:  1" in out


class TestRealRepository:
    """Filesystem-anchored expectations. These do not read the module constants."""

    def test_repository_is_clean(self):
        assert vamr.main(["--repo-root", str(REPO_ROOT)]) == 0

    def test_every_tree_holding_agents_is_scanned(self):
        """Any directory shipping agent markdown must be in MATRIX_TREES.

        Anchored on the filesystem, not on MATRIX_TREES, so shrinking that
        constant fails this test instead of silently narrowing the scan. The
        day a new agent tree appears, this fails and names it.
        """
        candidates = {
            Path("templates/agents"),
            Path(".claude/agents"),
            Path(".github/agents"),
            Path("src/claude"),
            Path("src/copilot-cli/agents"),
            Path("src/vs-code-agents"),
        }
        present = {c for c in candidates if (REPO_ROOT / c).is_dir()}
        assert present, "no agent trees found; the repo layout changed"
        missing = present - set(vamr.MATRIX_TREES)
        assert not missing, f"agent trees absent from MATRIX_TREES: {sorted(missing)}"

    def test_orchestrator_matrix_is_actually_scanned(self):
        """Guards against the scan silently missing the largest matrix."""
        result = vamr.scan(REPO_ROOT)
        assert Path("templates/agents/orchestrator.shared.md") in result.files_with_matrix
        cited = {c.name for c in result.citations}
        assert "implementer" in cited
        assert len(cited) > 10
