"""Tests for the user_prompt_submit_memory hook (auto-recall)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_enhancement.hooks.user_prompt_submit_memory import (
    _extract_query,
    _find_repo_root,
    _format_memory_context,
    _read_user_input,
    _render_for_host,
    _search_and_format,
    main,
)
from memory_enhancement.search import SearchResult


@pytest.fixture(autouse=True)
def _neutral_harness_identity(monkeypatch):
    """Clear both harness-identity signals before every test in this module.

    pytest runs under Claude Code or Copilot CLI, and whichever is live exports
    its own signal into the test process. `_render_for_host` branches on exactly
    those two variables, so an inherited value decides the output shape for any
    case that does not pin it, and the case then passes on one contributor's
    machine and fails on the other's. Clearing here forces each case to name its
    own host. This is `.claude/rules/testing.md` SHOULD-12 applied in-process.
    """
    monkeypatch.delenv("COPILOT_CLI", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)


class TestExtractQuery:
    """Tests for stop word filtering and term extraction."""

    @pytest.mark.unit
    def test_filters_stop_words(self):
        result = _extract_query("the quick brown fox is running")
        assert "the" not in result
        assert "is" not in result
        assert "quick" in result

    @pytest.mark.unit
    def test_filters_short_tokens(self):
        result = _extract_query("a b cd efg hij")
        assert "a" not in result.split()
        assert "b" not in result.split()
        assert "cd" not in result.split()

    @pytest.mark.unit
    def test_takes_top_5_terms(self):
        result = _extract_query("alpha beta gamma delta epsilon zeta eta")
        terms = result.split()
        assert len(terms) <= 5

    @pytest.mark.unit
    def test_empty_input_returns_empty(self):
        assert _extract_query("") == ""

    @pytest.mark.unit
    def test_only_stop_words_returns_empty(self):
        assert _extract_query("the and is for") == ""

    @pytest.mark.unit
    def test_lowercases_input(self):
        result = _extract_query("MEMORY Enhancement Layer")
        assert "memory" in result
        assert "enhancement" in result


class TestReadUserInput:
    """Tests for stdin parsing."""

    @pytest.mark.unit
    def test_json_with_query_field(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO('{"query": "test search"}'))
        result = _read_user_input()
        assert result == "test search"

    @pytest.mark.unit
    def test_json_with_prompt_field(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt": "hello world"}'))
        result = _read_user_input()
        assert result == "hello world"

    @pytest.mark.unit
    def test_plain_text_input(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO("plain text query"))
        result = _read_user_input()
        assert result == "plain text query"

    @pytest.mark.unit
    def test_empty_stdin(self, monkeypatch):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        result = _read_user_input()
        assert result == ""


class TestFindRepoRoot:
    """Tests for repository root detection."""

    @pytest.mark.unit
    def test_finds_git_directory(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        result = _find_repo_root(sub)
        assert result == tmp_path

    @pytest.mark.unit
    def test_returns_none_when_no_git(self, tmp_path: Path):
        """Verify None is returned when no .git exists in any ancestor."""
        with patch.object(Path, "exists", return_value=False):
            result = _find_repo_root(tmp_path)
            assert result is None


class TestRenderForHost:
    """The stdout envelope each harness consumes (issue #4727).

    Copilot CLI 1.0.79-6 discards plain UserPromptSubmit stdout and reads a
    top-level ``{"additionalContext": "..."}`` document. Claude Code reads the
    plain text and never a top-level ``additionalContext`` key.

    Two variables discriminate, and the order matters. Copilot exports
    ``COPILOT_CLI`` into every shell it spawns, so its presence alone does not
    identify the consuming host; a Claude session launched from inside a Copilot
    shell inherits it. ``CLAUDE_CODE_ENTRYPOINT`` is set by Claude Code and
    never by Copilot CLI, so it takes precedence.

    Every case sets both variables explicitly rather than deleting one and
    inheriting the other, because pytest itself runs under one of these two
    harnesses and would otherwise supply the answer.
    """

    BLOCK = "<memory-context>\nhit\n</memory-context>"

    @staticmethod
    def _host(monkeypatch, *, copilot: str | None, claude: str | None) -> None:
        """Pin both harness signals so nothing leaks in from the test runner."""
        for name, value in (("COPILOT_CLI", copilot), ("CLAUDE_CODE_ENTRYPOINT", claude)):
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)

    @pytest.mark.unit
    def test_copilot_gets_a_top_level_additional_context_envelope(self, monkeypatch):
        self._host(monkeypatch, copilot="1", claude=None)

        payload = json.loads(_render_for_host(self.BLOCK))

        assert payload == {"additionalContext": self.BLOCK}

    @pytest.mark.unit
    def test_claude_gets_the_block_unwrapped(self, monkeypatch):
        self._host(monkeypatch, copilot=None, claude=None)

        assert _render_for_host(self.BLOCK) == self.BLOCK

    @pytest.mark.unit
    def test_an_inherited_copilot_cli_does_not_override_a_live_claude_session(
        self, monkeypatch
    ):
        """Both signals set means Claude is the consumer and Copilot is an ancestor.

        Claude reads a nested ``hookSpecificOutput`` envelope, so a top-level
        ``additionalContext`` document parses as structured output with no
        recognized field and the memory block is dropped with no error. Sending
        the bare block instead fails safe in the other direction: Copilot merely
        discards it, which is what it did before this hook existed.
        """
        self._host(monkeypatch, copilot="1", claude="cli")

        assert _render_for_host(self.BLOCK) == self.BLOCK

    @pytest.mark.unit
    def test_copilot_alone_still_gets_the_envelope(self, monkeypatch):
        """The control for the case above: without the Claude signal, the same
        COPILOT_CLI value must still produce the envelope."""
        self._host(monkeypatch, copilot="1", claude=None)

        assert json.loads(_render_for_host(self.BLOCK)) == {
            "additionalContext": self.BLOCK
        }

    @pytest.mark.unit
    @pytest.mark.parametrize("value", ["", "   ", "\t"])
    def test_a_blank_claude_entrypoint_does_not_suppress_the_envelope(
        self, monkeypatch, value
    ):
        """An exported but empty Claude signal is indistinguishable from unset,
        so it must not strip a real Copilot session's envelope."""
        self._host(monkeypatch, copilot="1", claude=value)

        assert json.loads(_render_for_host(self.BLOCK)) == {
            "additionalContext": self.BLOCK
        }

    @pytest.mark.unit
    @pytest.mark.parametrize("value", ["", "   ", "\t"])
    def test_a_blank_copilot_cli_value_is_treated_as_absent(self, monkeypatch, value):
        self._host(monkeypatch, copilot=value, claude=None)

        assert _render_for_host(self.BLOCK) == self.BLOCK

    @pytest.mark.unit
    def test_the_envelope_is_one_json_document(self, monkeypatch):
        """Copilot parses at most one final JSON document per command hook, so
        a multi-line block must not become several."""
        self._host(monkeypatch, copilot="true", claude=None)

        rendered = _render_for_host(self.BLOCK)

        assert "\n" not in rendered


class TestFormatMemoryContext:
    """Tests for the stdout output format."""

    @pytest.mark.unit
    def test_format_single_result(self):
        result = SearchResult(
            memory_id="test-mem",
            file_path=Path("/tmp/test-mem.md"),
            confidence=0.85,
            title="Test Memory",
            snippet="This is a test snippet",
            citation_status="verified",
        )
        output = _format_memory_context([result])

        assert "<memory-context>" in output
        assert "</memory-context>" in output
        assert "Test Memory" in output
        assert "85%" in output
        assert "verified" in output
        assert "test-mem.md" in output

    @pytest.mark.unit
    def test_format_multiple_results(self):
        results = [
            SearchResult(
                memory_id=f"mem-{i}",
                file_path=Path(f"/tmp/mem-{i}.md"),
                confidence=0.5 + i * 0.1,
                title=f"Memory {i}",
                snippet=f"Snippet {i}",
                citation_status="unverified",
            )
            for i in range(3)
        ]
        output = _format_memory_context(results)
        assert output.count("###") == 3

    @pytest.mark.unit
    def test_format_empty_results(self):
        output = _format_memory_context([])
        assert "<memory-context>" in output
        assert "###" not in output


class TestSearchAndFormat:
    """Tests for the search-then-format pipeline."""

    @pytest.mark.unit
    @patch("memory_enhancement.search.search_memories")
    def test_returns_empty_when_no_results(self, mock_search, tmp_path: Path):
        mock_search.return_value = []
        result = _search_and_format("query", tmp_path, tmp_path)
        assert result == ""

    @pytest.mark.unit
    @patch("memory_enhancement.search.search_memories")
    def test_returns_formatted_when_results_found(self, mock_search, tmp_path: Path):
        mock_search.return_value = [
            SearchResult(
                memory_id="found",
                file_path=Path("/tmp/found.md"),
                confidence=0.9,
                title="Found Memory",
                snippet="A snippet",
                citation_status="verified",
            )
        ]
        result = _search_and_format("query", tmp_path, tmp_path)
        assert "<memory-context>" in result
        assert "Found Memory" in result


class TestExitContract:
    """UserPromptSubmit exit 2 erases the prompt, so recall must never use it.

    See issue #4011 and the per-event table in .agents/specs/hook-protocol.md.
    """

    @staticmethod
    def _repo(tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".serena" / "memories").mkdir(parents=True)
        return tmp_path

    @pytest.mark.unit
    def test_match_writes_stdout_and_returns_zero(self, tmp_path, monkeypatch, capsys):
        repo = self._repo(tmp_path)
        monkeypatch.delenv("COPILOT_CLI", raising=False)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "dispatch groups"})))
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._find_repo_root",
            lambda start=None: repo,
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._search_and_format",
            lambda *_args: "<memory-context>hit</memory-context>",
        )

        exit_code = main()

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "<memory-context>" in captured.out
        assert captured.err == ""

    @pytest.mark.unit
    def test_copilot_match_writes_one_envelope_and_returns_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        repo = self._repo(tmp_path)
        monkeypatch.setenv("COPILOT_CLI", "1")
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "dispatch groups"})))
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._find_repo_root",
            lambda start=None: repo,
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._search_and_format",
            lambda *_args: "<memory-context>hit</memory-context>",
        )

        exit_code = main()

        captured = capsys.readouterr()
        assert exit_code == 0
        payload = json.loads(captured.out)
        assert payload["additionalContext"] == "<memory-context>hit</memory-context>"
        assert captured.err == ""

    @pytest.mark.unit
    def test_no_match_writes_nothing_under_copilot(self, tmp_path, monkeypatch, capsys):
        """An empty recall must stay silent rather than send an empty
        envelope, which would inject a blank context block every prompt."""
        repo = self._repo(tmp_path)
        monkeypatch.setenv("COPILOT_CLI", "1")
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "dispatch groups"})))
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._find_repo_root",
            lambda start=None: repo,
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._search_and_format",
            lambda *_args: "",
        )

        exit_code = main()

        assert exit_code == 0
        assert capsys.readouterr().out == ""

    @pytest.mark.unit
    def test_no_match_returns_zero_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        repo = self._repo(tmp_path)
        monkeypatch.delenv("COPILOT_CLI", raising=False)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "dispatch groups"})))
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._find_repo_root",
            lambda start=None: repo,
        )
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._search_and_format",
            lambda *_args: "",
        )

        exit_code = main()

        assert exit_code == 0
        assert capsys.readouterr().out == ""

    @pytest.mark.unit
    def test_missing_memories_dir_returns_zero(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "dispatch groups"})))
        monkeypatch.setattr(
            "memory_enhancement.hooks.user_prompt_submit_memory._find_repo_root",
            lambda start=None: tmp_path,
        )

        assert main() == 0
