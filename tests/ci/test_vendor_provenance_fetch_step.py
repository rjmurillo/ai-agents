"""Behavior tests for the vendor provenance workflow's candidate fetch step.

Runs the real step script under bash against a stub git (issue 5593).
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "vendor-provenance.yml"
_TOKEN = "ghs_fake0token0for0tests"
_EXPECTED_BASIC = base64.b64encode(f"x-access-token:{_TOKEN}".encode()).decode()
_FETCH_STEP = "Fetch candidate commit via git"
_MATERIALIZE_STEP = "Materialize candidate tree"
_STUB_GIT = """\
import json
import os
import sys

record = {
    "argv": sys.argv[1:],
    "env": {k: v for k, v in os.environ.items() if k.startswith(("GIT_", "GH_"))},
}
with open(os.environ["STUB_GIT_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(record) + "\\n")
sys.exit(int(os.environ.get("STUB_GIT_EXIT", "0")))
"""


def _workflow_step(name: str) -> dict[str, Any]:
    wf = WORKFLOW.read_text(encoding="utf-8")
    steps = yaml.safe_load(wf)["jobs"]["provenance"]["steps"]
    matches = [step for step in steps if step.get("name") == name]
    assert len(matches) == 1, f"expected exactly one {name!r} step"
    return matches[0]


@pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("bash") is None,
    reason="runs the step under bash with GNU base64, as ubuntu runners do",
)
class TestFetchStepBehavior:
    """Run the real fetch step script against a stub git.

    Static string checks cannot catch a wrong header scheme: issue 5593 was a
    well-formed header that git smart-HTTP rejects. These tests execute the
    step's ``run`` body under ``bash -e`` (the Actions default shell) and
    assert what git actually receives.
    """

    TOKEN = _TOKEN
    SHA = "0123456789abcdef0123456789abcdef01234567"

    def _run_step(
        self, tmp_path: Path, token: str, git_exit: int = 0
    ) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "git"
        stub.write_text(f"#!{sys.executable}\n{_STUB_GIT}", encoding="utf-8")
        stub.chmod(0o755)
        script = tmp_path / "step.sh"
        script.write_text(_workflow_step(_FETCH_STEP)["run"], encoding="utf-8")
        log = tmp_path / "git.log"
        env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "PR_SHA": self.SHA,
            "GH_FETCH_TOKEN": token,
            "TOKEN_SOURCE": "VENDOR_PROVENANCE_PAT",
            "STUB_GIT_LOG": str(log),
            "STUB_GIT_EXIT": str(git_exit),
        }
        result = subprocess.run(
            ["bash", "-e", str(script)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
        calls = [
            json.loads(line) for line in (log.read_text().splitlines() if log.exists() else [])
        ]
        return result, calls

    def test_fetch_sends_basic_x_access_token_header(self, tmp_path: Path) -> None:
        """Git gets the Basic x-access-token header, not the REST token form."""
        result, calls = self._run_step(tmp_path, self.TOKEN)

        assert result.returncode == 0, result.stdout + result.stderr
        assert len(calls) == 1
        call = calls[0]
        assert call["argv"] == ["fetch", "--depth=1", "origin", self.SHA]
        env = call["env"]
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["GIT_CONFIG_COUNT"] == "1"
        assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
        assert env["GIT_CONFIG_VALUE_0"] == (f"AUTHORIZATION: basic {_EXPECTED_BASIC}")

    def test_header_is_not_the_rest_api_token_form(self, tmp_path: Path) -> None:
        """Discriminating half: the scheme git rejected must not come back."""
        _, calls = self._run_step(tmp_path, self.TOKEN)

        value = calls[0]["env"]["GIT_CONFIG_VALUE_0"]
        assert not value.lower().startswith("authorization: token")
        assert not value.lower().startswith("authorization: bearer")
        assert self.TOKEN not in value, "raw token must be base64 wrapped"

    def test_token_stays_out_of_argv_and_logs(self, tmp_path: Path) -> None:
        """The token never reaches argv or stdout; the Basic value is masked."""
        result, calls = self._run_step(tmp_path, self.TOKEN)

        assert all(self.TOKEN not in arg for arg in calls[0]["argv"])
        assert self.TOKEN not in result.stdout + result.stderr
        assert f"::add-mask::{_EXPECTED_BASIC}" in result.stdout
        assert "fetch token source: VENDOR_PROVENANCE_PAT" in result.stdout

    def test_fetch_failure_fails_step_with_named_source(self, tmp_path: Path) -> None:
        """A refused fetch fails the step and names the token source."""
        result, calls = self._run_step(tmp_path, self.TOKEN, git_exit=128)

        assert result.returncode == 1
        assert len(calls) == 1
        assert "::error::git fetch failed using VENDOR_PROVENANCE_PAT" in result.stdout
        assert self.TOKEN not in result.stdout + result.stderr

    def test_empty_token_fails_before_git_runs(self, tmp_path: Path) -> None:
        """An empty token fails with an error and never calls git."""
        result, calls = self._run_step(tmp_path, "")

        assert result.returncode == 1
        assert calls == []
        assert "::error::GH_FETCH_TOKEN is empty" in result.stdout

    def test_materialize_step_holds_no_token(self) -> None:
        """Only the fetch step sees the token; materialize runs without it."""
        step = _workflow_step(_MATERIALIZE_STEP)

        assert "GH_FETCH_TOKEN" not in step.get("env", {})
        assert "secrets." not in json.dumps(step)
        assert "github.token" not in json.dumps(step)

    def test_token_source_expression_names_both_sources(self) -> None:
        """TOKEN_SOURCE labels the same secret GH_FETCH_TOKEN falls back from.

        Actions evaluates this expression, so no local run can exercise it.
        This pins its shape: the secret test and both literal labels.
        """
        env = _workflow_step(_FETCH_STEP)["env"]

        assert "secrets.VENDOR_PROVENANCE_PAT || github.token" in env["GH_FETCH_TOKEN"]
        assert env["TOKEN_SOURCE"] == (
            "${{ secrets.VENDOR_PROVENANCE_PAT != '' "
            "&& 'VENDOR_PROVENANCE_PAT' || 'github.token' }}"
        )
