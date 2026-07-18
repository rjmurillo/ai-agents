"""Tests for check_pr_live_state.py skill script (issue #2455).

The script is the per-PR live-state re-triage probe that pr-autofix MUST
call immediately before acting on each PR. It catches two failure modes
that an early session-start triage misses:

1. **Live state drift**: a PR that was OPEN at session-start has been
   merged or closed by mid-run automation. Acting on it now wastes work
   and risks pushing redundant commits.
2. **Superseded by main**: the PR's diff has already landed on main (via
   a sibling consolidated PR) so its commits patch-id-match origin/main
   and a merge would create a no-op / conflicting duplicate.

Evidence: pr-autofix session 2026-06-05 deep-worked PRs #2409/#2412 that
were already superseded by the consolidated PR #2394 on main; #2409 was
auto-merge-armed before the redundancy was caught.

Exit codes follow ADR-035:
    0 - PR is safe to act on (still OPEN; not superseded by main)
    1 - PR should be skipped/closed (merged, closed, or superseded by main)
    2 - PR not found
    3 - External error (API failure or git failure)
    4 - Auth error
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
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


_mod = _import_script("check_pr_live_state")
main = _mod.main
build_parser = _mod.build_parser
classify_live_state = _mod.classify_live_state
parse_git_cherry = _mod.parse_git_cherry
is_superseded_by_base = _mod.is_superseded_by_base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=rc, stdout=stdout, stderr=stderr,
    )


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_pull_request_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--pull-request", "2409"])
        assert args.pull_request == 2409
        assert args.owner == ""
        assert args.repo == ""
        # Skip-fetch default is False so callers re-fetch by default; a
        # PR-autofix walk that already ran one fetch can pass --skip-fetch
        # to avoid a network call per PR.
        assert args.skip_fetch is False

    def test_skip_fetch_flag(self):
        args = build_parser().parse_args(
            ["--pull-request", "2409", "--skip-fetch"],
        )
        assert args.skip_fetch is True

    def test_owner_repo_passthrough(self):
        args = build_parser().parse_args(
            ["--pull-request", "1", "--owner", "rjmurillo", "--repo", "ai-agents"],
        )
        assert args.owner == "rjmurillo"
        assert args.repo == "ai-agents"


# ---------------------------------------------------------------------------
# Tests: parse_git_cherry
# ---------------------------------------------------------------------------


class TestParseGitCherry:
    """git cherry output: each commit on the PR branch is prefixed by
    '+ <sha>' (not in base) or '- <sha>' (patch-id present in base, i.e.
    superseded). 'Fully superseded' means every PR commit is prefixed '-'.
    """

    def test_empty_output_is_no_commits(self):
        verdict = parse_git_cherry("")
        assert verdict["fully_superseded"] is False
        assert verdict["pr_commits"] == 0
        assert verdict["superseded_commits"] == 0

    def test_all_plus_lines_means_no_supersession(self):
        out = "+ abc1234567890\n+ def4567890abc\n"
        verdict = parse_git_cherry(out)
        assert verdict["fully_superseded"] is False
        assert verdict["pr_commits"] == 2
        assert verdict["superseded_commits"] == 0

    def test_all_minus_lines_means_fully_superseded(self):
        out = "- abc1234567890\n- def4567890abc\n"
        verdict = parse_git_cherry(out)
        assert verdict["fully_superseded"] is True
        assert verdict["pr_commits"] == 2
        assert verdict["superseded_commits"] == 2

    def test_mixed_lines_means_partially_superseded(self):
        out = "- abc1234567890\n+ def4567890abc\n- ghi7890abcdef\n"
        verdict = parse_git_cherry(out)
        assert verdict["fully_superseded"] is False
        assert verdict["pr_commits"] == 3
        assert verdict["superseded_commits"] == 2

    def test_extra_whitespace_tolerated(self):
        out = "  - abc1234567890  \n  + def4567890abc  \n"
        verdict = parse_git_cherry(out)
        assert verdict["pr_commits"] == 2
        assert verdict["superseded_commits"] == 1

    def test_malformed_lines_ignored(self):
        out = "garbage line\n- abc1234567890\nnothing here\n"
        verdict = parse_git_cherry(out)
        # Only the well-formed '- abc' counts.
        assert verdict["pr_commits"] == 1
        assert verdict["superseded_commits"] == 1
        assert verdict["fully_superseded"] is True


# ---------------------------------------------------------------------------
# Tests: classify_live_state
# ---------------------------------------------------------------------------


class TestClassifyLiveState:
    """Classification of a PR's live GitHub state into a per-PR verdict.

    Verdict shape: {"action": str, "reason": str}
      - action="ACT" means safe to proceed with the planned per-tier action
      - action="SKIP" means do NOT act; the PR is closed/merged/superseded
    """

    def test_merged_pr_is_skip(self):
        pr = {"state": "MERGED", "merged": True, "isDraft": False, "closed": True}
        verdict = classify_live_state(pr, supersession=None)
        assert verdict["action"] == "SKIP"
        assert "merged" in verdict["reason"].lower()

    def test_closed_unmerged_pr_is_skip(self):
        pr = {"state": "CLOSED", "merged": False, "isDraft": False, "closed": True}
        verdict = classify_live_state(pr, supersession=None)
        assert verdict["action"] == "SKIP"
        assert "closed" in verdict["reason"].lower()

    def test_draft_pr_is_skip(self):
        pr = {"state": "OPEN", "merged": False, "isDraft": True, "closed": False}
        verdict = classify_live_state(pr, supersession=None)
        assert verdict["action"] == "SKIP"
        assert "draft" in verdict["reason"].lower()

    def test_open_pr_with_no_supersession_is_act(self):
        pr = {"state": "OPEN", "merged": False, "isDraft": False, "closed": False}
        verdict = classify_live_state(pr, supersession=None)
        assert verdict["action"] == "ACT"

    def test_open_pr_fully_superseded_is_skip(self):
        pr = {"state": "OPEN", "merged": False, "isDraft": False, "closed": False}
        supersession = {
            "fully_superseded": True,
            "pr_commits": 2,
            "superseded_commits": 2,
        }
        verdict = classify_live_state(pr, supersession=supersession)
        assert verdict["action"] == "SKIP"
        # The reason names the cause so the autofix log explains the skip.
        assert "superseded" in verdict["reason"].lower()

    def test_open_pr_partially_superseded_still_acts(self):
        pr = {"state": "OPEN", "merged": False, "isDraft": False, "closed": False}
        supersession = {
            "fully_superseded": False,
            "pr_commits": 3,
            "superseded_commits": 2,
        }
        verdict = classify_live_state(pr, supersession=supersession)
        # Partial supersession does NOT auto-skip: the remaining commit may
        # be a real change. Surface as a note instead.
        assert verdict["action"] == "ACT"
        assert "partial" in verdict["reason"].lower()

    def test_open_pr_inconclusive_probe_acts_with_distinct_reason(self):
        # An unresolvable PR head (deleted, network failure) must ACT but with
        # a reason that names the inconclusive probe, not the clean not-
        # superseded reason. Distinguishes trustworthy from inconclusive.
        pr = {"state": "OPEN", "merged": False, "isDraft": False, "closed": False}
        supersession = {
            "fully_superseded": False,
            "pr_commits": 0,
            "superseded_commits": 0,
            "git_cherry_failed": True,
            "probe_inconclusive": True,
            "head_unresolved": True,
        }
        verdict = classify_live_state(pr, supersession=supersession)
        assert verdict["action"] == "ACT"
        assert "inconclusive" in verdict["reason"].lower()
        assert verdict["reason"] != "PR is still open and actionable"
        assert "head could not be resolved" in verdict["reason"]

    def test_cherry_failure_inconclusive_reason_differs_from_head_unresolved(self):
        # A cherry failure (head resolved successfully, but git cherry failed)
        # must report a different reason than a head-unresolved failure. Both
        # are inconclusive, but the cause differs (issue #3116 follow-up).
        pr = {"state": "OPEN", "merged": False, "isDraft": False, "closed": False}
        supersession_cherry_failed = {
            "fully_superseded": False,
            "pr_commits": 0,
            "superseded_commits": 0,
            "git_cherry_failed": True,
            "probe_inconclusive": True,
        }
        verdict = classify_live_state(pr, supersession=supersession_cherry_failed)
        assert verdict["action"] == "ACT"
        assert "inconclusive" in verdict["reason"].lower()
        assert "git cherry failed" in verdict["reason"]
        assert "head could not be resolved" not in verdict["reason"]


# ---------------------------------------------------------------------------
# Tests: is_superseded_by_base
# ---------------------------------------------------------------------------


def _git_kind(cmd: list[str]) -> str:
    """Classify a mocked git invocation for the supersession probe.

    'base_fetch' populates origin/<base>; 'head_fetch' resolves the PR head
    via refs/pull/<n>/head (issue #3116); 'cherry' is the supersession diff.
    """
    if cmd[:2] == ["git", "fetch"]:
        return "head_fetch" if "refs/pull/" in cmd[-1] else "base_fetch"
    if "cherry" in cmd:
        return "cherry"
    return "other"


class TestIsSupersededByBase:
    """End-to-end git interaction: fetch base, resolve the PR head via
    refs/pull/<n>/head, then git cherry. Each subprocess call MUST be mocked.
    """

    def test_skip_fetch_skips_base_fetch_but_still_resolves_head(self):
        # --skip-fetch skips the shared base fetch (the outer loop already
        # ran one), but the per-PR head MUST still be resolved: the outer
        # loop never fetches individual PR branches (issue #3116).
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            kind = _git_kind(cmd)
            if kind == "base_fetch":
                raise AssertionError("base fetch must not run with skip_fetch=True")
            if kind == "cherry":
                return _completed(stdout="- abc1234567890\n", rc=0)
            return _completed(rc=0)

        with patch("check_pr_live_state.subprocess.run", side_effect=fake_run):
            result = is_superseded_by_base(
                base_branch="main",
                pr_number=2409,
                skip_fetch=True,
            )
        assert result["fully_superseded"] is True
        assert result["probe_inconclusive"] is False
        head_fetches = [c for c in calls if _git_kind(c) == "head_fetch"]
        assert len(head_fetches) == 1
        assert "+refs/pull/2409/head:refs/pr-live-state/2409" in head_fetches[0]
        assert [c for c in calls if _git_kind(c) == "base_fetch"] == []

    def test_base_and_head_fetched_by_default(self):
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if _git_kind(cmd) == "cherry":
                return _completed(stdout="+ abc1234567890\n", rc=0)
            return _completed(rc=0)

        with patch("check_pr_live_state.subprocess.run", side_effect=fake_run):
            is_superseded_by_base(
                base_branch="main",
                pr_number=2409,
                skip_fetch=False,
            )
        base_fetches = [c for c in calls if _git_kind(c) == "base_fetch"]
        head_fetches = [c for c in calls if _git_kind(c) == "head_fetch"]
        assert len(base_fetches) == 1
        # Fetch must populate origin/<base>; `git fetch origin main` only updates FETCH_HEAD.
        assert "+refs/heads/main:refs/remotes/origin/main" in base_fetches[0]
        assert len(head_fetches) == 1
        assert "+refs/pull/2409/head:refs/pr-live-state/2409" in head_fetches[0]

    def test_cherry_runs_against_resolved_pr_ref_fork_safe(self):
        # The cherry compares origin/<base> against the private pull ref, not
        # origin/<headRefName>. That path is fork-safe (a fork PR has no
        # branch in the base-repo namespace) and branch-name-agnostic.
        captured_cmd: list[str] = []

        def fake_run(cmd, **kwargs):
            if _git_kind(cmd) == "cherry":
                captured_cmd.extend(cmd)
                return _completed(stdout="", rc=0)
            return _completed(rc=0)

        with patch("check_pr_live_state.subprocess.run", side_effect=fake_run):
            is_superseded_by_base(
                base_branch="main",
                pr_number=2409,
                skip_fetch=True,
            )
        assert "origin/main" in captured_cmd
        assert "refs/pr-live-state/2409" in captured_cmd
        # No dependence on a possibly-absent origin/<head> remote-tracking ref.
        origin_refs = [c for c in captured_cmd if c.startswith("origin/")]
        assert origin_refs == ["origin/main"]

    def test_missing_local_head_ref_is_fetched_before_cherry(self):
        # A fresh/pruned clone lacks the PR branch locally; the fix fetches
        # refs/pull/<n>/head first, so the cherry then succeeds (issue #3116).
        order: list[str] = []

        def fake_run(cmd, **kwargs):
            kind = _git_kind(cmd)
            order.append(kind)
            if kind == "cherry":
                return _completed(stdout="- abc1234567890\n", rc=0)
            return _completed(rc=0)

        with patch("check_pr_live_state.subprocess.run", side_effect=fake_run):
            result = is_superseded_by_base(
                base_branch="main",
                pr_number=2409,
                skip_fetch=True,
            )
        assert result["fully_superseded"] is True
        assert result["probe_inconclusive"] is False
        # The head is resolved before the cherry that consumes it.
        assert order.index("head_fetch") < order.index("cherry")

    def test_deleted_head_is_inconclusive_not_false_negative(self):
        # A deleted / unresolvable PR head must NOT return a clean
        # "not superseded" ACT; it surfaces an inconclusive probe and the
        # cherry never runs against a phantom ref (issue #3116).
        def fake_run(cmd, **kwargs):
            kind = _git_kind(cmd)
            if kind == "cherry":
                raise AssertionError("cherry must not run when head is unresolved")
            if kind == "head_fetch":
                return _completed(stderr="fatal: couldn't find remote ref", rc=128)
            return _completed(rc=0)

        with patch("check_pr_live_state.subprocess.run", side_effect=fake_run):
            result = is_superseded_by_base(
                base_branch="main",
                pr_number=999,
                skip_fetch=True,
            )
        assert result["fully_superseded"] is False
        assert result["probe_inconclusive"] is True
        assert result["git_cherry_failed"] is True
        assert result.get("head_unresolved") is True

    def test_cherry_failure_surfaces_as_inconclusive(self):
        # If git cherry exits non-zero after the head resolves, we cannot
        # prove supersession; report inconclusive, never a false positive.
        def fake_run(cmd, **kwargs):
            if _git_kind(cmd) == "cherry":
                return _completed(stdout="", stderr="fatal: bad object", rc=128)
            return _completed(rc=0)

        with patch("check_pr_live_state.subprocess.run", side_effect=fake_run):
            result = is_superseded_by_base(
                base_branch="main",
                pr_number=2409,
                skip_fetch=True,
            )
        assert result["fully_superseded"] is False
        assert result["git_cherry_failed"] is True
        assert result["probe_inconclusive"] is True


# ---------------------------------------------------------------------------
# Tests: main exit codes (end-to-end)
# ---------------------------------------------------------------------------


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch(
            "check_pr_live_state.assert_gh_authenticated",
            side_effect=SystemExit(4),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--pull-request", "1"])
        assert exc.value.code == 4

    def test_pr_not_found_exits_2(self, capsys):
        # GraphQL returns an empty pullRequest: exit code 2.
        with patch("check_pr_live_state.assert_gh_authenticated"):
            with patch(
                "check_pr_live_state.resolve_repo_params",
                return_value=_mod.RepoInfo(owner="o", repo="r"),
            ):
                with patch(
                    "check_pr_live_state.gh_graphql",
                    return_value={"repository": {"pullRequest": None}},
                ):
                    with pytest.raises(SystemExit) as exc:
                        main(["--pull-request", "999"])
        assert exc.value.code == 2

    def test_open_pr_not_superseded_exits_0(self, capsys):
        pr = {
            "number": 2409,
            "state": "OPEN",
            "merged": False,
            "isDraft": False,
            "closed": False,
            "headRefName": "fix/foo",
            "baseRefName": "main",
        }
        with patch("check_pr_live_state.assert_gh_authenticated"), \
             patch(
                "check_pr_live_state.resolve_repo_params",
                return_value=_mod.RepoInfo(owner="o", repo="r"),
             ), \
             patch(
                "check_pr_live_state.gh_graphql",
                return_value={"repository": {"pullRequest": pr}},
             ), \
             patch(
                "check_pr_live_state.subprocess.run",
                return_value=_completed(stdout="+ abc1234567890\n", rc=0),
             ):
            rc = main(["--pull-request", "2409", "--skip-fetch"])
        assert rc == 0
        out = capsys.readouterr().out
        envelope = json.loads(out)
        assert envelope["Success"] is True
        payload = envelope["Data"]
        assert payload["action"] == "ACT"
        assert payload["pull_request"] == 2409
        assert payload["state"] == "OPEN"
        assert payload["superseded_by_base"]["fully_superseded"] is False

    def test_merged_pr_exits_1(self, capsys):
        pr = {
            "number": 2412,
            "state": "MERGED",
            "merged": True,
            "isDraft": False,
            "closed": True,
            "headRefName": "fix/bar",
            "baseRefName": "main",
        }
        with patch("check_pr_live_state.assert_gh_authenticated"), \
             patch(
                "check_pr_live_state.resolve_repo_params",
                return_value=_mod.RepoInfo(owner="o", repo="r"),
             ), \
             patch(
                "check_pr_live_state.gh_graphql",
                return_value={"repository": {"pullRequest": pr}},
             ):
            rc = main(["--pull-request", "2412", "--skip-fetch"])
        assert rc == 1
        out = capsys.readouterr().out
        envelope = json.loads(out)
        assert envelope["Success"] is True
        payload = envelope["Data"]
        assert payload["action"] == "SKIP"
        assert payload["state"] == "MERGED"

    def test_superseded_open_pr_exits_1(self, capsys):
        pr = {
            "number": 2409,
            "state": "OPEN",
            "merged": False,
            "isDraft": False,
            "closed": False,
            "headRefName": "fix/foo",
            "baseRefName": "main",
        }
        with patch("check_pr_live_state.assert_gh_authenticated"), \
             patch(
                "check_pr_live_state.resolve_repo_params",
                return_value=_mod.RepoInfo(owner="o", repo="r"),
             ), \
             patch(
                "check_pr_live_state.gh_graphql",
                return_value={"repository": {"pullRequest": pr}},
             ), \
             patch(
                "check_pr_live_state.subprocess.run",
                return_value=_completed(stdout="- abc1234567890\n- def4567890abc\n", rc=0),
             ):
            rc = main(["--pull-request", "2409", "--skip-fetch"])
        assert rc == 1
        out = capsys.readouterr().out
        envelope = json.loads(out)
        assert envelope["Success"] is True
        payload = envelope["Data"]
        assert payload["action"] == "SKIP"
        assert payload["state"] == "OPEN"
        assert payload["superseded_by_base"]["fully_superseded"] is True
        assert "superseded" in payload["reason"].lower()
