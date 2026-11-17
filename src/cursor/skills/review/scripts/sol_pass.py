#!/usr/bin/env python3
"""Cross-family Sol review pass, run after the fresh critic.

Adds one capped, read-only GPT Sol review on top of the fresh critic and logs
which findings only Sol raised. Runs on the agent side through the Codex CLI,
never in CI. The procedure and log format are in the skill's
``resources/cross-family-pass.md``.

Stricter/looser/different than canonical: the review-model failure circuit
breaker in the governance AI review model policy names five failure classes
(timeout, 5xx, rate-limit, invalid-output, quota). An agent-side CLI fails in
more ways, so this script adds ``not-installed``, ``model-unsupported``,
``auth`` and ``unknown``. The reason string and user message are shared with
the policy; ``tests/skills/review/test_sol_pass.py`` reads the policy and
fails when they drift.

Exit codes: 0 pass ran or was switched off, 1 round cap hit (escalate to a
human), 2 config error (no or stale critic output, refused model, unreadable
input, run log not written), 3 Sol unavailable (WARN, defer to a human).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


def _resolve_paths_lib_dir() -> Path:
    """Resolve the lib directory holding paths.py, or fail with context."""
    # ADR-047 keeps this bootstrap inline because imports need sys.path first.
    # A plugin-root variable can name another plugin, so use it only when it
    # holds paths.py, then fall back to this file's own plugin tree.
    roots = (os.environ.get("COPILOT_PLUGIN_ROOT"), os.environ.get("CLAUDE_PLUGIN_ROOT"))
    candidates = [Path(root) / "lib" for root in roots if root]
    candidates.append(Path(__file__).resolve().parents[3] / "lib")
    for lib_dir in candidates:
        if (lib_dir / "paths.py").is_file():
            return lib_dir.resolve()
    raise RuntimeError(f"paths.py not found in any of: {', '.join(map(str, candidates))}")


_LIB_DIR = _resolve_paths_lib_dir()
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import paths  # noqa: E402

_HERE = Path(__file__).absolute().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from sol_findings import (  # noqa: E402
    OVERLAP_LINE_WINDOW,
    classify_failure,
    failure_message,
    filter_findings,
    mark_sol_only,
)

DEFAULT_SOL_MODEL = "gpt-6.1-sol"
SOL_MODEL_PATTERN = re.compile(r"^gpt-\d+(?:\.\d+)?-sol$")
MAX_ROUNDS = 2
UNAVAILABLE_REASON = "review-model-unavailable"
LOG_SUBDIR = "metrics/sol-pass"
SCHEMA_VERSION = 1
OFF_VALUES = frozenset({"0", "off", "false", "no", "disabled"})
DEFAULT_TIMEOUT_SECONDS = 900

EXIT_OK, EXIT_ESCALATE, EXIT_CONFIG, EXIT_UNAVAILABLE = 0, 1, 2, 3

_FIELD_TYPES = {
    "file": "string",
    "line": "integer",
    "repro": "string",
    "summary": "string",
    "severity": "string",
    "category": "string",
}
FINDINGS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(_FIELD_TYPES),
                "properties": {name: {"type": kind} for name, kind in _FIELD_TYPES.items()},
            },
        }
    },
}

_PROMPT = """You are a read-only, cross-family code reviewer. Another reviewer
already reviewed this change; you have not seen its findings. Work independently.

Review the change: run `git diff {base}...HEAD` in this repository and read any
file you need. Do not edit files.

Report only defects: wrong behavior, crashes, data loss, security holes, broken
contracts, missing error paths. Skip style, naming, formatting, and wording.

Every finding MUST have:
- file: repository-relative path
- line: the 1-based line number in the current file
- repro: a failing test, a command, or concrete inputs that show the defect
A finding without all three will be discarded, so do not report it.
{frozen}
Return JSON that matches the provided schema. Return an empty list when you
find no defect. Do not invent findings to fill a quota.
"""

_FROZEN = """
This is round 2. Only a defect that this diff introduced (fix commits included)
counts. Do not report pre-existing issues, nice-to-haves, or new scope.
"""


@dataclasses.dataclass(frozen=True)
class RunResult:
    """Outcome of one reviewer call."""

    ok: bool
    text: str = ""
    failure_class: str = ""
    detail: str = ""


Runner = Callable[[str, str, Path, Path, int], RunResult]


def codex_runner(model: str, prompt: str, schema_path: Path, cwd: Path, timeout: int) -> RunResult:
    """Run one read-only Codex CLI review with the given model."""
    exe = shutil.which("codex")
    if exe is None:
        return RunResult(ok=False, failure_class="not-installed", detail="codex not on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        out_file = Path(tmp) / "last.json"
        cmd = [
            exe,
            "exec",
            "-m",
            model,
            "-s",
            "read-only",
            "--ephemeral",
            "--json",
            "--skip-git-repo-check",
        ]
        cmd += ["--output-schema", str(schema_path), "-o", str(out_file), "-C", str(cwd), prompt]
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return RunResult(ok=False, failure_class="timeout", detail=f"no result in {timeout}s")
        text = out_file.read_text(encoding="utf-8") if out_file.is_file() else ""
    if proc.returncode != 0:
        message = failure_message(proc.stdout, proc.stderr)
        return RunResult(ok=False, failure_class=classify_failure(message), detail=message)
    if not text.strip():
        return RunResult(ok=False, failure_class="invalid-output", detail="empty output")
    return RunResult(ok=True, text=text)


def validate_model(model: str) -> str | None:
    """Return an error message when ``model`` is not a GPT Sol id."""
    if SOL_MODEL_PATTERN.fullmatch(model.strip()):
        return None
    return (
        f"model {model!r} refused: the cross-family pass accepts only a GPT Sol "
        "id such as gpt-6.1-sol. Gemini, Grok, and same-family Claude ids are not allowed."
    )


def _git(cwd: Path, *args: str) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def default_log_base(repo: Path) -> Path:
    """Anchor logs at the reviewed checkout's top level.

    A linked worktree is removed when its work ends, so set
    ``AI_AGENTS_ARTIFACT_ROOT`` to a lasting directory to keep the logs.
    This script never writes into a different checkout on its own.
    """
    top = _git(repo, "rev-parse", "--show-toplevel")
    return Path(top) if top else repo


def load_runs(log_dir: Path) -> tuple[list[dict], int]:
    """Read every run file in ``log_dir``. Returns the records and the unreadable count."""
    records: list[dict] = []
    unreadable = 0
    for path in sorted(log_dir.glob("*.json")) if log_dir.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            record = None
        if isinstance(record, dict):
            records.append(record)
        else:
            unreadable += 1
    return records, unreadable


def prior_rounds(log_dir: Path, key: str) -> int:
    """Count completed Sol reviews already logged for this PR or branch."""
    records, _ = load_runs(log_dir)
    return sum(1 for r in records if r.get("key") == key and r.get("status") == "ok")


def write_run_log(record: dict, log_dir: Path) -> Path | None:
    """Write one run record as its own JSON file. Returns None when the write fails."""
    stamp = record["timestamp"].replace(":", "").replace("-", "")
    label = re.sub(r"[^A-Za-z0-9_.-]", "-", record["key"])
    stem = f"{stamp}-{label}-r{record['round']}-{record['status']}"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        for suffix in range(1000):
            target = log_dir / (f"{stem}-{suffix}.json" if suffix else f"{stem}.json")
            if not target.exists():
                target.write_text(
                    json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                return target
    except OSError as exc:
        print(f"sol_pass: run log not written to {log_dir}: {exc}", file=sys.stderr)
    return None


def _read_critic(path: Path) -> tuple[str, str]:
    """Return (critic text, error). The critic output must be non-empty UTF-8."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return "", f"cannot read critic output {path}: {exc}"
    if not text.strip():
        return "", f"critic output {path} is empty"
    return text, ""


def _critic_is_stale(repo: Path, critic: Path) -> bool:
    """True when the critic output predates the reviewed HEAD commit."""
    head_time = _git(repo, "log", "-1", "--format=%ct", "HEAD")
    return head_time.isdigit() and critic.stat().st_mtime < int(head_time)


@dataclasses.dataclass
class Run:
    """One invocation: its validated inputs, its log record, and where it logs."""

    repo: Path
    critic_text: str
    record: dict
    log_dir: Path

    def finish(self, status: str, payload: dict, exit_code: int, **fields: object) -> int:
        """Log the run, print the verdict, and return the exit code.

        The verdict prints even when the log write fails, so a WARN is never
        lost; a run that reviewed but could not log exits 2.
        """
        self.record.update(status=status, **fields)
        log = write_run_log(self.record, self.log_dir)
        print(json.dumps({**payload, "log": str(log) if log else None}, indent=2, sort_keys=True))
        return EXIT_CONFIG if log is None and exit_code == EXIT_OK else exit_code


def _start(args: argparse.Namespace) -> tuple[Run | None, str]:
    """Validate inputs and build the run record. Returns (run, error)."""
    repo = Path(args.repo).resolve()
    critic = Path(args.critic_findings)
    model = (args.model or os.environ.get("AI_AGENTS_SOL_MODEL") or DEFAULT_SOL_MODEL).strip()
    error = validate_model(model)
    critic_text = ""
    if not error:
        critic_text, error = _read_critic(critic)
    if not error and _critic_is_stale(repo, critic):
        error = "critic output is older than HEAD; rerun the fresh critic on this commit first"
    if error:
        return None, error
    branch = _git(repo, "branch", "--show-current")
    base = Path(args.log_base).resolve() if args.log_base else default_log_base(repo)
    log_dir = paths.artifact_dir(LOG_SUBDIR, base=base)
    key = f"pr-{args.pr}" if args.pr else (branch or "local")
    record = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "key": key,
        "pr": args.pr,
        "branch": branch,
        "head_sha": _git(repo, "rev-parse", "HEAD"),
        "base": args.base,
        "round": prior_rounds(log_dir, key) + 1,
        "model": model,
        "critic_sha256": hashlib.sha256(critic_text.encode("utf-8")).hexdigest(),
        "overlap_rule": f"same file and line within {OVERLAP_LINE_WINDOW} of a critic path:line or range",
        "failure_class": "",
        "findings": [],
        "dropped": [],
        "counts": {"raw": 0, "kept": 0, "dropped": 0, "sol_only": 0, "overlap": 0},
    }
    return Run(repo=repo, critic_text=critic_text, record=record, log_dir=log_dir), ""


def _parse_findings(result: RunResult) -> tuple[list | None, RunResult]:
    """Return (findings, result); findings is None when the call or its output failed."""
    if not result.ok:
        return None, result
    try:
        raw = json.loads(result.text).get("findings")
    except (json.JSONDecodeError, AttributeError) as exc:
        return None, RunResult(ok=False, failure_class="invalid-output", detail=str(exc))
    if not isinstance(raw, list):
        return None, RunResult(
            ok=False, failure_class="invalid-output", detail="findings is not a list"
        )
    return raw, result


def _call_sol(run: Run, args: argparse.Namespace, runner: Runner) -> tuple[list | None, RunResult]:
    frozen = _FROZEN if run.record["round"] >= 2 else ""
    prompt = _PROMPT.format(base=args.base, frozen=frozen)
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = Path(tmp) / "schema.json"
        schema_path.write_text(json.dumps(FINDINGS_SCHEMA), encoding="utf-8")
        return _parse_findings(
            runner(run.record["model"], prompt, schema_path, run.repo, args.timeout)
        )


def _unavailable(run: Run, result: RunResult) -> int:
    message = (
        "Review model unavailable, deferring to human.\n"
        f"Model: {run.record['model']} | Failure: {result.failure_class}"
    )
    payload = {
        "verdict": "WARN",
        "reason": UNAVAILABLE_REASON,
        "message": message,
        "detail": result.detail,
    }
    return run.finish("unavailable", payload, EXIT_UNAVAILABLE, failure_class=result.failure_class)


def _reviewed(run: Run, raw: list) -> int:
    kept, dropped = filter_findings(raw)
    marked = mark_sol_only(kept, run.critic_text)
    sol_only = sum(1 for f in marked if f["sol_only"])
    counts = {
        "raw": len(raw),
        "kept": len(marked),
        "dropped": len(dropped),
        "sol_only": sol_only,
        "overlap": len(marked) - sol_only,
    }
    payload = {"verdict": "WARN" if marked else "PASS", "findings": marked, "counts": counts}
    return run.finish("ok", payload, EXIT_OK, findings=marked, dropped=dropped, counts=counts)


def run_pass(args: argparse.Namespace, runner: Runner = codex_runner) -> int:
    """Run the capped Sol pass after the critic and log it. Returns the exit code."""
    run, error = _start(args)
    if run is None:
        print(f"sol_pass: {error}", file=sys.stderr)
        return EXIT_CONFIG
    if args.disable or os.environ.get("AI_AGENTS_SOL_PASS", "").strip().lower() in OFF_VALUES:
        return run.finish("skipped", {"verdict": "SKIPPED", "reason": "sol pass disabled"}, EXIT_OK)
    if run.record["round"] > MAX_ROUNDS:
        reason = f"{MAX_ROUNDS} Sol rounds already logged for {run.record['key']}; hand open findings to a human"
        return run.finish("escalated", {"verdict": "ESCALATE", "reason": reason}, EXIT_ESCALATE)
    raw, result = _call_sol(run, args, runner)
    return _unavailable(run, result) if raw is None else _reviewed(run, raw)


def summarize(log_dir: Path) -> dict:
    """Total every run file in ``log_dir``."""
    records, unreadable = load_runs(log_dir)
    totals = {"runs": len(records), "unreadable": unreadable}
    for status in ("ok", "skipped", "unavailable", "escalated"):
        totals[status] = sum(1 for r in records if r.get("status") == status)
    for key in ("kept", "dropped", "sol_only", "overlap"):
        totals[key] = sum(int((r.get("counts") or {}).get(key) or 0) for r in records)
    return totals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cross-family Sol review pass, run after the fresh critic."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one Sol pass after the critic")
    run.add_argument(
        "--critic-findings", required=True, help="file holding the fresh critic's output"
    )
    run.add_argument("--base", default="origin/main", help="diff base ref")
    run.add_argument("--pr", default="", help="PR number; keys the round count and the log")
    run.add_argument("--repo", default=".", help="checkout to review")
    run.add_argument("--model", default="", help="GPT Sol model id")
    run.add_argument("--log-base", default="", help="directory whose artifact root holds the log")
    run.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    run.add_argument("--disable", action="store_true", help="skip the pass and log a skipped run")
    summ = sub.add_parser("summarize", help="total the run logs")
    summ.add_argument("--repo", default=".")
    summ.add_argument("--log-base", default="")
    return parser


def main(argv: list[str] | None = None, runner: Runner = codex_runner) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "summarize":
            repo = Path(args.repo).resolve()
            base = Path(args.log_base).resolve() if args.log_base else default_log_base(repo)
            print(
                json.dumps(
                    summarize(paths.artifact_dir(LOG_SUBDIR, base=base)), indent=2, sort_keys=True
                )
            )
            return EXIT_OK
        return run_pass(args, runner)
    except (OSError, ValueError) as exc:
        print(f"sol_pass: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
