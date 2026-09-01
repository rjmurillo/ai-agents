"""Tests for scripts/ci/spec_prepare_context.py."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.spec_prepare_context import _write_multiline_output, main, run


class TestWriteMultilineOutput:
    def test_uses_random_not_static_delimiter(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        _write_multiline_output("key", "value", str(out))
        content = out.read_text()
        assert "EOF_SPEC" not in content  # must NOT use the static original

    def test_delimiter_is_hex(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        _write_multiline_output("key", "some value", str(out))
        content = out.read_text()
        # Delimiter format: EOF_<32 hex chars>
        assert re.search(r"EOF_[0-9a-f]{32}", content)

    def test_value_is_in_output(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        _write_multiline_output("ctx", "my spec content", str(out))
        assert "my spec content" in out.read_text()

    def test_key_in_output(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        _write_multiline_output("spec_context", "val", str(out))
        assert "spec_context<<" in out.read_text()


class TestRun:
    def test_writes_spec_content_from_file(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec\nRequirement text")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": str(spec_file),
            "INCREMENTAL_SCOPE": "",
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            rc = run()
        assert rc == 0
        out = out_file.read_text()
        assert "Requirement text" in out

    def test_includes_incremental_scope_block(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("content")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": str(spec_file),
            "INCREMENTAL_SCOPE": "phase-1",
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            run()
        out = out_file.read_text()
        assert "phase-1" in out
        assert "Incremental Scope" in out

    def test_includes_nonexecutable_criteria_block(self, tmp_path: Path) -> None:
        """Issue #5366: a command-execution criterion must reach the reviewer as N/A."""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("content")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": str(spec_file),
            "INCREMENTAL_SCOPE": "",
            "PR_BODY": (
                "## Acceptance criteria\n\n"
                "- [x] `uv run python scripts/validation/pre_pr.py` passes\n"
            ),
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            rc = run()
        out = out_file.read_text()
        assert rc == 0
        assert "## Non-Executable Criteria Declaration" in out
        assert "- `uv run python scripts/validation/pre_pr.py` passes" in out
        assert "N/A" in out

    def test_omits_nonexecutable_block_for_verifiable_criteria(self, tmp_path: Path) -> None:
        """Negative control: an ordinary criterion must stay inside the gate."""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("content")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": str(spec_file),
            "INCREMENTAL_SCOPE": "",
            "PR_BODY": "## Acceptance criteria\n\n- [ ] The parser rejects an empty ref\n",
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            rc = run()
        assert rc == 0
        assert "Non-Executable Criteria" not in out_file.read_text()

    def test_omits_nonexecutable_block_when_pr_body_is_absent(self, tmp_path: Path) -> None:
        """workflow_dispatch has no pull_request payload, so PR_BODY is empty."""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("content")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": str(spec_file),
            "INCREMENTAL_SCOPE": "",
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env, clear=True):
            rc = run()
        assert rc == 0
        assert "Non-Executable Criteria" not in out_file.read_text()

    def test_emits_both_declarations_together(self, tmp_path: Path) -> None:
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("content")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": str(spec_file),
            "INCREMENTAL_SCOPE": "Phase 2 of #1799",
            "PR_BODY": "## Acceptance criteria\n\n- [x] `pytest` passes\n",
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            run()
        out = out_file.read_text()
        assert "## Incremental Scope Declaration" in out
        assert "## Non-Executable Criteria Declaration" in out

    def test_fallback_when_spec_file_missing(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": str(tmp_path / "nonexistent.md"),
            "INCREMENTAL_SCOPE": "",
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            rc = run()
        assert rc == 2
        assert not out_file.exists()

    def test_stdout_when_no_github_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        spec_file = Path(__file__)
        with patch.dict(
            os.environ,
            {"SPEC_FILE": str(spec_file), "INCREMENTAL_SCOPE": ""},
            clear=True,
        ):
            run()
        out = capsys.readouterr().out
        assert "spec_context=" in out

    def test_missing_spec_file_env_returns_config_error(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": "",
            "INCREMENTAL_SCOPE": "",
            "GITHUB_OUTPUT": str(out_file),
        }
        with patch.dict(os.environ, env):
            rc = run()
        assert rc == 2
        assert not out_file.exists()


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.spec_prepare_context.run", return_value=0):
            assert main() == 0
