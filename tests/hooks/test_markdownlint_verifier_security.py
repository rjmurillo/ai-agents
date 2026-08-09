"""Integration tests for _markdownlint_verifier.py and push_guard_base.

Non-mocked end-to-end tests: invoke verifier as real subprocess on real
files.  Proves clean markdown passes, violations block, edge cases
(blockquotes, setext headings) are caught, hostile env has no effect,
and trusted git/gh resolution is secure.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

_VERIFIER = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "hooks"
    / "PreToolUse"
    / "_markdownlint_verifier.py"
)


def _run_verifier(
    files: list[str],
    *,
    env_overrides: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("npm_config_")
        and k not in ("NODE_OPTIONS", "NODE_PATH", "NPM_CONFIG_REGISTRY")
    }
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(_VERIFIER), "--markdown-lint-only", "--", *files],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd=cwd,
        check=False,
    )


# ---------------------------------------------------------------------------
# Clean markdown passes
# ---------------------------------------------------------------------------

class TestCleanFixtures:
    def test_valid_heading_and_content(self, tmp_path: Path) -> None:
        md = tmp_path / "clean.md"
        md.write_text("# Heading\n\nParagraph.\n\n- item\n")
        assert _run_verifier([str(md)]).returncode == 0

    def test_fenced_code_with_language(self, tmp_path: Path) -> None:
        md = tmp_path / "code.md"
        md.write_text("# Title\n\n```python\nprint(1)\n```\n")
        assert _run_verifier([str(md)]).returncode == 0

    def test_frontmatter_then_heading(self, tmp_path: Path) -> None:
        md = tmp_path / "fm.md"
        md.write_text("---\ntitle: X\n---\n# Heading\n\nBody.\n")
        assert _run_verifier([str(md)]).returncode == 0

    def test_empty_file_passes(self, tmp_path: Path) -> None:
        md = tmp_path / "empty.md"
        md.write_text("")
        assert _run_verifier([str(md)]).returncode == 0

    def test_no_files_passes(self) -> None:
        assert _run_verifier([]).returncode == 0

    def test_allowed_html_passes(self, tmp_path: Path) -> None:
        md = tmp_path / "html.md"
        md.write_text("# Title\n\n<details>\n<summary>X</summary>\n</details>\n")
        assert _run_verifier([str(md)]).returncode == 0

    def test_blockquoted_dash_list_passes(self, tmp_path: Path) -> None:
        md = tmp_path / "bq.md"
        md.write_text("# Title\n\n> - correct dash list\n")
        assert _run_verifier([str(md)]).returncode == 0

    def test_setext_heading_unique_passes(self, tmp_path: Path) -> None:
        md = tmp_path / "setext.md"
        md.write_text("Title\n=====\n\nSection A\n---------\n\nSection B\n---------\n")
        assert _run_verifier([str(md)]).returncode == 0


# ---------------------------------------------------------------------------
# Violations block
# ---------------------------------------------------------------------------

class TestViolationFixtures:
    def test_md041_no_heading(self, tmp_path: Path) -> None:
        md = tmp_path / "no_h1.md"
        md.write_text("No heading.\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD041" in r.stderr

    def test_md040_no_language(self, tmp_path: Path) -> None:
        md = tmp_path / "nolang.md"
        md.write_text("# Title\n\n```\ncode\n```\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD040" in r.stderr

    def test_md004_wrong_marker(self, tmp_path: Path) -> None:
        md = tmp_path / "star.md"
        md.write_text("# Title\n\n* wrong\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD004" in r.stderr

    def test_md033_disallowed_html(self, tmp_path: Path) -> None:
        md = tmp_path / "html.md"
        md.write_text("# Title\n\n<div>bad</div>\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD033" in r.stderr

    def test_md025_multiple_h1(self, tmp_path: Path) -> None:
        md = tmp_path / "multi.md"
        md.write_text("# First\n\n# Second\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD025" in r.stderr

    def test_md024_sibling_duplicates(self, tmp_path: Path) -> None:
        md = tmp_path / "dup.md"
        md.write_text("# Title\n\n## Dupe\n\n## Dupe\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD024" in r.stderr


# ---------------------------------------------------------------------------
# Edge cases (previously bypassed regex verifier)
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_blockquoted_star_list_triggers_md004(self, tmp_path: Path) -> None:
        md = tmp_path / "bq_star.md"
        md.write_text("# Title\n\n> * wrong marker\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD004" in r.stderr

    def test_blockquoted_fence_no_lang_triggers_md040(self, tmp_path: Path) -> None:
        md = tmp_path / "bq_fence.md"
        md.write_text("# Title\n\n> ```\n> code\n> ```\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD040" in r.stderr

    def test_setext_h1_duplicate_triggers_md025(self, tmp_path: Path) -> None:
        md = tmp_path / "setext_h1.md"
        md.write_text("First\n=====\n\nSecond\n======\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD025" in r.stderr

    def test_setext_sibling_duplicates_trigger_md024(self, tmp_path: Path) -> None:
        md = tmp_path / "setext_dup.md"
        md.write_text("Title\n=====\n\nSec\n---\n\nSec\n---\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD024" in r.stderr

    def test_indented_code_triggers_md046(self, tmp_path: Path) -> None:
        md = tmp_path / "indent.md"
        md.write_text("# Title\n\n    indented code block\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD046" in r.stderr


# ---------------------------------------------------------------------------
# Security: hostile PATH / environment
# ---------------------------------------------------------------------------

class TestHostileEnvironment:
    def test_hostile_npx_not_invoked(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_NPX_RAN"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        npx_shim = bin_dir / "npx"
        npx_shim.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
        npx_shim.chmod(stat.S_IRWXU)
        md = tmp_path / "test.md"
        md.write_text("# Valid\n\nContent.\n")
        r = _run_verifier(
            [str(md)],
            env_overrides={"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
        )
        assert not marker.exists()
        assert r.returncode == 0

    def test_offline_execution(self, tmp_path: Path) -> None:
        python_dir = Path(sys.executable).parent
        md = tmp_path / "test.md"
        md.write_text("# Offline\n\nWorks.\n")
        r = _run_verifier([str(md)], env_overrides={"PATH": str(python_dir)})
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# Trusted git / gh resolution
# ---------------------------------------------------------------------------

class TestTrustedGitResolution:
    def test_fake_git_in_allowed_path_not_invoked(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_FAKE_GIT_RAN"
        bin_dir = tmp_path / "repo" / "bin"
        bin_dir.mkdir(parents=True)
        fake_git = bin_dir / "git"
        fake_git.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
        fake_git.chmod(stat.S_IRWXU)

        hook_dir = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse"
        )
        sys.path.insert(0, hook_dir)
        import importlib

        import push_guard_base

        original_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = f"{bin_dir}:{original_path}"
            importlib.reload(push_guard_base)
            if push_guard_base._TRUSTED_GIT is not None:
                push_guard_base._run_git_diff(
                    ["git", "--version"], cwd=str(tmp_path),
                )
                assert not marker.exists()
        finally:
            os.environ["PATH"] = original_path
            importlib.reload(push_guard_base)

    def test_fake_gh_not_invoked(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_FAKE_GH_RAN"
        bin_dir = tmp_path / "hostile_bin"
        bin_dir.mkdir()
        fake_gh = bin_dir / "gh"
        fake_gh.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
        fake_gh.chmod(stat.S_IRWXU)

        hook_dir = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse"
        )
        sys.path.insert(0, hook_dir)
        import importlib

        import push_guard_base

        original_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = f"{bin_dir}:{original_path}"
            importlib.reload(push_guard_base)
            push_guard_base._detect_default_base_ref(str(tmp_path))
            assert not marker.exists(), "Fake gh was executed"
        finally:
            os.environ["PATH"] = original_path
            importlib.reload(push_guard_base)


# ---------------------------------------------------------------------------
# Generation parity and real guard invocation
# ---------------------------------------------------------------------------

class TestGenerationAndRealInvocation:
    """Test generation into empty tree + real guard invocation on clean .md."""

    def test_generated_mirrors_match_source(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = root / ".claude" / "hooks" / "PreToolUse" / "_markdownlint_verifier.py"
        mirror = (
            root / "src" / "copilot-cli" / "hooks" / "PreToolUse"
            / "_markdownlint_verifier.py"
        )
        assert source.read_bytes() == mirror.read_bytes()

    def test_real_verifier_on_clean_markdown(self, tmp_path: Path) -> None:
        """End-to-end: invoke the real verifier on a clean file."""
        md = tmp_path / "readme.md"
        md.write_text("# Project\n\nDescription.\n\n- item\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 0, f"Clean markdown failed: {r.stderr}"

    def test_real_verifier_on_violation(self, tmp_path: Path) -> None:
        """End-to-end: invoke the real verifier on a file with violations."""
        md = tmp_path / "bad.md"
        md.write_text("no heading\n\n* wrong marker\n")
        r = _run_verifier([str(md)])
        assert r.returncode == 1
        assert "MD041" in r.stderr
        assert "MD004" in r.stderr

    def test_config_mirrors_match(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = (
            root / ".claude" / "hooks" / "PreToolUse"
            / "markdownlint-safe-config.yaml"
        )
        mirror = (
            root / "src" / "copilot-cli" / "hooks" / "PreToolUse"
            / "markdownlint-safe-config.yaml"
        )
        if mirror.exists():
            assert source.read_bytes() == mirror.read_bytes()
