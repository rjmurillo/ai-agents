#!/usr/bin/env python3
"""Tests for SessionStart/invoke_context_loader.py.

Covers:
- No retrospective content is injected (Issues #7471, #7472)
- HANDOFF.md is never loaded (Issue #5168; the file is a frozen, stale
  artifact and injecting it wasted ~1,000 tokens/session for no benefit)
- Fail-open on missing files
- Consumer repo skip
- Audit trail creation
"""

from __future__ import annotations

import io
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "SessionStart"))

import invoke_context_loader


@pytest.fixture
def project_tree(tmp_path: Path) -> Path:
    """Create a minimal project directory tree.

    Includes a HANDOFF.md even though the hook must never load it: several
    tests use its presence as a regression guard against the hook starting
    to read it again.
    """
    agents = tmp_path / ".agents"
    agents.mkdir()
    toolkit = tmp_path / ".project-toolkit"
    (toolkit / "sessions").mkdir(parents=True)
    (toolkit / "retrospective").mkdir()

    # Present but must never be loaded (Issue #5168).
    (agents / "HANDOFF.md").write_text("# Handoff\n\nProject state dashboard.\n", encoding="utf-8")
    return tmp_path


class TestUtf8ProtocolOutput:
    """The SessionStart protocol must survive Windows console encodings."""

    PROTOCOL_TEXT = "## ⏳ 1 retro(s) need completion"

    def test_reconfigures_cp1252_stdout_to_utf8(self, monkeypatch) -> None:
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252")
        monkeypatch.setattr(sys, "stdout", stream)

        invoke_context_loader._emit_utf8(self.PROTOCOL_TEXT)

        assert raw.getvalue().decode("utf-8") == self.PROTOCOL_TEXT + "\n"

    def test_broken_pipe_is_not_retried_through_binary_buffer(self, monkeypatch) -> None:
        class BrokenPipeStream:
            def __init__(self) -> None:
                self.buffer = io.BytesIO()
                self.write_calls = 0

            def reconfigure(self, **_kwargs: object) -> None:
                return None

            def write(self, _text: str) -> int:
                self.write_calls += 1
                raise BrokenPipeError("consumer closed")

            def flush(self) -> None:
                raise AssertionError("flush must not follow a failed write")

        stream = BrokenPipeStream()
        monkeypatch.setattr(sys, "stdout", stream)

        with pytest.raises(BrokenPipeError, match="consumer closed"):
            invoke_context_loader._emit_utf8(self.PROTOCOL_TEXT)

        assert stream.write_calls == 1
        assert stream.buffer.getvalue() == b""

    @pytest.mark.parametrize(
        "error_type",
        [io.UnsupportedOperation, TypeError, ValueError],
    )
    def test_uses_binary_buffer_when_stdout_cannot_reconfigure(
        self, monkeypatch, error_type
    ) -> None:
        class NonReconfigurableStream:
            def __init__(self) -> None:
                self.buffer = io.BytesIO()

            def reconfigure(self, **_kwargs: object) -> None:
                raise error_type("fixed encoding")

        stream = NonReconfigurableStream()
        monkeypatch.setattr(sys, "stdout", stream)

        invoke_context_loader._emit_utf8(self.PROTOCOL_TEXT)

        assert stream.buffer.getvalue() == (self.PROTOCOL_TEXT + "\n").encode("utf-8")

    def test_text_only_fallback_when_no_reconfigure_or_buffer(self, monkeypatch) -> None:
        """A stream lacking BOTH reconfigure and buffer must still get the
        exact protocol text plus one trailing LF via the plain str write
        path (the third and last fallback branch in _emit_utf8; #14)."""

        class TextOnlyStream:
            def __init__(self) -> None:
                self.written: list[str] = []
                self.flushed = False

            def write(self, data: str) -> int:
                self.written.append(data)
                return len(data)

            def flush(self) -> None:
                self.flushed = True

        stream = TextOnlyStream()
        assert not hasattr(stream, "reconfigure")
        assert not hasattr(stream, "buffer")
        monkeypatch.setattr(sys, "stdout", stream)

        invoke_context_loader._emit_utf8(self.PROTOCOL_TEXT)

        assert stream.written == [self.PROTOCOL_TEXT + "\n"]
        assert stream.flushed is True


class TestMain:
    """Test main() function."""

    def test_skip_consumer_repo(self, capsys: pytest.CaptureFixture) -> None:
        with patch.object(invoke_context_loader, "skip_if_consumer_repo", return_value=True):
            with pytest.raises(SystemExit) as exc_info:
                invoke_context_loader.main()
            assert exc_info.value.code == 0

    def test_ignores_retro_and_handoff(
        self, project_tree: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Neither a fresh retrospective nor HANDOFF.md reaches session context."""
        today = datetime.now(tz=UTC).date().isoformat()
        retro = project_tree / ".project-toolkit" / "retrospective" / f"{today}-retro.md"
        retro.write_text("# Retro\n\nLearnings here.", encoding="utf-8")

        with (
            patch.object(invoke_context_loader, "skip_if_consumer_repo", return_value=False),
            patch.object(
                invoke_context_loader, "get_project_directory", return_value=str(project_tree)
            ),
        ):
            invoke_context_loader.main()

        captured = capsys.readouterr()
        assert "Learnings here." not in captured.out
        # Regression guard for Issue #5168: HANDOFF.md exists in project_tree
        # but must never be read or injected.
        assert "HANDOFF.md" not in captured.out
        assert captured.out == invoke_context_loader.RETRO_LOOKUP_GUIDE + "\n"

    def test_ignores_handoff_when_no_retro_present(
        self, project_tree: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """With only a (stale, unloaded) HANDOFF.md and no pending skeleton,
        the hook prints only the static lookup guide."""
        with (
            patch.object(invoke_context_loader, "skip_if_consumer_repo", return_value=False),
            patch.object(
                invoke_context_loader, "get_project_directory", return_value=str(project_tree)
            ),
        ):
            invoke_context_loader.main()

        captured = capsys.readouterr()
        assert captured.out == invoke_context_loader.RETRO_LOOKUP_GUIDE + "\n"
        assert "HANDOFF.md" not in captured.out

    def test_handles_missing_handoff(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        agents = tmp_path / ".agents"
        agents.mkdir()

        with (
            patch.object(invoke_context_loader, "skip_if_consumer_repo", return_value=False),
            patch.object(
                invoke_context_loader, "get_project_directory", return_value=str(tmp_path)
            ),
        ):
            invoke_context_loader.main()

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_writes_audit_log(self, project_tree: Path) -> None:
        with (
            patch.object(invoke_context_loader, "skip_if_consumer_repo", return_value=False),
            patch.object(
                invoke_context_loader, "get_project_directory", return_value=str(project_tree)
            ),
        ):
            invoke_context_loader.main()

        audit_dir = project_tree / ".project-toolkit" / ".hook-state"
        assert audit_dir.exists()
        log_files = list(audit_dir.glob("context-loader-*.log"))
        assert len(log_files) >= 1


class TestFailOpen:
    """Test that the script wrapper fails open on all errors."""

    def test_exception_in_main_exits_zero(self) -> None:
        """The ``__main__`` wrapper must catch internal errors and exit 0.

        Calling ``main()`` directly only proves the function raises; it
        cannot prove the wrapper around it is fail-open. We exercise the
        wrapper with a patched ``main`` to verify the contract Claude Code
        depends on.
        """
        from tests.hook_test_helpers import run_main_wrapper

        def raising_main() -> None:
            raise RuntimeError("boom")

        code, _stdout, stderr = run_main_wrapper(invoke_context_loader, raising_main)
        assert code == 0
        assert "boom" in stderr
