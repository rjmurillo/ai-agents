"""Focused GitHub Core contract cases."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.github_core import (
    RateLimitResult,
    RateLimitStatus,
    RepoInfo,
    bot_config,
    check_workflow_rate_limit,
    get_priority_emoji,
    get_reaction_emoji,
    is_gh_authenticated,
    resolve_repo_params,
)
from tests.github_core_test_helpers import (
    _REPO_ROOT,
    RATE_LIMIT_ALL_OK,
    RATE_LIMIT_CORE_LOW,
    RATE_LIMIT_MISSING_RESOURCE,
    _completed,
)


class TestCheckWorkflowRateLimit:
    def test_success_all_above_threshold(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()
        assert result.success is True
        assert result.status == RateLimitStatus.VERIFIED_HEALTHY
        assert result.core_remaining == 5000

    def test_failure_core_below_threshold(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit()
        assert result.success is False
        assert result.status == RateLimitStatus.VERIFIED_LIMITED
        assert result.resources["core"]["Passed"] is False

    def test_custom_thresholds_pass(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit(resource_thresholds={"core": 10})
        assert result.success is True
        assert result.status == RateLimitStatus.VERIFIED_HEALTHY

    def test_custom_thresholds_fail(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_CORE_LOW)):
            result = check_workflow_rate_limit(resource_thresholds={"core": 100})
        assert result.success is False
        assert result.status == RateLimitStatus.VERIFIED_LIMITED

    def test_markdown_summary(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()
        assert "API Rate Limit Status" in result.summary_markdown
        assert "| Resource |" in result.summary_markdown
        assert "OK" in result.summary_markdown

    def test_missing_resource_warns(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_MISSING_RESOURCE)):
            with pytest.warns(UserWarning, match="code_search"):
                result = check_workflow_rate_limit()
        assert result.success is False
        assert result.status == RateLimitStatus.COULD_NOT_DETERMINE

    def test_raises_on_api_failure(self):
        with patch("subprocess.run", return_value=_completed(rc=1, stderr="API error")):
            with pytest.raises(RuntimeError, match="Failed to fetch rate limits"):
                check_workflow_rate_limit()

    def test_invalid_json_response_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="not json")):
            with pytest.raises(RuntimeError, match="not valid JSON"):
                check_workflow_rate_limit()

    def test_returns_rate_limit_result_type(self):
        with patch("subprocess.run", return_value=_completed(stdout=RATE_LIMIT_ALL_OK)):
            result = check_workflow_rate_limit()
        assert isinstance(result, RateLimitResult)

    def test_null_resources_does_not_crash(self):
        """An explicit null ``resources`` from the API must not raise. Every
        resource reads as missing (warns, fails) and core_remaining is 0.
        """
        payload = json.dumps({"resources": None})
        with patch("subprocess.run", return_value=_completed(stdout=payload)):
            with pytest.warns(UserWarning):
                result = check_workflow_rate_limit()
        assert result.success is False
        assert result.status == RateLimitStatus.COULD_NOT_DETERMINE
        assert result.core_remaining == 0


class TestGetPriorityEmoji:
    def test_p0_fire(self):
        assert get_priority_emoji("P0") == "\U0001f525"

    def test_p1_exclamation(self):
        assert get_priority_emoji("P1") == "\u2757"

    def test_p2_dash(self):
        assert get_priority_emoji("P2") == "\u2796"

    def test_p3_down_arrow(self):
        assert get_priority_emoji("P3") == "\u2b07\ufe0f"

    def test_unknown_question_mark(self):
        assert get_priority_emoji("unknown") == "\u2754"


class TestGetReactionEmoji:
    def test_thumbs_up(self):
        assert get_reaction_emoji("+1") == "\U0001f44d"

    def test_thumbs_down(self):
        assert get_reaction_emoji("-1") == "\U0001f44e"

    def test_laugh(self):
        assert get_reaction_emoji("laugh") == "\U0001f604"

    def test_confused(self):
        assert get_reaction_emoji("confused") == "\U0001f615"

    def test_heart(self):
        assert get_reaction_emoji("heart") == "\u2764\ufe0f"

    def test_hooray(self):
        assert get_reaction_emoji("hooray") == "\U0001f389"

    def test_rocket(self):
        assert get_reaction_emoji("rocket") == "\U0001f680"

    def test_eyes(self):
        assert get_reaction_emoji("eyes") == "\U0001f440"

    def test_unknown_returns_input(self):
        assert get_reaction_emoji("custom") == "custom"


class TestYamlFallback:
    """No-PyYAML fallback path (issue #1844).

    When PyYAML is not importable, bot_config must still load authors via
    the vendored _parse_simple_yaml and produce the same result.
    """

    def test_parse_simple_yaml_matches_yaml_safe_load(self) -> None:
        import yaml as _yaml

        text = (_REPO_ROOT / ".github" / "bot-authors.yml").read_text(encoding="utf-8")
        reference = _yaml.safe_load(text)
        assert bot_config._parse_simple_yaml(text) == reference

    def test_get_bot_authors_config_without_yaml(self, monkeypatch) -> None:
        with_yaml = bot_config.get_bot_authors_config(force=True)
        monkeypatch.setattr(bot_config, "yaml", None)
        without_yaml = bot_config.get_bot_authors_config(force=True)
        assert without_yaml == with_yaml

    def test_is_bot_without_yaml(self, monkeypatch) -> None:
        monkeypatch.setattr(bot_config, "yaml", None)
        bot_config.get_bot_authors_config(force=True)
        assert bot_config.is_bot("coderabbitai[bot]")
        assert not bot_config.is_bot("octocat-human")

    def test_missing_file_without_yaml_uses_defaults(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(bot_config, "yaml", None)
        missing = str(tmp_path / "none.yml")
        cfg = bot_config.get_bot_authors_config(config_path=missing, force=True)
        assert cfg == bot_config._DEFAULT_BOTS


class TestParseSimpleYaml:
    """Unit coverage for the vendored YAML-subset parser (issue #1844)."""

    def test_block_list(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\n  - foo\n  - bar\n") == {
            "bots": ["foo", "bar"]
        }

    def test_inline_comment_stripped_from_item(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\n  - foo  # note\n") == {"bots": ["foo"]}

    def test_comments_and_blanks_ignored(self) -> None:
        text = "# header\n\nbots:\n  - foo\n\n  - bar\n# trailer\n"
        assert bot_config._parse_simple_yaml(text) == {"bots": ["foo", "bar"]}

    def test_item_with_space_and_brackets_preserved(self) -> None:
        text = "bots:\n  - Copilot   # no suffix\n  - renovate[bot]\n"
        assert bot_config._parse_simple_yaml(text) == {"bots": ["Copilot", "renovate[bot]"]}

    def test_literal_hash_in_item_preserved(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\n  - foo#bar\n") == {"bots": ["foo#bar"]}

    def test_inline_scalar_value(self) -> None:
        assert bot_config._parse_simple_yaml("name: value\n") == {"name": "value"}

    def test_quoted_value_unwrapped(self) -> None:
        assert bot_config._parse_simple_yaml('name: "value"\n') == {"name": "value"}

    def test_quoted_item_unwrapped(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\n  - 'foo'\n") == {"bots": ["foo"]}

    def test_hash_inside_quoted_item_preserved(self) -> None:
        # A # inside quotes is literal content, not a comment marker.
        assert bot_config._parse_simple_yaml("bots:\n  - 'foo # bar'\n") == {"bots": ["foo # bar"]}
        assert bot_config._parse_simple_yaml('name: "value # note"\n') == {"name": "value # note"}

    def test_empty_text(self) -> None:
        assert bot_config._parse_simple_yaml("") == {}

    def test_orphan_item_without_key_ignored(self) -> None:
        assert bot_config._parse_simple_yaml("- foo\n") == {}

    def test_bare_scalar_text_yields_empty(self) -> None:
        # A document with no `key:` mapping has nothing to collect; the
        # caller then falls back to defaults via the empty-dict guard.
        assert bot_config._parse_simple_yaml("just a string\n") == {}

    def test_mismatched_quote_left_intact(self) -> None:
        # Only a matched surrounding pair is stripped.
        assert bot_config._parse_simple_yaml("bots:\n  - \"foo'\n") == {"bots": ["\"foo'"]}

    def test_colon_value_without_space(self) -> None:
        # Per YAML spec, a colon without a following space is part of a plain
        # scalar, not a key-value separator. yaml.safe_load("name:value\n")
        # returns the string "name:value", not a dict. Our parser follows suit
        # by returning {} for non-mapping documents.
        assert bot_config._parse_simple_yaml("name:value\n") == {}

    def test_crlf_line_endings(self) -> None:
        assert bot_config._parse_simple_yaml("bots:\r\n  - foo\r\n") == {"bots": ["foo"]}


class TestResolveRepoParams:
    def test_uses_provided_params(self):
        result = resolve_repo_params("myowner", "myrepo")
        assert result == RepoInfo(owner="myowner", repo="myrepo")

    def test_infers_from_git_remote(self):
        with patch(
            "scripts.github_core.api.get_repo_info",
            return_value=RepoInfo(owner="inferred", repo="repo"),
        ):
            result = resolve_repo_params()
        assert result == RepoInfo(owner="inferred", repo="repo")

    def test_exits_when_cannot_infer(self):
        with patch("scripts.github_core.api.get_repo_info", return_value=None):
            with pytest.raises(SystemExit) as exc:
                resolve_repo_params()
            assert exc.value.code == 2

    def test_exits_on_invalid_owner(self):
        with pytest.raises(SystemExit) as exc:
            resolve_repo_params("-bad", "repo")
        assert exc.value.code == 2

    def test_exits_on_invalid_repo(self):
        with pytest.raises(SystemExit) as exc:
            resolve_repo_params("owner", "bad/repo/name!")
        assert exc.value.code == 2

    def test_returns_repo_info_type(self):
        result = resolve_repo_params("owner", "repo")
        assert isinstance(result, RepoInfo)


class TestIsGhAuthenticated:
    def test_true_when_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert is_gh_authenticated() is True

    def test_false_when_not_authenticated(self):
        with patch("subprocess.run", return_value=_completed(rc=1)):
            assert is_gh_authenticated() is False

    def test_false_when_gh_not_installed(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert is_gh_authenticated() is False

    def test_false_when_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=10)):
            assert is_gh_authenticated() is False

    def test_returns_bool(self):
        with patch("subprocess.run", return_value=_completed(rc=0)):
            assert isinstance(is_gh_authenticated(), bool)
