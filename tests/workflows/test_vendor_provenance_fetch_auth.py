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

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/vendor-provenance.yml"
TOKEN = "ghs_FakeTokenValue0123456789abcdef"
PR_SHA = "0123456789abcdef0123456789abcdef01234567"
SOURCE = "VENDOR_PROVENANCE_PAT"
BASIC = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()

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


def _step(name: str) -> dict[str, Any]:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["provenance"]["steps"]
    matches: list[dict[str, Any]] = [step for step in steps if step.get("name") == name]
    assert len(matches) == 1, f"expected exactly one {name!r} step"
    return matches[0]


def _run_fetch(tmp_path: Path, token: str, git_exit: int) -> tuple[int, list[str], list[Any]]:
    """Run the fetch step with a fake git; return exit code, stdout lines, git calls."""
    script = tmp_path / "step.sh"
    script.write_text(_step("Fetch candidate commit via git")["run"], encoding="utf-8")
    fake = tmp_path / "bin" / "git"
    fake.parent.mkdir()
    fake.write_text(f"#!{sys.executable}\n{_FAKE_GIT}", encoding="utf-8")
    fake.chmod(0o755)
    log = tmp_path / "git-calls.jsonl"
    env = {
        "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
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
    return result.returncode, result.stdout.splitlines(), calls


def test_accepted_token_sends_masked_basic_header_outside_argv(tmp_path: Path) -> None:
    """One run, every success property: exit, header, prompt, argv, mask, log."""
    code, lines, calls = _run_fetch(tmp_path, TOKEN, git_exit=0)
    assert code == 0
    assert len(calls) == 1, "git must run exactly once"
    assert calls[0]["argv"] == ["fetch", "--depth=1", "origin", PR_SHA]
    assert calls[0]["env"] == {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {BASIC}",
        "GIT_TERMINAL_PROMPT": "0",
    }
    assert not any(TOKEN in arg or BASIC in arg for arg in calls[0]["argv"])
    showing = [line for line in lines if BASIC in line]
    assert showing[:1] == [f"::add-mask::{BASIC}"], "credential must be masked first"
    assert f"fetch token source: {SOURCE}" in lines
    assert not any(TOKEN in line for line in lines)


def test_empty_token_fails_before_git_runs(tmp_path: Path) -> None:
    code, lines, calls = _run_fetch(tmp_path, "", git_exit=0)
    assert code == 1
    assert calls == []
    assert any(line.startswith("::error::GH_FETCH_TOKEN is empty") for line in lines)


def test_rejected_token_fails_with_error_naming_the_source(tmp_path: Path) -> None:
    code, lines, calls = _run_fetch(tmp_path, TOKEN, git_exit=128)
    errors = [line for line in lines if line.startswith("::error::")]
    assert code == 1
    assert len(calls) == 1
    assert len(errors) == 1
    assert f"git fetch failed using {SOURCE}" in errors[0]
    assert "contents:read" in errors[0]
    assert not any(TOKEN in line for line in lines)


def test_materialize_step_holds_no_token() -> None:
    step = _step("Materialize candidate tree")
    exposed = json.dumps(step.get("env") or {}) + step["run"]
    assert "GH_FETCH_TOKEN" not in exposed
    assert "secrets." not in exposed
