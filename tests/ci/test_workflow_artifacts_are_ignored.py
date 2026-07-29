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

# A redirect, a --body-file, or an --*-out flag whose target is a bare filename
# with no directory part. A path containing a slash lands somewhere deliberate;
# a bare name lands in whatever directory the step happens to run in.
ARTIFACT_WRITE_RE = re.compile(
    r"""(?:^|\s)(?:>>?|--[a-z-]*out|--body-file|--output)\s+
        "?(?P<path>[A-Za-z0-9][A-Za-z0-9._-]*\.(?:md|json|txt|sarif|xml))"?""",
    re.VERBOSE,
)


def _bare_root_artifacts() -> dict[str, list[str]]:
    """Map each workflow file to the bare-root artifact paths it writes."""
    found: dict[str, list[str]] = {}
    for workflow in sorted(WORKFLOWS_DIR.glob("*.yml")):
        paths = {m.group("path") for m in ARTIFACT_WRITE_RE.finditer(workflow.read_text())}
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
