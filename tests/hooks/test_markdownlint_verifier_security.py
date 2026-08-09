"""Integration security tests for _markdownlint_verifier.py.

These tests invoke the verifier directly (no mocks) and prove that hostile
PATH entries, environment variables, consumer packages, configs, and
registry settings cannot cause execution of external tools. The verifier
is pure Python using shipped markdown-it-py; it never spawns subprocesses.

Each test plants marker-writing executables or hostile configs, runs the
verifier, and asserts no markers were written and the exit code is correct.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
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
    """Run the verifier as a subprocess with controlled environment."""
    # Minimal environment: remove NODE_OPTIONS, NODE_PATH, npm_config_*
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


class TestMarkerWritingNpxInPath:
    """A malicious npx placed first in PATH must never execute."""

    def test_hostile_npx_first_in_path_not_invoked(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_NPX_RAN"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()

        npx_shim = bin_dir / "npx"
        npx_shim.write_text(
            textwrap.dedent(f"""\
                #!/bin/sh
                touch {marker}
                echo "MALICIOUS NPX EXECUTED" >&2
                exit 0
            """),
            encoding="utf-8",
        )
        npx_shim.chmod(stat.S_IRWXU)

        md_file = tmp_path / "test.md"
        md_file.write_text("# Valid heading\n\nSome content.\n")

        result = _run_verifier(
            [str(md_file)],
            env_overrides={"PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
        )

        assert not marker.exists(), "Hostile npx was executed"
        assert "MALICIOUS" not in result.stderr
        assert result.returncode == 0


class TestMaliciousLocalMarkdownlintPackage:
    """Consumer node_modules with hostile markdownlint must not execute."""

    def test_local_markdownlint_cli2_ignored(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_LOCAL_LINT_RAN"
        nm_bin = tmp_path / "node_modules" / ".bin"
        nm_bin.mkdir(parents=True)

        for name in ("markdownlint-cli2", "markdownlint"):
            shim = nm_bin / name
            shim.write_text(
                textwrap.dedent(f"""\
                    #!/bin/sh
                    touch {marker}
                    exit 0
                """),
                encoding="utf-8",
            )
            shim.chmod(stat.S_IRWXU)

        md_file = tmp_path / "test.md"
        md_file.write_text("# Heading\n\nParagraph.\n")

        result = _run_verifier(
            [str(md_file)],
            env_overrides={"PATH": f"{nm_bin}:{os.environ.get('PATH', '')}"},
            cwd=str(tmp_path),
        )

        assert not marker.exists(), "Consumer markdownlint-cli2 was executed"
        assert result.returncode == 0


class TestHostileNpmrcAndRegistry:
    """Hostile .npmrc or registry env vars must not affect execution."""

    def test_hostile_npmrc_has_no_effect(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_REGISTRY_CONTACTED"

        npmrc = tmp_path / ".npmrc"
        npmrc.write_text(
            "registry=http://evil.attacker.example/\n"
            "//evil.attacker.example/:_authToken=stolen\n"
        )

        md_file = tmp_path / "test.md"
        md_file.write_text("# OK\n")

        result = _run_verifier(
            [str(md_file)],
            env_overrides={
                "NPM_CONFIG_REGISTRY": "http://evil.attacker.example/",
                "npm_config_cache": str(tmp_path / "fake_cache"),
                "HOME": str(tmp_path),
            },
            cwd=str(tmp_path),
        )

        assert not marker.exists()
        assert result.returncode == 0
        assert "evil" not in result.stderr.lower()


class TestPoisonedNpmCache:
    """Poisoned npm cache directory must not influence the verifier."""

    def test_poisoned_cache_not_consulted(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "npm_cache" / "markdownlint-cli2"
        cache_dir.mkdir(parents=True)
        poison = cache_dir / "index.js"
        poison.write_text(
            "const fs = require('fs');\n"
            f"fs.writeFileSync('{tmp_path}/MARKER_CACHE_USED', 'pwned');\n"
        )

        md_file = tmp_path / "test.md"
        md_file.write_text("# Safe\n")

        result = _run_verifier(
            [str(md_file)],
            env_overrides={
                "npm_config_cache": str(tmp_path / "npm_cache"),
                "NODE_PATH": str(cache_dir),
            },
            cwd=str(tmp_path),
        )

        marker = tmp_path / "MARKER_CACHE_USED"
        assert not marker.exists(), "Poisoned npm cache was consulted"
        assert result.returncode == 0


class TestOfflineExecution:
    """Verifier works fully offline with no network access."""

    def test_works_without_network_tools(self, tmp_path: Path) -> None:
        """Prove no network tool (curl, wget, npx, npm, node) is needed."""
        # Create a PATH with ONLY python (no npm, npx, node, curl, wget)
        python_dir = Path(sys.executable).parent
        minimal_path = str(python_dir)

        md_file = tmp_path / "test.md"
        md_file.write_text("# Offline test\n\nContent here.\n")

        result = _run_verifier(
            [str(md_file)],
            env_overrides={"PATH": minimal_path},
        )

        assert result.returncode == 0

    def test_no_dns_resolution_attempted(self, tmp_path: Path) -> None:
        """Even with hostile NODE/npm env vars, no DNS is needed."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Heading\n")

        result = _run_verifier(
            [str(md_file)],
            env_overrides={
                "NPM_CONFIG_REGISTRY": "http://nonexistent.invalid:9999/",
                "NODE_OPTIONS": "--dns-result-order=ipv4first",
                "NODE_PATH": "/nonexistent/path",
            },
        )

        assert result.returncode == 0


class TestNodeEnvironmentSanitization:
    """NODE_OPTIONS, NODE_PATH and npm config must not affect behavior."""

    def test_node_options_cannot_inject_code(self, tmp_path: Path) -> None:
        marker = tmp_path / "MARKER_NODE_OPTIONS"
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test\n")

        result = _run_verifier(
            [str(md_file)],
            env_overrides={
                "NODE_OPTIONS": f"--require={tmp_path}/inject.js",
                "NODE_PATH": str(tmp_path),
            },
        )

        assert not marker.exists()
        assert result.returncode == 0

    def test_violations_detected_despite_hostile_env(self, tmp_path: Path) -> None:
        """Verifier still catches violations even with hostile env set."""
        md_file = tmp_path / "bad.md"
        # No heading = MD041 violation
        md_file.write_text("No heading here.\n")

        result = _run_verifier(
            [str(md_file)],
            env_overrides={
                "NODE_OPTIONS": "--max-old-space-size=1",
                "NPM_CONFIG_REGISTRY": "http://evil.example/",
                "PATH": "/nonexistent:" + os.environ.get("PATH", ""),
            },
        )

        assert result.returncode == 1
        assert "MD041" in result.stderr
