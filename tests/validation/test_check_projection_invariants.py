"""Golden-task suite for ADR-107 projection invariants 6 and 8 (issue #5687).

Asserted: invariant 6 (``allowed-tools`` set) for ``push-pr`` and invariant 8
(``## Exit Codes`` table) for ``security-scan``, comparing the committed
``.claude/skills`` source with the committed ``src/copilot-cli/skills``
projection.

Out of scope, on purpose. Invariants 1 (ordered steps), 2 (completion
criteria), 3 (evidence requirements), 4 (failure states), 5 (approval gates),
and 7 (idempotence and rollback) are prose with no extractor. The body
transform in ``build/scripts/copilot_body_translation.py`` cannot reorder
steps, delete a criterion, or change an exit code, so a suite that reported
them green would measure nothing. Their absence from this file is not
coverage. They stay advisory until ADR-107 names a machine-readable
representation.

Each asserted invariant has a negative-control fixture built from the real
committed source with that invariant dropped from the projection. Each must
fail. The real-tree test reads committed files and never calls the generator,
so it does not agree with the generator by construction.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_projection_invariants.py"
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
import check_projection_invariants as cpi

SOURCE = ".claude/skills"
PROJECTION = "src/copilot-cli/skills"


def _read_real(root: str, skill: str) -> str:
    return (REPO_ROOT / root / skill / "SKILL.md").read_text(encoding="utf-8")


def _make_repo(
    tmp_path: Path, push_pr_projection: str | None = None, scan_projection: str | None = None
) -> Path:
    """Copy the real committed pilot files into tmp_path, optionally mutating."""
    projections = {"push-pr": push_pr_projection, "security-scan": scan_projection}
    for skill, override in projections.items():
        for root in (SOURCE, PROJECTION):
            target = tmp_path / root / skill / "SKILL.md"
            target.parent.mkdir(parents=True)
            text = _read_real(root, skill)
            if root == PROJECTION and override is not None:
                text = override
            target.write_text(text, encoding="utf-8")
    return tmp_path


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(_SCRIPT), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )


FM = "---\nname: x\nallowed-tools: {tools}\n---\nbody\n"
EXIT = "# T\n\n## Exit Codes\n\n| Code | Meaning |\n|---|---|\n{rows}\n\n## Next\n"


class TestParseAllowedTools:
    def test_inline_comma_list(self) -> None:
        assert cpi.parse_allowed_tools(FM.format(tools="Read, Grep")) == {"Read", "Grep"}

    def test_commas_inside_parentheses_do_not_split(self) -> None:
        text = FM.format(tools="Bash(git a,b:*), Read")
        assert cpi.parse_allowed_tools(text) == {"Bash(git a,b:*)", "Read"}

    def test_block_list(self) -> None:
        text = "---\nallowed-tools:\n  - Read\n  - Grep\nname: x\n---\n"
        assert cpi.parse_allowed_tools(text) == {"Read", "Grep"}

    def test_comment_lines_between_keys_are_ignored(self) -> None:
        text = "---\nallowed-tools: Read\n# note: Bash\nname: x\n---\n"
        assert cpi.parse_allowed_tools(text) == {"Read"}

    def test_crlf_frontmatter(self) -> None:
        text = "---\r\nallowed-tools: Read, Grep\r\n---\r\n"
        assert cpi.parse_allowed_tools(text) == {"Read", "Grep"}

    @pytest.mark.parametrize("text", ["", "no frontmatter", "---\nname: x\n---\n", "---\nunclosed"])
    def test_absent_returns_empty(self, text: str) -> None:
        assert cpi.parse_allowed_tools(text) == frozenset()

    def test_key_after_closing_marker_is_not_frontmatter(self) -> None:
        assert cpi.parse_allowed_tools("---\nname: x\n---\nallowed-tools: Read\n") == frozenset()


class TestCountAllowedToolsKeys:
    def test_one_key(self) -> None:
        assert cpi.count_allowed_tools_keys(FM.format(tools="Read")) == 1

    def test_repeated_key_counts_each(self) -> None:
        text = "---\nname: x\nallowed-tools: Read\nallowed-tools: Read, Bash\n---\nbody\n"
        assert cpi.count_allowed_tools_keys(text) == 2

    def test_none(self) -> None:
        assert cpi.count_allowed_tools_keys("---\nname: x\n---\n") == 0

    def test_indented_key_and_body_key_do_not_count(self) -> None:
        text = (
            "---\nname: x\nmeta:\n  allowed-tools: Bash\nallowed-tools: Read\n---\n"
            "allowed-tools: Bash\n"
        )
        assert cpi.count_allowed_tools_keys(text) == 1


class TestParseExitCodes:
    def test_reads_rows(self) -> None:
        text = EXIT.format(rows="| 0 | ok |\n| 10 | bad   news |")
        assert cpi.parse_exit_codes(text) == {"0": "ok", "10": "bad news"}

    def test_keeps_every_cell_after_the_code(self) -> None:
        text = EXIT.format(rows="| 10 | Vulns  found | Fail |")
        assert cpi.parse_exit_codes(text) == {"10": "Vulns found | Fail"}

    def test_stops_at_next_heading(self) -> None:
        text = EXIT.format(rows="| 0 | ok |") + "| 9 | leaked |\n"
        assert cpi.parse_exit_codes(text) == {"0": "ok"}

    def test_no_section(self) -> None:
        assert cpi.parse_exit_codes("# T\n\n| 0 | ok |\n") == {}

    def test_non_numeric_and_short_rows_skipped(self) -> None:
        text = EXIT.format(rows="| x | no |\n| 1 |\nprose\n| 2 | yes |")
        assert cpi.parse_exit_codes(text) == {"2": "yes"}

    def test_heading_case_insensitive(self) -> None:
        assert cpi.parse_exit_codes("## exit codes\n| 0 | ok |\n") == {"0": "ok"}

    def test_reads_every_section(self) -> None:
        text = EXIT.format(rows="| 0 | ok |") + "\n## Exit Codes\n\n| 9 | later |\n"
        assert cpi.parse_exit_codes(text) == {"0": "ok", "9": "later"}


class TestExitCodeDuplicates:
    def test_clean_table(self) -> None:
        assert cpi.exit_code_duplicates(EXIT.format(rows="| 0 | ok |\n| 1 | err |")) == []

    def test_no_section(self) -> None:
        assert cpi.exit_code_duplicates("# T\n") == []

    def test_repeated_row(self) -> None:
        problems = cpi.exit_code_duplicates(EXIT.format(rows="| 0 | ok |\n| 0 | changed |"))
        assert problems == ["lists exit code 0 2 times"]

    def test_second_heading(self) -> None:
        text = EXIT.format(rows="| 0 | ok |") + "\n## Exit Codes\n\n| 1 | err |\n"
        assert cpi.exit_code_duplicates(text) == [
            "declares 2 Exit Codes sections; the comparison needs one"
        ]

    def test_second_heading_repeating_a_code_reports_both(self) -> None:
        text = EXIT.format(rows="| 0 | ok |") + "\n## exit codes\n\n| 0 | other |\n"
        assert len(cpi.exit_code_duplicates(text)) == 2


class TestCheckTools:
    def test_equal_sets_pass(self) -> None:
        text = FM.format(tools="Read, Bash(git add:*)")
        assert cpi.check_tools(text, FM.format(tools="Bash(git add:*), Read")) == []

    def test_dropped_entry_fails(self) -> None:
        problems = cpi.check_tools(FM.format(tools="Read, Grep"), FM.format(tools="Read"))
        assert problems == ["projection dropped allowed-tools entry: Grep"]

    def test_widened_entry_fails(self) -> None:
        problems = cpi.check_tools(
            FM.format(tools="Bash(git push:*)"), FM.format(tools="Bash(git push:*), Bash")
        )
        assert problems == ["projection added allowed-tools entry: Bash"]

    def test_argument_scope_stripped_fails(self) -> None:
        problems = cpi.check_tools(FM.format(tools="Bash(git push:*)"), FM.format(tools="Bash"))
        assert len(problems) == 2

    def test_empty_source_is_unmeasurable(self) -> None:
        assert "unmeasurable" in cpi.check_tools("---\nname: x\n---\n", FM.format(tools="Read"))[0]

    def test_missing_projection_line_fails(self) -> None:
        problems = cpi.check_tools(FM.format(tools="Read"), "---\nname: x\n---\n")
        assert problems == ["projection dropped allowed-tools entry: Read"]

    def test_repeated_key_in_projection_fails_even_when_the_first_matches(self) -> None:
        """A loader keeps the last key, so the wider second grant is the live one."""
        projection = "---\nname: x\nallowed-tools: Read\nallowed-tools: Read, Bash\n---\nbody\n"
        problems = cpi.check_tools(FM.format(tools="Read"), projection)
        assert problems == [
            "projection declares allowed-tools 2 times; a loader keeps the last one"
        ]

    def test_repeated_key_in_source_fails(self) -> None:
        source = "---\nname: x\nallowed-tools: Read\nallowed-tools: Read\n---\nbody\n"
        problems = cpi.check_tools(source, FM.format(tools="Read"))
        assert problems == ["source declares allowed-tools 2 times; a loader keeps the last one"]

    def test_single_key_reports_no_duplicate(self) -> None:
        assert cpi.check_tools(FM.format(tools="Read"), FM.format(tools="Read")) == []


class TestCheckExitCodes:
    def test_equal_tables_pass(self) -> None:
        text = EXIT.format(rows="| 0 | ok |\n| 1 | err |")
        assert cpi.check_exit_codes(text, text) == []

    def test_dropped_code_fails(self) -> None:
        source = EXIT.format(rows="| 0 | ok |\n| 10 | bad |")
        problems = cpi.check_exit_codes(source, EXIT.format(rows="| 0 | ok |"))
        assert problems == ["projection dropped exit code 10"]

    def test_added_code_fails(self) -> None:
        source = EXIT.format(rows="| 0 | ok |")
        problems = cpi.check_exit_codes(source, EXIT.format(rows="| 0 | ok |\n| 7 | new |"))
        assert problems == ["projection added exit code 7"]

    def test_renumbered_code_fails(self) -> None:
        source = EXIT.format(rows="| 0 | ok |\n| 10 | bad |")
        problems = cpi.check_exit_codes(source, EXIT.format(rows="| 0 | ok |\n| 11 | bad |"))
        assert len(problems) == 2

    def test_changed_meaning_fails(self) -> None:
        source = EXIT.format(rows="| 10 | Vulnerabilities detected |")
        problems = cpi.check_exit_codes(source, EXIT.format(rows="| 10 | Scan clean |"))
        assert problems == [
            "exit code 10 row changed: 'Vulnerabilities detected' became 'Scan clean'"
        ]

    def test_changed_ci_behavior_fails(self) -> None:
        source = EXIT.format(rows="| 10 | Vulnerabilities detected | Fail |")
        problems = cpi.check_exit_codes(
            source, EXIT.format(rows="| 10 | Vulnerabilities detected | Pass |")
        )
        assert problems == [
            "exit code 10 row changed: "
            "'Vulnerabilities detected | Fail' became 'Vulnerabilities detected | Pass'"
        ]

    def test_empty_source_is_unmeasurable(self) -> None:
        assert "unmeasurable" in cpi.check_exit_codes("# T\n", EXIT.format(rows="| 0 | ok |"))[0]

    def test_missing_projection_table_fails(self) -> None:
        problems = cpi.check_exit_codes(EXIT.format(rows="| 0 | ok |"), "# T\n")
        assert problems == ["projection dropped exit code 0"]

    def test_repeated_row_in_projection_fails_when_the_last_matches(self) -> None:
        source = EXIT.format(rows="| 0 | ok |")
        projection = EXIT.format(rows="| 0 | different |\n| 0 | ok |")
        assert cpi.check_exit_codes(source, projection) == ["projection lists exit code 0 2 times"]

    def test_second_heading_in_projection_fails(self) -> None:
        source = EXIT.format(rows="| 0 | ok |")
        projection = source + "\n## Exit Codes\n\n| 0 | ok |\n"
        problems = cpi.check_exit_codes(source, projection)
        assert any("declares 2 Exit Codes sections" in p for p in problems)

    def test_second_heading_hiding_a_changed_row_fails(self) -> None:
        source = EXIT.format(rows="| 0 | ok |")
        projection = source + "\n## Exit Codes\n\n| 0 | changed |\n"
        problems = cpi.check_exit_codes(source, projection)
        assert any("declares 2 Exit Codes sections" in p for p in problems)
        assert any("lists exit code 0 2 times" in p for p in problems)
        assert any("row changed" in p for p in problems)

    def test_repeated_row_in_source_fails(self) -> None:
        source = EXIT.format(rows="| 0 | ok |\n| 0 | ok |")
        problems = cpi.check_exit_codes(source, EXIT.format(rows="| 0 | ok |"))
        assert problems == ["source lists exit code 0 2 times"]


class TestRealTree:
    def test_committed_pilots_pass(self) -> None:
        result = _run(REPO_ROOT)
        assert result.returncode == 0, result.stderr

    def test_pilot_set_is_the_issue_contract(self) -> None:
        assert {(p.skill, p.invariant) for p in cpi.PILOTS} == {
            ("push-pr", 6),
            ("security-scan", 8),
        }

    def test_pilot_inputs_are_measurable(self) -> None:
        """A pilot whose extractor returns nothing would pass vacuously."""
        assert cpi.parse_allowed_tools(_read_real(SOURCE, "push-pr"))
        codes = cpi.parse_exit_codes(_read_real(SOURCE, "security-scan"))
        assert set(codes) == {"0", "1", "10"}


class TestNegativeControls:
    """One fixture per asserted invariant, built from the real committed files."""

    def test_baseline_fixture_passes(self, tmp_path: Path) -> None:
        assert _run(_make_repo(tmp_path)).returncode == 0

    def test_invariant_6_dropped_entry_fails(self, tmp_path: Path) -> None:
        text = _read_real(PROJECTION, "push-pr")
        assert "Bash(git push:*), " in text
        repo = _make_repo(tmp_path, push_pr_projection=text.replace("Bash(git push:*), ", "", 1))
        result = _run(repo)
        assert result.returncode == 1
        assert "push-pr (invariant 6)" in result.stderr
        assert "Bash(git push:*)" in result.stderr

    def test_invariant_6_widened_grant_fails(self, tmp_path: Path) -> None:
        text = _read_real(PROJECTION, "push-pr")
        widened = text.replace("Bash(git push:*)", "Bash", 1)
        result = _run(_make_repo(tmp_path, push_pr_projection=widened))
        assert result.returncode == 1
        assert "added allowed-tools entry: Bash" in result.stderr

    def test_invariant_6_repeated_allowed_tools_key_fails(self, tmp_path: Path) -> None:
        text = _read_real(PROJECTION, "push-pr")
        line = next(ln for ln in text.splitlines() if ln.startswith("allowed-tools:"))
        repeated = text.replace(line, f"{line}\n{line}", 1)
        result = _run(_make_repo(tmp_path, push_pr_projection=repeated))
        assert result.returncode == 1
        assert "push-pr (invariant 6)" in result.stderr
        assert "declares allowed-tools 2 times" in result.stderr

    def test_invariant_8_second_exit_codes_heading_fails(self, tmp_path: Path) -> None:
        text = _read_real(PROJECTION, "security-scan")
        extra = text + "\n## Exit Codes\n\n| 0 | Scan clean |\n"
        result = _run(_make_repo(tmp_path, scan_projection=extra))
        assert result.returncode == 1
        assert "security-scan (invariant 8)" in result.stderr
        assert "declares 2 Exit Codes sections" in result.stderr

    def test_invariant_8_dropped_code_fails(self, tmp_path: Path) -> None:
        text = _read_real(PROJECTION, "security-scan")
        row = "| 10 | Vulnerabilities detected | Fail |\n"
        assert row in text
        result = _run(_make_repo(tmp_path, scan_projection=text.replace(row, "", 1)))
        assert result.returncode == 1
        assert "security-scan (invariant 8): projection dropped exit code 10" in result.stderr

    def test_invariant_8_changed_code_fails(self, tmp_path: Path) -> None:
        text = _read_real(PROJECTION, "security-scan")
        result = _run(_make_repo(tmp_path, scan_projection=text.replace("| 10 |", "| 11 |", 1)))
        assert result.returncode == 1

    def test_invariant_8_changed_ci_behavior_fails(self, tmp_path: Path) -> None:
        text = _read_real(PROJECTION, "security-scan")
        row = "| 10 | Vulnerabilities detected | Fail |"
        assert row in text
        changed = text.replace(row, "| 10 | Vulnerabilities detected | Pass |", 1)
        result = _run(_make_repo(tmp_path, scan_projection=changed))
        assert result.returncode == 1
        assert "security-scan (invariant 8): exit code 10 row changed" in result.stderr

    def test_missing_projection_fails_closed(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / PROJECTION / "push-pr" / "SKILL.md").unlink()
        result = _run(repo)
        assert result.returncode == 1
        assert "cannot read" in result.stderr

    def test_missing_source_fails_closed(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / SOURCE / "security-scan" / "SKILL.md").unlink()
        assert _run(repo).returncode == 1

    def test_empty_repo_fails_closed(self, tmp_path: Path) -> None:
        assert _run(tmp_path).returncode == 1

    def test_usage_error_exits_2(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(_SCRIPT), "--bogus"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2


class TestInProcessEntryPoints:
    """Drive run() and main() in-process so coverage sees them."""

    def test_run_clean_tree_has_no_findings(self, tmp_path: Path) -> None:
        assert cpi.run(_make_repo(tmp_path)) == []

    def test_run_labels_each_finding_with_skill_and_invariant(self, tmp_path: Path) -> None:
        text = _read_real(PROJECTION, "security-scan")
        repo = _make_repo(tmp_path, scan_projection=text.replace("| 10 |", "| 11 |", 1))
        findings = cpi.run(repo)
        assert findings
        assert all(f.startswith("security-scan (invariant 8): ") for f in findings)

    def test_run_reports_unreadable_input(self, tmp_path: Path) -> None:
        findings = cpi.run(tmp_path)
        assert len(findings) == 4
        assert all("cannot read" in f for f in findings)

    def test_main_returns_zero_and_reports_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cpi.main(["--repo-root", str(_make_repo(tmp_path))]) == 0
        assert "hold for 2 pilot skills" in capsys.readouterr().out

    def test_main_returns_one_and_lists_findings(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cpi.main(["--repo-root", str(tmp_path)]) == 1
        assert "violations" in capsys.readouterr().err
