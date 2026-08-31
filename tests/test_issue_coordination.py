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

    def test_span_crossing_a_real_fence_does_not_hide_a_claim_after_it(self):
        # A 4-backtick run in the paragraph before a real 3-backtick fence
        # can pair with a later 4-backtick run after the fence closes,
        # producing a candidate span that starts before the fence and ends
        # after it, engulfing both the fence and a real claim right after
        # it. Rejecting a span only when its start falls inside the fence
        # (round 4) missed this shape and could let a duplicate PR through
        # undetected (Copilot, PR #5371 round 5).
        body = "See ````\n```\nhidden\n```\nFixes #4965 end````\n"
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
            "See ````\n```\nhidden\n```\nFixes #1 end````\n",
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
            "See ````\n```\nhidden\n```\nFixes #1 end````\n",
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


def _lsr(*branches: tuple[str, str]) -> subprocess.CompletedProcess[str]:
    """Build a `git ls-remote --heads origin` result from (sha, branch) pairs."""
    lines = "".join(f"{sha}\trefs/heads/{name}\n" for sha, name in branches)
    return _proc(0, lines)


def _probe_run(
    *,
    ls_remote,
    rev_list=None,
    fetch=None,
    origin_url="https://github.com/o/r.git",
    origin_main_rc=0,
    calls=None,
):
    """A `subprocess.run` fake covering every git call the probe makes.

    Dispatches on the command (never on call order) and records each argv into
    ``calls`` when provided, so a test can assert `ls-remote` runs exactly once
    and `rev-list` carries ``^origin/main`` (issue #5428 requirement 1).
    ``rev_list`` may be a CompletedProcess or a callable(sha) -> CompletedProcess.
    """
    fetch_result = _proc(0) if fetch is None else fetch

    def run(cmd, *a, **k):
        argv = list(cmd)
        if calls is not None:
            calls.append(argv)
        if argv[:3] == ["git", "remote", "get-url"]:
            if origin_url is None:
                return _proc(1, stderr="no origin")
            return _proc(0, origin_url + "\n")
        if argv[:2] == ["git", "rev-parse"]:
            return _proc(origin_main_rc, "" if origin_main_rc else "abc\n")
        if argv[:2] == ["git", "ls-remote"]:
            return ls_remote
        if argv[:2] == ["git", "fetch"]:
            return fetch_result
        if argv[:3] == ["git", "rev-list", "--count"]:
            if callable(rev_list):
                return rev_list(argv[3])
            return rev_list
        raise AssertionError(f"unexpected call: {argv}")

    return run


class TestProbeCompetingBranches:
    """Remote-branch probe for a pushed-work collision (issue #5428)."""

    def test_no_matching_branch_no_warning(self):
        # (a) branches exist but none reference the issue -> no warning.
        run = _probe_run(ls_remote=_lsr(("aaa", "codex/9999-other"), ("bbb", "main")))
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert in_flight == []
        assert warnings == []

    def test_numeric_near_miss_not_matched(self):
        # (d) 54200 must not match a claim of 5420 (boundary).
        run = _probe_run(ls_remote=_lsr(("aaa", "codex/54200-x"), ("bbb", "codex/15420-y")))
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert in_flight == []
        assert warnings == []

    def test_ancestor_branch_excluded(self):
        # (b) matching branch that is an ancestor of main (0 ahead) -> no warning.
        run = _probe_run(
            ls_remote=_lsr(("sha1", "codex/5420-a-paths")), rev_list=_proc(0, "0\n")
        )
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert in_flight == []
        assert warnings == []

    def test_ahead_branch_warns_with_ref_and_count(self):
        # (c) matching branch ahead of main (count > 0) -> in-flight with ref+count.
        calls: list[list[str]] = []
        run = _probe_run(
            ls_remote=_lsr(("sha1", "codex/5420-a-paths")),
            rev_list=_proc(0, "3\n"),
            calls=calls,
        )
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert warnings == []
        assert in_flight == [
            {"ref": "refs/heads/codex/5420-a-paths", "sha": "sha1", "commits_ahead": 3}
        ]
        # Issue requirement 1: ls-remote runs EXACTLY once.
        ls_remote_calls = [c for c in calls if c[:2] == ["git", "ls-remote"]]
        assert len(ls_remote_calls) == 1
        # rev-list must carry the ^origin/main exclusion and the advertised sha.
        rev_list_calls = [c for c in calls if c[:3] == ["git", "rev-list", "--count"]]
        assert rev_list_calls == [["git", "rev-list", "--count", "sha1", "^origin/main"]]

    def test_missing_object_fetches_then_counts(self):
        # (Finding 1) ls-remote advertises a sha absent locally: first rev-list
        # fails "bad object", we fetch the ref, retry once, and count succeeds.
        attempts = {"n": 0}

        def rev_list(sha):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return _proc(128, stderr=f"fatal: bad object {sha}")
            return _proc(0, "2\n")

        calls: list[list[str]] = []
        run = _probe_run(
            ls_remote=_lsr(("18488aff", "codex/5420-a-paths")),
            rev_list=rev_list,
            calls=calls,
        )
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert warnings == []
        assert in_flight == [
            {"ref": "refs/heads/codex/5420-a-paths", "sha": "18488aff", "commits_ahead": 2}
        ]
        # The on-demand fetch targeted exactly the unresolved ref.
        fetch_calls = [c for c in calls if c[:2] == ["git", "fetch"]]
        assert fetch_calls == [
            ["git", "fetch", "--quiet", "origin", "refs/heads/codex/5420-a-paths"]
        ]

    def test_unresolved_object_surfaces_branch_with_unknown_marker(self):
        # (Finding 1) fetch does not resolve the object: never silently drop the
        # branch. Surface it with commits_ahead=None + a reason AND a warning.
        run = _probe_run(
            ls_remote=_lsr(("18488aff", "codex/5420-a-paths")),
            rev_list=_proc(128, stderr="fatal: bad object 18488aff"),
            fetch=_proc(1, stderr="couldn't find remote ref"),
        )
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert len(in_flight) == 1
        assert in_flight[0]["ref"] == "refs/heads/codex/5420-a-paths"
        assert in_flight[0]["commits_ahead"] is None
        assert "undetermined" in in_flight[0]["reason"]
        assert len(warnings) == 1
        assert "could not count commits on refs/heads/codex/5420-a-paths" in warnings[0]

    def test_ls_remote_failure_degrades_to_warning(self):
        # (e) ls-remote fails -> named warning, no in-flight branches, no raise.
        run = _probe_run(ls_remote=_proc(1, stderr="no remote"))
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert in_flight == []
        assert len(warnings) == 1
        assert "could not probe remote branches for issue #5420" in warnings[0]

    def test_origin_mismatch_skips_probe(self):
        # (Finding 4) checkout origin is a different repo than requested -> skip
        # the probe entirely and degrade to a named warning (never use the data).
        run = _probe_run(
            ls_remote=_lsr(("sha1", "codex/5420-a-paths")),
            rev_list=_proc(0, "3\n"),
            origin_url="https://github.com/other/elsewhere.git",
        )
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert in_flight == []
        assert len(warnings) == 1
        assert "checkout origin is other/elsewhere" in warnings[0]

    def test_no_origin_remote_skips_probe(self):
        # (Finding 4) not inside a git repo / no origin -> same named degradation.
        run = _probe_run(ls_remote=_lsr(("sha1", "codex/5420-a-paths")), origin_url=None)
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert in_flight == []
        assert len(warnings) == 1
        assert "no 'origin' remote" in warnings[0]

    def test_missing_origin_main_skips_probe(self):
        # (Finding 4) origin/main absent (non-main default) -> named degradation.
        run = _probe_run(
            ls_remote=_lsr(("sha1", "codex/5420-a-paths")),
            rev_list=_proc(0, "3\n"),
            origin_main_rc=1,
        )
        with patch.object(_claim.subprocess, "run", side_effect=run):
            in_flight, warnings = _claim.probe_competing_branches(5420, "o", "r")
        assert in_flight == []
        assert len(warnings) == 1
        assert "origin/main not found" in warnings[0]

    def test_branch_matches_issue_boundaries(self):
        assert _claim._branch_matches_issue("refs/heads/codex/5420-a", 5420) is True
        assert _claim._branch_matches_issue("refs/heads/codex/fix-5420-a", 5420) is True
        assert _claim._branch_matches_issue("refs/heads/5420", 5420) is True
        assert _claim._branch_matches_issue(
            "refs/heads/feature/pr-1234-fixes-5420", 5420
        ) is True
        assert _claim._branch_matches_issue("refs/heads/codex/54200-a", 5420) is False
        assert _claim._branch_matches_issue("refs/heads/codex/15420-a", 5420) is False
        # (Finding 3) letter-adjacent digits must NOT match.
        assert _claim._branch_matches_issue("refs/heads/fix/deadbeef5420cafe", 5420) is False
        assert _claim._branch_matches_issue("refs/heads/fix/issue5420work", 5420) is False


class TestClaimMainBranchProbe:
    """main() surfaces the branch probe on both exit-0 success paths."""

    @staticmethod
    def _claim_runner(*, login="alice", ls_remote, rev_list=None, self_held=False):
        """Fake for a full main() run. ``self_held=True`` makes the first issue
        view already report the current user, exercising the resume path."""
        view = {"n": 0}

        def run(cmd, *a, **k):
            argv = list(cmd)
            if argv[:3] == ["gh", "api", "user"]:
                return _proc(0, login + "\n")
            if argv[:2] == ["gh", "issue"] and "view" in argv:
                view["n"] += 1
                held = self_held or view["n"] > 1
                payload = {"assignees": [{"login": login}]} if held else {"assignees": []}
                return _proc(0, json.dumps(payload))
            if argv[:2] == ["gh", "issue"] and "edit" in argv:
                return _proc(0, "")
            if argv[:3] == ["git", "remote", "get-url"]:
                return _proc(0, "https://github.com/o/r.git\n")
            if argv[:2] == ["git", "rev-parse"]:
                return _proc(0, "abc\n")
            if argv[:2] == ["git", "ls-remote"]:
                return ls_remote
            if argv[:2] == ["git", "fetch"]:
                return _proc(0)
            if argv[:3] == ["git", "rev-list", "--count"]:
                return rev_list
            raise AssertionError(f"unexpected call: {argv}")

        return run

    def _run_main(self, runner, capsys, fmt="json"):
        with (
            patch.object(_claim, "assert_gh_authenticated", return_value=None),
            patch.object(_claim, "resolve_repo_params") as resolve,
            patch.object(_claim.subprocess, "run", side_effect=runner),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            code = _claim.main(["--issue", "5420", "--output-format", fmt])
        return code, capsys.readouterr().out

    def _run_main_json(self, runner, capsys):
        code, out = self._run_main(runner, capsys)
        return code, json.loads(out.strip())

    def test_clean_claim_no_in_flight_branches(self, capsys):
        runner = self._claim_runner(ls_remote=_lsr(("aaa", "codex/9999-x")))
        code, envelope = self._run_main_json(runner, capsys)
        assert code == 0
        assert envelope["Success"] is True
        assert envelope["Data"]["in_flight_branches"] == []

    def test_claim_with_in_flight_branch_warns_but_succeeds(self, capsys):
        runner = self._claim_runner(
            ls_remote=_lsr(("sha1", "codex/5420-a-paths")),
            rev_list=_proc(0, "3\n"),
        )
        code, envelope = self._run_main_json(runner, capsys)
        # Warning path must still succeed (exit 0) so it cannot deadlock a resume.
        assert code == 0
        assert envelope["Success"] is True
        assert envelope["Data"]["in_flight_branches"] == [
            {"ref": "refs/heads/codex/5420-a-paths", "sha": "sha1", "commits_ahead": 3}
        ]

    def test_self_held_path_surfaces_in_flight_branch(self, capsys):
        # (Finding 2) resuming an issue we already hold must ALSO probe: a
        # competing branch is ahead of main -> in_flight populated, still exit 0.
        runner = self._claim_runner(
            ls_remote=_lsr(("sha1", "codex/5420-a-paths")),
            rev_list=_proc(0, "4\n"),
            self_held=True,
        )
        code, envelope = self._run_main_json(runner, capsys)
        assert code == 0
        assert envelope["Success"] is True
        assert envelope["Data"]["in_flight_branches"] == [
            {"ref": "refs/heads/codex/5420-a-paths", "sha": "sha1", "commits_ahead": 4}
        ]

    def test_self_held_warning_status_surfaces_in_human_output(self, capsys):
        # (Finding 5) write_skill_output drops status from JSON, so assert the
        # WARNING status on the human channel where it is actually rendered.
        runner = self._claim_runner(
            ls_remote=_lsr(("sha1", "codex/5420-a-paths")),
            rev_list=_proc(0, "4\n"),
            self_held=True,
        )
        code, out = self._run_main(runner, capsys, fmt="human")
        assert code == 0
        assert "[WARNING]" in out

    def test_clean_claim_reports_pass_status_in_human_output(self, capsys):
        # (Finding 5) the negative case: no competing work -> PASS, not WARNING.
        runner = self._claim_runner(ls_remote=_lsr(("aaa", "codex/9999-x")))
        code, out = self._run_main(runner, capsys, fmt="human")
        assert code == 0
        assert "[PASS]" in out
        assert "[WARNING]" not in out

    def test_claim_survives_ls_remote_failure(self, capsys):
        runner = self._claim_runner(ls_remote=_proc(1, stderr="offline"))
        code, envelope = self._run_main_json(runner, capsys)
        assert code == 0
        assert envelope["Success"] is True
        assert envelope["Data"]["in_flight_branches"] == []
        assert len(envelope["Data"]["warnings"]) == 1
