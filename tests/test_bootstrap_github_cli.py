"""Tests for scripts/bootstrap-vm.sh's GitHub CLI authentication setup.

Split out of test_bootstrap.py (which crossed the 500-line taste-lint
threshold once this class was added) so the two files stay under the
limit without changing what either suite covers.

Covers ``configure_github_cli`` token precedence, command ordering, and
the no-token warning path, run against a fake ``gh`` on PATH.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VM_BOOTSTRAP_PATH = REPO_ROOT / "scripts" / "bootstrap-vm.sh"


class TestConfigureGithubCli:
    """Run the shipped ``configure_github_cli`` against a fake ``gh``.

    The prior version of these tests asserted that certain substrings
    appeared in the function body, which passes whether or not the
    credential flow actually works: it cannot tell whether GH_TOKEN
    precedence is honored, which commands actually run, or in what order.
    These extract the function verbatim (per .claude/rules/
    canonical-source-mirror.md) and execute it, so the assertions are
    about behavior.
    """

    @staticmethod
    def _extract() -> str:
        text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")
        start = text.index("configure_github_cli() {")
        end = text.index("\n}\n", start) + len("\n}\n")
        return text[start:end]

    @staticmethod
    def _fake_gh(tmp_path: Path) -> Path:
        """A ``gh`` that logs each invocation and the visible token env."""
        log = tmp_path / "gh.log"
        script = tmp_path / "gh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            f'log="{log}"\n'
            'printf "argv:%s\\n" "$*" >>"$log"\n'
            'printf "env:GH_TOKEN=%s\\n" "${GH_TOKEN-<unset>}" >>"$log"\n'
            "exit 0\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return log

    def _run(
        self, tmp_path: Path, env: dict[str, str]
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        log = self._fake_gh(tmp_path)
        script = f"set -uo pipefail\n{self._extract()}\nconfigure_github_cli\n"
        base = {
            k: v for k, v in os.environ.items() if k not in {"GH_TOKEN", "GITHUB_TOKEN"}
        }
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env={**base, "PATH": f"{tmp_path}:{os.environ['PATH']}", **env},
            check=False,
        )
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return result, lines

    def test_persists_the_token_and_wires_git_transport(self, tmp_path: Path) -> None:
        result, lines = self._run(tmp_path, {"GH_TOKEN": "tok-gh"})

        assert result.returncode == 0, result.stderr
        argv = [line.removeprefix("argv:") for line in lines if line.startswith("argv:")]
        assert argv == ["auth status --active --hostname github.com", "api meta", "auth setup-git"]
        assert "✓ GitHub CLI authenticated" in result.stdout

    def test_github_token_fills_in_when_gh_token_is_unset(self, tmp_path: Path) -> None:
        """GitHub-hosted environments expose GITHUB_TOKEN; it must reach gh."""
        result, lines = self._run(tmp_path, {"GITHUB_TOKEN": "tok-github"})

        assert result.returncode == 0, result.stderr
        assert "env:GH_TOKEN=tok-github" in lines

    def test_explicit_gh_token_wins_over_the_actions_alias(self, tmp_path: Path) -> None:
        _result, lines = self._run(
            tmp_path, {"GH_TOKEN": "tok-gh", "GITHUB_TOKEN": "tok-github"}
        )

        assert "env:GH_TOKEN=tok-gh" in lines

    def test_missing_token_warns_and_skips_every_gh_call(self, tmp_path: Path) -> None:
        result, lines = self._run(tmp_path, {})

        assert result.returncode == 0
        assert lines == []
        assert "GitHub CLI is installed but unauthenticated; set GH_TOKEN" in result.stderr
