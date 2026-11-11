"""Tests for the pure duplicate-comment helpers in pr_comment_dedupe.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "pr"
)
_spec = importlib.util.spec_from_file_location(
    "pr_comment_dedupe", _SCRIPTS_DIR / "pr_comment_dedupe.py"
)
assert _spec is not None
assert _spec.loader is not None
dedupe = importlib.util.module_from_spec(_spec)
sys.modules["pr_comment_dedupe"] = dedupe
_spec.loader.exec_module(dedupe)


class TestPaginatedArgs:
    def test_requests_every_page_in_one_slurped_call(self):
        assert dedupe.paginated_args("repos/o/r/issues/1/comments") == [
            "--paginate",
            "--slurp",
            "repos/o/r/issues/1/comments?per_page=100",
        ]

    def test_appends_to_an_existing_query_string(self):
        assert dedupe.paginated_args("x?a=1")[-1] == "x?a=1&per_page=100"


class TestFlattenPages:
    def test_flattens_pages_in_order(self):
        assert dedupe.flatten_pages(json.dumps([[{"id": 1}], [{"id": 2}, {"id": 3}]])) == [
            {"id": 1},
            {"id": 2},
            {"id": 3},
        ]

    def test_empty_listing_is_an_empty_list(self):
        assert dedupe.flatten_pages("[[]]") == []
        assert dedupe.flatten_pages("[]") == []

    @pytest.mark.parametrize(
        "stdout",
        ["", "not json", '{"message": "x"}', '[{"id": 1}]', "[[1]]", "[[[]]]"],
        ids=["empty", "text", "object", "unslurped", "scalar-item", "nested"],
    )
    def test_rejects_anything_that_is_not_a_list_of_pages_of_objects(self, stdout):
        with pytest.raises(ValueError):
            dedupe.flatten_pages(stdout)


class TestNormalizeBody:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a\r\nb", "a\nb"),
            ("  a\n", "a"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert dedupe.normalize_body(raw) == expected

    def test_keeps_interior_whitespace_and_case(self):
        assert dedupe.normalize_body("A  b") == "A  b"


class TestBodyMatches:
    def test_returns_only_identical_bodies(self):
        comments = [{"id": 1, "body": "x"}, {"id": 2, "body": "y"}, {"id": 3, "body": "x\r\n"}]
        assert [c["id"] for c in dedupe.body_matches(comments, "x")] == [1, 3]

    def test_missing_body_never_matches_a_non_empty_body(self):
        assert dedupe.body_matches([{"id": 1}], "x") == []


class TestFirstByAuthor:
    def test_matches_case_insensitively(self):
        comments = [{"id": 1, "user": {"login": "Bot"}}]
        assert dedupe.first_by_author(comments, "bot") == comments[0]

    @pytest.mark.parametrize(
        "user", [None, {}, {"login": None}, "bot"], ids=["none", "empty", "null-login", "string"]
    )
    def test_tolerates_missing_or_malformed_user(self, user):
        assert dedupe.first_by_author([{"id": 1, "user": user}], "bot") is None

    def test_returns_none_for_other_authors(self):
        assert dedupe.first_by_author([{"user": {"login": "other"}}], "bot") is None


class TestThreadComments:
    COMMENTS = [
        {"id": 10, "in_reply_to_id": None},
        {"id": 11, "in_reply_to_id": 10},
        {"id": 12, "in_reply_to_id": 10},
        {"id": 20, "in_reply_to_id": None},
        {"id": 21, "in_reply_to_id": 20},
    ]

    @pytest.mark.parametrize("comment_id", [10, 11, 12])
    def test_any_member_resolves_the_same_thread(self, comment_id):
        thread = dedupe.thread_comments(self.COMMENTS, comment_id)
        assert [c["id"] for c in thread] == [10, 11, 12]

    def test_unknown_comment_returns_none(self):
        assert dedupe.thread_comments(self.COMMENTS, 99) is None


class TestCommentsAtLine:
    @staticmethod
    def _c(**fields):
        base = {"id": 1, "path": "a.py", "line": 5, "side": "RIGHT", "in_reply_to_id": None}
        return {**base, **fields}

    def test_matches_path_line_and_side(self):
        assert dedupe.comments_at_line([self._c()], "a.py", 5, "RIGHT") == [self._c()]

    @pytest.mark.parametrize(
        "fields",
        [{"path": "b.py"}, {"line": 6}, {"side": "LEFT"}, {"in_reply_to_id": 3}],
    )
    def test_excludes_other_spots_and_replies(self, fields):
        assert dedupe.comments_at_line([self._c(**fields)], "a.py", 5, "RIGHT") == []

    def test_outdated_comment_uses_original_line(self):
        outdated = self._c(line=None, original_line=5)
        assert dedupe.comments_at_line([outdated], "a.py", 5, "RIGHT") == [outdated]

    def test_missing_side_is_treated_as_right(self):
        c = self._c()
        del c["side"]
        assert dedupe.comments_at_line([c], "a.py", 5, "RIGHT") == [c]
        assert dedupe.comments_at_line([c], "a.py", 5, "LEFT") == []
