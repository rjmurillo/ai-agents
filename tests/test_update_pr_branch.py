"""Tests for update_pr_branch.py: request, refusal, auth, and error paths.

AC numbers refer to the acceptance criteria in the PR body. The --wait loop
is covered in tests/test_update_pr_branch_wait.py.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from tests.update_pr_branch_harness import (
    HEAD_MOVED_BODY,
    HEAD_MOVED_MESSAGE,
    OLD_HEAD,
    OTHER_HEAD,
    SKILL_MD,
    FakeGh,
    GhAuthResult,
    GhAuthStatus,
    assert_expected_sha_forwarded,
    completed,
    envelope,
    pr_json,
    run_main,
    script,
)


class TestUpdateRequested:
    def test_update_without_wait_returns_old_head_and_message(self, capsys):
        """AC1: 202 returns exit 0 with old head and API message."""
        fake = FakeGh()
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Success"] is True
        data = env["Data"]
        assert data["action"] == "update_requested"
        assert data["already_up_to_date"] is False
        assert data["old_head_sha"] == OLD_HEAD
        assert data["new_head_sha"] is None
        assert data["message"] == "Updating pull request branch."
        assert data["behind_by"] == 3
        assert len(fake.put_calls()) == 1
        # AC2: without the flag, no expected_head_sha field is sent.
        assert not any("expected_head_sha" in arg for arg in fake.put_calls()[0])

    def test_expected_head_sha_is_forwarded(self, capsys):
        """AC2: --expected-head-sha reaches the PUT body."""
        fake = FakeGh()
        rc = run_main(["--pull-request", "50", "--expected-head-sha", OLD_HEAD], fake)
        assert rc == 0
        assert_expected_sha_forwarded(fake.put_calls(), OLD_HEAD)
        assert envelope(capsys)["Data"]["expected_head_sha"] == OLD_HEAD

    def test_negative_control_unforwarded_sha_fails_the_forwarding_check(self, capsys):
        """AC2 negative control: drop the SHA from the PUT and the check goes red."""
        original = script._build_update_args

        def _drops_sha(pr, repo_flag, expected_head_sha):
            return original(pr, repo_flag, "")

        fake = FakeGh()
        with patch.object(script, "_build_update_args", side_effect=_drops_sha):
            rc = run_main(["--pull-request", "50", "--expected-head-sha", OLD_HEAD], fake)
        assert rc == 0
        assert fake.put_calls(), "PUT never ran, so the control proves nothing"
        with pytest.raises(AssertionError):
            assert_expected_sha_forwarded(fake.put_calls(), OLD_HEAD)


class TestHeadMoved:
    def test_422_head_moved_exits_1_typed(self, capsys):
        """AC3: GitHub 422 on a head that moved after the read maps to exit 1."""
        fake = FakeGh(put=completed(
            stdout=HEAD_MOVED_BODY,
            stderr=f"gh: {HEAD_MOVED_MESSAGE} (HTTP 422)",
            rc=1,
        ))
        rc = run_main(["--pull-request", "50", "--expected-head-sha", OLD_HEAD], fake)
        env = envelope(capsys)
        assert rc == 1
        assert env["Success"] is False
        assert env["Error"]["Type"] == "VerificationFailed"
        assert env["Data"]["reason"] == "head_moved"
        assert env["Data"]["expected_head_sha"] == OLD_HEAD
        # The head read before the PUT is stale once GitHub refuses it.
        assert env["Data"]["current_head_sha"] is None
        assert env["Error"]["Message"].endswith(
            f"head is no longer {OLD_HEAD}. Re-read the head and retry.",
        )
        assert len(fake.put_calls()) == 1

    @pytest.mark.parametrize("behind", ["0", "3"])
    def test_local_pin_mismatch_exits_1_without_put(self, capsys, behind):
        """AC3: a pin that already disagrees with the PR head is refused locally,
        even when the PR is already up to date."""
        fake = FakeGh(behind=[behind])
        rc = run_main(["--pull-request", "50", "--expected-head-sha", OTHER_HEAD], fake)
        env = envelope(capsys)
        assert rc == 1
        assert env["Data"]["reason"] == "head_moved"
        assert env["Data"]["current_head_sha"] == OLD_HEAD
        assert f"the PR head is {OLD_HEAD}, not {OTHER_HEAD}." in env["Error"]["Message"]
        assert fake.put_calls() == []

    def test_other_422_exits_3(self, capsys):
        """AC9: a 422 that is neither head-moved nor up-to-date is external."""
        fake = FakeGh(put=completed(
            stdout=json.dumps({"message": "merge conflict between base and head"}),
            stderr="gh: merge conflict between base and head (HTTP 422)",
            rc=1,
        ))
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 3
        assert env["Error"]["Type"] == "ApiError"
        assert "merge conflict" in env["Error"]["Message"]


class TestRefusedStates:
    @pytest.mark.parametrize(
        ("state", "shown"),
        [("CLOSED", "closed"), ("MERGED", "merged"), ("", "unknown state")],
    )
    def test_non_open_pr_exits_1_without_put(self, capsys, state, shown):
        """AC4: closed, merged, and unreadable states are refused before any mutation."""
        fake = FakeGh(pr_views=[pr_json(state=state)])
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 1
        assert env["Error"]["Type"] == "InvalidParams"
        assert shown in env["Error"]["Message"]
        assert fake.put_calls() == []

    def test_invalid_sha_exits_1_before_any_call(self, capsys):
        """AC10: a malformed SHA fails before auth or API work."""
        fake = FakeGh()
        rc = run_main(["--pull-request", "50", "--expected-head-sha", "abc"], fake)
        assert rc == 1
        assert envelope(capsys)["Error"]["Type"] == "InvalidParams"
        assert fake.calls == []

    def test_timeout_without_wait_exits_1(self, capsys):
        """--timeout-seconds only means something with --wait."""
        fake = FakeGh()
        rc = run_main(["--pull-request", "50", "--timeout-seconds", "10"], fake)
        assert rc == 1
        assert fake.calls == []

    def test_pr_not_found_exits_2(self, capsys):
        """AC9: GraphQL's could-not-resolve text maps to not found."""
        def _missing(cmd, **kwargs):
            return completed(
                stderr="GraphQL: Could not resolve to a PullRequest with the number of 50.",
                rc=1,
            )

        rc = run_main(["--pull-request", "50"], _missing)
        assert rc == 2
        assert envelope(capsys)["Error"]["Type"] == "NotFound"


class TestAlreadyUpToDate:
    def test_behind_by_zero_is_success_without_put(self, capsys):
        """AC5: compare reports 0 behind, so no PUT and a clear field."""
        fake = FakeGh(behind=["0"])
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["already_up_to_date"] is True
        assert env["Data"]["action"] == "none"
        assert env["Data"]["new_head_sha"] == OLD_HEAD
        assert fake.put_calls() == []

    def test_422_no_new_commits_race_is_success(self, capsys):
        """AC5: the base caught up between compare and PUT."""
        fake = FakeGh(put=completed(
            stdout=json.dumps({"message": "There are no new commits on the base branch."}),
            stderr="gh: There are no new commits on the base branch. (HTTP 422)",
            rc=1,
        ))
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["already_up_to_date"] is True

    def test_compare_failure_still_attempts_update_and_says_so(self, capsys):
        """A compare failure is reported in precheck, and GitHub adjudicates."""
        fake = FakeGh(behind=["not-a-number"])
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["behind_by"] is None
        assert env["Data"]["precheck"].startswith("unavailable")
        assert len(fake.put_calls()) == 1


class TestAuth:
    def test_auth_preflight_failure_exits_4(self, capsys):
        """AC6: invalid credentials exit 4 with an AuthError envelope."""
        fake = FakeGh()
        rc = run_main(
            ["--pull-request", "50"],
            fake,
            auth=GhAuthResult(GhAuthStatus.INVALID_CREDENTIALS, "bad token"),
        )
        assert rc == 4
        assert envelope(capsys)["Error"]["Type"] == "AuthError"
        assert fake.calls == []

    def test_put_auth_failure_exits_4(self, capsys):
        """AC6: a 401 on the PUT itself exits 4."""
        fake = FakeGh(put=completed(stderr="gh: Bad credentials (HTTP 401)", rc=1))
        rc = run_main(["--pull-request", "50"], fake)
        assert rc == 4
        assert envelope(capsys)["Error"]["Type"] == "AuthError"


class TestSkillDoc:
    def test_skill_md_documents_the_script(self):
        """The github SKILL.md names the script and its exit codes."""
        text = SKILL_MD.read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if "`update_pr_branch.py`" in line)
        assert "--expected-head-sha" in row
        assert "--wait" in row
        for code in ("Exit 0", "exit 1", "exit 2", "exit 3", "exit 4"):
            assert code in row, code


class TestErrorPaths:
    def test_gh_timeout_exits_3(self, capsys):
        """AC9: a hung gh call becomes an exit-3 Timeout envelope."""
        def _hangs(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 30)

        rc = run_main(["--pull-request", "50"], _hangs)
        assert rc == 3
        assert envelope(capsys)["Error"]["Type"] == "Timeout"

    @pytest.mark.parametrize("body", ["not json", "[1, 2]"])
    def test_unparseable_pr_state_exits_3(self, capsys, body):
        """AC9: a PR view that is not a JSON object is an external failure."""
        fake = FakeGh(pr_views=[body])
        rc = run_main(["--pull-request", "50"], fake)
        assert rc == 3
        assert envelope(capsys)["Error"]["Type"] == "ApiError"
        assert fake.put_calls() == []

    @pytest.mark.parametrize(
        ("stderr", "code", "error_type"),
        [
            ("HTTP 403: Resource not accessible by integration", 4, "AuthError"),
            ("HTTP 502: Bad Gateway", 3, "ApiError"),
        ],
    )
    def test_pr_lookup_failure_maps_exit_code(self, capsys, stderr, code, error_type):
        """AC6, AC9: lookup failures split into auth (4) and external (3)."""
        def _fails(cmd, **kwargs):
            return completed(stderr=stderr, rc=1)

        rc = run_main(["--pull-request", "50"], _fails)
        assert rc == code
        assert envelope(capsys)["Error"]["Type"] == error_type

    def test_missing_head_skips_compare_and_reports_precheck(self, capsys):
        """No head SHA means no compare call; GitHub still adjudicates."""
        fake = FakeGh(pr_views=[pr_json(head="")])
        rc = run_main(["--pull-request", "50"], fake)
        env = envelope(capsys)
        assert rc == 0
        assert env["Data"]["precheck"] == "unavailable: PR head SHA or base ref missing"
        assert not any("/compare/" in " ".join(c) for c in fake.calls)

    def test_non_object_api_body_gives_empty_message(self, capsys):
        """A 202 body that is not an object yields an empty message, not a crash."""
        fake = FakeGh(put=completed(stdout="[]"))
        rc = run_main(["--pull-request", "50"], fake)
        assert rc == 0
        assert envelope(capsys)["Data"]["message"] == ""

    def test_put_not_found_exits_2(self, capsys):
        """AC9: a PR deleted between the read and the PUT maps to not found."""
        fake = FakeGh(put=completed(stderr="gh: Not Found (HTTP 404)", rc=1))
        rc = run_main(["--pull-request", "50"], fake)
        assert rc == 2
        assert envelope(capsys)["Error"]["Type"] == "NotFound"

    def test_base_ref_is_url_quoted_in_compare(self, capsys):
        """A base ref with '#' cannot truncate the compare path."""
        fake = FakeGh(pr_views=[json.dumps(
            {"state": "OPEN", "headRefOid": OLD_HEAD, "baseRefName": "rel/v1#x"},
        )])
        assert run_main(["--pull-request", "50"], fake) == 0
        compare = next(c for c in fake.calls if "/compare/" in " ".join(c))
        assert f"compare/rel/v1%23x...{OLD_HEAD}" in compare[2]

    def test_nonpositive_timeout_exits_1(self, capsys):
        """A zero wait bound is refused before any call."""
        fake = FakeGh()
        rc = run_main(["--pull-request", "50", "--wait", "--timeout-seconds", "0"], fake)
        assert rc == 1
        assert fake.calls == []
