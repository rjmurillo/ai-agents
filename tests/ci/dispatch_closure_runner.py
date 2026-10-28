"""Run verify_dispatch_closure.py against a base checkout and a pull request head."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import verify_dispatch_closure as vdc
from tests.ci.dispatch_closure_helpers import git


def commit_on_base(base: Path, message: str) -> None:
    git(base, "add", "-A")
    git(base, "commit", "-q", "-m", message)


def check(base: Path, upstream: Path, sha: str, capsys: pytest.CaptureFixture[str]) -> dict:
    """Run ``main`` with ``--json`` and return its report plus the exit ``code``."""
    argv = ["--tool-root", str(base), "--head-sha", sha, "--pull-number", "1"]
    code = vdc.main([*argv, "--remote", str(upstream), "--json"])
    report = json.loads(capsys.readouterr().out)
    report["code"] = code
    return report
