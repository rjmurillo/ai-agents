"""Tests for scripts/bootstrap-vm.sh's GitHub CLI auth and origin-remote setup.

Split out of test_bootstrap.py (which crossed the 500-line taste-lint
threshold once these classes were added) so the two files stay under the
limit without changing what either suite covers.

Covers:
- ``configure_github_cli`` token precedence, command ordering, and failure
  handling, run against a fake ``gh`` on PATH.
- ``restore_origin_remote`` behavior against real temporary Git repositories.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VM_BOOTSTRAP_PATH = REPO_ROOT / "scripts" / "bootstrap-vm.sh"


class TestConfigureGithubCli:
    """Run the shipped ``configure_github_cli`` against a fake ``gh``.

    The prior version of these tests asserted that certain substrings appeared
    in the function body, which passes whether or not the credential flow
    works: it cannot tell login-before-unset from unset-before-login, cannot
    see which token reaches stdin, and cannot notice a dropped failure check.
    These extract the function verbatim (per .claude/rules/
    canonical-source-mirror.md) and execute it, so the assertions are about
    behavior.
    """

    @staticmethod
    def _extract() -> str:
        text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")
        start = text.index("configure_github_cli() {")
        end = text.index("\n}\n", start) + len("\n}\n")
        return text[start:end]

    @staticmethod
    def _fake_gh(tmp_path: Path, fail_on: str = "") -> Path:
        """A ``gh`` that logs each invocation, its stdin, and the token env."""
        log = tmp_path / "gh.log"
        script = tmp_path / "gh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            f'log="{log}"\n'
            'printf "argv:%s\\n" "$*" >>"$log"\n'
            'printf "env:GH_TOKEN=%s GITHUB_TOKEN=%s\\n" '
            '"${GH_TOKEN-<unset>}" "${GITHUB_TOKEN-<unset>}" >>"$log"\n'
            'if [[ "$1 $2" == "auth login" ]]; then\n'
            '  printf "stdin:%s\\n" "$(cat)" >>"$log"\n'
            "fi\n"
            f'if [[ -n "{fail_on}" && "$1 $2" == "{fail_on}" ]]; then exit 1; fi\n'
            "exit 0\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return log

    def _run(
        self, tmp_path: Path, env: dict[str, str], fail_on: str = ""
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        log = self._fake_gh(tmp_path, fail_on)
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
        result, lines = self._run(tmp_path, {"GITHUB_TOKEN": "tok-github"})

        assert result.returncode == 0, result.stderr
        argv = [line.removeprefix("argv:") for line in lines if line.startswith("argv:")]
        assert argv == [
            "auth login --with-token",
            "auth status",
            "api user --jq .login",
            "auth setup-git",
        ]
        assert "stdin:tok-github" in lines
        assert "✓ GitHub CLI authenticated" in result.stdout

    def test_login_sees_no_environment_token(self, tmp_path: Path) -> None:
        """gh prefers an env token over stored credentials, so the unset must
        happen before login or the stored credential never gets written."""
        _result, lines = self._run(
            tmp_path, {"GH_TOKEN": "tok-gh", "GITHUB_TOKEN": "tok-github"}
        )

        assert lines[1] == "env:GH_TOKEN=<unset> GITHUB_TOKEN=<unset>"

    def test_explicit_gh_token_wins_over_the_actions_alias(
        self, tmp_path: Path
    ) -> None:
        _result, lines = self._run(
            tmp_path, {"GH_TOKEN": "tok-gh", "GITHUB_TOKEN": "tok-github"}
        )

        assert "stdin:tok-gh" in lines
        assert "stdin:tok-github" not in lines

    def test_missing_token_warns_and_skips_every_gh_call(
        self, tmp_path: Path
    ) -> None:
        result, lines = self._run(tmp_path, {})

        assert result.returncode == 0
        assert lines == []
        assert "set GITHUB_TOKEN in the Codex environment" in result.stderr

    @pytest.mark.parametrize(
        ("fail_on", "expected_calls"),
        [
            ("auth login", 1),
            ("auth status", 2),
            ("api user", 3),
            ("auth setup-git", 4),
        ],
    )
    def test_a_failed_step_stops_the_sequence(
        self, tmp_path: Path, fail_on: str, expected_calls: int
    ) -> None:
        """Each step is checked, so a failure aborts the rest. The function
        still returns 0: bootstrap continues without GitHub auth by design
        (a hard exit here left the whole VM unprovisioned)."""
        result, lines = self._run(tmp_path, {"GITHUB_TOKEN": "tok"}, fail_on=fail_on)

        assert result.returncode == 0, result.stderr
        assert sum(1 for line in lines if line.startswith("argv:")) == expected_calls
        assert "WARNING" in result.stderr
        assert "✓ GitHub CLI authenticated" not in result.stdout

    def test_setup_git_failure_does_not_blame_the_token(self, tmp_path: Path) -> None:
        """`auth status` and `api user` already passed, so reporting missing
        authentication would send operators to rotate a valid credential."""
        result, _lines = self._run(
            tmp_path, {"GITHUB_TOKEN": "tok"}, fail_on="auth setup-git"
        )

        assert "authentication succeeded" in result.stderr
        assert "the token itself is valid" in result.stderr


class TestRestoreOriginRemote:
    """Run the shipped ``restore_origin_remote`` against real repositories."""

    @staticmethod
    def _extract() -> str:
        text = VM_BOOTSTRAP_PATH.read_text(encoding="utf-8")
        start = text.index("restore_origin_remote() {")
        end = text.index("\n}\n", start) + len("\n}\n")
        return text[start:end]

    def _run(self, repo: Path) -> subprocess.CompletedProcess[str]:
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        script = f"set -uo pipefail\n{self._extract()}\nrestore_origin_remote\n"
        return subprocess.run(
            ["bash", "-c", script],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    @staticmethod
    def _origin(repo: Path) -> str:
        return subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()

    def test_adds_the_canonical_remote_when_origin_is_absent(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "no-origin"
        result = self._run(repo)

        assert result.returncode == 0, result.stderr
        assert self._origin(repo) == "https://github.com/rjmurillo/ai-agents.git"

    def test_leaves_an_existing_fork_remote_alone(self, tmp_path: Path) -> None:
        """Bootstrapping a fork must not repoint later fetches and pushes at
        upstream."""
        repo = tmp_path / "fork"
        fork_url = "https://github.com/someone-else/ai-agents.git"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", fork_url], cwd=repo, check=True
        )

        script = f"set -uo pipefail\n{self._extract()}\nrestore_origin_remote\n"
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert self._origin(repo) == fork_url
