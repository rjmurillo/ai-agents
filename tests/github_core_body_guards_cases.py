"""Focused GitHub Core contract cases."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core import validation
from tests.github_core_test_helpers import RATE_LIMIT_ALL_OK, _completed


class TestCapturedTextDecoding:
    """Every captured-text reader in this package pins its codec.

    Without an explicit ``encoding`` Python decodes with the locale's
    preferred codec, so a cp1252 or cp932 runner turns the same bytes into
    different characters without raising. `gh` emits raw UTF-8 and `git`
    emits raw filesystem bytes, so both readers are exposed.
    """

    def test_rate_limit_pins_utf8(self):
        from scripts.github_core import rate_limit

        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)) as run:
            rate_limit._fetch_rate_limit()
        assert run.call_args.kwargs.get("encoding") == "utf-8"
        assert "errors" not in run.call_args.kwargs

    def test_repo_root_pins_utf8(self, tmp_path: Path):
        from scripts.github_core import repo

        with patch("subprocess.run", return_value=_completed(stdout=str(tmp_path))) as run:
            repo.get_repo_root()
        assert run.call_args.kwargs.get("encoding") == "utf-8"
        assert "errors" not in run.call_args.kwargs

    def test_repo_root_returns_none_when_git_output_will_not_decode(self):
        """Strict decoding must not crash a helper documented to return None.

        Filesystem paths on POSIX are bytes, so a checkout under a name that is
        not valid UTF-8 makes ``subprocess.run`` raise while decoding. The
        function promises ``None`` on failure, and every caller anchors paths on
        the result, so an escaping decode error would take out unrelated tools.
        """
        from scripts.github_core import repo

        boom = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
        with patch("subprocess.run", side_effect=boom):
            assert repo.get_repo_root() is None

    def test_repo_root_survives_a_non_ascii_path(self, tmp_path: Path):
        """The repo root seeds every derived path, so a mojibake read is load-bearing."""
        from scripts.github_core import repo

        root = tmp_path / "\u30d7\u30ed\u30b8\u30a7\u30af\u30c8"
        root.mkdir()
        with patch("subprocess.run", return_value=_completed(stdout=f"{root}\n")):
            assert repo.get_repo_root() == root


class TestEscapedNewlineBodyError:
    """Guard against inline --body strings that carry literal backslash-n.

    Issue #3777. Two shipped issues (#3598, #3646) reached GitHub with their
    line breaks written as the two characters backslash and n, so GitHub
    rendered each as one unbroken paragraph and dropped every heading, list
    and table. Nothing errored at the time.

    The premise recorded in #3777 ("0 real newlines") is wrong and was
    re-measured before this guard was written: #3598 carries 15 literal
    sequences and 1 real newline, #3646 carries 9 and 1, in both cases a
    trailing newline supplied by the API. A naive ``"\\n" not in body``
    check therefore misses both, which is why the predicate strips first.
    """

    def test_flags_escaped_newlines_with_no_real_break(self) -> None:
        body = "## Summary\\n\\nSome text\\n- item"
        message = validation.escaped_newline_body_error(body)
        assert message is not None
        assert "3 literal backslash-n" in message
        assert "--body-file" in message

    def test_flags_the_measured_shape_of_issue_3598(self) -> None:
        """Trailing-newline-only bodies are the real-world failure shape."""
        body = "## Summary\\n\\nDetail\\n" + "\n"
        assert validation.escaped_newline_body_error(body) is not None

    def test_allows_escaped_newlines_alongside_real_ones(self) -> None:
        """A code fence may legitimately show a backslash-n sequence."""
        body = '## Notes\n\n```python\nprint("a\\nb")\n```\n'
        assert validation.escaped_newline_body_error(body) is None

    def test_allows_a_normal_multiline_body(self) -> None:
        assert validation.escaped_newline_body_error("## H\n\ntext\n") is None

    def test_allows_a_single_line_body_without_escapes(self) -> None:
        assert validation.escaped_newline_body_error("Just one line.") is None

    def test_allows_empty_and_none_bodies(self) -> None:
        """Empty-body rejection belongs to the callers, not this predicate."""
        assert validation.escaped_newline_body_error("") is None
        assert validation.escaped_newline_body_error(None) is None

    def test_message_counts_every_occurrence(self) -> None:
        message = validation.escaped_newline_body_error("a\\nb\\nc")
        assert message is not None
        assert "2 literal backslash-n" in message


class TestEscapedNewlineGuardIsWiredAtEveryInlineBodySite:
    """Isolating control: each caller must reject a corrupt inline body.

    A shared predicate that no caller invokes fixes nothing. Issue #3777 is
    about the six scripts that pass an inline ``--body`` straight to gh, so
    the guard is only load-bearing if every one of them calls it.
    """

    # Three sites reach the guard through inline_body_error, which folds the
    # empty-body check in with it so the host main() spends one branch
    # instead of two. Two sites call escaped_newline_body_error directly
    # because their empty-body rule differs (new_issue.py validates only the
    # title; edit_issue_body.py rejects empty strings with exit 1).
    _SITE_ENTRY_POINTS = {
        "issue/new_issue.py": "escaped_newline_body_error",
        "issue/edit_issue_body.py": "escaped_newline_body_error",
        "issue/post_issue_comment.py": "resolved_body_error",
        "pr/post_pr_comment_reply.py": "resolved_body_error",
        "pr/add_pr_review_thread_reply.py": "resolved_body_error",
    }

    def _script(self, rel: str) -> str:
        root = Path(__file__).resolve().parents[1]
        path = root / ".claude" / "skills" / "github" / "scripts" / rel
        assert path.is_file(), f"missing script: {path}"
        return path.read_text(encoding="utf-8")

    @pytest.mark.parametrize("rel,entry", sorted(_SITE_ENTRY_POINTS.items()))
    def test_site_imports_and_calls_the_shared_predicate(self, rel: str, entry: str) -> None:
        source = self._script(rel)
        tree = ast.parse(source)
        imported = {
            (alias.name, alias.asname or alias.name)
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module in {"github_core", "github_core.validation"}
            for alias in node.names
        }
        assert (entry, entry) in imported, f"{rel} never imports {entry}"
        called = any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == entry
            for node in ast.walk(tree)
        )
        assert called, f"{rel} never calls {entry}"

    def test_pr_copy_cites_the_canonical_source(self) -> None:
        """The PR path carries a second copy and must say where it came from.

        new_pr.py resolves only its own directory on sys.path, so importing
        github_core would mean adding the lib bootstrap the other scripts
        use, which hard-exits 2 whenever .claude/lib is absent. On the push
        path that trades a rendering bug for an outage. The copy therefore
        lives in the sibling module new_pr.py already imports from, and the
        citation is what keeps the two findable from each other.

        Behaviour is pinned by
        tests/test_new_pr.py::TestValidation6EscapedNewlineCheck; only the
        cross-reference is asserted here, because no runtime test can.
        """
        source = self._script("pr/validate_pr_description.py")
        assert "scripts/github_core/validation.py::escaped_newline_body_error" in source
        assert "validate_no_escaped_newlines" in self._script("pr/new_pr.py")


class TestInlineBodyError:
    """The folded predicate the three symmetric callers use.

    Issue #3777. Both rejections are reported through one branch so the
    host main() functions, all of which already carry a noqa: C901, do not
    grow another. post_issue_comment.py::main measured 21 before this change
    and 20 after.

    Check order is deliberately untested. A body that strips to empty cannot
    contain a literal backslash-n, because neither backslash nor n is
    whitespace, so the two conditions are mutually exclusive. Verified
    exhaustively over 9331 bodies drawn from space, tab, newline, backslash,
    n and x up to length 5: zero satisfy both. Swapping the arms is an
    equivalent mutant, and a test asserting the order would never fail.
    """

    def test_rejects_an_empty_body(self) -> None:
        assert validation.inline_body_error("") == "Body cannot be empty."

    def test_rejects_a_none_body(self) -> None:
        assert validation.inline_body_error(None) == "Body cannot be empty."

    def test_rejects_a_whitespace_only_body(self) -> None:
        assert validation.inline_body_error("  \n\t ") == "Body cannot be empty."

    def test_rejects_escaped_newlines(self) -> None:
        message = validation.inline_body_error("## H\\n\\ntext")
        assert message is not None
        assert "literal backslash-n" in message

    def test_allows_a_normal_body(self) -> None:
        assert validation.inline_body_error("## H\n\ntext\n") is None
