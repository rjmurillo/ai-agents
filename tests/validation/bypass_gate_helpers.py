"""Shared builders for the bypass allowlist gate tests.

A throwaway git repository, allowlist entries, and workflow text. The gate reads
the tracked tree at HEAD, so every test needs a real repository.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from scripts.validation import check_bypass_allowlist as gate
from scripts.validation.bypass_allowlist import parse_allowlist
from scripts.validation.evidence import EvidenceState

TODAY = date(2026, 9, 30)
WORKFLOW = ".github/workflows/ci.yml"


def git(root: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    git(tmp_path, "init", "-q")
    for relpath, text in files.items():
        target = tmp_path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "init")
    return tmp_path


def allow(*entries: dict[str, Any]) -> Any:
    return parse_allowlist({"schema_version": "1", "entries": list(entries)})


def toggle(name: str, expires: str = "2026-12-31") -> dict[str, Any]:
    return {"kind": "toggle", "toggle": name, "reason": "r", "owner": "o", "expires": expires}


def step(job: str, name: str, expires: str = "2026-12-31") -> dict[str, Any]:
    return {
        "kind": "continue-on-error",
        "path": WORKFLOW,
        "job": job,
        "step": name,
        "reason": "r",
        "owner": "o",
        "expires": expires,
    }


def workflow(*step_lines: str, job_lines: str = "") -> str:
    steps = "\n".join(step_lines)
    return f"on: push\njobs:\n  build:\n    runs-on: x\n{job_lines}    steps:\n{steps}\n"


def run_gate(root: Path, allowlist: Any) -> tuple[EvidenceState, str]:
    outcome, _ = gate.evaluate(root, allowlist, TODAY)
    return outcome.state, outcome.detail
