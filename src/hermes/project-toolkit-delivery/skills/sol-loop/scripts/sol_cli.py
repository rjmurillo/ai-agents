"""Last-resort Sol route: call a native harness CLI on a Sol model, read-only.

Used only when the harness has neither T3 ``delegate_task`` nor a native Sol
subagent. Tries ``codex exec`` first, then ``droid exec``:

- ``codex exec -m <model> -s read-only --ignore-user-config --disable apps ... -``
  reads the brief on stdin and writes Sol's last message to a file. The two
  extra flags drop user MCP servers and account app connectors.
- ``droid exec -m <model> -f <brief> --only-tools Read,Grep,Glob,LS`` runs
  read-only (no ``--auto`` level) with file-reading tools only, and prints the
  reply on stdout.

A failed call returns a failure class; the caller takes the
review-model-unavailable WARN path. No other model is ever tried.
"""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

RUNNERS = ("codex", "droid")
DROID_READ_TOOLS = "Read,Grep,Glob,LS"
DEFAULT_TIMEOUT_SECONDS = 900

_FAILURE_RULES = (
    (
        re.compile(r"not supported|unknown model|model_not_found|unknown provider", re.I),
        "model-unsupported",
    ),
    (re.compile(r"\b(?:401|403)\b|unauthori[sz]ed|not logged in|login required", re.I), "auth"),
    (re.compile(r"rate.?limit|\b429\b", re.I), "rate-limit"),
    (re.compile(r"quota|usage limit|\b402\b|payment required", re.I), "quota"),
    (
        re.compile(
            r"\b(?:http(?:/[\d.]+)?|status(?: code)?|code)\s*[:=]?\s*5\d\d\b|server error|service unavailable"
            r"|bad gateway|gateway timeout|overloaded",
            re.I,
        ),
        "5xx",
    ),
)


@dataclasses.dataclass(frozen=True)
class CliResult:
    """Outcome of one CLI review call."""

    ok: bool
    text: str = ""
    failure_class: str = ""
    detail: str = ""


def classify_failure(message: str) -> str:
    """Map a CLI failure message to a failure class, ``unknown`` when unmatched."""
    return next((label for pattern, label in _FAILURE_RULES if pattern.search(message)), "unknown")


def available_runner() -> str:
    """Return the first Sol-capable CLI on PATH, or "" when there is none."""
    return next((name for name in RUNNERS if shutil.which(name)), "")


def _turn_failed(events_text: str) -> str:
    for raw in events_text.splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "turn.failed":
            return str((event.get("error") or {}).get("message", ""))
    return ""


def _run(cmd: list[str], brief: str | None, cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        input=brief,
        stdin=None if brief is not None else subprocess.DEVNULL,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _call(
    runner: str, model: str, brief: str, cwd: Path, timeout: int, tmp: Path
) -> tuple[subprocess.CompletedProcess, str]:
    """Run one CLI. Returns (process, reply text)."""
    exe = shutil.which(runner) or runner
    if runner == "codex":
        out = tmp / "last.txt"
        cmd = [exe, "exec", "-m", model, "-s", "read-only", "--ephemeral", "--skip-git-repo-check"]
        cmd += ["--ignore-user-config", "--disable", "apps"]
        proc = _run([*cmd, "--json", "-C", str(cwd), "-o", str(out), "-"], brief, cwd, timeout)
        return proc, out.read_text(encoding="utf-8") if out.is_file() else ""
    brief_file = tmp / "brief.md"
    brief_file.write_text(brief, encoding="utf-8")
    cmd = [exe, "exec", "-m", model, "-f", str(brief_file), "--only-tools", DROID_READ_TOOLS]
    proc = _run(cmd, None, cwd, timeout)
    return proc, proc.stdout


def run_sol(
    runner: str, model: str, brief: str, cwd: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> CliResult:
    """Run one read-only Sol review through ``runner``."""
    if runner not in RUNNERS or not shutil.which(runner):
        return CliResult(
            ok=False, failure_class="unknown", detail=f"{runner or 'no runner'} is not on PATH"
        )
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc, text = _call(runner, model, brief, cwd, timeout, Path(tmp))
        except subprocess.TimeoutExpired:
            return CliResult(
                ok=False, failure_class="timeout", detail=f"{runner}: no result in {timeout}s"
            )
    if proc.returncode != 0:
        message = _turn_failed(proc.stdout) or (proc.stderr or proc.stdout).strip()[-500:]
        return CliResult(
            ok=False, failure_class=classify_failure(message), detail=f"{runner}: {message}"
        )
    if not text.strip():
        return CliResult(ok=False, failure_class="invalid-output", detail=f"{runner}: empty reply")
    return CliResult(ok=True, text=text)
