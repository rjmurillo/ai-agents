"""Tests for add_comment_reaction.py."""

import json
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "add_comment_reaction"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestAddCommentReaction:
    def test_single_success(self, _import_module):
        mod = _import_module
        with patch.object(mod, "_run_gh") as mock_gh:
            mock_gh.return_value = make_completed_process(
                stdout=json.dumps({"id": 1})
            )
            result = mod.add_comment_reaction(
                "o", "r", [123], "review", "eyes"
            )

        assert result["Succeeded"] == 1
        assert result["Failed"] == 0
        assert result["Results"][0]["Success"] is True

    def test_batch_success(self, _import_module):
        mod = _import_module
        with patch.object(mod, "_run_gh") as mock_gh:
            mock_gh.return_value = make_completed_process()
            result = mod.add_comment_reaction(
                "o", "r", [1, 2, 3], "review", "heart"
            )

        assert result["TotalCount"] == 3
        assert result["Succeeded"] == 3
        assert result["Failed"] == 0

    def test_partial_failure(self, _import_module):
        mod = _import_module

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                return make_completed_process(
                    returncode=1, stderr="error"
                )
            return make_completed_process()

        with patch.object(mod, "_run_gh", side_effect=side_effect):
            result = mod.add_comment_reaction(
                "o", "r", [1, 2, 3], "issue", "rocket"
            )

        assert result["Succeeded"] == 2
        assert result["Failed"] == 1

    def test_duplicate_reaction_succeeds(self, _import_module):
        mod = _import_module
        with patch.object(mod, "_run_gh") as mock_gh:
            mock_gh.return_value = make_completed_process(
                stdout="already reacted"
            )
            result = mod.add_comment_reaction(
                "o", "r", [1], "review", "+1"
            )

        assert result["Succeeded"] == 1

    def test_review_endpoint(self, _import_module):
        mod = _import_module
        with patch.object(mod, "_run_gh") as mock_gh:
            mock_gh.return_value = make_completed_process()
            mod.add_comment_reaction("o", "r", [99], "review", "eyes")

        call_args = mock_gh.call_args[0]
        assert "pulls/comments/99/reactions" in call_args[1]

    def test_issue_endpoint(self, _import_module):
        mod = _import_module
        with patch.object(mod, "_run_gh") as mock_gh:
            mock_gh.return_value = make_completed_process()
            mod.add_comment_reaction("o", "r", [99], "issue", "eyes")

        call_args = mock_gh.call_args[0]
        assert "issues/comments/99/reactions" in call_args[1]

    def test_all_reaction_types_valid(self, _import_module):
        mod = _import_module
        assert len(mod.VALID_REACTIONS) == 8
        for r in mod.VALID_REACTIONS:
            assert r in mod.REACTION_EMOJI
