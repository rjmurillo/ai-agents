# taste-lint: ignore file-size, this suite covers one validator end to end.
"""Tests for the exec-path vendor-portability ratchet (issue #2838).

Covers: detection regex, opt-out marker, two-tree scan, diff ratchet, CLI exit
codes, and the committed-tree baseline assertion.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest.mock
from pathlib import Path

import pytest
import yaml

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
_ORIGINAL_SYS_PATH = sys.path.copy()
try:
    sys.path.insert(0, str(_VALIDATION))
    import check_skill_md_exec_portability as cep
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH


def _seed_git_tree(root: Path) -> None:
    """Make the fixture a repository: an unverifiable tree refuses the write."""
    for args in (
        ("init", "-q", "-b", "main"),
        ("add", "-A"),
        ("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "s"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class TestCountExecInvocations:
    def test_counts_bare_python_invocation(self) -> None:
        text = "python3 .claude/skills/github/scripts/pr/x.py --flag\n"
        assert cep.count_exec_invocations(text) == 1

    def test_counts_bash_and_sh_and_python2(self) -> None:
        text = (
            "bash .claude/skills/a/setup.sh\n"
            "sh .claude/skills/b/run.sh\n"
            "python .claude/skills/c/tool.py\n"
        )
        assert cep.count_exec_invocations(text) == 3

    def test_counts_inline_backtick_and_table_cell(self) -> None:
        text = "Run `python3 .claude/skills/x/y.py` or | `bash .claude/skills/z/w.sh` |\n"
        assert cep.count_exec_invocations(text) == 2

    def test_counts_after_shell_operators(self) -> None:
        text = "foo | python3 .claude/skills/x/y.py && bash .claude/skills/z/w.sh\n"
        assert cep.count_exec_invocations(text) == 2

    def test_counts_interpreter_options(self) -> None:
        # Short options between the interpreter and the path (python3 -u ...,
        # bash -x ...) are still bare, non-portable invocations.
        text = "python3 -u .claude/skills/x/y.py\nbash -x .claude/skills/z/w.sh\n"
        assert cep.count_exec_invocations(text) == 2

    def test_counts_direct_dot_slash_execution(self) -> None:
        # A ./-prefixed executable hard-codes the upstream tree just like an
        # interpreter-prefixed one.
        text = "./.claude/skills/x/y.sh --flag\n"
        assert cep.count_exec_invocations(text) == 1

    def test_counts_line_continuation_invocation(self) -> None:
        # A shell backslash-newline splices the path onto the interpreter line;
        # the split invocation must still be counted.
        text = "python3 \\\n  .claude/skills/x/y.py --flag\n"
        assert cep.count_exec_invocations(text) == 1

    def test_counts_quoted_script_path(self) -> None:
        text = 'python3 ".claude/skills/github/scripts/pr/x.py" --flag\n'
        assert cep.count_exec_invocations(text) == 1

    def test_ignores_intermediate_script_extension(self) -> None:
        text = "python3 .claude/skills/github/scripts/pr/x.py.tmp --flag\n"
        assert cep.count_exec_invocations(text) == 0

    def test_ignores_resolved_variable_forms(self) -> None:
        text = (
            'SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/x"\n'
            'python3 "$SCRIPTS_DIR/y.py"\n'
            'python3 "${CLAUDE_PLUGIN_ROOT:-.claude}/skills/x/y.py"\n'
        )
        assert cep.count_exec_invocations(text) == 0

    def test_ignores_prose_crosslinks(self) -> None:
        # A cross-reference to a sibling skill doc is not an exec invocation.
        text = "See .claude/skills/review/SKILL.md and .claude/skills/memory/references/x.md.\n"
        assert cep.count_exec_invocations(text) == 0

    def test_ignores_prose_script_mention(self) -> None:
        # A bare prose mention of a script path (no interpreter, no ./ lead-in)
        # is not an invocation; the sibling prose guard owns those references.
        text = "The `.claude/skills/x/y.py` helper does the work; run it via SCRIPTS_DIR.\n"
        assert cep.count_exec_invocations(text) == 0

    def test_interpreter_must_be_standalone_token(self) -> None:
        # The "sh" inside another word (flavash/bash-as-substring) must not match.
        text = "flavash .claude/skills/x/y.py\nmypython .claude/skills/x/z.py\n"
        assert cep.count_exec_invocations(text) == 0

    def test_ignores_non_skills_claude_paths(self) -> None:
        text = "python3 .claude/lib/paths.py\npython3 .claude/commands/x.py\n"
        assert cep.count_exec_invocations(text) == 0

    def test_ignores_non_script_targets(self) -> None:
        text = "python3 .claude/skills/x/data.json\ncat .claude/skills/x/SKILL.md\n"
        assert cep.count_exec_invocations(text) == 0


class TestExecMarker:
    def test_marker_suppresses_all_invocations(self) -> None:
        text = (
            "<!-- vendor-portability-exec: bootstrap must use the source tree -->\n"
            "python3 .claude/skills/a/x.py\npython3 .claude/skills/b/y.py\n"
        )
        assert cep.has_portability_marker(text) is True
        assert cep.count_file_invocations(text) == 0

    def test_prose_marker_does_not_suppress_exec(self) -> None:
        # The sibling prose marker (no -exec suffix) must NOT exempt exec paths.
        text = (
            "<!-- vendor-portability: declares a prose .agents/ dependency -->\n"
            "python3 .claude/skills/a/x.py\n"
        )
        assert cep.has_portability_marker(text) is False
        assert cep.count_file_invocations(text) == 1

    def test_marker_case_insensitive_and_spacing_tolerant(self) -> None:
        text = "<!--vendor-portability-exec:ok-->\npython3 .claude/skills/a/x.py\n"
        assert cep.has_portability_marker(text) is True

    def test_no_marker_counts_invocations(self) -> None:
        text = "python3 .claude/skills/a/x.py\n"
        assert cep.has_portability_marker(text) is False
        assert cep.count_file_invocations(text) == 1

    def test_marker_suppressed_count_tracks_hidden_invocations(self) -> None:
        text = (
            "<!-- vendor-portability-exec: declared -->\n"
            "python3 .claude/skills/a/x.py\n"
            "python3 build/scripts/generate_rules.py\n"
        )
        assert cep.count_marker_suppressed_invocations(text) == 2

    def test_marker_suppressed_count_is_zero_without_marker(self) -> None:
        text = "python3 .claude/skills/a/x.py\n"
        assert cep.count_marker_suppressed_invocations(text) == 0


class TestScan:
    def _skill_md(self, root: Path, parts: tuple[str, ...], rel: str, body: str) -> None:
        path = root.joinpath(*parts) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_scan_collects_both_trees(self, tmp_path: Path) -> None:
        self._skill_md(
            tmp_path,
            (".claude", "skills"),
            "alpha/SKILL.md",
            "python3 .claude/skills/alpha/x.py\n",
        )
        self._skill_md(
            tmp_path,
            ("src", "copilot-cli", "skills"),
            "beta/SKILL.md",
            "bash .claude/skills/beta/y.sh\nsh .claude/skills/beta/z.sh\n",
        )
        # Clean file contributes nothing.
        self._skill_md(
            tmp_path,
            (".claude", "skills"),
            "gamma/SKILL.md",
            'python3 "$SCRIPTS_DIR/clean.py"\n',
        )
        counts = cep.scan_skill_execs(tmp_path)
        assert counts == {
            ".claude/skills/alpha/SKILL.md": 1,
            "src/copilot-cli/skills/beta/SKILL.md": 2,
        }

    def test_scan_collects_reference_docs_and_script_readmes(self, tmp_path: Path) -> None:
        self._skill_md(tmp_path, (".claude", "skills"), "alpha/SKILL.md", "clean\n")
        self._skill_md(
            tmp_path,
            (".claude", "skills"),
            "alpha/references/guide.md",
            "python3 .claude/skills/alpha/scripts/tool.py\n",
        )
        self._skill_md(
            tmp_path,
            (".claude", "skills"),
            "alpha/scripts/README-tool.md",
            "bash .claude/skills/alpha/scripts/tool.sh\nsh .claude/skills/alpha/scripts/other.sh\n",
        )
        self._skill_md(
            tmp_path,
            (".claude", "skills"),
            "alpha/scripts/not-readme.md",
            "python3 .claude/skills/alpha/scripts/ignored.py\n",
        )
        self._skill_md(tmp_path, ("src", "copilot-cli", "skills"), "beta/SKILL.md", "clean\n")
        self._skill_md(
            tmp_path,
            ("src", "copilot-cli", "skills"),
            "beta/references/ref.md",
            "./.claude/skills/beta/scripts/run.sh\n",
        )

        counts = cep.scan_skill_execs(tmp_path)

        assert counts == {
            ".claude/skills/alpha/references/guide.md": 1,
            ".claude/skills/alpha/scripts/README-tool.md": 2,
            "src/copilot-cli/skills/beta/references/ref.md": 1,
        }

    def test_scan_skips_marked_files(self, tmp_path: Path) -> None:
        self._skill_md(
            tmp_path,
            (".claude", "skills"),
            "alpha/SKILL.md",
            "<!-- vendor-portability-exec: declared -->\npython3 .claude/skills/a/x.py\n",
        )
        assert cep.scan_skill_execs(tmp_path) == {}

    def test_scan_skips_missing_root(self, tmp_path: Path) -> None:
        # Only one of the two trees exists; scan must not error.
        self._skill_md(
            tmp_path,
            (".claude", "skills"),
            "alpha/SKILL.md",
            "python3 .claude/skills/alpha/x.py\n",
        )
        counts = cep.scan_skill_execs(tmp_path)
        assert counts == {".claude/skills/alpha/SKILL.md": 1}


class TestDiff:
    def test_regression_when_count_rises(self) -> None:
        regressions, improvements = cep.diff_against_baseline(
            {".claude/skills/a/SKILL.md": 3}, {".claude/skills/a/SKILL.md": 2}
        )
        assert regressions and ".claude/skills/a/SKILL.md" in regressions[0]
        assert improvements == []

    def test_regression_when_new_file_offends(self) -> None:
        regressions, _ = cep.diff_against_baseline({".claude/skills/new/SKILL.md": 1}, {})
        assert regressions and ".claude/skills/new/SKILL.md" in regressions[0]

    def test_improvement_when_count_drops(self) -> None:
        regressions, improvements = cep.diff_against_baseline(
            {".claude/skills/a/SKILL.md": 1}, {".claude/skills/a/SKILL.md": 3}
        )
        assert regressions == []
        assert improvements and ".claude/skills/a/SKILL.md" in improvements[0]

    def test_no_drift_at_baseline(self) -> None:
        regressions, improvements = cep.diff_against_baseline(
            {".claude/skills/a/SKILL.md": 2}, {".claude/skills/a/SKILL.md": 2}
        )
        assert regressions == []
        assert improvements == []


class TestMainCli:
    def _make_skill(self, root: Path, body: str) -> None:
        d = root / ".claude" / "skills" / "a"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")

    def test_exit_2_when_no_scan_roots(self, tmp_path: Path) -> None:
        rc = cep.main(["--repo-root", str(tmp_path)])
        assert rc == 2

    def test_update_baseline_writes_and_exits_zero(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "python3 .claude/skills/a/x.py\n")
        # Every shipped root must hold a readable file or the scan-coverage guard
        # refuses the write, because one starved root is a partial checkout.
        second = tmp_path / "src" / "copilot-cli" / "skills" / "a"
        second.mkdir(parents=True)
        (second / "SKILL.md").write_text("No bare invocations.\n", encoding="utf-8")
        _seed_git_tree(tmp_path)
        baseline = tmp_path / "baseline.json"
        rc = cep.main(
            ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--update-baseline"]
        )
        assert rc == 0
        data = json.loads(baseline.read_text(encoding="utf-8"))
        assert data["files"] == {".claude/skills/a/SKILL.md": 1}

    def test_drift_returns_exit_1(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "python3 .claude/skills/a/x.py\npython3 .claude/skills/a/y.py\n")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps({"files": {".claude/skills/a/SKILL.md": 1}}), encoding="utf-8"
        )
        rc = cep.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 1

    def test_marker_stale_count_returns_exit_1(self, tmp_path: Path) -> None:
        self._make_skill(
            tmp_path,
            "<!-- vendor-portability-exec: declared -->\n"
            "The declaration stayed but the invocation moved away.\n",
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps({"files": {}, "marker_files": {".claude/skills/a/SKILL.md": 1}}),
            encoding="utf-8",
        )
        rc = cep.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 1

    def test_clean_repo_returns_zero(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, 'python3 "$SCRIPTS_DIR/x.py"\n')
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cep.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 0

    def test_baseline_path_traversal_returns_none(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        (root / ".claude" / "skills").mkdir(parents=True)
        result = cep._resolve_baseline_path(root, Path("../../etc/passwd"))
        assert result is None, "path traversal must return None"

    def test_absolute_baseline_outside_root_returns_none(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        result = cep._resolve_baseline_path(root, outside)
        assert result is None, "absolute path outside root must return None"

    def test_dangling_scan_oserror_returns_exit_2(self, tmp_path: Path) -> None:
        # I/O failure must exit 2 (fail-closed), not 0 (false green).
        self._make_skill(tmp_path, "python3 .claude/skills/a/x.py\n")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps({"files": {".claude/skills/a/SKILL.md": 1}}), encoding="utf-8"
        )
        with unittest.mock.patch.object(
            cep, "scan_dangling_skill_relative_scripts", side_effect=OSError("disk read failed")
        ):
            rc = cep.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 2, "OSError during dangling scan must exit 2, not 0 or 1"


class TestPrAutofixConverted:
    """Issue #2837: pr-autofix must ship zero bare invocations."""

    def test_pr_autofix_has_no_bare_invocations(self) -> None:
        root = Path(__file__).resolve().parents[2]
        skill = root / "src" / "copilot-cli" / "skills" / "pr-autofix" / "SKILL.md"
        if not skill.is_file():
            pytest.skip("pr-autofix SKILL.md not in this checkout")
        assert cep.count_exec_invocations(skill.read_text(encoding="utf-8")) == 0


class TestCommittedRepoHasNoDrift:
    """The CI ratchet: the committed baseline must match the committed tree."""

    def test_repo_execs_match_baseline(self) -> None:
        root = Path(__file__).resolve().parents[2]
        if not any((root.joinpath(*parts)).is_dir() for parts in cep.SCAN_ROOTS):
            pytest.skip("no skill scan roots in this checkout")
        baseline_path = root / "scripts" / "validation" / cep._DEFAULT_BASELINE_NAME
        current = cep.scan_skill_execs(root)
        baseline = cep._load_baseline(baseline_path)
        regressions, _ = cep.diff_against_baseline(current, baseline)
        assert regressions == [], "\n".join(regressions)

    def test_repo_has_no_dangling_skill_relative_scripts(self) -> None:
        root = Path(__file__).resolve().parents[2]
        if not any(root.joinpath(*parts).is_dir() for parts in cep.SCAN_ROOTS):
            pytest.skip("no skill scan roots in this checkout")
        assert not (d := cep.scan_dangling_skill_relative_scripts(root)), str(d)


class TestDanglingSkillScripts:
    def _sr(self, tmp_path: Path) -> Path:
        p = tmp_path / ".claude" / "skills" / "myfoo"
        p.mkdir(parents=True)
        return p

    def test_find_skill_relative_scripts(self) -> None:
        cases = [
            ("python3 scripts/validation/pre_pr.py\n", ["scripts/validation/pre_pr.py"]),
            ("python3 .claude/skills/foo/scripts/bar.py\n", []),
            ('python3 "${ENV:-x}/skills/foo/bar.py"\n', []),
            ("python3 scripts/dangling.py\n<!-- vendor-portability-exec: examples -->\n", []),
            ("python3 -u scripts/foo.py\n", ["scripts/foo.py"]),
        ]
        for text, expected in cases:
            assert cep.find_skill_relative_scripts(text) == expected

    def test_detects_script_not_in_skill_dir_or_repo_root(self, tmp_path: Path) -> None:
        (self._sr(tmp_path) / "SKILL.md").write_text("python3 scripts/nx.py\n", encoding="utf-8")
        dangling = cep.scan_dangling_skill_relative_scripts(tmp_path)
        assert len(dangling) == 1 and dangling[0][1] == "scripts/nx.py"

    def test_accepts_script_present_in_skill_dir(self, tmp_path: Path) -> None:
        sr = self._sr(tmp_path)
        (sr / "scripts").mkdir()
        (sr / "scripts" / "s.py").write_text("", encoding="utf-8")
        (sr / "SKILL.md").write_text("python3 scripts/s.py\n", encoding="utf-8")
        assert cep.scan_dangling_skill_relative_scripts(tmp_path) == []

    def test_marker_suppresses_dangling_detection(self, tmp_path: Path) -> None:
        md = "python3 scripts/missing.py\n<!-- vendor-portability-exec: framework -->\n"
        (self._sr(tmp_path) / "SKILL.md").write_text(md, encoding="utf-8")
        assert cep.scan_dangling_skill_relative_scripts(tmp_path) == []


class TestWorkflowWiring:
    def test_workflow_runs_exec_validator_unconditionally(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = root / ".github" / "workflows" / "validate-vendor-portability.yml"
        parsed = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        job = parsed["jobs"]["validate-portability"]

        assert "if" not in job
        command = "uv run --frozen python scripts/validation/check_skill_md_exec_portability.py"
        steps = [step for step in job["steps"] if step.get("run", "").strip() == command]
        assert len(steps) == 1
        assert "if" not in steps[0]
        assert "continue-on-error" not in steps[0]


class TestScriptsExecDetection:
    """Executable invocation detection for scripts/ paths (issue #4013).

    The scripts/ tree is upstream-only; python3 scripts/x.py in a SKILL.md
    will fail silently in every consumer install just like a bare
    .claude/skills/ invocation would.
    """

    def test_counts_scripts_python_invocation(self) -> None:
        """python3 scripts/... is counted as a non-portable exec invocation.

        Isolating negative control: reverting EXEC_PATTERN to only match
        .claude/skills/ causes count_exec_invocations to return 0, failing
        this assertion. The text contains no .claude/skills/ invocation, so
        only the scripts/ component triggers detection.
        """
        text = "python3 scripts/validation/check_vendor_portability.py --repo-root .\n"
        assert cep.count_exec_invocations(text) == 1

    def test_counts_scripts_bash_invocation(self) -> None:
        """bash scripts/... is counted as a non-portable exec invocation."""
        text = "bash scripts/bootstrap-vm.sh --dev\n"
        assert cep.count_exec_invocations(text) == 1

    def test_ignores_scripts_prose_mention_without_interpreter(self) -> None:
        """A scripts/ path mentioned in prose without an interpreter is not an exec.

        The prose guard (check_skill_md_portability.py) owns bare prose mentions.
        The exec checker requires an interpreter prefix (python3/bash/sh) or a
        ./ lead-in before the path.
        """
        text = "See `scripts/validation/pre_pr.py` for details.\n"
        assert cep.count_exec_invocations(text) == 0

    def test_counts_build_scripts_python_invocation(self) -> None:
        """python3 build/scripts/... is counted as an upstream-only invocation."""
        text = "python3 build/scripts/generate_rules.py\n"
        assert cep.count_exec_invocations(text) == 1


class TestDotSlashScriptsExecDetection:
    def test_counts_dot_slash_scripts_python_invocation(self) -> None:
        """python3 ./scripts/... is counted despite the ./ prefix."""
        text = "python3 ./scripts/validation/check_vendor_portability.py --repo-root .\n"
        assert cep.count_exec_invocations(text) == 1

    def test_counts_dot_slash_scripts_under_uv_run(self) -> None:
        """The `uv run python ./scripts/...` form used in this repo is counted.

        The runner prefix (`uv run`) is not part of the match; the interpreter
        token inside it is what anchors the lead-in.
        """
        text = "uv run python ./scripts/validation/pre_pr.py\n"
        assert cep.count_exec_invocations(text) == 1

    def test_counts_dot_slash_scripts_with_interpreter_option(self) -> None:
        """A short option between the interpreter and ./scripts/... still counts."""
        text = "python3 -u ./scripts/validation/pre_pr.py\n"
        assert cep.count_exec_invocations(text) == 1

    def test_counts_bare_dot_slash_scripts_shell_invocation(self) -> None:
        """./scripts/x.sh with no interpreter token is counted."""
        text = "./scripts/bootstrap-vm.sh --dev\n"
        assert cep.count_exec_invocations(text) == 1

    def test_counts_dot_slash_build_scripts_invocation(self) -> None:
        """./build/scripts/... is counted when executed directly."""
        text = "./build/scripts/generate_rules.py\n"
        assert cep.count_exec_invocations(text) == 1

    def test_ignores_parent_relative_scripts_path(self) -> None:
        """python3 ../scripts/... is not counted.

        Edge case bounding the ./ branch: `../` is not `./`, and the
        path-prefix group does not match at `../scripts/`, so a parent-relative
        path is out of scope for this gate.
        """
        text = "python3 ../scripts/x.py\n"
        assert cep.count_exec_invocations(text) == 0


class TestMarkerDiff:
    def test_marker_count_increase_is_regression(self) -> None:
        regressions, improvements = cep.diff_marker_baseline(
            {".claude/skills/a/SKILL.md": 2},
            {".claude/skills/a/SKILL.md": 1},
        )
        assert regressions and ".claude/skills/a/SKILL.md" in regressions[0]
        assert improvements == []

    def test_marker_count_decrease_is_regression(self) -> None:
        regressions, improvements = cep.diff_marker_baseline(
            {".claude/skills/a/SKILL.md": 0},
            {".claude/skills/a/SKILL.md": 1},
        )
        assert regressions and "baseline 1" in regressions[0]
        assert improvements == []
