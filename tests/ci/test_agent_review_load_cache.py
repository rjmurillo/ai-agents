"""Tests for scripts/ci/agent_review_load_cache.py."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.agent_review_load_cache import _write_multiline_output, main, run


class TestWriteMultilineOutput:
    def test_uses_random_not_static_delimiter(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        _write_multiline_output("key", "value", str(out))
        content = out.read_text()
        # Must not use a static string like "EOF_CACHED_FINDINGS"
        assert re.search(r"EOF_CACHED_FINDINGS_[0-9a-f]{32}", content)

    def test_value_present_in_output(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        _write_multiline_output("findings", "my findings text", str(out))
        assert "my findings text" in out.read_text()


class TestRun:
    def test_missing_agent_returns_1(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("AGENT", None)
            assert run() == 1

    def test_invalid_agent_name_returns_1(self) -> None:
        with patch.dict(os.environ, {"AGENT": "../../etc/passwd"}):
            assert run() == 1

    def test_valid_agent_reads_cache(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "ai-review-cache" / "security"
        cache_dir.mkdir(parents=True)
        (cache_dir / "verdict.txt").write_text("PASS")
        (cache_dir / "findings.txt").write_text("All good")
        out_file = tmp_path / "out.txt"
        env = {"AGENT": "security", "GITHUB_OUTPUT": str(out_file)}
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                rc = run()
        finally:
            os.chdir(original_cwd)
        assert rc == 0
        content = out_file.read_text()
        assert "verdict=PASS" in content
        assert "retry_count=0" in content

    def test_infra_failure_defaults_false_when_missing(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "ai-review-cache" / "qa"
        cache_dir.mkdir(parents=True)
        (cache_dir / "verdict.txt").write_text("PASS")
        (cache_dir / "findings.txt").write_text("OK")
        # No infrastructure-failure.txt
        out_file = tmp_path / "out.txt"
        env = {"AGENT": "qa", "GITHUB_OUTPUT": str(out_file)}
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env):
                run()
        finally:
            os.chdir(original_cwd)
        content = out_file.read_text()
        assert "infrastructure_failure=false" in content

    def test_stdout_fallback_when_no_github_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cache_dir = tmp_path / "ai-review-cache" / "analyst"
        cache_dir.mkdir(parents=True)
        (cache_dir / "verdict.txt").write_text("PASS")
        (cache_dir / "findings.txt").write_text("findings here")
        env = {"AGENT": "analyst"}
        env.pop("GITHUB_OUTPUT", None)
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch.dict(os.environ, env, clear=False):
                os.environ.pop("GITHUB_OUTPUT", None)
                run()
        finally:
            os.chdir(original_cwd)
        out = capsys.readouterr().out
        assert "verdict=PASS" in out


class TestMain:
    def test_main_delegates(self) -> None:
        with patch("scripts.ci.agent_review_load_cache.run", return_value=0):
            assert main() == 0
