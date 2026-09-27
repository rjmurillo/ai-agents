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
    _search_and_format,
    main,
    main_transformed,
)
from memory_enhancement.search import SearchResult


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


class TestFormatMemoryContext:
    """Tests for the stderr output format."""

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

    See issue #4011 and the per-event table in .project-toolkit/specs/hook-protocol.md.
    """

    @staticmethod
    def _repo(tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".serena" / "memories").mkdir(parents=True)
        return tmp_path

    @pytest.mark.unit
    def test_match_writes_stdout_and_returns_zero(self, tmp_path, monkeypatch, capsys):
        repo = self._repo(tmp_path)
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
    def test_no_match_returns_zero_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        repo = self._repo(tmp_path)
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


class TestCopilotTransformedContract:
    """Copilot CLI drops config-file UserPromptSubmit output (issue #4727).

    Recall reaches Copilot through userPromptTransformed, whose documented
    output field is ``modifiedTransformedPrompt``.
    """

    _MODULE = "memory_enhancement.hooks.user_prompt_submit_memory"

    def _run(self, monkeypatch, capsys, tmp_path, payload, recall, cloud_env=None):
        cloud_env = cloud_env or {}
        (tmp_path / ".git").mkdir(exist_ok=True)
        (tmp_path / ".serena" / "memories").mkdir(parents=True, exist_ok=True)
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        monkeypatch.setattr(f"{self._MODULE}._find_repo_root", lambda start=None: tmp_path)
        for name in ("COPILOT_AGENT_PROMPT", "GITHUB_COPILOT_API_TOKEN"):
            if name not in cloud_env:
                monkeypatch.delenv(name, raising=False)
        for name, value in cloud_env.items():
            monkeypatch.setenv(name, value)
        seen: list[str] = []

        def fake_search(query, *_args):
            seen.append(query)
            return recall

        monkeypatch.setattr(f"{self._MODULE}._search_and_format", fake_search)
        exit_code = main_transformed()
        captured = capsys.readouterr()
        return exit_code, captured, seen

    @pytest.mark.unit
    def test_match_emits_one_envelope_appending_block(self, tmp_path, monkeypatch, capsys):
        payload = {"prompt": "dispatch groups", "transformedPrompt": "<ctx/>dispatch groups"}
        block = "<memory-context>hit</memory-context>"

        exit_code, captured, seen = self._run(monkeypatch, capsys, tmp_path, payload, block)

        assert exit_code == 0
        assert captured.err == ""
        assert json.loads(captured.out) == {
            "modifiedTransformedPrompt": f"<ctx/>dispatch groups\n\n{block}"
        }
        assert seen == ["dispatch groups"]

    @pytest.mark.unit
    def test_query_uses_prompt_not_transformed_content(self, tmp_path, monkeypatch, capsys):
        payload = {"prompt": "routing table", "transformedPrompt": "attachment noise routing table"}

        block = "<memory-context>x</memory-context>"

        _, _, seen = self._run(monkeypatch, capsys, tmp_path, payload, block)

        assert seen == ["routing table"]

    @pytest.mark.unit
    def test_no_match_writes_nothing(self, tmp_path, monkeypatch, capsys):
        payload = {"prompt": "dispatch groups", "transformedPrompt": "dispatch groups"}

        exit_code, captured, _ = self._run(monkeypatch, capsys, tmp_path, payload, "")

        assert exit_code == 0
        assert captured.out == ""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "payload",
        [
            {"prompt": "dispatch groups"},
            {"prompt": "dispatch groups", "transformedPrompt": ""},
            {"prompt": "dispatch groups", "transformedPrompt": "   "},
            {"prompt": "dispatch groups", "transformedPrompt": 7},
            {"transformedPrompt": "dispatch groups"},
            {"prompt": None, "transformedPrompt": "dispatch groups"},
            ["not", "an", "object"],
            "not json",
            "",
        ],
    )
    def test_unusable_payload_writes_nothing(self, tmp_path, monkeypatch, capsys, payload):
        stdin = payload if isinstance(payload, str) else json.dumps(payload)

        exit_code, captured, seen = self._run(
            monkeypatch, capsys, tmp_path, stdin, "<memory-context>x</memory-context>"
        )

        assert exit_code == 0
        assert captured.out == ""
        assert seen == []

    @pytest.mark.unit
    def test_stop_word_prompt_skips_search(self, tmp_path, monkeypatch, capsys):
        payload = {"prompt": "is it the", "transformedPrompt": "is it the"}

        exit_code, captured, seen = self._run(monkeypatch, capsys, tmp_path, payload, "x")

        assert exit_code == 0
        assert captured.out == ""
        assert seen == []

    @pytest.mark.unit
    def test_unreadable_stdin_writes_nothing(self, monkeypatch, capsys):
        class _Broken(io.StringIO):
            def read(self, *_args):
                raise OSError("closed")

        monkeypatch.setattr("sys.stdin", _Broken())

        assert main_transformed() == 0
        assert capsys.readouterr().out == ""

    @pytest.mark.unit
    @pytest.mark.parametrize("name", ["COPILOT_AGENT_PROMPT", "GITHUB_COPILOT_API_TOKEN"])
    def test_cloud_agent_skips_recall(self, tmp_path, monkeypatch, capsys, name):
        """Cloud agent runs unattended on a checked-out branch (ADR-068, #4727)."""
        payload = {"prompt": "dispatch groups", "transformedPrompt": "dispatch groups"}

        exit_code, captured, seen = self._run(
            monkeypatch, capsys, tmp_path, payload, "<memory-context>x</memory-context>",
            cloud_env={name: "set"},
        )

        assert exit_code == 0
        assert captured.out == ""
        assert seen == []

    @pytest.mark.unit
    def test_empty_cloud_variable_does_not_skip(self, tmp_path, monkeypatch, capsys):
        payload = {"prompt": "dispatch groups", "transformedPrompt": "dispatch groups"}

        _, captured, seen = self._run(
            monkeypatch, capsys, tmp_path, payload, "<memory-context>x</memory-context>",
            cloud_env={"COPILOT_AGENT_PROMPT": ""},
        )

        assert seen == ["dispatch groups"]
        assert "modifiedTransformedPrompt" in captured.out
