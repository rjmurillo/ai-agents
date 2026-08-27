# taste-lint: ignore file-size, cohesive CLI contract suite shares fixtures.
"""Tests for the issue-coordination skill scripts (issue #2477).

Covers check_existing_pr_for_issue.py (duplicate-PR detection) and claim_issue.py
(self-assign with existing-claimant guard). gh I/O is mocked at the subprocess
boundary; the keyword-matching domain logic is exercised directly.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import scripts.validation.pr_description as _prdesc

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _import(name: str):
    module_name = f"issue_coordination_{name}"
    spec = importlib.util.spec_from_file_location(module_name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_check = _import("check_existing_pr_for_issue")
_claim = _import("claim_issue")


def _proc(rc: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["gh"], rc, stdout=stdout, stderr=stderr)


def _gh_dispatch(*, user=None, pulls=None):
    """Return a ``subprocess.run`` fake that routes gh calls by command.

    ``current_login`` runs ``gh api user`` and the preflight runs
    ``gh api repos/<owner>/<repo>/pulls...``. A positional ``side_effect`` list
    binds responses to call order, so a test can pass for the wrong reason if
    the two calls swap. Dispatching on the command proves which call maps to
    which outcome and rejects any unexpected call.
    """
    def _run(cmd, *args, **kwargs):
        argv = list(cmd) if isinstance(cmd, (list, tuple)) else [cmd]
        path = argv[2] if len(argv) > 2 else ""
        if argv[:3] == ["gh", "api", "user"]:
            if user is None:
                raise AssertionError(f"unexpected `gh api user` call: {argv}")
            return user
        if "pulls" in path:
            if pulls is None:
                raise AssertionError(f"unexpected pulls call: {argv}")
            return pulls
        raise AssertionError(f"unexpected gh call: {argv}")

    return _run


class TestReferencesIssue:
    def test_fixes_keyword(self):
        assert _check.references_issue("Fixes #2477 in this PR", 2477) is True

    def test_qualified_fixes_keyword_for_same_repo(self):
        assert (
            _check.references_issue(
                "Fixes rjmurillo/ai-agents#2477",
                2477,
                repo_slug="rjmurillo/ai-agents",
            )
            is True
        )

    def test_qualified_fixes_keyword_for_other_repo_not_matched(self):
        assert (
            _check.references_issue(
                "Fixes other/repo#2477",
                2477,
                repo_slug="rjmurillo/ai-agents",
            )
            is False
        )

    def test_closes_and_resolves_keywords(self):
        assert _check.references_issue("Closes #5", 5) is True
        assert _check.references_issue("Resolves #5", 5) is True

    def test_ref_keywords_not_matched(self):
        assert _check.references_issue("Ref #5", 5) is False
        assert _check.references_issue("Refs #5", 5) is False

    def test_case_insensitive(self):
        assert _check.references_issue("FIXES #5", 5) is True

    def test_bare_number_not_matched(self):
        assert _check.references_issue("see issue #5 maybe", 5) is False

    def test_different_issue_not_matched(self):
        assert _check.references_issue("Fixes #50", 5) is False

    def test_empty(self):
        assert _check.references_issue("", 5) is False

    # -- issue #3827: closing keyword inside a code span must not count --

    def test_inline_code_span_not_matched(self):
        # Repro from issue #3827 comment (against issue 4965): a backtick-
        # wrapped closing keyword never creates a real GitHub closing link,
        # so it must not count as a claim of implementation ownership.
        assert _check.references_issue("Example: `Fixes #4965`", 4965) is False

    def test_double_backtick_inline_code_span_not_matched(self):
        assert _check.references_issue("See `` Fixes #42 `` for context", 42) is False

    def test_fenced_code_block_not_matched(self):
        body = "Prior attempt:\n```\nFixes #4965\n```\n"
        assert _check.references_issue(body, 4965) is False

    def test_tilde_fenced_code_block_not_matched(self):
        body = "~~~\nFixes #4965\n~~~\n"
        assert _check.references_issue(body, 4965) is False

    def test_bare_keyword_outside_code_span_still_matches(self):
        # Positive control: the same keyword as a real claim, no markup.
        assert _check.references_issue("Fixes #4965 on its own line", 4965) is True

    def test_keyword_in_code_span_plus_real_claim_outside_still_matches(self):
        # Edge: one match is excluded (code span) and a second, real match
        # for the SAME issue exists outside any span. The function must not
        # let the excluded match short-circuit the real one.
        body = "Example: `Fixes #4965`. Fixes #4965"
        assert _check.references_issue(body, 4965) is True

    def test_diagnostic_reference_in_code_span_still_not_matched(self):
        # Refs is already excluded by _KEYWORDS; confirm code-span exclusion
        # does not accidentally flip a non-keyword into a match.
        assert _check.references_issue("`Refs #4965`", 4965) is False

    def test_unclosed_fence_still_excludes_the_keyword_inside_it(self):
        # Copilot review on PR #5371: CommonMark treats an unclosed fence as
        # running to end of input, not as no fence at all. A body ending
        # mid-fence must still be excluded, or the keyword inside it counts
        # as a real claim GitHub never linked.
        body = "Prior attempt:\n```\nFixes #4965"
        assert _check.references_issue(body, 4965) is False

    def test_unclosed_tilde_fence_still_excludes_the_keyword_inside_it(self):
        body = "~~~\nFixes #4965"
        assert _check.references_issue(body, 4965) is False

    def test_fence_indented_up_to_three_spaces_still_excludes_the_keyword(self):
        # CommonMark 0.31.2 4.5 permits up to 3 spaces of indent on both the
        # opening and closing fence (Copilot, PR #5371 round 2). A fence
        # requiring column-0 anchoring would misread this as ordinary text
        # and count the keyword as a real claim.
        body = "  ```\n  Fixes #4965\n  ```\n"
        assert _check.references_issue(body, 4965) is False

    def test_a_line_starting_with_the_fence_chars_does_not_close_it_early(self):
        # A closing fence line must hold nothing but the fence run and
        # trailing whitespace. `` ```not-a-closer `` merely starts with the
        # same run; ending the block there would let the following keyword
        # (still code to GitHub) count as a real claim (Copilot, PR #5371
        # round 2).
        body = "```\n```not-a-closer\nFixes #4965\n```\n"
        assert _check.references_issue(body, 4965) is False

    def test_closer_longer_than_opener_still_closes_the_fence(self):
        # CommonMark 0.31.2 4.5: the closer must be the same character and
        # AT LEAST as long as the opener, not exactly as long. A 3-backtick
        # opener closes on a 4-backtick line, so the claim after it is real,
        # unfenced text (Copilot, PR #5371 round 3).
        body = "```\nignore this\n````\nFixes #4965\n"
        assert _check.references_issue(body, 4965) is True

    def test_multiline_triple_backtick_inline_span_still_excludes_the_keyword(self):
        # CommonMark 0.31.2 6.1 allows a code span to cross lines for any
        # delimiter length; confining the 3+ backtick branch to a single
        # line missed this and read the keyword as a genuine bare claim
        # (Copilot, PR #5371 round 4).
        body = "See ```example\nFixes #4965\nend``` for details."
        assert _check.references_issue(body, 4965) is False

    def test_backtick_fence_opener_with_backtick_in_info_string_is_not_a_fence(self):
        # CommonMark 0.31.2 4.5: a backtick fence's info string must not
        # itself contain a backtick; an opener that does isn't a fence at
        # all, so a real keyword after it is a genuine unfenced claim
        # (Copilot, PR #5371 round 4).
        body = "```lang`x`\nFixes #4965\n"
        assert _check.references_issue(body, 4965) is True


class TestSpanPatternsMatchCanonical:
    """Drift guard for the two duplicated span-exclusion mechanisms (PR #5371 review).

    `references_issue()`'s span-exclusion patterns are ported verbatim from
    `scripts/validation/pr_description.py`. Nothing else keeps the two in
    sync, so a fix applied to one copy and not the other silently reopens
    whichever gap the fix closed. `_INLINE_CODE_SPAN` stays one static
    pattern, so a `.pattern`/`.flags` comparison still fits it. The fenced
    block is no longer one static pattern (round 3: CommonMark's "at least
    as long" closer rule needs a per-opener dynamic closer, not a fixed `\1`
    backreference), so its drift guard compares `_fenced_code_block_ranges`
    output on shared tricky inputs instead of comparing source text.
    """

    def test_inline_code_span_pattern_matches_canonical(self):
        assert _check._INLINE_CODE_SPAN.pattern == _prdesc._INLINE_CODE_SPAN.pattern
        assert _check._INLINE_CODE_SPAN.flags == _prdesc._INLINE_CODE_SPAN.flags

    def test_fence_open_line_pattern_matches_canonical(self):
        assert _check._FENCE_OPEN_LINE.pattern == _prdesc._FENCE_OPEN_LINE.pattern
        assert _check._FENCE_OPEN_LINE.flags == _prdesc._FENCE_OPEN_LINE.flags

    def test_fenced_code_block_ranges_behavior_matches_canonical(self):
        bodies = [
            "```\nFixes #1\n```\n",
            "~~~\nFixes #1",
            "  ```\n  Fixes #1\n  ```\n",
            "```\n```not-a-closer\nFixes #1\n```\n",
            "```\nignore this\n````\nFixes #1\n",
            "no fence here at all",
            "```\nfirst\n```\ntext\n~~~\nsecond\n~~~\n",
            "```lang`x`\nFixes #1\n",
            "~~~lang`x`\nFixes #1\n~~~\n",
            "See ```example\nFixes #1\nend``` for details.",
        ]
        for body in bodies:
            assert _check._fenced_code_block_ranges(
                body
            ) == _prdesc._fenced_code_block_ranges(body), body

    def test_code_spans_outside_fences_behavior_matches_canonical(self):
        bodies = [
            "`Fixes #1`",
            "``Fixes #1``",
            "See ```example\nFixes #1\nend``` for details.",
            "```\nFixes #1\n```\n",
            "```\nignore this\n````\nFixes #1\n",
        ]
        for body in bodies:
            fenced = _check._fenced_code_block_ranges(body)
            assert _check._code_spans_outside_fences(
                body, fenced
            ) == _prdesc._code_spans_outside_fences(body, fenced), body


class TestFindOpenPrsForIssue:
    def test_match_in_body(self):
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Closes #2477",
                "html_url": "u",
                "head": {"ref": "b"},
                "user": {"login": "alice"},
            },
            {
                "number": 11,
                "title": "other",
                "body": "unrelated",
                "html_url": "u2",
                "head": {"ref": "b2"},
                "user": {"login": "bob"},
            },
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue("o", "r", 2477)
        assert [m["number"] for m in out] == [10]

    def test_a_backtick_split_across_title_and_body_does_not_hide_a_real_claim(self):
        # Copilot review on PR #5371: title and body are two separate
        # Markdown documents, so a code span cannot straddle them. An
        # unmatched backtick in the title paired with one in the body used
        # to form an artificial cross-field span that swallowed a real
        # closing keyword sitting in the body.
        prs = [
            {
                "number": 42,
                "title": "fix: handle the `weird case",
                "body": "Fixes #4965`, see the linked discussion.",
                "html_url": "u",
                "head": {"ref": "b"},
                "user": {"login": "alice"},
            }
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue("o", "r", 4965)
        assert [m["number"] for m in out] == [42]

    def test_code_span_closing_keyword_does_not_suppress_new_pr(self):
        # End-to-end regression for issue #3827: a PR that only quotes a
        # closing keyword inside backticks (e.g. documenting the bug, as
        # this repro does) must not be surfaced as an existing claim on the
        # issue, or a legitimate new PR gets falsely blocked as a duplicate.
        prs = [
            {
                "number": 5296,
                "title": "docs(github): note the code-span closing-keyword defect",
                "body": "The matcher incorrectly treats `Fixes #4965` as a real claim.",
                "html_url": "https://github.com/rjmurillo/ai-agents/pull/5296",
                "head": {"ref": "docs/note-3827-code-span-defect"},
                "user": {"login": "rjmurillo"},
            }
        ]
        with patch.object(
            _check.subprocess,
            "run",
            return_value=_proc(0, json.dumps([prs])),
        ):
            out = _check.find_open_prs_for_issue("rjmurillo", "ai-agents", 4965)

        assert out == []

    def test_diagnostic_reference_does_not_claim_implementation(self):
        prs = [
            {
                "number": 4866,
                "title": "fix(workflows): rerun required checks after reopen",
                "body": "Fixes #4827\n\nRefs #4859 as a diagnostic blocker.",
                "html_url": "https://github.com/rjmurillo/ai-agents/pull/4866",
                "head": {"ref": "fix/issue-4827-reopened-pr-workflows"},
                "user": {"login": "rjmurillo"},
            }
        ]
        with patch.object(
            _check.subprocess,
            "run",
            return_value=_proc(0, json.dumps([prs])),
        ):
            out = _check.find_open_prs_for_issue("rjmurillo", "ai-agents", 4859)

        assert out == []

    def test_no_match(self):
        prs = [
            {
                "number": 11,
                "title": "x",
                "body": "y",
                "html_url": "u",
                "head": {"ref": "b"},
                "user": {"login": "alice"},
            }
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            assert _check.find_open_prs_for_issue("o", "r", 2477) == []

    def test_skips_current_branch_pr(self):
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Fixes #2477",
                "html_url": "u",
                "head": {"ref": "work"},
                "user": {"login": "alice"},
            },
            {
                "number": 11,
                "title": "feat",
                "body": "Fixes #2477",
                "html_url": "u2",
                "head": {"ref": "other"},
                "user": {"login": "bob"},
            },
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue(
                "o",
                "r",
                2477,
                current_branch_name="work",
                current_user_login="alice",
            )
        assert [m["number"] for m in out] == [11]

    def test_surfaces_own_pr_when_branch_context_missing(self):
        # Detached HEAD / empty branch must NOT suppress the owner's PR (#4965).
        # Previously this returned [] and hid every current-user PR.
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Fixes #2477",
                "html_url": "u",
                "head": {"ref": "work"},
                "user": {"login": "alice"},
            }
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue(
                "o",
                "r",
                2477,
                current_user_login="alice",
            )
        assert [m["number"] for m in out] == [10]

    def test_same_branch_from_different_author_still_blocks(self):
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Fixes #2477",
                "html_url": "u",
                "head": {"ref": "work"},
                "user": {"login": "bob"},
            }
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue(
                "o",
                "r",
                2477,
                current_branch_name="work",
                current_user_login="alice",
            )
        assert [m["number"] for m in out] == [10]

    def test_handles_null_title_and_body(self):
        prs = [
            {
                "number": 10,
                "title": None,
                "body": None,
                "html_url": "u",
                "head": {"ref": "b"},
                "user": {"login": "alice"},
            }
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            assert _check.find_open_prs_for_issue("o", "r", 2477) == []

    def test_api_failure_raises(self):
        with patch.object(_check.subprocess, "run", return_value=_proc(1)):
            try:
                _check.find_open_prs_for_issue("o", "r", 1)
                raised = False
            except RuntimeError:
                raised = True
        assert raised

    def test_timeout_raises_runtime_error(self):
        timeout = subprocess.TimeoutExpired(["gh"], 30)
        with patch.object(_check.subprocess, "run", side_effect=timeout):
            try:
                _check.find_open_prs_for_issue("o", "r", 1)
                raised = False
            except RuntimeError:
                raised = True
        assert raised


def _owner_pr(number: int, head: str, login: str, issue: int = 2477):
    return {
        "number": number,
        "title": "feat",
        "body": f"Fixes #{issue}",
        "html_url": f"u{number}",
        "head": {"ref": head},
        "user": {"login": login},
    }


class TestSelfBranchSuppression:
    """Self-branch suppression fires only on an exact non-empty branch match (#4965)."""

    def test_helper_same_branch_returns_true(self):
        assert _check._is_self_branch_pr(
            "alice", "work", current_branch_name="work", current_user_login="alice"
        )

    def test_helper_detached_head_returns_false(self):
        assert not _check._is_self_branch_pr(
            "alice", "work", current_branch_name="", current_user_login="alice"
        )

    def test_helper_different_branch_returns_false(self):
        assert not _check._is_self_branch_pr(
            "alice", "work", current_branch_name="other", current_user_login="alice"
        )

    def test_helper_different_author_returns_false(self):
        assert not _check._is_self_branch_pr(
            "bob", "work", current_branch_name="work", current_user_login="alice"
        )

    def test_helper_different_author_and_branch_returns_false(self):
        # Truth-table cell: neither author nor branch matches. A different
        # author on a different branch is never the current session's own PR,
        # so suppression must not fire and the PR must surface.
        assert not _check._is_self_branch_pr(
            "bob", "other", current_branch_name="work", current_user_login="alice"
        )

    def test_detached_head_surfaces_owner_pr(self):
        prs = [[_owner_pr(10, "work", "alice")]]
        out = _check.filter_prs_for_issue(
            prs, 2477, current_branch_name="", current_user_login="alice"
        )
        assert [m["number"] for m in out] == [10]

    def test_empty_environment_surfaces_owner_pr(self, monkeypatch):
        # Regression for the duplicate-test finding: the empty branch must come
        # from the REAL resolution path, not a hardcoded "". CI without
        # GITHUB_HEAD_REF plus a git call that reports no branch (detached HEAD)
        # resolves current_branch() to "", which must not suppress the owner PR.
        monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
        with patch.object(_check.subprocess, "run", return_value=_proc(0, "\n")):
            resolved_branch = _check.current_branch()
        assert resolved_branch == ""
        prs = [[_owner_pr(10, "feature", "alice")]]
        out = _check.filter_prs_for_issue(
            prs, 2477, current_branch_name=resolved_branch, current_user_login="alice"
        )
        assert [m["number"] for m in out] == [10]

    def test_same_branch_still_suppressed(self):
        prs = [[_owner_pr(10, "work", "alice")]]
        out = _check.filter_prs_for_issue(
            prs, 2477, current_branch_name="work", current_user_login="alice"
        )
        assert out == []

    def test_different_branch_surfaced(self):
        prs = [[_owner_pr(10, "work", "alice")]]
        out = _check.filter_prs_for_issue(
            prs, 2477, current_branch_name="feature-x", current_user_login="alice"
        )
        assert [m["number"] for m in out] == [10]

    def test_different_author_surfaced_from_detached_head(self):
        prs = [[_owner_pr(10, "work", "bob")]]
        out = _check.filter_prs_for_issue(
            prs, 2477, current_branch_name="", current_user_login="alice"
        )
        assert [m["number"] for m in out] == [10]

    def test_multiple_candidate_prs_all_surfaced(self):
        prs = [[
            _owner_pr(10, "work", "alice"),
            _owner_pr(11, "other", "bob"),
        ]]
        out = _check.filter_prs_for_issue(
            prs, 2477, current_branch_name="", current_user_login="alice"
        )
        assert sorted(m["number"] for m in out) == [10, 11]

    def test_no_candidates_returns_empty(self):
        prs = [[{
            "number": 12,
            "title": "chore",
            "body": "unrelated work",
            "html_url": "u12",
            "head": {"ref": "b"},
            "user": {"login": "alice"},
        }]]
        out = _check.filter_prs_for_issue(
            prs, 2477, current_branch_name="", current_user_login="alice"
        )
        assert out == []


class TestCheckExistingMain:
    """End-to-end main() behavior for the detached-HEAD fix (#4965)."""

    def test_detached_head_reports_existing_owner_pr(self):
        prs = [_owner_pr(10, "work", "alice", issue=5)]
        run = _gh_dispatch(
            user=_proc(0, "alice\n"),
            pulls=_proc(0, json.dumps([prs])),
        )
        with (
            patch.object(_check, "assert_gh_authenticated", return_value=None),
            patch.object(_check, "resolve_repo_params") as resolve,
            patch.object(_check, "current_branch", return_value=""),  # detached HEAD
            patch.object(_check.subprocess, "run", side_effect=run),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _check.main(["--issue", "5", "--output-format", "json"])
                code = 0
            except SystemExit as exc:
                code = exc.code
        assert code == 1

    def test_api_error_is_not_reported_as_no_pr(self):
        # A failed gh pulls call must surface an external error, never a clean
        # "no PR". Dispatch by command so the pulls failure, not a misordered
        # login call, is what maps to exit 3.
        run = _gh_dispatch(
            user=_proc(0, "alice\n"),
            pulls=_proc(1, stderr="gh api pulls failed"),
        )
        with (
            patch.object(_check, "assert_gh_authenticated", return_value=None),
            patch.object(_check, "resolve_repo_params") as resolve,
            patch.object(_check, "current_branch", return_value=""),
            patch.object(_check.subprocess, "run", side_effect=run),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _check.main(["--issue", "5", "--output-format", "json"])
                code = 0
            except SystemExit as exc:
                code = exc.code
        assert code == 3


class TestClaimIssueAssignees:
    def test_parses_assignees(self):
        payload = json.dumps({"assignees": [{"login": "alice"}, {"login": "bob"}]})
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, payload)):
            assert _claim.issue_assignees("o", "r", 5) == ["alice", "bob"]

    def test_empty_assignees(self):
        payload = json.dumps({"assignees": []})
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, payload)):
            assert _claim.issue_assignees("o", "r", 5) == []

    def test_null_assignees_treated_as_empty(self):
        payload = json.dumps({"assignees": None})
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, payload)):
            assert _claim.issue_assignees("o", "r", 5) == []

    def test_view_failure_raises(self):
        with patch.object(_claim.subprocess, "run", return_value=_proc(1)):
            try:
                _claim.issue_assignees("o", "r", 5)
                raised = False
            except RuntimeError:
                raised = True
        assert raised


class TestCurrentLogin:
    def test_returns_login(self):
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, "alice\n")):
            assert _claim.current_login() == "alice"

    def test_empty_login_raises(self):
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, "\n")):
            try:
                _claim.current_login()
                raised = False
            except RuntimeError:
                raised = True
        assert raised


class TestClaimMain:
    def test_no_match_reports_no_implementation_claim(self, capsys):
        calls = [
            _proc(0, "alice\n"),
            _proc(0, json.dumps([[]])),
        ]
        with (
            patch.object(_check, "assert_gh_authenticated", return_value=None),
            patch.object(_check, "resolve_repo_params") as resolve,
            patch.object(_check, "current_branch", return_value="work"),
            patch.object(_check.subprocess, "run", side_effect=calls),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"

            assert _check.main(["--issue", "5", "--output-format", "human"]) == 0

        output = capsys.readouterr().out
        assert "No open PR claims implementation ownership of issue #5" in output

    def test_duplicate_pr_exits_without_invalid_error_type(self):
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Fixes #5",
                "html_url": "u",
                "head": {"ref": "other"},
                "user": {"login": "bob"},
            }
        ]
        calls = [
            _proc(0, "alice\n"),
            _proc(0, json.dumps([prs])),
        ]
        with (
            patch.object(_check, "assert_gh_authenticated", return_value=None),
            patch.object(_check, "resolve_repo_params") as resolve,
            patch.object(_check, "current_branch", return_value="work"),
            patch.object(_check.subprocess, "run", side_effect=calls),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _check.main(["--issue", "5", "--output-format", "json"])
                raised = False
            except SystemExit as exc:
                raised = exc.code == 1
        assert raised

    def test_detects_competing_assignment_after_claim(self):
        calls = [
            _proc(0, "alice\n"),
            _proc(0, json.dumps({"assignees": []})),
            _proc(0, ""),
            _proc(0, json.dumps({"assignees": [{"login": "alice"}, {"login": "bob"}]})),
            _proc(0, ""),
        ]
        with (
            patch.object(_claim, "assert_gh_authenticated", return_value=None),
            patch.object(_claim, "resolve_repo_params") as resolve,
            patch.object(_claim.subprocess, "run", side_effect=calls),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _claim.main(["--issue", "5", "--output-format", "json"])
                raised = False
            except SystemExit as exc:
                raised = exc.code == 1
        assert raised

    def test_cleanup_failure_after_competing_assignment_exits_external_error(self):
        calls = [
            _proc(0, "alice\n"),
            _proc(0, json.dumps({"assignees": []})),
            _proc(0, ""),
            _proc(0, json.dumps({"assignees": [{"login": "alice"}, {"login": "bob"}]})),
            _proc(1, stderr="remove failed"),
        ]
        with (
            patch.object(_claim, "assert_gh_authenticated", return_value=None),
            patch.object(_claim, "resolve_repo_params") as resolve,
            patch.object(_claim.subprocess, "run", side_effect=calls),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _claim.main(["--issue", "5", "--output-format", "json"])
                raised = False
            except SystemExit as exc:
                raised = exc.code == 3
        assert raised

    def test_missing_self_after_claim_exits_external_error(self):
        calls = [
            _proc(0, "alice\n"),
            _proc(0, json.dumps({"assignees": []})),
            _proc(0, ""),
            _proc(0, json.dumps({"assignees": []})),
        ]
        with (
            patch.object(_claim, "assert_gh_authenticated", return_value=None),
            patch.object(_claim, "resolve_repo_params") as resolve,
            patch.object(_claim.subprocess, "run", side_effect=calls),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _claim.main(["--issue", "5", "--output-format", "json"])
                raised = False
            except SystemExit as exc:
                raised = exc.code == 3
        assert raised

    def test_failure_raises(self):
        with patch.object(_claim.subprocess, "run", return_value=_proc(1, stderr="no auth")):
            try:
                _claim.current_login()
                raised = False
            except RuntimeError:
                raised = True
        assert raised
