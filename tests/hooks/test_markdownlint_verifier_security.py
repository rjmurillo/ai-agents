"""End-to-end security tests for vendored markdownlint verifier.

Non-mocked tests that invoke the real vendored markdownlint-cli2 engine
to verify correct behavior under clean, violation, and hostile conditions.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

# Resolve the hook directory and import the verifier
_HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(_HOOK_DIR))
import _markdownlint_verifier as verifier


@pytest.fixture(autouse=True)
def _patch_node_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow test environments where node is in ~/.nvm or similar."""
    import shutil

    node = shutil.which("node")
    if node:
        monkeypatch.setattr(verifier, "_TEST_NODE_OVERRIDE", Path(node))


class TestCleanMarkdown:
    """Clean Markdown must return 0 (success)."""

    def test_clean_heading_and_list(self, tmp_path: Path) -> None:
        md = tmp_path / "clean.md"
        md.write_text("# Title\n\nA paragraph.\n\n- item one\n- item two\n")
        assert verifier.main([str(md)]) == 0

    def test_empty_file_list(self) -> None:
        assert verifier.main([]) == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        assert verifier.main([str(tmp_path / "missing.md")]) == 0


class TestViolationDetection:
    """Violations must return 1."""

    def test_missing_top_heading(self, tmp_path: Path) -> None:
        md = tmp_path / "no_heading.md"
        md.write_text("Just a paragraph without heading.\n")
        assert verifier.main([str(md)]) == 1

    def test_bare_url(self, tmp_path: Path) -> None:
        md = tmp_path / "bare_url.md"
        md.write_text("# Title\n\nVisit https://example.com today.\n")
        assert verifier.main([str(md)]) == 1


class TestConsumerIsolation:
    """Consumer config and environment must not influence results."""

    def test_consumer_markdownlint_config_ignored(self, tmp_path: Path) -> None:
        """Consumer .markdownlint.yaml must not be picked up."""
        # Create consumer config that disables all rules
        (tmp_path / ".markdownlint.yaml").write_text("default: false\n")
        # File with violation (no top heading)
        md = tmp_path / "test.md"
        md.write_text("Just text without heading.\n")
        # Sterile temp dir prevents consumer config pickup
        assert verifier.main([str(md)]) == 1

    def test_node_options_scrubbed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """NODE_OPTIONS cannot influence execution."""
        monkeypatch.setenv("NODE_OPTIONS", "--require=/tmp/evil.js")
        md = tmp_path / "clean.md"
        md.write_text("# Title\n\nClean paragraph.\n")
        assert verifier.main([str(md)]) == 0


class TestFailClosed:
    """Infrastructure absence must fail closed (return 2)."""

    def test_missing_node(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(verifier, "_TEST_NODE_OVERRIDE", Path("/nonexistent/node"))
        monkeypatch.setattr(verifier, "_SAFE_NODE_DIRS", ("/nonexistent_dir",))
        md = tmp_path / "test.md"
        md.write_text("# Title\n\nText.\n")
        assert verifier.main([str(md)]) == 2

    def test_missing_vendor_entry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(verifier, "_ENTRY", Path("/nonexistent/entry.mjs"))
        md = tmp_path / "test.md"
        md.write_text("# Title\n\nText.\n")
        assert verifier.main([str(md)]) == 2


class TestIntegrity:
    """Integrity verification must block tampered entry points."""

    def test_tampered_integrity_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Create a fake integrity file with wrong hash
        fake_integrity = tmp_path / "INTEGRITY.sha256"
        entry_rel = str(verifier._ENTRY.relative_to(verifier._VENDOR))
        bad_hash = "0" * 64
        fake_integrity.write_text(f"{bad_hash}  {entry_rel}\n")
        monkeypatch.setattr(verifier, "_INTEGRITY", fake_integrity)
        md = tmp_path / "test.md"
        md.write_text("# Title\n\nText.\n")
        assert verifier.main([str(md)]) == 2


class TestHostileEnvironment:
    """Hostile PATH/npx must not be invoked."""

    def test_fake_npx_not_invoked(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_NPX_RAN"
        bin_dir = tmp_path / "hostile"
        bin_dir.mkdir()
        fake_npx = bin_dir / "npx"
        fake_npx.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
        fake_npx.chmod(stat.S_IRWXU)

        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = f"{bin_dir}:{old_path}"
            md = tmp_path / "clean.md"
            md.write_text("# Title\n\nClean text.\n")
            verifier.main([str(md)])
            assert not marker.exists(), "Hostile npx was invoked!"
        finally:
            os.environ["PATH"] = old_path

    def test_fake_gh_not_invoked(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_GH_RAN"
        bin_dir = tmp_path / "hostile"
        bin_dir.mkdir()
        fake_gh = bin_dir / "gh"
        fake_gh.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
        fake_gh.chmod(stat.S_IRWXU)

        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = f"{bin_dir}:{old_path}"
            md = tmp_path / "clean.md"
            md.write_text("# Title\n\nClean text.\n")
            verifier.main([str(md)])
            assert not marker.exists(), "Hostile gh was invoked!"
        finally:
            os.environ["PATH"] = old_path
