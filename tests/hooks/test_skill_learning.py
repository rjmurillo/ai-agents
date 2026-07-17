#!/usr/bin/env python3
"""Tests for the invoke_skill_learning Stop hook.

Covers: main entry point, skill detection, learning extraction,
non-blocking exits, required-loader failure, path validation, consumer repo skip.
"""

from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "Stop")
sys.path.insert(0, HOOK_DIR)

import invoke_skill_learning  # noqa: E402


def test_atomic_write_text_uses_replace(tmp_path, monkeypatch):
    target = tmp_path / "memory.md"
    calls = []
    original_replace = invoke_skill_learning.os.replace

    def recording_replace(src, dst):
        calls.append((src, dst))
        original_replace(src, dst)

    monkeypatch.setattr(invoke_skill_learning.os, "replace", recording_replace)

    invoke_skill_learning._atomic_write_text(target, "updated")

    assert len(calls) == 1
    temp_path, replaced_path = calls[0]
    assert replaced_path == target
    assert temp_path.parent == target.parent
    assert temp_path.name.startswith(f".{target.name}.")
    assert temp_path.name.endswith(".tmp")
    assert target.read_text(encoding="utf-8") == "updated"


# ---------------------------------------------------------------------------
# Unit tests for _validate_path_string
# ---------------------------------------------------------------------------


class TestValidatePathString:
    def test_accepts_normal_path(self):
        assert invoke_skill_learning._validate_path_string("/tmp/project") == "/tmp/project"

    def test_rejects_null_byte(self):
        assert invoke_skill_learning._validate_path_string("/tmp/\x00evil") is None

    def test_rejects_newline(self):
        assert invoke_skill_learning._validate_path_string("/tmp/\nevil") is None

    def test_rejects_tab(self):
        assert invoke_skill_learning._validate_path_string("/tmp/\tevil") is None

    def test_rejects_traversal(self):
        assert invoke_skill_learning._validate_path_string("../../etc/passwd") is None

    def test_rejects_non_string(self):
        assert invoke_skill_learning._validate_path_string(123) is None


# ---------------------------------------------------------------------------
# Unit tests for _is_relative_to
# ---------------------------------------------------------------------------


class TestIsRelativeTo:
    def test_child_is_relative(self, tmp_path):
        child = tmp_path / "sub" / "file.txt"
        assert invoke_skill_learning._is_relative_to(child, tmp_path)

    def test_unrelated_is_not_relative(self, tmp_path):
        other = Path("/completely/different/path")
        assert not invoke_skill_learning._is_relative_to(other, tmp_path)


# ---------------------------------------------------------------------------
# Unit tests for get_conversation_messages
# ---------------------------------------------------------------------------


class TestGetConversationMessages:
    def test_extracts_messages(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = invoke_skill_learning.get_conversation_messages({"messages": msgs})
        assert result == msgs

    def test_returns_empty_when_missing(self):
        result = invoke_skill_learning.get_conversation_messages({})
        assert result == []


# ---------------------------------------------------------------------------
# Unit tests for detect_skill_usage
# ---------------------------------------------------------------------------


class TestDetectSkillUsage:
    def test_detects_skill_path_reference(self):
        messages = [
            {"role": "user", "content": "Check .claude/skills/reflect/SKILL.md"},
            {"role": "assistant", "content": "Using .claude/skills/reflect/SKILL.md"},
        ]
        result = invoke_skill_learning.detect_skill_usage(messages)
        assert "reflect" in result

    def test_returns_empty_for_no_skills(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = invoke_skill_learning.detect_skill_usage(messages)
        assert result == {}


# ---------------------------------------------------------------------------
# Unit tests for check_skill_context
# ---------------------------------------------------------------------------


class TestCheckSkillContext:
    def test_finds_skill_name(self):
        assert invoke_skill_learning.check_skill_context(
            "Used the reflect skill", "reflect"
        )

    def test_finds_skill_path(self):
        assert invoke_skill_learning.check_skill_context(
            "See .claude/skills/reflect/SKILL.md", "reflect"
        )

    def test_returns_false_when_absent(self):
        assert not invoke_skill_learning.check_skill_context(
            "Nothing relevant here", "reflect"
        )


# ---------------------------------------------------------------------------
# Unit tests for write_learning_notification
# ---------------------------------------------------------------------------


class TestPrivacyDefaultsM7T6:
    """M7-T6: privacy + reliability defaults for the LLM fallback path."""

    def test_use_llm_fallback_defaults_to_false(self, monkeypatch):
        """Module-level USE_LLM_FALLBACK MUST default to False (opt-in).

        The pre-fix default sent session transcripts to Anthropic on every
        Stop hook fire unless the operator opted out. Now operators MUST
        explicitly set SKILL_LEARNING_USE_LLM=true to opt in.
        """
        monkeypatch.delenv("SKILL_LEARNING_USE_LLM", raising=False)
        # Reload the module under fresh env
        import importlib
        importlib.reload(invoke_skill_learning)
        assert invoke_skill_learning.USE_LLM_FALLBACK is False

    def test_use_llm_fallback_true_when_explicit(self, monkeypatch):
        monkeypatch.setenv("SKILL_LEARNING_USE_LLM", "true")
        import importlib
        importlib.reload(invoke_skill_learning)
        assert invoke_skill_learning.USE_LLM_FALLBACK is True

    def test_get_api_key_no_dotenv_fallback(self, tmp_path, monkeypatch):
        """M7-T6: get_api_key() MUST NOT scan .env files anymore."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("SKILL_LEARNING_API_KEY", raising=False)
        # Drop a .env in cwd that the old code would have read
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-DO-NOT-LEAK\n")
        monkeypatch.chdir(tmp_path)
        # Reload to pick up cleared env vars
        import importlib
        importlib.reload(invoke_skill_learning)
        assert invoke_skill_learning.get_api_key() is None

    def test_get_api_key_prefers_skill_learning_specific_var(self, monkeypatch):
        """SKILL_LEARNING_API_KEY takes precedence over ANTHROPIC_API_KEY."""
        monkeypatch.setenv("SKILL_LEARNING_API_KEY", "sk-skill")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-shared")
        import importlib
        importlib.reload(invoke_skill_learning)
        assert invoke_skill_learning.get_api_key() == "sk-skill"

    def test_llm_timeout_default_is_bounded(self, monkeypatch):
        """LLM_TIMEOUT_SEC MUST be a finite positive float (M7-T6)."""
        monkeypatch.delenv("SKILL_LEARNING_LLM_TIMEOUT_SEC", raising=False)
        import importlib
        importlib.reload(invoke_skill_learning)
        assert invoke_skill_learning.LLM_TIMEOUT_SEC > 0
        assert invoke_skill_learning.LLM_TIMEOUT_SEC < 60  # sanity ceiling


class TestSafeBaseDirM7T5:
    """The runtime worktree comes from Git at cwd, never the installed hook."""

    @staticmethod
    def _git_result(root: Path, returncode: int = 0) -> MagicMock:
        result = MagicMock()
        result.returncode = returncode
        result.stdout = str(root) if returncode == 0 else ""
        result.stderr = "git failure" if returncode else ""
        return result

    def test_accepts_exact_project_dir_corroboration(self, monkeypatch, tmp_path):
        worktree = tmp_path / "worktree"
        child = worktree / "subdir"
        child.mkdir(parents=True)
        monkeypatch.chdir(child)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(worktree))
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            lambda *_args, **_kwargs: self._git_result(worktree),
        )

        result = invoke_skill_learning._detect_safe_base_dir()

        assert result == worktree.resolve()

    def test_uses_cwd_git_worktree_when_project_dir_unset(self, monkeypatch, tmp_path):
        worktree = tmp_path / "worktree"
        child = worktree / "subdir"
        child.mkdir(parents=True)
        monkeypatch.chdir(child)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            lambda *_args, **_kwargs: self._git_result(worktree),
        )

        result = invoke_skill_learning._detect_safe_base_dir()

        assert result == worktree.resolve()

    def test_rejects_mismatched_project_dir(self, monkeypatch, tmp_path, caplog):
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        arbitrary = tmp_path / "arbitrary"
        arbitrary.mkdir()
        monkeypatch.chdir(worktree)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(arbitrary))
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            lambda *_args, **_kwargs: self._git_result(worktree),
        )

        result = invoke_skill_learning._detect_safe_base_dir()

        assert result == invoke_skill_learning._FAILED_PROJECT_ROOT
        assert any(
            getattr(record, "code", "") == "E_CWE22_PROJECT_DIR_MISMATCH"
            for record in caplog.records
        )

    def test_rejects_malformed_project_dir(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path) + "\nevil")
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            lambda *_args, **_kwargs: self._git_result(tmp_path),
        )

        result = invoke_skill_learning._detect_safe_base_dir()

        assert result == invoke_skill_learning._FAILED_PROJECT_ROOT

    def test_rejects_git_failure_without_falling_back(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            lambda *_args, **_kwargs: self._git_result(tmp_path, returncode=128),
        )

        result = invoke_skill_learning._detect_safe_base_dir()

        assert result == invoke_skill_learning._FAILED_PROJECT_ROOT

    def test_rejects_arbitrary_git_root_that_does_not_contain_cwd(
        self, monkeypatch, tmp_path
    ):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        arbitrary = tmp_path / "arbitrary"
        arbitrary.mkdir()
        monkeypatch.chdir(cwd)
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            lambda *_args, **_kwargs: self._git_result(arbitrary),
        )

        result = invoke_skill_learning._detect_safe_base_dir()

        assert result == invoke_skill_learning._FAILED_PROJECT_ROOT

    def test_returns_none_when_git_invocation_raises_oserror(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            MagicMock(side_effect=OSError("git unavailable")),
        )

        assert invoke_skill_learning._git_worktree_root_from_cwd() is None

    def test_returns_none_when_git_invocation_times_out(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)
        timeout = invoke_skill_learning.subprocess.TimeoutExpired("git", 5)
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            MagicMock(side_effect=timeout),
        )

        assert invoke_skill_learning._git_worktree_root_from_cwd() is None

    def test_returns_none_for_malformed_git_root(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = self._git_result(tmp_path)
        result.stdout = f"{tmp_path}\nmalformed"
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            lambda *_args, **_kwargs: result,
        )

        assert invoke_skill_learning._git_worktree_root_from_cwd() is None

    def test_returns_none_for_non_absolute_git_root(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = self._git_result(tmp_path)
        result.stdout = "relative/worktree"
        monkeypatch.setattr(
            invoke_skill_learning.subprocess,
            "run",
            lambda *_args, **_kwargs: result,
        )

        assert invoke_skill_learning._git_worktree_root_from_cwd() is None


class TestRequiredSkillPatternLoader:
    def test_missing_loader_raises_companion_error_and_does_not_mark_loaded(
        self, monkeypatch, tmp_path
    ):
        """A missing companion module is a config error, not a generic defect."""
        monkeypatch.setattr(invoke_skill_learning, "_patterns_loaded", False)

        with patch.dict(sys.modules, {"skill_pattern_loader": None}):
            with pytest.raises(invoke_skill_learning.SkillPatternCompanionError):
                invoke_skill_learning._ensure_patterns_loaded(tmp_path)

        assert invoke_skill_learning._patterns_loaded is False

    def test_broken_loader_raises_base_error_and_does_not_mark_loaded(
        self, monkeypatch, tmp_path
    ):
        """An unexpected non-OSError defect is the generic internal-defect class."""
        monkeypatch.setattr(invoke_skill_learning, "_patterns_loaded", False)

        with patch(
            "skill_pattern_loader.load_skill_patterns",
            side_effect=RuntimeError("loader broke"),
        ):
            with pytest.raises(invoke_skill_learning.SkillPatternLoadError) as excinfo:
                invoke_skill_learning._ensure_patterns_loaded(tmp_path)

        assert not isinstance(
            excinfo.value,
            (
                invoke_skill_learning.SkillPatternCompanionError,
                invoke_skill_learning.SkillPatternExternalError,
            ),
        )
        assert invoke_skill_learning._patterns_loaded is False

    def test_external_io_failure_raises_external_error_and_does_not_mark_loaded(
        self, monkeypatch, tmp_path
    ):
        """An OSError from the companion is an external failure, not a defect."""
        monkeypatch.setattr(invoke_skill_learning, "_patterns_loaded", False)

        with patch(
            "skill_pattern_loader.load_skill_patterns",
            side_effect=OSError("disk full"),
        ):
            with pytest.raises(invoke_skill_learning.SkillPatternExternalError):
                invoke_skill_learning._ensure_patterns_loaded(tmp_path)

        assert invoke_skill_learning._patterns_loaded is False

    def test_import_syntax_error_raises_load_error_and_does_not_mark_loaded(
        self, monkeypatch, tmp_path
    ):
        """A companion with a SyntaxError is a logic defect (ADR-035 exit 1).

        Regression test: previously the import statement was wrapped only in
        ``except ImportError``, so a ``SyntaxError`` raised while importing a
        corrupted ``skill_pattern_loader.py`` fell through uncaught to
        ``main()``'s generic ``except Exception: return 0``, reporting the
        optional learning step as a success instead of surfacing the defect.
        """
        monkeypatch.setattr(invoke_skill_learning, "_patterns_loaded", False)
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "skill_pattern_loader":
                raise SyntaxError("invalid syntax")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(invoke_skill_learning.SkillPatternLoadError) as excinfo:
                invoke_skill_learning._ensure_patterns_loaded(tmp_path)

        assert not isinstance(
            excinfo.value,
            (
                invoke_skill_learning.SkillPatternCompanionError,
                invoke_skill_learning.SkillPatternExternalError,
            ),
        )
        assert invoke_skill_learning._patterns_loaded is False

    def test_import_oserror_raises_external_error_and_does_not_mark_loaded(
        self, monkeypatch, tmp_path
    ):
        """An import-time OSError is an external failure (ADR-035 exit 3).

        Covers a local filesystem ``PermissionError`` (a subclass of
        ``OSError``) raised while reading the companion module file during
        import, e.g. restrictive file permissions or an antivirus lock.
        Regression test: previously only ``ImportError`` was caught around
        the import statement, so this fell through to ``main()``'s generic
        ``except Exception: return 0`` instead of ADR-035 exit 3. This is
        deliberately NOT mapped to ADR-035 exit 4 ("Auth Error"): exit 4 is
        reserved for service auth/credential failures (token/session
        expiry), not local filesystem permission errors.
        """
        monkeypatch.setattr(invoke_skill_learning, "_patterns_loaded", False)
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "skill_pattern_loader":
                raise PermissionError("denied")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(invoke_skill_learning.SkillPatternExternalError):
                invoke_skill_learning._ensure_patterns_loaded(tmp_path)

        assert invoke_skill_learning._patterns_loaded is False


class TestWriteLearningNotification:
    def test_outputs_notification(self, capsys):
        invoke_skill_learning.write_learning_notification("reflect", 1, 2, 0)
        captured = capsys.readouterr()
        assert "reflect" in captured.out
        assert "1 HIGH" in captured.out

    def test_no_output_when_zero(self, capsys):
        invoke_skill_learning.write_learning_notification("reflect", 0, 0, 0)
        captured = capsys.readouterr()
        assert captured.out == ""


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=True)
    def test_exits_0_when_consumer_repo(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("{}")
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_tty(self, _mock, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_empty_input(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("")
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_invalid_json(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin("not json")
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_exits_0_with_no_messages(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(json.dumps({"cwd": "/tmp/test", "messages": []}))
        result = invoke_skill_learning.main()
        assert result == 0

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    @patch("invoke_skill_learning.detect_skill_usage", return_value={})
    @patch("invoke_skill_learning.get_safe_project_path")
    def test_exits_0_when_no_skills_detected(
        self,
        mock_safe_path,
        _detect,
        _skip,
        mock_stdin: Callable[[str], None],
        tmp_path,
    ):
        mock_safe_path.return_value = tmp_path
        mock_stdin(
            json.dumps(
                {
                    "cwd": str(tmp_path),
                    "messages": [{"role": "user", "content": "hello"}],
                }
            )
        )
        result = invoke_skill_learning.main()
        assert result == 0

    def test_returns_one_when_required_loader_fails(
        self,
        mock_stdin: Callable[[str], None],
        tmp_path,
        capsys,
    ):
        mock_stdin(json.dumps({"cwd": str(tmp_path), "messages": []}))
        error = invoke_skill_learning.SkillPatternLoadError("loader broke")

        with patch.object(
            invoke_skill_learning, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_skill_learning, "get_project_directory", return_value=str(tmp_path)
        ), patch.object(
            invoke_skill_learning, "get_safe_project_path", return_value=tmp_path
        ), patch.object(
            invoke_skill_learning, "_ensure_patterns_loaded", side_effect=error
        ):
            result = invoke_skill_learning.main()

        captured = capsys.readouterr()

        assert result == 1
        assert captured.out == ""
        assert "loader broke" in captured.err

    def test_returns_two_when_companion_missing(
        self,
        mock_stdin: Callable[[str], None],
        tmp_path,
        capsys,
    ):
        """A missing runtime companion is a Config Error (ADR-035 exit 2)."""
        mock_stdin(json.dumps({"cwd": str(tmp_path), "messages": []}))
        error = invoke_skill_learning.SkillPatternCompanionError("companion missing")

        with patch.object(
            invoke_skill_learning, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_skill_learning, "get_project_directory", return_value=str(tmp_path)
        ), patch.object(
            invoke_skill_learning, "get_safe_project_path", return_value=tmp_path
        ), patch.object(
            invoke_skill_learning, "_ensure_patterns_loaded", side_effect=error
        ):
            result = invoke_skill_learning.main()

        captured = capsys.readouterr()

        assert result == 2
        assert captured.out == ""
        assert "companion missing" in captured.err

    def test_returns_three_when_external_io_fails(
        self,
        mock_stdin: Callable[[str], None],
        tmp_path,
        capsys,
    ):
        """An external I/O failure is an External Error (ADR-035 exit 3)."""
        mock_stdin(json.dumps({"cwd": str(tmp_path), "messages": []}))
        error = invoke_skill_learning.SkillPatternExternalError("disk full")

        with patch.object(
            invoke_skill_learning, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_skill_learning, "get_project_directory", return_value=str(tmp_path)
        ), patch.object(
            invoke_skill_learning, "get_safe_project_path", return_value=tmp_path
        ), patch.object(
            invoke_skill_learning, "_ensure_patterns_loaded", side_effect=error
        ):
            result = invoke_skill_learning.main()

        captured = capsys.readouterr()

        assert result == 3
        assert captured.out == ""
        assert "disk full" in captured.err

    @patch("invoke_skill_learning.skip_if_consumer_repo", return_value=False)
    def test_always_exits_0_on_exception(
        self, _mock, mock_stdin: Callable[[str], None]
    ):
        """Stop hooks must never block (always exit 0)."""
        mock_stdin(json.dumps({"cwd": None, "messages": "not a list"}))
        result = invoke_skill_learning.main()
        assert result == 0
