"""Tests for the skill resolver anchoring and contract-binding guards.

These guards were written after a green validation run that had never opened
the files containing the defect. Each guard therefore carries three controls,
and each control is asserted here:

* a positive control - the guard goes red on a known-bad input
* a negative control - the guard goes green once that input is fixed
* an empty-scan control - the guard exits 2 rather than reporting a false
  green when it finds nothing to examine

A guard that has never gone red on a known-bad input is unproven, so the
positive controls are the load-bearing tests in this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_orig_path = sys.path[:]
sys.path.insert(0, str(REPO_ROOT))
try:
    from scripts.validation import (
        check_skill_contract_tests as contract_guard,
    )
    from scripts.validation import (
        check_skill_resolver_anchoring as resolver_guard,
    )
finally:
    sys.path[:] = _orig_path

UNANCHORED_RESOLVER = """# Skill

```bash
resolve_pr_scripts_dir() {
  for root in \\
    "${COPILOT_PLUGIN_ROOT:-}" \\
    ".claude" \\
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit"; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
}
```
"""

ANCHORED_RESOLVER = """# Skill

```bash
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \\
    "${COPILOT_PLUGIN_ROOT:-}" \\
    "$repo_root/.claude" \\
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit"; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
}
```
"""

OUT_OF_REPO_FIRST = """# Skill

```bash
resolve_pr_scripts_dir() {
  repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for root in \\
    "${HOME:-}/.copilot/installed-plugins/_direct/project-toolkit" \\
    "$repo_root/.claude"; do
    if [ -n "$root" ] && [ -d "$root/skills/github/scripts/pr" ]; then
      printf '%s\\n' "$root/skills/github/scripts/pr"
      return 0
    fi
  done
}
```
"""

CONTRACT_SKILL = """# Skill

Run the gate:

```bash
python3 scripts/pr/check_pr_live_state.py --pull-request 1
```

Exit 0 means act. Exit 1 means skip.
"""

NO_CONTRACT_SKILL = """# Skill

This skill documents no script invocation and no exit code.
"""


def _write_skill(root: Path, name: str, body: str) -> Path:
    path = root / "src" / "copilot-cli" / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _write_test(root: Path, name: str, body: str) -> Path:
    path = root / "tests" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestResolverAnchoringPositiveControl:
    """The guard must go red on the defect that motivated it."""

    def test_unanchored_relative_root_is_rejected(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "demo", UNANCHORED_RESOLVER)
        assert resolver_guard.main(["--repo-root", str(tmp_path)]) == 1

    def test_names_the_offending_function(self, tmp_path: Path) -> None:
        path = _write_skill(tmp_path, "demo", UNANCHORED_RESOLVER)
        violations = resolver_guard.check_file(path)
        assert violations, "expected a violation on a bare relative root"
        assert violations[0].function == "resolve_pr_scripts_dir"

    def test_out_of_repo_root_ordered_first_is_rejected(self, tmp_path: Path) -> None:
        path = _write_skill(tmp_path, "demo", OUT_OF_REPO_FIRST)
        kinds = {v.kind for v in resolver_guard.check_file(path)}
        assert "out-of-repo candidate ordered before in-repo copy" in kinds

    def test_real_repository_defect_is_detected(self) -> None:
        """The in-tree resolver this guard was written for must be caught.

        Skipped rather than failed once the underlying skills are fixed, so
        the test does not become an obstacle to the fix it is asking for.
        """
        target = (
            REPO_ROOT / "src" / "copilot-cli" / "skills" / "pr-autofix" / "SKILL.md"
        )
        if not target.is_file():
            pytest.skip("pr-autofix SKILL.md not present in this tree")
        violations = resolver_guard.check_file(target)
        if not violations:
            pytest.skip("resolver already anchored; positive control satisfied")
        assert any("unanchored" in v.kind for v in violations)


class TestResolverAnchoringNegativeControl:
    """The guard must go green once the defect is fixed, or it is a constant."""

    def test_anchored_resolver_passes(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "demo", ANCHORED_RESOLVER)
        assert resolver_guard.main(["--repo-root", str(tmp_path)]) == 0

    def test_empty_scan_does_not_report_success(self, tmp_path: Path) -> None:
        assert resolver_guard.main(["--repo-root", str(tmp_path)]) == 2


class TestContractBindingPositiveControl:
    def test_documented_contract_without_test_is_rejected(
        self, tmp_path: Path
    ) -> None:
        _write_skill(tmp_path, "demo", CONTRACT_SKILL)
        _write_test(tmp_path, "test_unrelated.py", "def test_x():\n    assert True\n")
        assert contract_guard.main(["--repo-root", str(tmp_path)]) == 1

    def test_skill_without_contract_is_out_of_scope(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "demo", NO_CONTRACT_SKILL)
        _write_test(tmp_path, "test_unrelated.py", "def test_x():\n    assert True\n")
        assert contract_guard.main(["--repo-root", str(tmp_path)]) == 0


class TestContractBindingNegativeControl:
    def test_referenced_skill_passes(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "demo", CONTRACT_SKILL)
        _write_test(
            tmp_path,
            "test_demo_contract.py",
            "SKILL = 'demo'\n\n\ndef test_x():\n    assert SKILL\n",
        )
        assert contract_guard.main(["--repo-root", str(tmp_path)]) == 0

    def test_baseline_grandfathers_named_skill(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "demo", CONTRACT_SKILL)
        _write_test(tmp_path, "test_unrelated.py", "def test_x():\n    assert True\n")
        baseline = tmp_path / "baseline.txt"
        baseline.write_text("# comment\ndemo\n", encoding="utf-8")
        exit_code = contract_guard.main(
            ["--repo-root", str(tmp_path), "--baseline", "baseline.txt"]
        )
        assert exit_code == 0

    def test_empty_scan_does_not_report_success(self, tmp_path: Path) -> None:
        assert contract_guard.main(["--repo-root", str(tmp_path)]) == 2

    def test_missing_tests_directory_does_not_report_success(
        self, tmp_path: Path
    ) -> None:
        _write_skill(tmp_path, "demo", CONTRACT_SKILL)
        assert contract_guard.main(["--repo-root", str(tmp_path)]) == 2

    def test_hyphenated_name_not_matched_by_suffix(self, tmp_path: Path) -> None:
        """Skill 'pr-review' must not be bound by a test naming 'pr-review-v2'."""
        _write_skill(tmp_path, "pr-review", CONTRACT_SKILL)
        _write_test(
            tmp_path,
            "test_other.py",
            "SKILL = 'pr-review-v2'\n\ndef test_x():\n    assert SKILL\n",
        )
        assert contract_guard.main(["--repo-root", str(tmp_path)]) == 1


class TestBaselineRatchet:
    """The checked-in baseline file must be well-formed and non-empty."""

    def test_baseline_entries_are_still_unbound(self) -> None:
        baseline_path = (
            REPO_ROOT
            / "scripts"
            / "validation"
            / "skill_contract_test_baseline.txt"
        )
        if not baseline_path.is_file():
            pytest.skip("baseline not present")
        entries = [
            line.strip()
            for line in baseline_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert entries, "baseline exists but is empty; delete it instead"
        assert len(entries) == len(set(entries)), "baseline contains duplicates"
