"""Integration security tests for _markdownlint_verifier.py and push_guard_base.

These tests invoke the verifier as a real subprocess (no mocks).  They
prove that:
- The verifier fails closed (returns 1) for any .md files present.
- Hostile PATH, env vars, consumer packages cannot execute external tools.
- push_guard_base resolves git from system dirs, not PATH.
- push_guard_base never executes gh from inherited PATH.
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
# Fail-closed behavior
# ---------------------------------------------------------------------------

class TestFailClosedBehavior:
    """Verifier blocks all .md pushes (no complete engine shipped)."""

    def test_any_md_file_returns_1(self, tmp_path: Path) -> None:
        md = tmp_path / "clean.md"
        md.write_text("# Valid Heading\n\nParagraph.\n")
        result = _run_verifier([str(md)])
        assert result.returncode == 1
        assert "no integrity-pinned" in result.stderr

    def test_no_files_returns_0(self) -> None:
        result = _run_verifier([])
        assert result.returncode == 0

    def test_missing_separator_returns_2(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_VERIFIER), "--markdown-lint-only", "file.md"],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# Security: hostile PATH / environment cannot execute external tools
# ---------------------------------------------------------------------------

class TestMarkerWritingNpxInPath:
    def test_hostile_npx_not_invoked(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_NPX_RAN"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        npx_shim = bin_dir / "npx"
        npx_shim.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
        npx_shim.chmod(stat.S_IRWXU)

        md = tmp_path / "test.md"
        md.write_text("# Valid\n\nContent.\n")
        result = _run_verifier(
            [str(md)],
            env_overrides={"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
        )
        assert not marker.exists(), "Hostile npx was executed"
        assert result.returncode == 1  # fail-closed


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
        assert result.returncode == 1  # fail-closed


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
        assert result.returncode == 1  # fail-closed
        assert "evil" not in result.stderr.lower()


class TestOfflineExecution:
    def test_works_without_network_tools(self, tmp_path: Path) -> None:
        python_dir = Path(sys.executable).parent
        md = tmp_path / "test.md"
        md.write_text("# Offline\n\nWorks.\n")
        result = _run_verifier(
            [str(md)], env_overrides={"PATH": str(python_dir)},
        )
        assert result.returncode == 1  # fail-closed


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
        assert result.returncode == 1  # fail-closed


# ---------------------------------------------------------------------------
# Trusted git resolution
# ---------------------------------------------------------------------------

class TestTrustedGitResolution:
    """push_guard_base resolves git from system dirs, not inherited PATH."""

    def test_marker_writing_fake_git_in_allowed_path(
        self, tmp_path: Path,
    ) -> None:
        """Fake git in <repo>/bin/ (no denied segments) must not execute."""
        marker = tmp_path / "MARKER_FAKE_GIT_RAN"
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
            os.environ["PATH"] = f"{bin_dir}:{original_path}"
            importlib.reload(push_guard_base)
            if push_guard_base._TRUSTED_GIT is not None:
                rc, out = push_guard_base._run_git_diff(
                    ["git", "--version"], cwd=str(tmp_path),
                )
                assert not marker.exists(), "Fake git was executed"
                assert "FAKE" not in out
        finally:
            os.environ["PATH"] = original_path
            importlib.reload(push_guard_base)

    def test_system_git_not_from_path(self) -> None:
        """_TRUSTED_GIT must be under a known system directory."""
        hook_dir = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "PreToolUse"
        )
        sys.path.insert(0, hook_dir)
        import push_guard_base

        if push_guard_base._TRUSTED_GIT is None:
            pytest.skip("No system git available")
        git_path = push_guard_base._TRUSTED_GIT
        assert os.path.isabs(git_path)
        known = push_guard_base._SYSTEM_GIT_DIRS
        assert any(git_path.startswith(d) for d in known)

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
                assert var not in env
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
# Fake gh marker test (Defect 1: gh must never execute from consumer PATH)
# ---------------------------------------------------------------------------

class TestFakeGhNotExecuted:
    """push_guard_base must never invoke gh from inherited PATH."""

    def test_marker_writing_fake_gh_not_invoked(self, tmp_path: Path) -> None:
        """A malicious gh placed first in PATH must not execute."""
        marker = tmp_path / "MARKER_FAKE_GH_RAN"
        bin_dir = tmp_path / "hostile_bin"
        bin_dir.mkdir()
        fake_gh = bin_dir / "gh"
        fake_gh.write_text(
            textwrap.dedent(f"""\
                #!/bin/sh
                touch {marker}
                echo "FAKE GH EXECUTED" >&2
                exit 0
            """),
        )
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
            # Call _detect_default_base_ref which previously used gh
            push_guard_base._detect_default_base_ref(str(tmp_path))
            assert not marker.exists(), "Fake gh was executed by the guard"
        finally:
            os.environ["PATH"] = original_path
            importlib.reload(push_guard_base)


# ---------------------------------------------------------------------------
# Generated mirror parity
# ---------------------------------------------------------------------------

class TestGeneratedMirrorParity:
    def test_verifier_mirrors_match(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = root / ".claude" / "hooks" / "PreToolUse" / "_markdownlint_verifier.py"
        mirror = (
            root / "src" / "copilot-cli" / "hooks" / "PreToolUse"
            / "_markdownlint_verifier.py"
        )
        assert source.read_bytes() == mirror.read_bytes()

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
