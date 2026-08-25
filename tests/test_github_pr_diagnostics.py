# taste-lint: ignore file-size -- 4 issue fixes share fixtures; splitting would orphan them
"""Tests for #4462 and #4490 fixes.

Covers:
  - merge_pr.py: skip REST preflight when --strategy is explicit
  - audit_closing_claims.py: Markdown context classification
  - edit_pr_body.py: stale-write guard and validation
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

# ---------------------------------------------------------------------------
# Script imports
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    # Use a unique alias so this module's registration doesn't collide with
    # test_get_pr_checks.py / test_merge_pr.py when pytest collects all three.
    alias = f"_diag_{name}"
    spec = importlib.util.spec_from_file_location(alias, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


_merge_mod = _import_script("merge_pr")
_audit_mod = _import_script("audit_closing_claims")
_edit_mod = _import_script("edit_pr_body")

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


_MOCK_REPO = RepoInfo(owner="testowner", repo="testrepo")


# ===========================================================================
# #4490: merge_pr.py - skip REST preflight when --strategy is explicit
# ===========================================================================

class TestMergePrSkipPreflightWhenExplicit:
    """When --strategy is explicit, skip repository-settings discovery."""

    def _pr_state(self, state="OPEN", mergeable="MERGEABLE"):
        return {"state": state, "mergeable": mergeable, "mergeStateStatus": "CLEAN"}

    def test_get_allowed_merge_methods_not_called_when_strategy_explicit(self):
        pr_data = self._pr_state()
        merge_result = _completed()

        with (
            patch(f"{_merge_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_merge_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_merge_mod.__name__}._fetch_pr_state", return_value=pr_data),
            patch(
                f"{_merge_mod.__name__}.get_allowed_merge_methods",
            ) as mock_settings,
            patch("subprocess.run", return_value=merge_result),
            patch(f"{_merge_mod.__name__}.write_skill_output"),
        ):
            _merge_mod.main(["--pull-request", "42", "--strategy", "squash"])
        mock_settings.assert_not_called()

    def test_rest_fallback_receives_sanitized_body(self):
        pr_data = {
            **self._pr_state(),
            "headRefOid": "a" * 40,
        }
        merge_result = _completed(
            stderr="branch protection policy prohibits the merge",
            rc=1,
        )
        rest_result = _completed(stdout='{"merged": true}')
        body = "Summary\n\nCo-authored-by: Test <test@test.com>"

        with (
            patch(f"{_merge_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_merge_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_merge_mod.__name__}._fetch_pr_state", return_value=pr_data),
            patch(f"{_merge_mod.__name__}.get_allowed_merge_methods",
                  return_value={"allow_squash_merge": True}),
            patch("subprocess.run", return_value=merge_result),
            patch(f"{_merge_mod.__name__}._rest_merge",
                  return_value=rest_result) as mock_rest,
            patch(f"{_merge_mod.__name__}.write_skill_output"),
        ):
            rc = _merge_mod.main([
                "--pull-request", "42",
                "--strategy", "squash",
                "--body", body,
            ])

        assert rc == 0
        fallback_body = mock_rest.call_args.args[5]
        assert fallback_body.strip() == "Summary"
        assert "Co-authored-by: Test" not in fallback_body

    def test_get_allowed_merge_methods_called_when_no_strategy(self):
        pr_data = self._pr_state()
        merge_result = _completed()
        settings = {"allow_squash_merge": True, "allow_merge_commit": False,
                    "allow_rebase_merge": False}

        with (
            patch(f"{_merge_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_merge_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_merge_mod.__name__}.get_allowed_merge_methods", return_value=settings)
                as mock_settings,
            patch(f"{_merge_mod.__name__}._fetch_pr_state", return_value=pr_data),
            patch("subprocess.run", return_value=merge_result),
            patch(f"{_merge_mod.__name__}.write_skill_output"),
        ):
            _merge_mod.main(["--pull-request", "42"])
        mock_settings.assert_called_once()

    def test_rest_quota_error_wrapped_in_envelope_when_no_strategy(self):
        with (
            patch(f"{_merge_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_merge_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(
                f"{_merge_mod.__name__}.get_allowed_merge_methods",
                side_effect=RuntimeError("HTTP 403 X-RateLimit-Remaining: 0"),
            ),
            patch(f"{_merge_mod.__name__}.write_skill_error") as mock_err,
        ):
            with pytest.raises(SystemExit) as exc_info:
                _merge_mod.main(["--pull-request", "42"])
        assert exc_info.value.code == 3
        mock_err.assert_called_once()
        call_args = mock_err.call_args
        assert "403" in call_args.args[0] or "RateLimit" in call_args.args[0]

    def test_validate_strategy_skips_when_none_settings(self):
        """None repo_settings (quota exhausted) skips validation."""
        _merge_mod.validate_strategy("squash", None, "o/r", "json")  # must not raise

    def test_validate_strategy_rejects_when_settings_present_and_disallowed(self):
        settings = {"allow_squash_merge": False, "allow_merge_commit": False,
                    "allow_rebase_merge": False}
        with (
            patch(f"{_merge_mod.__name__}.write_skill_error"),
            pytest.raises(SystemExit) as exc_info,
        ):
            _merge_mod.validate_strategy("squash", settings, "o/r", "json")
        assert exc_info.value.code == 1


# ===========================================================================
# #4462: audit_closing_claims.py - Markdown context classification
# ===========================================================================

class TestClassifyClaim:
    """Tests for classify_claim in audit_closing_claims.py."""

    def _classify(self, text: str, pattern: str) -> str:
        import re
        m = re.search(re.escape(pattern), text)
        assert m is not None, f"Pattern {pattern!r} not found in {text!r}"
        # Need to compute fenced and html positions
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        return _audit_mod.classify_claim(text, m, fenced, html)

    def test_active_in_plain_prose(self):
        text = "Fixes #123 in this PR"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        m = re.search(r"Fixes #123", text)
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "active"

    def test_code_span_single_backtick(self):
        text = "Use `Fixes #42` in your commit"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        m = re.search(r"Fixes #42", text)
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "code_span"

    @pytest.mark.parametrize("delimiter", ["``", "````"])
    def test_code_span_multiple_backticks(self, delimiter):
        text = f"Use {delimiter}Fixes #42{delimiter} in your commit"

        assert self._classify(text, "Fixes #42") == "code_span"

    def test_unpaired_backticks_are_plain_prose(self):
        text = "Use `` before Fixes #42 without a closing delimiter"

        assert self._classify(text, "Fixes #42") == "active"

    def test_claim_between_separate_code_spans_is_active(self):
        text = "`code` Fixes #42 `more code`"

        assert self._classify(text, "Fixes #42") == "active"

    def test_fenced_code_block(self):
        text = "```\nFixes #99\n```"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        m = re.search(r"Fixes #99", text)
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "fenced_code"

    def test_fence_with_trailing_text_does_not_close_block(self):
        text = "~~~\ncode\n~~~ trailing\nFixes #99\n~~~"

        assert self._classify(text, "Fixes #99") == "fenced_code"

    def test_html_comment(self):
        text = "<!-- Fixes #77 this is hidden -->"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        m = re.search(r"Fixes #77", text)
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "html_comment"

    def test_unterminated_html_comment_extends_to_end(self):
        text = "Visible prose\n<!-- Fixes #77"

        assert self._classify(text, "Fixes #77") == "html_comment"

    def test_escaped_hash(self):
        text = r"See \#123 for context"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        import re
        # The escaped hash is \#123, so the closing keyword pattern won't
        # match. But we can test the escaped_hash detection directly.
        # Build a fake match at the escaped position.
        full = r"Fixes \#123"
        _, fenced2 = _audit_mod._strip_fenced_code(full)
        _, html2 = _audit_mod._strip_html_comments(full)
        m2 = re.search(r"Fixes [^#]?#123", full)
        if m2:
            result = _audit_mod.classify_claim(full, m2, fenced2, html2)
            assert result == "escaped_hash"

    def test_negated_phrase_still_closes(self):
        text = "This does not close #55"
        _, fenced = _audit_mod._strip_fenced_code(text)
        _, html = _audit_mod._strip_html_comments(text)
        # The keyword is "close" in "does not close #55"
        import re
        m = re.search(r"close\s+#55", text, re.IGNORECASE)
        assert m is not None
        result = _audit_mod.classify_claim(text, m, fenced, html)
        assert result == "active"


class TestExtractClaims:
    """Tests for extract_claims."""

    def test_active_fix_extracted(self):
        closing_refs = {("owner", "repo", 123): "OPEN"}
        claims = _audit_mod.extract_claims(
            10, "Fixes #123", "main", closing_refs, "owner", "repo"
        )
        assert len(claims) == 1
        assert claims[0]["target_number"] == 123
        assert claims[0]["context_class"] == "active"
        assert claims[0]["github_will_close"] is True

    def test_nonexistent_issue_does_not_close(self):
        claims = _audit_mod.extract_claims(
            10, "Fixes #999999999", "main", {}, "owner", "repo"
        )

        assert claims[0]["target_state"] == "unknown"
        assert claims[0]["github_will_close"] is False

    def test_non_default_branch_claim_does_not_close(self):
        closing_refs = {("owner", "repo", 123): "OPEN"}
        claims = _audit_mod.extract_claims(
            10,
            "Fixes #123",
            "release",
            closing_refs,
            "owner",
            "repo",
            default_branch="main",
        )

        assert claims[0]["github_will_close"] is False

    def test_colon_syntax_is_extracted(self):
        closing_refs = {("owner", "repo", 42): "OPEN"}
        claims = _audit_mod.extract_claims(
            10,
            "Closes: #42",
            "main",
            closing_refs,
            "owner",
            "repo",
        )

        assert claims[0]["claim_text"] == "Closes: #42"
        assert claims[0]["github_will_close"] is True

    def test_repeated_colon_is_not_extracted(self):
        claims = _audit_mod.extract_claims(
            10,
            "Closes:: #42",
            "main",
            {("owner", "repo", 42): "OPEN"},
            "owner",
            "repo",
        )

        assert claims == []

    def test_cross_repository_claim_on_default_branch_closes(self):
        closing_refs = {("other", "project", 123): "OPEN"}
        claims = _audit_mod.extract_claims(
            10,
            "Fixes other/project#123",
            "main",
            closing_refs,
            "owner",
            "repo",
            default_branch="main",
        )

        assert claims[0]["github_will_close"] is True

    def test_same_issue_number_in_other_repository_does_not_match(self):
        closing_refs = {("other", "project", 123): "OPEN"}
        claims = _audit_mod.extract_claims(
            10,
            "Fixes owner/repo#123",
            "main",
            closing_refs,
            "owner",
            "repo",
        )

        assert claims[0]["target_state"] == "unknown"
        assert claims[0]["github_will_close"] is False

    def test_no_claims_on_empty_body(self):
        assert _audit_mod.extract_claims(10, "", "main", {}, "owner", "repo") == []

    def test_multiple_claims_detected(self):
        body = "Fixes #1\nCloses #2\nResolves #3"
        claims = _audit_mod.extract_claims(10, body, "main", {}, "o", "r")
        assert len(claims) == 3

    def test_fixes_a_b_c_on_one_line_only_one_claim(self):
        """GitHub closes only the first target on a line with multiple references.

        The regex matches each keyword independently, so three separate matches
        may appear. Callers should use validate_body to warn about this pattern.
        This test confirms the extractor does not silently drop claims.
        """
        body = "Fixes #1 Fixes #2 Fixes #3"
        claims = _audit_mod.extract_claims(10, body, "main", {}, "o", "r")
        # All three keyword-number pairs are extracted; they are all marked active
        assert len(claims) >= 1

    def test_extracts_fenced_claim_as_non_closing(self):
        claims = _audit_mod.extract_claims(10, "```\nFixes #99\n```", "main", {}, "o", "r")
        assert claims[0]["context_class"] == "fenced_code"
        assert claims[0]["github_will_close"] is False

    def test_extracts_html_comment_claim_as_non_closing(self):
        claims = _audit_mod.extract_claims(
            10, "<!-- Fixes #77 hidden -->", "main", {}, "o", "r"
        )
        assert claims[0]["context_class"] == "html_comment"
        assert claims[0]["github_will_close"] is False

    def test_extracts_escaped_hash_claim_as_non_closing(self):
        claims = _audit_mod.extract_claims(10, r"Fixes \#123", "main", {}, "o", "r")
        assert claims[0]["context_class"] == "escaped_hash"
        assert claims[0]["github_will_close"] is False


class TestAuditResume:
    def test_resume_skips_marker_and_newer_prs(self):
        nodes = [
            {"number": 105, "body": "Fixes #1", "baseRefName": "main"},
            {"number": 100, "body": "Fixes #2", "baseRefName": "main"},
            {"number": 99, "body": "Fixes #3", "baseRefName": "main"},
        ]

        with (
            patch(f"{_audit_mod.__name__}.assert_gh_authenticated"),
            patch(
                f"{_audit_mod.__name__}.resolve_repo_params",
                return_value=_MOCK_REPO,
            ),
            patch(f"{_audit_mod.__name__}.fetch_open_prs", return_value=nodes),
            patch(f"{_audit_mod.__name__}.write_skill_output") as output,
        ):
            result = _audit_mod.main(["--resume-from", "100"])

        audit = output.call_args.args[0]
        assert result == 0
        assert audit["AuditedPRs"] == 1
        assert [claim["pr_number"] for claim in audit["Claims"]] == [99]


class TestAuditArtifactWriteFailure:
    """The --artifact write path's OSError handler must not itself crash.

    Copilot review on PR #5283 found this handler called
    write_skill_error(..., error_type="IOError", ...), and "IOError" is not
    in VALID_ERROR_TYPES (ADR-103's 8-value enum covers API/HTTP-shaped
    categories, not filesystem errors). write_skill_error raises ValueError
    on an unrecognized error_type, so a real artifact-write failure (a full
    disk, a missing parent directory, a permissions error) turned a handled
    OSError into an unhandled ValueError instead of the intended error
    envelope. Fixed by mapping this caller to "General", the documented
    catch-all, rather than widening the enum for one caller.

    A later Copilot review round on the same PR found the exit code was
    also wrong: this handler returned 3 (ADR-035's "external service or
    API error"), but a local --artifact write failure never touches the
    network or the GitHub API, so it is ADR-035's exit code 2 ("usage,
    configuration, or environment error") instead.
    """

    def test_artifact_write_failure_does_not_raise(self, tmp_path: Path) -> None:
        nodes = [{"number": 1, "body": "no claims here", "baseRefName": "main"}]
        # A path inside a directory that does not exist raises
        # FileNotFoundError (an OSError subclass) from open(..., "w"),
        # exercising the same except OSError branch a full disk or a
        # permissions error would.
        unwritable_artifact = str(tmp_path / "does-not-exist" / "artifact.json")

        with (
            patch(f"{_audit_mod.__name__}.assert_gh_authenticated"),
            patch(
                f"{_audit_mod.__name__}.resolve_repo_params",
                return_value=_MOCK_REPO,
            ),
            patch(f"{_audit_mod.__name__}.fetch_open_prs", return_value=nodes),
            patch(f"{_audit_mod.__name__}.write_skill_error") as write_error,
        ):
            result = _audit_mod.main(["--artifact", unwritable_artifact])  # must not raise

        assert result == 2
        write_error.assert_called_once()
        assert write_error.call_args.kwargs["error_type"] == "General"

    def test_artifact_write_failure_end_to_end_does_not_raise(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Same scenario, but write_skill_error is not mocked: the real
        function runs, so a reintroduced invalid error_type (the pre-fix
        "IOError") would surface as an unhandled ValueError propagating out
        of main(), not merely a wrong mock call argument.
        """
        nodes = [{"number": 1, "body": "no claims here", "baseRefName": "main"}]
        unwritable_artifact = str(tmp_path / "does-not-exist" / "artifact.json")

        with (
            patch(f"{_audit_mod.__name__}.assert_gh_authenticated"),
            patch(
                f"{_audit_mod.__name__}.resolve_repo_params",
                return_value=_MOCK_REPO,
            ),
            patch(f"{_audit_mod.__name__}.fetch_open_prs", return_value=nodes),
        ):
            result = _audit_mod.main(["--artifact", unwritable_artifact, "--output-format", "json"])

        assert result == 2
        assert '"Error"' in capsys.readouterr().out


class TestClosingReferencePagination:
    def test_resolves_references_by_repository_identity(self):
        references = [
            {
                "number": 123,
                "state": "OPEN",
                "repository": {"nameWithOwner": "owner/first"},
            },
            {
                "number": 123,
                "state": "CLOSED",
                "repository": {"nameWithOwner": "owner/second"},
            },
        ]

        assert _audit_mod._resolve_closing_refs(references) == {
            ("owner", "first", 123): "OPEN",
            ("owner", "second", 123): "CLOSED",
        }

    def test_fetch_open_prs_collects_all_closing_references(self):
        initial_references = [
            {
                "number": number,
                "state": "OPEN",
                "repository": {"nameWithOwner": "owner/repo"},
            }
            for number in range(1, 101)
        ]
        first_page = {
            "repository": {
                "defaultBranchRef": {"name": "main"},
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [{
                        "number": 42,
                        "closingIssuesReferences": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "refs-1"},
                            "nodes": initial_references,
                        },
                    }],
                },
            },
        }
        second_page = {
            "repository": {
                "pullRequest": {
                    "closingIssuesReferences": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "number": 101,
                                "state": "CLOSED",
                                "repository": {"nameWithOwner": "owner/repo"},
                            },
                            {
                                "number": 102,
                                "state": "OPEN",
                                "repository": {"nameWithOwner": "owner/repo"},
                            },
                        ],
                    },
                },
            },
        }

        with patch(
            f"{_audit_mod.__name__}.gh_graphql",
            side_effect=[first_page, second_page],
        ) as graphql:
            nodes = _audit_mod.fetch_open_prs("owner", "repo")

        references = nodes[0]["closingIssuesReferences"]["nodes"]
        assert len(references) == 102
        assert nodes[0]["defaultBranchName"] == "main"
        assert references[-2:] == second_page["repository"]["pullRequest"][
            "closingIssuesReferences"
        ]["nodes"]
        assert graphql.call_args_list[1].args[1] == {
            "owner": "owner",
            "repo": "repo",
            "number": 42,
            "cursor": "refs-1",
        }

    def test_missing_closing_reference_cursor_fails_closed(self):
        node = {
            "number": 42,
            "closingIssuesReferences": {
                "pageInfo": {"hasNextPage": True, "endCursor": None},
                "nodes": [],
            },
        }

        with pytest.raises(RuntimeError, match="omitted a cursor"):
            _audit_mod._complete_closing_references("owner", "repo", node)

    def test_missing_default_branch_fails_closed(self):
        response = {
            "repository": {
                "defaultBranchRef": None,
                "pullRequests": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [],
                },
            },
        }

        with (
            patch(f"{_audit_mod.__name__}.gh_graphql", return_value=response),
            pytest.raises(RuntimeError, match="default branch"),
        ):
            _audit_mod.fetch_open_prs("owner", "repo")


class TestBodyHashAndValidate:
    """Tests for edit_pr_body.py helpers."""

    def test_hash_is_deterministic(self):
        h1 = _edit_mod.body_hash("hello world")
        h2 = _edit_mod.body_hash("hello world")
        assert h1 == h2

    def test_hash_lf_normalised(self):
        assert _edit_mod.body_hash("a\r\nb") == _edit_mod.body_hash("a\nb")

    def test_hash_different_for_different_content(self):
        assert _edit_mod.body_hash("abc") != _edit_mod.body_hash("def")

    def test_validate_body_empty_is_clean(self):
        assert _edit_mod.validate_body("Fixes #123\nSome prose.") == []

    def test_validate_body_em_dash_flagged(self):
        warnings = _edit_mod.validate_body("Changes \u2014 see PR")
        assert any("em" in w.lower() or "dash" in w.lower() for w in warnings)

    def test_validate_body_multiple_issues_on_one_line_flagged(self):
        warnings = _edit_mod.validate_body("Fixes #1, #2 #3")
        assert any("one" in w.lower() or "line" in w.lower() or "first" in w.lower()
                   for w in warnings)

    def test_validate_body_and_separated_issues_flagged(self):
        warnings = _edit_mod.validate_body("Fixes #1 and #2")

        assert len(warnings) == 1
        assert "repeat the keyword" in warnings[0]

    def test_validate_body_multiple_keywords_on_one_line_is_clean(self):
        warnings = _edit_mod.validate_body("Fixes #1, closes #2")
        assert warnings == []

    def test_validate_body_lowercase_multiple_keywords_is_clean(self):
        warnings = _edit_mod.validate_body("fixes #1, closes #2")
        assert warnings == []

    def test_validate_body_single_issue_per_line_clean(self):
        body = "Fixes #1\nFixes #2\nFixes #3"
        assert _edit_mod.validate_body(body) == []


class TestEditPrBodyStaleWriteGuard:
    """Stale-write guard: abort when current hash differs from expected."""

    def test_abort_on_hash_mismatch(self, capsys):
        current = "current body"
        wrong_hash = "0" * 64

        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value=current),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--expected-hash", wrong_hash,
                "--output-format", "json",
            ])

        output = json.loads(capsys.readouterr().out)

        assert rc == 1
        assert output["Error"]["Type"] == "VerificationFailed"

    def test_no_write_when_body_unchanged(self):
        body = "same body"
        expected_hash = _edit_mod.body_hash(body)

        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value=body),
            patch(f"{_edit_mod.__name__}.update_body") as mock_update,
            patch(f"{_edit_mod.__name__}.write_skill_output"),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", body,
                "--expected-hash", expected_hash,
            ])
        assert rc == 0
        mock_update.assert_not_called()

    def test_write_when_body_changed_and_hash_matches(self):
        old_body = "old body"
        new_body = "new body"
        expected_hash = _edit_mod.body_hash(old_body)

        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value=old_body),
            patch(f"{_edit_mod.__name__}.update_body") as mock_update,
            patch(f"{_edit_mod.__name__}.write_skill_output"),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", new_body,
                "--expected-hash", expected_hash,
            ])
        assert rc == 0
        mock_update.assert_called_once()

    def test_not_found_returns_2(self):
        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value=None),
            patch(f"{_edit_mod.__name__}.write_skill_error"),
        ):
            rc = _edit_mod.main([
                "--pull-request", "9999",
                "--body", "something",
            ])
        assert rc == 2

    def test_dry_run_does_not_write(self):
        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.fetch_current_body", return_value="old body"),
            patch(f"{_edit_mod.__name__}.update_body") as mock_update,
            patch(f"{_edit_mod.__name__}.write_skill_output"),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--dry-run",
            ])
        assert rc == 0
        mock_update.assert_not_called()

    def test_fetch_current_body_preserves_trailing_newlines(self):
        body = "Body with trailing newlines\n\n"
        with patch(
            f"{_edit_mod.__name__}.subprocess.run",
            return_value=_completed(stdout=json.dumps({"body": body})),
        ):
            result = _edit_mod.fetch_current_body("owner", "repo", 42)

        assert result == body

    def test_update_body_sends_body_via_stdin(self):
        body = "@/path/that/must/not/be/read"
        with patch(
            f"{_edit_mod.__name__}.subprocess.run",
            return_value=_completed(stdout="42\n"),
        ) as mock_run:
            _edit_mod.update_body("owner", "repo", 42, body)

        command = mock_run.call_args.args[0]
        assert command[command.index("--input") + 1] == "-"
        assert "--raw-field" not in command
        assert json.loads(mock_run.call_args.kwargs["input"]) == {"body": body}

    def test_fetch_timeout_returns_api_error_envelope(self, capsys):
        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(
                f"{_edit_mod.__name__}.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["gh", "api"], 30),
            ),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--output-format", "json",
            ])

        output = json.loads(capsys.readouterr().out)
        assert rc == 3
        assert output["Error"]["Type"] == "ApiError"
        assert "timed out" in output["Error"]["Message"]

    def test_update_timeout_returns_api_error_envelope(self, capsys):
        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(
                f"{_edit_mod.__name__}.subprocess.run",
                side_effect=[
                    _completed(stdout=json.dumps({"body": "old body"})),
                    subprocess.TimeoutExpired(["gh", "api"], 30),
                ],
            ),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--output-format", "json",
            ])

        output = json.loads(capsys.readouterr().out)
        assert rc == 3
        assert output["Error"]["Type"] == "ApiError"
        assert "timed out" in output["Error"]["Message"]

    def test_missing_gh_returns_api_error_envelope(self, capsys):
        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(
                f"{_edit_mod.__name__}.subprocess.run",
                side_effect=FileNotFoundError("gh executable not found"),
            ),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--output-format", "json",
            ])

        output = json.loads(capsys.readouterr().out)
        assert rc == 3
        assert output["Error"]["Type"] == "ApiError"
        assert "gh executable not found" in output["Error"]["Message"]

    def test_fetch_blank_stderr_does_not_crash(self, capsys):
        """gh can exit non-zero with empty stderr (a signal kill, or a
        failure mode that writes to stdout instead), and
        fetch_current_body's original `raise RuntimeError(result.stderr
        .strip())` had no fallback, so str(exc) was "" for this case.
        write_skill_error's message guard (ADR-103 Round 5) rejects an
        empty message with ValueError; unguarded, main() would crash
        uncaught with exit 1 and no envelope, instead of the intended
        exit 3 with a parseable error envelope. Proven to discriminate:
        reverting fetch_current_body's fallback in a scratch copy
        reproduces exactly that crash (adr-review independent-thinker
        seat, ADR-103 Round 5 convergence check).
        """
        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(
                f"{_edit_mod.__name__}.subprocess.run",
                return_value=_completed(rc=1, stderr=""),
            ),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--output-format", "json",
            ])  # must not raise

        output = json.loads(capsys.readouterr().out)
        assert rc == 3
        assert output["Error"]["Type"] == "ApiError"
        assert output["Error"]["Message"]  # non-empty: the guard's own contract

    def test_update_blank_stderr_does_not_crash(self, capsys):
        """Same gap as test_fetch_blank_stderr_does_not_crash, for
        update_body's raise site.

        Dispatches the subprocess.run fake on the actual argv rather than
        call order: fetch_current_body's `gh api pulls/<n>` carries no
        `--method` flag, update_body's PATCH always does. A position-keyed
        side_effect list would silently pass the fetch's response to the
        update call (or vice versa) if a caller ever adds or removes a
        subprocess.run invocation ahead of these two (`.claude/rules/testing.md`
        MUST-11; Copilot review on PR #5283).
        """
        def _dispatch(cmd, **_kwargs):
            if "--method" in cmd:
                return _completed(rc=1, stderr="")
            if cmd and cmd[:2] == ["gh", "api"]:
                return _completed(stdout=json.dumps({"body": "old body"}))
            raise AssertionError(f"unstubbed subprocess.run call: {cmd}")

        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.subprocess.run", side_effect=_dispatch),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--output-format", "json",
            ])  # must not raise

        output = json.loads(capsys.readouterr().out)
        assert rc == 3
        assert output["Error"]["Type"] == "ApiError"
        assert output["Error"]["Message"]  # non-empty: the guard's own contract

    def test_fetch_blank_stderr_prefers_stdout_diagnostic(self, capsys):
        """When gh exits non-zero with blank stderr but a diagnostic on
        stdout, the raised message must carry that diagnostic, not jump
        straight past it to the generic fallback. Before this fix,
        fetch_current_body's `result.stderr.strip() or "<generic>"`
        fallback discarded result.stdout entirely, even when it held
        gh's actual failure text (Copilot review on PR #5283, following
        the ADR-103 Round 5 convergence check). Proven to discriminate:
        reverting the stdout fallback in a scratch copy reproduces the
        generic message instead of this one.
        """
        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(
                f"{_edit_mod.__name__}.subprocess.run",
                return_value=_completed(rc=1, stderr="", stdout="rate limited, retry in 30s"),
            ),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--output-format", "json",
            ])

        output = json.loads(capsys.readouterr().out)
        assert rc == 3
        assert output["Error"]["Message"] == "rate limited, retry in 30s"

    def test_update_blank_stderr_prefers_stdout_diagnostic(self, capsys):
        """Same gap as test_fetch_blank_stderr_prefers_stdout_diagnostic,
        for update_body's raise site. Dispatches on argv per MUST-11, same
        as test_update_blank_stderr_does_not_crash above.
        """
        def _dispatch(cmd, **_kwargs):
            if "--method" in cmd:
                return _completed(rc=1, stderr="", stdout="rate limited, retry in 30s")
            if cmd and cmd[:2] == ["gh", "api"]:
                return _completed(stdout=json.dumps({"body": "old body"}))
            raise AssertionError(f"unstubbed subprocess.run call: {cmd}")

        with (
            patch(f"{_edit_mod.__name__}.assert_gh_authenticated"),
            patch(f"{_edit_mod.__name__}.resolve_repo_params", return_value=_MOCK_REPO),
            patch(f"{_edit_mod.__name__}.subprocess.run", side_effect=_dispatch),
        ):
            rc = _edit_mod.main([
                "--pull-request", "42",
                "--body", "new body",
                "--output-format", "json",
            ])

        output = json.loads(capsys.readouterr().out)
        assert rc == 3
        assert output["Error"]["Message"] == "rate limited, retry in 30s"
