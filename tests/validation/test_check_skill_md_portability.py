"""Tests for the Markdown vendor-portability ratchet (issue #2050).

scripts/validation/check_skill_md_portability.py is the Markdown counterpart to
check_skill_portability.py. The script-only ratchet explicitly deferred SKILL.md
and reference .md files because prose carries a prose-vs-runtime ambiguity. This
validator closes that gap: it counts upstream-only runtime path references in
skill ``.md`` files, grandfathers the existing offenders in a JSON baseline,
fails on new drift, and honors a machine-readable ``vendor-portability`` HTML
comment that lets a skill declare a documented path dependency (the issue's
acceptance criterion: declare paths in a machine-readable section of SKILL.md).

These tests cover the counting/scan/diff units, the opt-out marker, the
code-block / inline-code stripping, and assert the committed repo has no drift
against its baseline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
sys.path.insert(0, str(_VALIDATION))

import check_skill_md_portability as cmp  # noqa: E402


class TestCountUpstreamRefs:
    def test_counts_each_prefix(self) -> None:
        text = (
            "Write to .agents/analysis/foo.md and read .claude/lib/paths.py "
            "and load .claude/review-axes/qa.md.\n"
        )
        assert cmp.count_upstream_refs(text) == 3

    def test_counts_windows_separators_and_mixed_case(self) -> None:
        text = (
            "Save under .agents\\sessions and import from .CLAUDE\\lib\\github_core "
            "and the .claude\\review-axes\\roadmap.md file.\n"
        )
        assert cmp.count_upstream_refs(text) == 3

    def test_ignores_glued_names(self) -> None:
        text = "The word prefix.agents/architecture and .agentship are not paths.\n"
        assert cmp.count_upstream_refs(text) == 0

    def test_counts_multiple_occurrences(self) -> None:
        text = "Files: .agents/a, .agents/b, .claude/review-axes/c.\n"
        assert cmp.count_upstream_refs(text) == 3

    def test_does_not_count_claude_skills_prefix(self) -> None:
        # .claude/skills/ is the install-root-relative convention the helper
        # resolves; it is intentionally not flagged (matches script ratchet
        # exclusion that .claude/skills/ is resolvable, unlike .agents/).
        text = "Run .claude/skills/memory/scripts/search_memory.py here.\n"
        assert cmp.count_upstream_refs(text) == 0


class TestCodeBlockAndInlineStripping:
    def test_ignores_fenced_code_blocks(self) -> None:
        text = (
            "Prose before.\n\n"
            "```bash\n"
            "cat .agents/sessions/log.json\n"
            "ls .claude/lib/\n"
            "```\n\n"
            "Prose after with a real path .agents/analysis/x.md.\n"
        )
        # Only the prose-level path counts; fenced example commands are skipped.
        assert cmp.count_upstream_refs(text) == 1

    def test_ignores_inline_code_spans(self) -> None:
        text = "See `.agents/sessions/` for examples; write to .agents/analysis/y.md.\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_tilde_fences_are_stripped(self) -> None:
        text = "~~~\n.agents/foo\n~~~\nReal .claude/lib/bar here.\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_indented_fences_are_stripped(self) -> None:
        # CommonMark allows 0-3 spaces of indentation on fence markers.
        text = (
            "   ```bash\n"
            "   .agents/foo\n"
            "   ```\n"
            "Real .claude/lib/bar here.\n"
        )
        assert cmp.count_upstream_refs(text) == 1

    def test_indented_fence_marker_not_opted_out(self) -> None:
        # A marker inside an indented code block must not opt the file out.
        text = (
            "   ```\n"
            "   <!-- vendor-portability: example -->\n"
            "   ```\n"
            "This prose references .agents/sessions/.\n"
        )
        assert cmp.has_portability_marker(text) is False
        assert cmp.count_file_refs(text) == 1


class TestVendorPortabilityMarker:
    def test_marker_suppresses_all_refs_in_file(self) -> None:
        text = (
            "<!-- vendor-portability: declared -->\n"
            "This skill writes to .agents/analysis/foo.md and reads "
            ".claude/lib/paths.py; both documented above.\n"
        )
        assert cmp.has_portability_marker(text) is True
        assert cmp.count_file_refs(text) == 0

    def test_marker_is_case_insensitive_and_tolerant_of_spacing(self) -> None:
        text = "<!--vendor-portability:ok-->\nWrites .agents/x.\n"
        assert cmp.has_portability_marker(text) is True

    def test_no_marker_counts_refs(self) -> None:
        text = "Writes .agents/x and .claude/lib/y.\n"
        assert cmp.has_portability_marker(text) is False
        assert cmp.count_file_refs(text) == 2

    def test_marker_inside_fenced_code_does_not_suppress(self) -> None:
        # A marker shown only inside a code block must not opt the file out.
        text = (
            "```\n"
            "<!-- vendor-portability: example -->\n"
            "```\n"
            "This prose references .agents/sessions/ which must still be counted.\n"
        )
        assert cmp.has_portability_marker(text) is False
        assert cmp.count_file_refs(text) == 1

    def test_marker_inside_inline_code_does_not_suppress(self) -> None:
        # Same rule for inline code spans.
        text = (
            "Use `<!-- vendor-portability: ok -->` in your file header.\n"
            "But this prose still references .agents/sessions/ without declaring.\n"
        )
        assert cmp.has_portability_marker(text) is False
        assert cmp.count_file_refs(text) == 1


class TestScan:
    def _skill_md(self, root: Path, rel: str, body: str) -> None:
        path = root / ".claude" / "skills" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_scan_collects_md_with_refs(self, tmp_path: Path) -> None:
        self._skill_md(tmp_path, "alpha/SKILL.md", "Writes .agents/analysis/a.md\n")
        self._skill_md(tmp_path, "beta/references/b.md", "Clean prose only.\n")
        self._skill_md(
            tmp_path, "gamma/SKILL.md", "Reads .claude/lib/x and .agents/y\n"
        )
        skills_dir = tmp_path / ".claude" / "skills"
        counts = cmp.scan_skill_markdown(skills_dir)
        assert counts == {
            "skills/alpha/SKILL.md": 1,
            "skills/gamma/SKILL.md": 2,
        }

    def test_scan_skips_marked_files(self, tmp_path: Path) -> None:
        self._skill_md(
            tmp_path,
            "alpha/SKILL.md",
            "<!-- vendor-portability: declared -->\nWrites .agents/a and .agents/b\n",
        )
        skills_dir = tmp_path / ".claude" / "skills"
        assert cmp.scan_skill_markdown(skills_dir) == {}


class TestDiff:
    def test_regression_when_count_rises(self) -> None:
        regressions, improvements = cmp.diff_against_baseline(
            {"skills/a/SKILL.md": 3}, {"skills/a/SKILL.md": 2}
        )
        assert regressions and "skills/a/SKILL.md" in regressions[0]
        assert improvements == []

    def test_regression_when_new_file_offends(self) -> None:
        regressions, _ = cmp.diff_against_baseline({"skills/new/SKILL.md": 1}, {})
        assert regressions and "skills/new/SKILL.md" in regressions[0]

    def test_improvement_when_count_drops(self) -> None:
        regressions, improvements = cmp.diff_against_baseline(
            {"skills/a/SKILL.md": 1}, {"skills/a/SKILL.md": 3}
        )
        assert regressions == []
        assert improvements and "skills/a/SKILL.md" in improvements[0]

    def test_no_drift_at_baseline(self) -> None:
        regressions, improvements = cmp.diff_against_baseline(
            {"skills/a/SKILL.md": 2}, {"skills/a/SKILL.md": 2}
        )
        assert regressions == []
        assert improvements == []


class TestMainCli:
    def test_exit_2_when_skills_dir_missing(self, tmp_path: Path) -> None:
        rc = cmp.main(["--repo-root", str(tmp_path)])
        assert rc == 2

    def test_update_baseline_writes_and_exits_zero(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Writes .agents/x\n", encoding="utf-8"
        )
        baseline = tmp_path / "baseline.json"
        rc = cmp.main(
            ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--update-baseline"]
        )
        assert rc == 0
        data = json.loads(baseline.read_text(encoding="utf-8"))
        assert data["files"] == {"skills/a/SKILL.md": 1}

    def test_drift_returns_exit_1(self, tmp_path: Path) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text(
            "Writes .agents/x and .agents/z\n", encoding="utf-8"
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps({"files": {"skills/a/SKILL.md": 1}}), encoding="utf-8"
        )
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 1

    def test_clean_repo_returns_zero(self, tmp_path: Path) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Clean prose.\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 0

    def test_baseline_path_traversal_returns_empty(self, tmp_path: Path) -> None:
        # A --baseline argument escaping the repo root must resolve to Path("")
        # and cause a config error (exit 2), not read an arbitrary file.
        root = tmp_path / "repo"
        root.mkdir()
        (root / ".claude" / "skills").mkdir(parents=True)
        traversal = Path("../../etc/passwd")
        result = cmp._resolve_baseline_path(root, traversal)
        assert result == Path(""), "path traversal must return empty Path"

    def test_absolute_baseline_outside_root_returns_empty(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        result = cmp._resolve_baseline_path(root, outside)
        assert result == Path(""), "absolute path outside root must return empty Path"


class TestCommittedRepoHasNoDrift:
    """The CI ratchet: the committed baseline must match the committed tree."""

    def test_repo_markdown_matches_baseline(self) -> None:
        root = Path(__file__).resolve().parents[2]
        skills_dir = root / ".claude" / "skills"
        if not skills_dir.is_dir():
            pytest.skip("no .claude/skills in this checkout")
        baseline_path = (
            root / "scripts" / "validation" / cmp._DEFAULT_BASELINE_NAME
        )
        current = cmp.scan_skill_markdown(skills_dir)
        baseline = cmp._load_baseline(baseline_path)
        regressions, _ = cmp.diff_against_baseline(current, baseline)
        assert regressions == [], "\n".join(regressions)
