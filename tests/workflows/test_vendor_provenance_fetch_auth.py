"""Run the vendor provenance fetch step against a fake git (issue #5593).

The step authenticates its candidate fetch with a header that git sends to
github.com. A string search over the YAML cannot show what git receives, what
the log shows, or how the step fails. These tests run the real ``run:``
script under ``bash -eo pipefail`` with a fake ``git`` first on PATH. The fake
records its argv and the git config env vars, then exits with a chosen code.

``pull_request_target`` runs the workflow from the base branch, so a PR cannot
exercise its own change to this step in CI. This test is the pre-merge check.
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
WORKFLOW = REPO_ROOT / ".github/workflows/vendor-provenance.yml"
FETCH_STEP = "Fetch candidate commit via git"
MATERIALIZE_STEP = "Materialize candidate tree"
TOKEN = "ghs_FakeTokenValue0123456789abcdef"
PR_SHA = "0123456789abcdef0123456789abcdef01234567"
SOURCE = "VENDOR_PROVENANCE_PAT"
EXPECTED_BASIC = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="the step runs under bash on a Linux runner",
)

_FAKE_GIT = """\
import json, os, sys
keys = ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0",
        "GIT_TERMINAL_PROMPT")
record = {"argv": sys.argv[1:], "env": {k: os.environ.get(k) for k in keys}}
with open(os.environ["FAKE_GIT_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(record) + "\\n")
sys.exit(int(os.environ["FAKE_GIT_EXIT"]))
"""


def _steps() -> list[dict[str, Any]]:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps: list[dict[str, Any]] = doc["jobs"]["provenance"]["steps"]
    return steps


def _step(name: str) -> dict[str, Any]:
    matches = [step for step in _steps() if step.get("name") == name]
    assert len(matches) == 1, f"expected exactly one {name!r} step"
    return matches[0]


def _install_fake_git(bin_dir: Path) -> None:
    bin_dir.mkdir()
    fake = bin_dir / "git"
    fake.write_text(f"#!{sys.executable}\n{_FAKE_GIT}", encoding="utf-8")
    fake.chmod(0o755)


def _run_fetch(tmp_path: Path, token: str, git_exit: int) -> tuple[int, str, list[dict[str, Any]]]:
    """Run the fetch step; return exit code, stdout, and fake git calls."""
    script = tmp_path / "step.sh"
    script.write_text(_step(FETCH_STEP)["run"], encoding="utf-8")
    _install_fake_git(tmp_path / "bin")
    log = tmp_path / "git-calls.jsonl"
    env = {
        "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_GIT_LOG": str(log),
        "FAKE_GIT_EXIT": str(git_exit),
        "GH_FETCH_TOKEN": token,
        "PR_SHA": PR_SHA,
        "TOKEN_SOURCE": SOURCE,
    }
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return result.returncode, result.stdout, calls


class TestFetchSucceeds:
    """A token git accepts: the header shape, masking, and argv hygiene."""

    def test_step_exits_zero_and_calls_git_once(self, tmp_path: Path) -> None:
        code, _, calls = _run_fetch(tmp_path, TOKEN, git_exit=0)
        assert code == 0
        assert len(calls) == 1
        assert calls[0]["argv"] == ["fetch", "--depth=1", "origin", PR_SHA]

    def test_header_is_basic_x_access_token_scoped_to_github(self, tmp_path: Path) -> None:
        _, _, calls = _run_fetch(tmp_path, TOKEN, git_exit=0)
        env = calls[0]["env"]
        assert env["GIT_CONFIG_COUNT"] == "1"
        assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
        assert env["GIT_CONFIG_VALUE_0"] == f"AUTHORIZATION: basic {EXPECTED_BASIC}"
        assert env["GIT_TERMINAL_PROMPT"] == "0"

    def test_token_and_credential_stay_out_of_argv(self, tmp_path: Path) -> None:
        _, _, calls = _run_fetch(tmp_path, TOKEN, git_exit=0)
        for arg in calls[0]["argv"]:
            assert TOKEN not in arg
            assert EXPECTED_BASIC not in arg

    def test_credential_is_masked_before_any_other_line_shows_it(self, tmp_path: Path) -> None:
        _, stdout, _ = _run_fetch(tmp_path, TOKEN, git_exit=0)
        lines = stdout.splitlines()
        showing = [i for i, line in enumerate(lines) if EXPECTED_BASIC in line]
        assert showing, "the encoded credential was never masked"
        assert lines[showing[0]] == f"::add-mask::{EXPECTED_BASIC}"

    def test_log_names_the_source_and_never_the_token(self, tmp_path: Path) -> None:
        _, stdout, _ = _run_fetch(tmp_path, TOKEN, git_exit=0)
        assert f"fetch token source: {SOURCE}" in stdout.splitlines()
        assert TOKEN not in stdout


class TestFetchFails:
    """An empty or rejected token fails with an annotation, not a git prompt."""

    def test_empty_token_fails_before_git_runs(self, tmp_path: Path) -> None:
        code, stdout, calls = _run_fetch(tmp_path, "", git_exit=0)
        assert code == 1
        assert calls == []
        assert any(
            line.startswith("::error::GH_FETCH_TOKEN is empty") for line in stdout.splitlines()
        )

    def test_rejected_token_names_the_source(self, tmp_path: Path) -> None:
        code, stdout, calls = _run_fetch(tmp_path, TOKEN, git_exit=128)
        assert code == 1
        assert len(calls) == 1
        errors = [line for line in stdout.splitlines() if line.startswith("::error::")]
        assert len(errors) == 1
        assert f"git fetch failed using {SOURCE}" in errors[0]
        assert "contents:read" in errors[0]
        assert TOKEN not in stdout


class TestMaterializeStepHoldsNoToken:
    """Only the fetch step may carry the token into its environment."""

    def test_materialize_env_has_no_token_or_secret(self) -> None:
        step = _step(MATERIALIZE_STEP)
        env = step.get("env") or {}
        assert "GH_FETCH_TOKEN" not in env
        assert all("secrets." not in str(value) for value in env.values())
        assert "secrets." not in step["run"]
        assert "GH_FETCH_TOKEN" not in step["run"]
