"""Tests for the vendor-portability ratchet (issue #2050).

scripts/validation/check_skill_portability.py grandfathers existing upstream-only
path references in skill scripts and fails on new drift. These tests cover the
counting/scan/diff units and assert the committed repo has no drift against its
baseline (the CI ratchet that blocks new upstream-path references).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
sys.path.insert(0, str(_VALIDATION))

import check_skill_portability as csp  # noqa: E402


class TestCountUpstreamRefs:
    def test_counts_each_prefix(self) -> None:
        text = "x = Path('.agents/architecture')\ny = '.claude/lib/foo'\n"
        assert csp.count_upstream_refs(text) == 2

    def test_counts_multiple_occurrences(self) -> None:
        text = ".agents/a .agents/b .claude/review-axes/c .claude/skills/d"
        assert csp.count_upstream_refs(text) == 4

    def test_zero_when_clean(self) -> None:
        assert csp.count_upstream_refs("import os\nPath('./local')\n") == 0


class TestScanSkillScripts:
    def _skill_script(self, root: Path, name: str, body: str) -> None:
        d = root / ".claude" / "skills" / name / "scripts"
        d.mkdir(parents=True, exist_ok=True)
        (d / "run.py").write_text(body, encoding="utf-8")

    def test_reports_scripts_with_refs(self, tmp_path: Path) -> None:
        self._skill_script(tmp_path, "alpha", "Path('.agents/architecture')\n")
        counts = csp.scan_skill_scripts(tmp_path / ".claude" / "skills")
        assert counts == {"skills/alpha/scripts/run.py": 1}

    def test_ignores_markdown_and_clean_scripts(self, tmp_path: Path) -> None:
        skills = tmp_path / ".claude" / "skills"
        self._skill_script(tmp_path, "beta", "Path('./local')\n")
        (skills / "beta" / "SKILL.md").write_text("mentions .agents/ in prose\n", encoding="utf-8")
        assert csp.scan_skill_scripts(skills) == {}


class TestDiffAgainstBaseline:
    def test_regression_when_count_rises(self) -> None:
        regressions, _ = csp.diff_against_baseline({"a": 3}, {"a": 2})
        assert len(regressions) == 1 and "a:" in regressions[0]

    def test_new_offending_file_is_regression(self) -> None:
        regressions, _ = csp.diff_against_baseline({"new.py": 1}, {})
        assert len(regressions) == 1

    def test_count_at_baseline_is_clean(self) -> None:
        regressions, improvements = csp.diff_against_baseline({"a": 2}, {"a": 2})
        assert regressions == [] and improvements == []

    def test_count_below_baseline_is_improvement(self) -> None:
        regressions, improvements = csp.diff_against_baseline({"a": 1}, {"a": 2})
        assert regressions == [] and len(improvements) == 1

    def test_removed_file_is_improvement(self) -> None:
        regressions, improvements = csp.diff_against_baseline({}, {"a": 2})
        assert regressions == [] and len(improvements) == 1


class TestRepoRatchet:
    def test_committed_repo_has_no_drift(self) -> None:
        # The CI ratchet: the committed skill scripts must not exceed the
        # committed baseline. A new upstream-path reference (issue #2050) fails
        # here until the author either makes it portable or updates the baseline.
        assert csp.main([]) == 0

    def test_baseline_file_is_valid_json_with_files(self) -> None:
        baseline = _VALIDATION / "skill_portability_baseline.json"
        data = json.loads(baseline.read_text(encoding="utf-8"))
        assert "files" in data and isinstance(data["files"], dict)
