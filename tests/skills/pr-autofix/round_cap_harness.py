"""Shared plumbing for the check_pr_round_cap.py test modules (issues #5056, #5477)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package), matching
# tests/test_check_pr_live_state.py's pattern for the sibling gate script.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("check_pr_round_cap")
main = _mod.main
build_parser = _mod.build_parser
evaluate_round_cap = _mod.evaluate_round_cap
parse_marker = _mod.parse_marker
render_state_marker = _mod.render_state_marker
render_escalation_comment = _mod.render_escalation_comment
select_latest_state = _mod.select_latest_state
RoundCapStoreError = _mod.RoundCapStoreError


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


class MainHarness:
    """Shared patch plumbing for the main() test classes."""

    def teardown_method(self):
        for extra in getattr(self, "_extra", []):
            extra.stop()
        self._extra = []

    def _patch_common(
        self, list_comments_result=None, list_comments_error=None,
        head_sha="sha-1", events=None,
    ):
        self._extra = [
            patch("check_pr_round_cap._fetch_head_sha", return_value=head_sha),
            patch("check_pr_round_cap._list_issue_events", return_value=events or []),
        ]
        for extra in self._extra:
            extra.start()
        patches = [
            patch("check_pr_round_cap.assert_gh_authenticated"),
            patch(
                "check_pr_round_cap.resolve_repo_params",
                return_value=_mod.RepoInfo(owner="o", repo="r"),
            ),
        ]
        if list_comments_error is not None:
            list_patch = patch(
                "check_pr_round_cap._list_comments", side_effect=list_comments_error,
            )
        else:
            list_patch = patch(
                "check_pr_round_cap._list_comments",
                return_value=list_comments_result or [],
            )
        patches.append(list_patch)
        return patches


