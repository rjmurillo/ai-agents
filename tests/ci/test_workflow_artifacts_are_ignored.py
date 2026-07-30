"""Workflow artifacts written to the checkout root must be ignored by git.

Several workflows generate reports, issue bodies, and counters into the working
directory. On an ephemeral runner that is harmless. Locally, anything a workflow
step or a test harness produces at the repository root is untracked litter, and
`git add -A` sweeps it into a commit. That has already happened once, which is
why `pr-validation-report.md` carries an ignore rule.

This test generalizes that one rule: every bare-root artifact any workflow
writes must be ignored, so adding a new one fails here instead of surfacing as a
stray file in somebody's commit months later.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

_ARTIFACT_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*\.(?:md|json|txt|sarif|xml)"
_WRITE_OP = r"(?:>>?|--[a-z-]*out|--body-file|--output)"

# A redirect, a --body-file, or an --*-out flag whose target is a bare filename
# with no directory part, which lands in whatever directory the step happens to
# run in.
#
# A slash in the target is not by itself proof the write is deliberate:
# `${VAR:-.}/name` contains a slash and still lands in the checkout root
# whenever VAR is unset. This pattern deliberately does not try to cover that
# case; FALLBACK_ROOTED_WRITE_RE below does, and the two are checked together.
ARTIFACT_WRITE_RE = re.compile(
    rf"""(?:^|\s){_WRITE_OP}\s+ "?(?P<path>{_ARTIFACT_NAME})"?""",
    re.VERBOSE,
)

# The same write, but rooted at a shell variable carrying a relative fallback:
# `${RUNNER_TEMP:-.}/comment.md` resolves to `./comment.md` whenever the
# variable is unset, which is every local run and every harness that is not a
# GitHub-hosted runner. The slash makes it invisible to ARTIFACT_WRITE_RE, so
# without this pattern a workflow could sidestep the ignore requirement by
# adding a fallback that lands right back in the checkout root.
FALLBACK_ROOTED_WRITE_RE = re.compile(
    rf"""(?:^|\s){_WRITE_OP}\s+
        "?\$\{{[A-Za-z_][A-Za-z0-9_]*:-\.\}}/(?P<path>{_ARTIFACT_NAME})"?""",
    re.VERBOSE,
)


def _bare_root_artifacts() -> dict[str, list[str]]:
    """Map each workflow file to the bare-root artifact paths it writes.

    Covers both a literal bare name and a name rooted at a variable whose
    fallback is the current directory, because the two land in the same place
    once the variable is unset.
    """
    found: dict[str, list[str]] = {}
    for workflow in sorted(WORKFLOWS_DIR.glob("*.yml")):
        text = workflow.read_text()
        paths = {m.group("path") for m in ARTIFACT_WRITE_RE.finditer(text)}
        paths |= {m.group("path") for m in FALLBACK_ROOTED_WRITE_RE.finditer(text)}
        if paths:
            found[workflow.name] = sorted(paths)
    return found


def _is_ignored(relative_path: str) -> bool:
    """Ask git whether a path is ignored, without needing the file to exist."""
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", relative_path],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode not in (0, 1):
        pytest.fail(
            f"git check-ignore failed for {relative_path!r}: "
            f"rc={completed.returncode} stderr={completed.stderr.decode(errors='replace')}"
        )
    return completed.returncode == 0


class TestWorkflowArtifactsStayOutOfCommits:
    def test_every_bare_root_artifact_is_ignored(self) -> None:
        """Positive: no workflow can leave an unignored file at the repo root."""
        exposed = {
            workflow: [path for path in paths if not _is_ignored(path)]
            for workflow, paths in _bare_root_artifacts().items()
        }
        exposed = {workflow: paths for workflow, paths in exposed.items() if paths}
        assert exposed == {}, (
            "these workflows write files to the repository root that git does "
            f"not ignore, so `git add -A` will commit them: {exposed}. Either "
            "add an anchored .gitignore rule or write the artifact under a "
            "temporary directory instead"
        )

    def test_the_scan_finds_artifacts_to_check(self) -> None:
        """Edge: a regex that matches nothing would make the assertion vacuous."""
        found = _bare_root_artifacts()
        assert found, (
            f"no artifact writes were found in {WORKFLOWS_DIR}, so the check "
            "above passed without examining anything"
        )

    def test_a_tracked_file_is_not_reported_as_ignored(self) -> None:
        """Negative control: the probe distinguishes ignored from not ignored."""
        assert not _is_ignored("README.md"), (
            "the ignore probe reports a tracked file as ignored, so a passing "
            "result in the positive test would prove nothing"
        )

    def test_no_artifact_rule_is_broad_enough_to_hide_source(self) -> None:
        """Negative control: an unanchored rule would hide files tree-wide."""
        leaked = [
            path
            for paths in _bare_root_artifacts().values()
            for path in paths
            if _is_ignored((Path("docs") / path).as_posix())
        ]
        assert leaked == [], (
            f"these artifact names are ignored outside the repository root: "
            f"{sorted(set(leaked))}. The rules lost their leading slash and now "
            "hide every same-named file in the tree, not just the generated one"
        )


class TestFallbackRootedWritesAreNotAnEscapeHatch:
    """A `${VAR:-.}/name` destination is the checkout root whenever VAR is unset."""

    def test_a_fallback_rooted_write_is_detected(self) -> None:
        """Positive: the pattern claims the form it exists to catch."""
        match = FALLBACK_ROOTED_WRITE_RE.search('--body-file "${RUNNER_TEMP:-.}/comment.md"')
        assert match is not None, (
            "a write rooted at a variable with a current-directory fallback was "
            "not detected, so such a write could skip the ignore requirement"
        )
        assert match.group("path") == "comment.md"

    def test_a_redirect_with_a_fallback_root_is_detected(self) -> None:
        """Positive: redirects use the same operator set as flag-style writes."""
        match = FALLBACK_ROOTED_WRITE_RE.search('cat x >> "${RUNNER_TEMP:-.}/issue-body.md"')
        assert match is not None
        assert match.group("path") == "issue-body.md"

    def test_an_unconditional_variable_root_is_not_flagged(self) -> None:
        """Negative: `${RUNNER_TEMP}/x` never resolves into the checkout."""
        assert FALLBACK_ROOTED_WRITE_RE.search('--body-file "${RUNNER_TEMP}/comment.md"') is None, (
            "a destination with no current-directory fallback was flagged, "
            "which would force ignore rules for files that never land in the tree"
        )

    def test_an_absolute_destination_is_not_flagged(self) -> None:
        """Negative: an absolute path is already outside the checkout."""
        assert FALLBACK_ROOTED_WRITE_RE.search('--body-file "/tmp/issue-body.md"') is None

    def test_a_non_dot_fallback_is_not_flagged(self) -> None:
        """Edge: only a `.` fallback lands in the checkout root."""
        assert (
            FALLBACK_ROOTED_WRITE_RE.search('--body-file "${RUNNER_TEMP:-/tmp}/comment.md"') is None
        ), "a fallback pointing outside the checkout was treated as pollution"

    def test_every_fallback_rooted_artifact_is_ignored(self) -> None:
        """Positive: the live workflows honour the rule this pattern enforces."""
        exposed = sorted(
            {
                match.group("path")
                for workflow in WORKFLOWS_DIR.glob("*.yml")
                for match in FALLBACK_ROOTED_WRITE_RE.finditer(workflow.read_text())
                if not _is_ignored(match.group("path"))
            }
        )
        assert exposed == [], (
            f"these fallback-rooted artifacts are not ignored: {exposed}. With "
            "the variable unset they land in the checkout root, so `git add -A` "
            "would commit them"
        )

    def test_fallback_rooted_names_reach_the_shared_artifact_scan(self) -> None:
        """Positive: the union feeds the tree-wide ignore control, not just this class.

        Without this the fallback pattern can be unwired from
        `_bare_root_artifacts` and every other test still passes, which leaves
        the over-broad-ignore-rule control blind to the relocated artifacts.
        """
        direct = {
            match.group("path")
            for workflow in WORKFLOWS_DIR.glob("*.yml")
            for match in FALLBACK_ROOTED_WRITE_RE.finditer(workflow.read_text())
        }
        assert direct, "no workflow uses a fallback-rooted destination, so this test is vacuous"
        scanned = {path for paths in _bare_root_artifacts().values() for path in paths}
        assert direct <= scanned, (
            f"these fallback-rooted artifacts are missing from the shared scan: "
            f"{sorted(direct - scanned)}. The checks built on _bare_root_artifacts "
            "cannot see them"
        )
