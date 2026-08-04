"""Tests for the vendor-portability ratchet (issue #2050).

scripts/validation/check_skill_portability.py grandfathers existing upstream-only
path references in skill scripts and fails on new drift. These tests cover the
counting/scan/diff units and assert the committed repo has no drift against its
baseline (the CI ratchet that blocks new upstream-path references).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
sys.path.insert(0, str(_VALIDATION))

import check_skill_portability as csp


class TestCountUpstreamRefs:
    def test_counts_each_prefix(self) -> None:
        text = "x = Path('.agents/architecture')\ny = '.claude/lib/foo'\n"
        assert csp.count_upstream_refs(text) == 2

    def test_counts_windows_separators_bare_dirs_and_mixed_case(self) -> None:
        text = (
            r"base / '.agents' "
            "p = '.CLAUDE\\lib\\github_core' "
            "q = '.claude\\review-axes\\roadmap.md' "
            "s = '.claude\\skills\\github'"
        )
        assert csp.count_upstream_refs(text) == 4

    def test_ignores_glued_names_and_escaped_regex_prefixes(self) -> None:
        text = (
            r"not_a_path_agents = 'prefix.agents/architecture' "
            r"also_not = '.agentship' "
            r"regex = r'^\\.agents/.*' "
            r"regex2 = r'\\.claude/lib/'"
        )
        assert csp.count_upstream_refs(text) == 0

    def test_counts_multiple_occurrences(self) -> None:
        text = "paths = ['.agents/a', '.agents/b', '.claude/review-axes/c', '.claude/skills/d']"
        assert csp.count_upstream_refs(text) == 4

    def test_counts_split_claude_path_construction(self) -> None:
        text = """\
os.path.join(root, ".claude", "lib")
Path(".claude") / "review-axes"
base / ".claude" / "skills"
"""
        assert csp.count_upstream_refs(text) == 3

    def test_ignores_python_comments_and_docstrings(self) -> None:
        text = '''\
"""Mentions .agents/ in a module docstring."""

def path() -> str:
    """Mentions .claude/lib/ in a function docstring."""
    # Mentions .claude/skills/ in a comment.
    return ".agents/runtime"
'''
        assert csp.count_upstream_refs(text) == 1

    def test_ignores_python_cli_prose_strings(self) -> None:
        text = """\
parser = argparse.ArgumentParser(
    description="Mentions .agents/ as CLI prose.",
    epilog="Mentions .claude/lib/ as CLI prose.",
)
parser.add_argument("--path", help="Mentions .claude/skills/ as CLI prose.")
runtime = ".agents/runtime"
"""
        assert csp.count_upstream_refs(text) == 1

    def test_ignores_python_cli_prose_fstrings(self) -> None:
        text = """\
parser.add_argument(
    "--path",
    help=f"Mentions .agents/{name} and .claude/lib/{name} as CLI prose.",
)
runtime = ".agents/runtime"
"""
        assert csp.count_upstream_refs(text) == 1

    def test_ignores_hash_comments_in_shell_and_powershell(self) -> None:
        text = (
            "# .agents/comment\n"
            "value='label # .claude/skills/runtime'\n"
            'other="label # .agents/runtime"\n'
        )
        assert csp.count_upstream_refs(text, ".sh") == 2
        assert csp.count_upstream_refs(text, ".ps1") == 2

    def test_strips_unquoted_hash_comments_in_shell_and_powershell(self) -> None:
        text = "value='.claude/skills/runtime' # .agents/comment\n"
        assert csp.count_upstream_refs(text, ".sh") == 1
        assert csp.count_upstream_refs(text, ".ps1") == 1

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

    def test_ignores_non_runtime_python_prose(self, tmp_path: Path) -> None:
        self._skill_script(
            tmp_path,
            "docs",
            '''\
"""Mentions .agents/ in a docstring."""

# Mentions .claude/lib/ in a comment.
RUNTIME_PATH = ".claude/skills/runtime"
''',
        )
        counts = csp.scan_skill_scripts(tmp_path / ".claude" / "skills")
        assert counts == {"skills/docs/scripts/run.py": 1}

    def test_fails_closed_on_unreadable_script(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._skill_script(tmp_path, "gamma", "Path('.agents/architecture')\n")
        original_read_text = Path.read_text

        def read_text(
            path: Path,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> str:
            if path.name == "run.py":
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad byte")
            return original_read_text(path, encoding, errors, newline)

        monkeypatch.setattr(Path, "read_text", read_text)

        with pytest.raises(OSError):
            csp.scan_skill_scripts(tmp_path / ".claude" / "skills")


class TestRepoRoot:
    def test_fallback_is_parent_directory_when_start_is_file(self, external_tmp_path: Path) -> None:
        script = external_tmp_path / "script.py"
        script.write_text("print('ok')\n", encoding="utf-8")

        assert csp._repo_root(script) == external_tmp_path


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
    def _repo_with_clean_skill(self, root: Path) -> None:
        skills = root / ".claude" / "skills" / "alpha" / "scripts"
        skills.mkdir(parents=True, exist_ok=True)
        (skills / "run.py").write_text("print('ok')\n", encoding="utf-8")

    def test_committed_repo_has_no_drift(self) -> None:
        # The CI ratchet: the committed skill scripts must not exceed the
        # committed baseline. A new upstream-path reference (issue #2050) fails
        # here until the author either makes it portable or updates the baseline.
        assert csp.main([]) == 0

    def test_baseline_file_is_valid_json_with_files(self) -> None:
        baseline = _VALIDATION / "skill_portability_baseline.json"
        data = json.loads(baseline.read_text(encoding="utf-8"))
        assert "files" in data and isinstance(data["files"], dict)

    def test_missing_baseline_is_configuration_error(self, tmp_path: Path) -> None:
        self._repo_with_clean_skill(tmp_path)

        assert csp.main(["--repo-root", str(tmp_path), "--baseline", "missing.json"]) == 2

    @pytest.mark.parametrize(
        "baseline",
        [
            [],
            {"files": None},
            {"files": []},
            {"files": {"skills/a/scripts/run.py": None}},
            {"files": {"skills/a/scripts/run.py": "not-an-int"}},
        ],
    )
    def test_malformed_baseline_is_configuration_error(
        self, tmp_path: Path, baseline: object
    ) -> None:
        self._repo_with_clean_skill(tmp_path)
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

        assert csp.main(["--repo-root", str(tmp_path), "--baseline", "baseline.json"]) == 2

    def test_relative_baseline_resolves_under_repo_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._repo_with_clean_skill(tmp_path)
        validation = tmp_path / "scripts" / "validation"
        validation.mkdir(parents=True)
        (validation / "baseline.json").write_text('{"files": {}}\n', encoding="utf-8")
        other_cwd = tmp_path / "other"
        other_cwd.mkdir()
        monkeypatch.chdir(other_cwd)

        assert (
            csp.main(
                [
                    "--repo-root",
                    str(tmp_path),
                    "--baseline",
                    "scripts/validation/baseline.json",
                ]
            )
            == 0
        )

    def test_scan_failure_is_configuration_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._repo_with_clean_skill(tmp_path)
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}}\n', encoding="utf-8")
        original_read_text = Path.read_text

        def read_text(
            path: Path,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> str:
            if path.name == "run.py":
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad byte")
            return original_read_text(path, encoding, errors, newline)

        monkeypatch.setattr(Path, "read_text", read_text)

        assert csp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == 2

    def test_improvement_triggers_failure_to_tighten_baseline(self, tmp_path: Path) -> None:
        """Baseline slack (current < baseline) must exit 1 (issue #3730).

        A stale baseline allows future regressions to accumulate silently up to
        the slack headroom. The fix: any non-zero improvement list exits 1 so
        the author must run --update-baseline.
        """
        self._repo_with_clean_skill(tmp_path)
        # Baseline records 5 refs; current code has 0. That is an improvement.
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(
            '{"files": {"skills/alpha/scripts/run.py": 5}}\n', encoding="utf-8"
        )
        assert csp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline_path)]) == 1

    def test_baseline_shrink_requires_the_explicit_override(self, tmp_path: Path) -> None:
        self._repo_with_clean_skill(tmp_path)
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(
            '{"files": {"skills/alpha/scripts/run.py": 5}}\n', encoding="utf-8"
        )
        # The floor now comes from the committed copy, so the fixture has to be
        # a real repository. A directory with no git in it cannot answer what
        # was already forgiven, and the guard refuses rather than guess.
        for command in (
            ["init", "-q"],
            ["config", "user.email", "t@example.com"],
            ["config", "user.name", "t"],
            ["add", "-A"],
            ["commit", "-qm", "seed"],
        ):
            subprocess.run(
                ["git", "-C", str(tmp_path), *command], check=True, capture_output=True
            )
        args = [
            "--repo-root",
            str(tmp_path),
            "--baseline",
            str(baseline_path),
            "--update-baseline",
        ]

        assert csp.main(args) == 2
        assert csp.main([*args, "--allow-baseline-shrink"]) == 0
        assert json.loads(baseline_path.read_text(encoding="utf-8"))["files"] == {}

    def test_regression_still_triggers_failure(self, tmp_path: Path) -> None:
        """Regressions (current > baseline) must still exit 1."""
        skills = tmp_path / ".claude" / "skills" / "beta" / "scripts"
        skills.mkdir(parents=True, exist_ok=True)
        (skills / "run.py").write_text(
            "import subprocess\nsubprocess.run(['.agents/run.sh'])\n",
            encoding="utf-8",
        )
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text('{"files": {"skills/beta/scripts/run.py": 0}}\n', encoding="utf-8")
        assert csp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline_path)]) == 1

    def test_exact_match_exits_zero(self, tmp_path: Path) -> None:
        """Only an exact match between current and baseline exits 0."""
        skills = tmp_path / ".claude" / "skills" / "gamma" / "scripts"
        skills.mkdir(parents=True, exist_ok=True)
        (skills / "run.py").write_text("print('ok')\n", encoding="utf-8")
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(
            '{"files": {"skills/gamma/scripts/run.py": 0}}\n', encoding="utf-8"
        )
        assert csp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline_path)]) == 0

    def test_a_baseline_outside_the_repository_is_refused_in_both_modes(
        self, tmp_path: Path
    ) -> None:
        """The read and the write have to agree about what they will accept.

        This checker used to resolve any `--baseline` while the write path
        refused every out-of-tree destination, so a read succeeded and the
        update it was meant to precede failed. The permissiveness was never a
        decision: the resolver predated the containment test its two siblings
        apply, and a later dedupe preserved the gap verbatim.
        """
        root = tmp_path / "repo"
        skills = root / ".claude" / "skills" / "delta" / "scripts"
        skills.mkdir(parents=True)
        (skills / "run.py").write_text("print('ok')\n", encoding="utf-8")
        outside = tmp_path / "outside.json"
        outside.write_text('{"files": {}}\n', encoding="utf-8")
        argv = ["--repo-root", str(root), "--baseline", str(outside)]

        assert csp.main(argv) == 2
        assert csp.main([*argv, "--update-baseline"]) == 2
        assert json.loads(outside.read_text(encoding="utf-8")) == {"files": {}}

    def test_a_baseline_inside_the_repository_is_still_accepted(
        self, tmp_path: Path
    ) -> None:
        """The refusal above is only correct if the supported path still works."""
        root = tmp_path / "repo"
        skills = root / ".claude" / "skills" / "delta" / "scripts"
        skills.mkdir(parents=True)
        (skills / "run.py").write_text("print('ok')\n", encoding="utf-8")
        inside = root / "baseline.json"
        inside.write_text('{"files": {"skills/delta/scripts/run.py": 0}}\n', encoding="utf-8")

        assert csp.main(["--repo-root", str(root), "--baseline", str(inside)]) == 0
