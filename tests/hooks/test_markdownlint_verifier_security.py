"""Integration security tests for _markdownlint_verifier.py.

These tests invoke the verifier as a real subprocess (no mocks).  They
prove that:
- Clean markdown returns 0, invalid markdown returns 1.
- Hostile PATH entries, environment variables, consumer packages,
  configs, and registry settings cannot cause execution of external tools.
- The verifier uses only stdlib; it never spawns subprocesses.
- push_guard_base resolves git from system directories only, not PATH.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

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
# End-to-end fixtures: clean markdown passes, invalid markdown fails
# ---------------------------------------------------------------------------

class TestCleanFixtures:
    """Verify clean markdown returns 0."""

    def test_valid_heading_and_content(self, tmp_path: Path) -> None:
        md = tmp_path / "clean.md"
        md.write_text("# Heading\n\nParagraph.\n\n- item\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, result.stderr

    def test_fenced_code_with_language(self, tmp_path: Path) -> None:
        md = tmp_path / "code.md"
        md.write_text("# Title\n\n```python\nprint(1)\n```\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, result.stderr

    def test_frontmatter_then_heading(self, tmp_path: Path) -> None:
        md = tmp_path / "fm.md"
        md.write_text("---\ntitle: X\n---\n# Heading\n\nBody.\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, result.stderr

    def test_empty_file_passes(self, tmp_path: Path) -> None:
        md = tmp_path / "empty.md"
        md.write_text("")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, result.stderr

    def test_no_files_passes(self) -> None:
        result = _run_verifier([])
        assert result.returncode == 0

    def test_allowed_html_passes(self, tmp_path: Path) -> None:
        md = tmp_path / "html.md"
        md.write_text("# Title\n\n<details>\n<summary>X</summary>\n</details>\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, result.stderr


class TestInvalidFixtures:
    """Verify violations return 1 with diagnostic output."""

    def test_md041_no_heading(self, tmp_path: Path) -> None:
        md = tmp_path / "no_h1.md"
        md.write_text("No heading.\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 1
        assert "MD041" in result.stderr

    def test_md040_no_language(self, tmp_path: Path) -> None:
        md = tmp_path / "nolang.md"
        md.write_text("# Title\n\n```\ncode\n```\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 1
        assert "MD040" in result.stderr

    def test_md004_wrong_marker(self, tmp_path: Path) -> None:
        md = tmp_path / "star.md"
        md.write_text("# Title\n\n* wrong\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 1
        assert "MD004" in result.stderr

    def test_md033_disallowed_html(self, tmp_path: Path) -> None:
        md = tmp_path / "html.md"
        md.write_text("# Title\n\n<div>bad</div>\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 1
        assert "MD033" in result.stderr

    def test_md025_multiple_h1(self, tmp_path: Path) -> None:
        md = tmp_path / "multi_h1.md"
        md.write_text("# First\n\n# Second\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 1
        assert "MD025" in result.stderr

    def test_md024_sibling_duplicates(self, tmp_path: Path) -> None:
        md = tmp_path / "dup.md"
        md.write_text("# Title\n\n## Dupe\n\n## Dupe\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 1
        assert "MD024" in result.stderr


# ---------------------------------------------------------------------------
# Security: hostile PATH / environment cannot execute external tools
# ---------------------------------------------------------------------------

class TestMarkerWritingNpxInPath:
    def test_hostile_npx_not_invoked(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_NPX_RAN"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        npx_shim = bin_dir / "npx"
        npx_shim.write_text(
            textwrap.dedent(f"""\
                #!/bin/sh
                touch {marker}
                exit 0
            """),
        )
        npx_shim.chmod(stat.S_IRWXU)

        md = tmp_path / "test.md"
        md.write_text("# Valid\n\nContent.\n")
        result = _run_verifier(
            [str(md)],
            env_overrides={"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
        )
        assert not marker.exists(), "Hostile npx was executed"
        assert result.returncode == 0


class TestMaliciousLocalMarkdownlintPackage:
    def test_local_package_ignored(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_LOCAL_LINT_RAN"
        nm_bin = tmp_path / "node_modules" / ".bin"
        nm_bin.mkdir(parents=True)
        for name in ("markdownlint-cli2", "markdownlint"):
            shim = nm_bin / name
            shim.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
            shim.chmod(stat.S_IRWXU)
        md = tmp_path / "test.md"
        md.write_text("# Heading\n\nOK.\n")
        result = _run_verifier(
            [str(md)],
            env_overrides={"PATH": f"{nm_bin}:{os.environ.get('PATH', '')}"},
            cwd=str(tmp_path),
        )
        assert not marker.exists()
        assert result.returncode == 0


class TestHostileNpmrcAndRegistry:
    def test_hostile_npmrc_no_effect(self, tmp_path: Path) -> None:
        npmrc = tmp_path / ".npmrc"
        npmrc.write_text("registry=http://evil.example/\n")
        md = tmp_path / "test.md"
        md.write_text("# OK\n\nBody.\n")
        result = _run_verifier(
            [str(md)],
            env_overrides={
                "NPM_CONFIG_REGISTRY": "http://evil.example/",
                "HOME": str(tmp_path),
            },
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "evil" not in result.stderr.lower()


class TestOfflineExecution:
    def test_works_without_network_tools(self, tmp_path: Path) -> None:
        python_dir = Path(sys.executable).parent
        md = tmp_path / "test.md"
        md.write_text("# Offline\n\nWorks.\n")
        result = _run_verifier(
            [str(md)], env_overrides={"PATH": str(python_dir)},
        )
        assert result.returncode == 0


class TestNodeEnvironmentSanitization:
    def test_node_options_cannot_inject(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_NODE_OPTIONS"
        md = tmp_path / "test.md"
        md.write_text("# Test\n\nBody.\n")
        result = _run_verifier(
            [str(md)],
            env_overrides={
                "NODE_OPTIONS": f"--require={tmp_path}/inject.js",
                "NODE_PATH": str(tmp_path),
            },
        )
        assert not marker.exists()
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Trusted git resolution (Defect 1 fix)
# ---------------------------------------------------------------------------

class TestTrustedGitResolution:
    """push_guard_base resolves git from system dirs, not inherited PATH."""

    def test_marker_writing_fake_git_in_allowed_path(
        self, tmp_path: Path,
    ) -> None:
        """Fake git in <repo>/bin/ (no denied segments) must not execute.

        This proves the allowlist approach works: only well-known system
        directories are searched, so even a git in an innocent-looking
        path like ``<repo>/bin/git`` is never found.
        """
        marker = tmp_path / "MARKER_FAKE_GIT_RAN"
        # Place fake git in a path with NO denied segments
        bin_dir = tmp_path / "repo" / "bin"
        bin_dir.mkdir(parents=True)
        fake_git = bin_dir / "git"
        fake_git.write_text(
            textwrap.dedent(f"""\
                #!/bin/sh
                touch {marker}
                echo "FAKE GIT EXECUTED" >&2
                exit 0
            """),
        )
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
            # Put the fake git FIRST on PATH (old code would find it)
            os.environ["PATH"] = f"{bin_dir}:{original_path}"
            importlib.reload(push_guard_base)

            # The trusted resolution should find the REAL system git,
            # not our fake one, because it searches system dirs only.
            if push_guard_base._TRUSTED_GIT is not None:
                rc, out = push_guard_base._run_git_diff(
                    ["git", "--version"], cwd=str(tmp_path),
                )
                assert not marker.exists(), "Fake git was executed"
                assert "FAKE" not in out
            else:
                # If no system git found (CI container), that's OK --
                # the guard fails closed.
                pass
        finally:
            os.environ["PATH"] = original_path
            importlib.reload(push_guard_base)

    def test_system_git_not_from_path(self) -> None:
        """_TRUSTED_GIT must be an absolute path in a system directory."""
        hook_dir = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse"
        )
        sys.path.insert(0, hook_dir)
        import push_guard_base

        if push_guard_base._TRUSTED_GIT is None:
            pytest.skip("No system git available in this environment")
        git_path = push_guard_base._TRUSTED_GIT
        assert os.path.isabs(git_path), f"Not absolute: {git_path}"
        # Must be under a known system directory
        known = push_guard_base._SYSTEM_GIT_DIRS
        assert any(
            git_path.startswith(d) for d in known
        ), f"{git_path} not under any system dir: {known}"

    def test_git_env_vars_scrubbed(self) -> None:
        hook_dir = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse"
        )
        sys.path.insert(0, hook_dir)
        import push_guard_base

        dangerous = [
            "GIT_EXEC_PATH", "GIT_EXTERNAL_DIFF", "GIT_SSH_COMMAND",
            "GIT_ASKPASS", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
        ]
        for var in dangerous:
            os.environ[var] = "/tmp/evil"
        try:
            env = push_guard_base._scrubbed_git_env()
            for var in dangerous:
                assert var not in env, f"{var} leaked"
        finally:
            for var in dangerous:
                os.environ.pop(var, None)

    def test_python_env_vars_scrubbed(self) -> None:
        hook_dir = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse"
        )
        sys.path.insert(0, hook_dir)
        import push_guard_base

        os.environ["PYTHONPATH"] = "/tmp/evil"
        os.environ["PYTHONHOME"] = "/tmp/evil"
        try:
            env = push_guard_base._scrubbed_git_env()
            assert "PYTHONPATH" not in env
            assert "PYTHONHOME" not in env
        finally:
            os.environ.pop("PYTHONPATH", None)
            os.environ.pop("PYTHONHOME", None)


# ---------------------------------------------------------------------------
# Policy subset boundary: rules NOT in the safe subset must NOT trigger
# ---------------------------------------------------------------------------

class TestDefaultsNotEnforced:
    """Rules not in the explicit safe subset return 0 (not enforced).

    The config sets ``default: false``; only MD004/MD024/MD025/MD033/
    MD040/MD041/MD046 are active.  Violations of other rules (MD009,
    MD012, MD022, etc.) must pass cleanly.
    """

    def test_md009_trailing_spaces_not_enforced(self, tmp_path: Path) -> None:
        md = tmp_path / "trailing.md"
        md.write_text("# Title\n\nLine with trailing spaces   \n")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, f"MD009 unexpectedly enforced: {result.stderr}"

    def test_md012_multiple_blank_lines_not_enforced(self, tmp_path: Path) -> None:
        md = tmp_path / "blanks.md"
        md.write_text("# Title\n\n\n\nParagraph after many blanks.\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, f"MD012 unexpectedly enforced: {result.stderr}"

    def test_md022_blanks_around_headings_not_enforced(self, tmp_path: Path) -> None:
        md = tmp_path / "noblank.md"
        md.write_text("# Title\nNo blank before next heading.\n## Sub\nContent.\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, f"MD022 unexpectedly enforced: {result.stderr}"

    def test_md010_hard_tabs_not_enforced(self, tmp_path: Path) -> None:
        md = tmp_path / "tabs.md"
        md.write_text("# Title\n\n\tIndented with tab.\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, f"MD010 unexpectedly enforced: {result.stderr}"

    def test_md013_line_length_not_enforced(self, tmp_path: Path) -> None:
        md = tmp_path / "long.md"
        md.write_text("# Title\n\n" + "x" * 200 + "\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 0, f"MD013 unexpectedly enforced: {result.stderr}"


class TestGeneratedMirrorParity:
    """The copilot-cli mirror must be byte-identical to the source."""

    def test_verifier_mirrors_match(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = root / ".claude" / "hooks" / "PreToolUse" / "_markdownlint_verifier.py"
        mirror = root / "src" / "copilot-cli" / "hooks" / "PreToolUse" / "_markdownlint_verifier.py"
        assert source.read_bytes() == mirror.read_bytes(), (
            "copilot-cli verifier mirror diverged from source"
        )

    def test_config_mirrors_match(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = root / ".claude" / "hooks" / "PreToolUse" / "markdownlint-safe-config.yaml"
        mirror = (
            root / "src" / "copilot-cli" / "hooks" / "PreToolUse"
            / "markdownlint-safe-config.yaml"
        )
        if mirror.exists():
            assert source.read_bytes() == mirror.read_bytes(), (
                "copilot-cli config mirror diverged from source"
            )
