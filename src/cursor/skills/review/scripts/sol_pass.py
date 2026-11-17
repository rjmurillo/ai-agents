#!/usr/bin/env python3
"""Cross-family Sol review pass, run after the fresh Opus critic.

The fresh critic (same family as the author) stays as it is. This script adds
one capped, read-only GPT Sol review on top of it and logs which findings only
Sol raised, so the operator can measure whether the second family earns its
place. It runs on the agent side through the Codex CLI. It never runs in CI.

Contract:

- Ordering. The critic's output file is a required input. Without it the pass
  refuses to run (exit 2), so it cannot run before the critic. Sol never sees
  the critic's findings; they are used only to mark overlap afterward.
- Model. Only a GPT Sol model id is accepted (``SOL_MODEL_PATTERN``). Gemini,
  Grok, Claude, and every other id are refused before any call.
- Rounds. At most ``MAX_ROUNDS`` (2). Round 2 applies the frozen finding
  contract. A higher round exits 1 (escalate) with no model call.
- Findings. Each kept finding needs a file, a line, and a repro. A finding
  missing one, or one that is a style nit, is dropped and logged as dropped.
- Unavailable. When the Sol call fails, the verdict is ``WARN`` with reason
  ``review-model-unavailable`` and the run exits 3. There is no second model
  call and no same-family fallback.
- Log. Every run, including skipped, unavailable, and escalated runs, writes
  one JSON file under ``<artifact root>/metrics/sol-pass/``. ``summarize``
  totals those files.

Stricter/looser/different than canonical: the review-model failure circuit
breaker in the governance AI review model policy lists five failure classes
(timeout, 5xx, rate-limit, invalid-output, quota). This script adds two
local classes, ``not-installed`` (no ``codex`` on PATH) and
``model-unsupported`` (the CLI refused the model id), because an agent-side
CLI fails in ways a hosted CI call does not. The policy reason string and
message are shared; ``tests/skills/review/test_sol_pass.py`` reads the policy
and fails if the reason string or the five classes drift.

Exit codes: 0 pass ran or was skipped by the off switch, 1 round cap hit
(escalate to a human), 2 config error, 3 Sol unavailable (WARN, defer to a
human).
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
    """Resolve the plugin path-helper lib directory or fail with context."""
    # ADR-047 keeps this bootstrap inline because imports need sys.path first.
    plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        lib_dir = Path(plugin_root) / "lib"
    else:
        lib_dir = Path(__file__).resolve().parents[3] / "lib"
    if not lib_dir.is_dir():
        raise RuntimeError(
            f"Expected portability helper lib directory not found: {lib_dir}. "
            "Set COPILOT_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT to the plugin root."
        )
    return lib_dir.resolve()


_LIB_DIR = _resolve_paths_lib_dir()
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import paths  # noqa: E402

DEFAULT_SOL_MODEL = "gpt-6.1-sol"
SOL_MODEL_PATTERN = re.compile(r"^gpt-\d+(?:\.\d+)?-sol$")
MAX_ROUNDS = 2
UNAVAILABLE_REASON = "review-model-unavailable"
LOG_SUBDIR = "metrics/sol-pass"
SCHEMA_VERSION = 1
OVERLAP_LINE_WINDOW = 3
STYLE_CATEGORIES = frozenset({"style", "nit", "naming", "formatting", "typo", "wording"})
OFF_VALUES = frozenset({"0", "off", "false", "no", "disabled"})
DEFAULT_TIMEOUT_SECONDS = 900

EXIT_OK = 0
EXIT_ESCALATE = 1
EXIT_CONFIG = 2
EXIT_UNAVAILABLE = 3

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
                "required": ["file", "line", "repro", "summary", "severity", "category"],
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "repro": {"type": "string"},
                    "summary": {"type": "string"},
                    "severity": {"type": "string"},
                    "category": {"type": "string"},
                },
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


def _classify_failure(message: str) -> str:
    lowered = message.lower()
    if "not supported" in lowered or "unknown model" in lowered or "model_not_found" in lowered:
        return "model-unsupported"
    if "rate limit" in lowered or "429" in lowered:
        return "rate-limit"
    if "quota" in lowered or "usage limit" in lowered:
        return "quota"
    return "5xx"


def _failure_message(events_text: str, stderr: str) -> str:
    for raw in events_text.splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.failed":
            return str((event.get("error") or {}).get("message", ""))
    return stderr.strip()[-500:]


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
            "--output-schema",
            str(schema_path),
            "-o",
            str(out_file),
            "-C",
            str(cwd),
            prompt,
        ]
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
        if proc.returncode != 0 or not text.strip():
            message = _failure_message(proc.stdout, proc.stderr)
            if proc.returncode == 0:
                return RunResult(ok=False, failure_class="invalid-output", detail="empty output")
            return RunResult(ok=False, failure_class=_classify_failure(message), detail=message)
        return RunResult(ok=True, text=text)


def validate_model(model: str) -> str | None:
    """Return an error message when ``model`` is not a GPT Sol id."""
    if SOL_MODEL_PATTERN.fullmatch(model.strip()):
        return None
    return (
        f"model {model!r} refused: the cross-family pass accepts only a GPT Sol "
        "id such as gpt-6.1-sol. Gemini, Grok, and same-family Claude ids are not allowed."
    )


def _valid_line(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def filter_findings(raw: list[object]) -> tuple[list[dict], list[dict]]:
    """Split findings into kept and dropped. Dropped entries carry a reason."""
    kept: list[dict] = []
    dropped: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            dropped.append({"reason": "not-an-object", "finding": item})
            continue
        file_value = str(item.get("file") or "").strip()
        repro = str(item.get("repro") or "").strip()
        category = str(item.get("category") or "").strip().lower()
        if not file_value:
            reason = "missing-file"
        elif not _valid_line(item.get("line")):
            reason = "missing-line"
        elif not repro:
            reason = "missing-repro"
        elif category in STYLE_CATEGORIES:
            reason = "style-nit"
        else:
            reason = ""
        if reason:
            dropped.append({"reason": reason, "finding": item})
        else:
            kept.append({**item, "file": file_value, "repro": repro})
    return kept, dropped


_LOCATION = re.compile(r"([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+):(\d+)")


def critic_locations(critic_text: str) -> list[tuple[str, int]]:
    """Extract ``path:line`` locations the critic cited."""
    return [
        (m.group(1).replace("\\", "/").lstrip("./"), int(m.group(2)))
        for m in _LOCATION.finditer(critic_text)
    ]


def _same_file(a: str, b: str) -> bool:
    a, b = a.lstrip("./"), b.lstrip("./")
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def mark_sol_only(findings: list[dict], critic_text: str) -> list[dict]:
    """Flag each finding ``sol_only`` unless the critic cited a nearby location."""
    cited = critic_locations(critic_text)
    marked = []
    for finding in findings:
        hit = any(
            _same_file(finding["file"], path) and abs(finding["line"] - line) <= OVERLAP_LINE_WINDOW
            for path, line in cited
        )
        marked.append({**finding, "sol_only": not hit})
    return marked


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


def write_run_log(record: dict, base: Path) -> Path:
    """Write one run record as its own JSON file and return its path."""
    log_dir = paths.resolve_artifact_root(LOG_SUBDIR, base=base)
    stamp = record["timestamp"].replace(":", "").replace("-", "")
    label = re.sub(
        r"[^A-Za-z0-9_.-]", "-", str(record.get("pr") or record.get("branch") or "local")
    )
    target = log_dir / f"{stamp}-{label}-r{record['round']}-{record['status']}.json"
    suffix = 1
    while target.exists():
        target = log_dir / f"{stamp}-{label}-r{record['round']}-{record['status']}-{suffix}.json"
        suffix += 1
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _base_record(args: argparse.Namespace, repo: Path, model: str, critic_text: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pr": args.pr,
        "branch": _git(repo, "branch", "--show-current"),
        "head_sha": _git(repo, "rev-parse", "HEAD"),
        "base": args.base,
        "round": args.round,
        "model": model,
        "critic_sha256": hashlib.sha256(critic_text.encode("utf-8")).hexdigest()
        if critic_text
        else "",
        "overlap_rule": f"same file and line within {OVERLAP_LINE_WINDOW} of a critic path:line",
        "status": "",
        "failure_class": "",
        "findings": [],
        "dropped": [],
        "counts": {"raw": 0, "kept": 0, "dropped": 0, "sol_only": 0, "overlap": 0},
    }


def _emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_pass(args: argparse.Namespace, runner: Runner = codex_runner) -> int:
    """Run the capped Sol pass and log it. Returns the process exit code."""
    repo = Path(args.repo).resolve()
    model = (args.model or os.environ.get("AI_AGENTS_SOL_MODEL") or DEFAULT_SOL_MODEL).strip()
    model_error = validate_model(model)
    if model_error:
        print(f"sol_pass: {model_error}", file=sys.stderr)
        return EXIT_CONFIG

    critic_path = Path(args.critic_findings) if args.critic_findings else None
    if (
        critic_path is None
        or not critic_path.is_file()
        or not critic_path.read_text(encoding="utf-8").strip()
    ):
        print(
            "sol_pass: refusing to run. The Sol pass runs after the fresh critic; "
            "pass the critic's non-empty output with --critic-findings.",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    critic_text = critic_path.read_text(encoding="utf-8")

    base = Path(args.log_base).resolve() if args.log_base else default_log_base(repo)
    record = _base_record(args, repo, model, critic_text)

    if os.environ.get("AI_AGENTS_SOL_PASS", "").strip().lower() in OFF_VALUES or args.disable:
        record["status"] = "skipped"
        log = write_run_log(record, base)
        _emit({"verdict": "SKIPPED", "reason": "sol pass disabled", "log": str(log)})
        return EXIT_OK

    if args.round < 1:
        print("sol_pass: --round must be 1 or higher", file=sys.stderr)
        return EXIT_CONFIG
    if args.round > MAX_ROUNDS:
        record["status"] = "escalated"
        log = write_run_log(record, base)
        _emit(
            {
                "verdict": "ESCALATE",
                "reason": f"round {args.round} exceeds the {MAX_ROUNDS}-round cap; hand open findings to a human",
                "log": str(log),
            }
        )
        return EXIT_ESCALATE

    prompt = _PROMPT.format(base=args.base, frozen=_FROZEN if args.round >= 2 else "")
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = Path(tmp) / "schema.json"
        schema_path.write_text(json.dumps(FINDINGS_SCHEMA), encoding="utf-8")
        result = runner(model, prompt, schema_path, repo, args.timeout)

    if result.ok:
        try:
            raw = json.loads(result.text).get("findings")
            if not isinstance(raw, list):
                raise ValueError("findings is not a list")
        except (json.JSONDecodeError, ValueError, AttributeError) as exc:
            result = RunResult(ok=False, failure_class="invalid-output", detail=str(exc))

    if not result.ok:
        record["status"] = "unavailable"
        record["failure_class"] = result.failure_class
        log = write_run_log(record, base)
        _emit(
            {
                "verdict": "WARN",
                "reason": UNAVAILABLE_REASON,
                "message": (
                    "Review model unavailable, deferring to human.\n"
                    f"Model: {model} | Failure: {result.failure_class} | Run: {log}"
                ),
                "detail": result.detail,
                "log": str(log),
            }
        )
        return EXIT_UNAVAILABLE

    kept, dropped = filter_findings(raw)
    marked = mark_sol_only(kept, critic_text)
    sol_only = sum(1 for f in marked if f["sol_only"])
    record.update(
        status="ok",
        findings=marked,
        dropped=dropped,
        counts={
            "raw": len(raw),
            "kept": len(marked),
            "dropped": len(dropped),
            "sol_only": sol_only,
            "overlap": len(marked) - sol_only,
        },
    )
    log = write_run_log(record, base)
    _emit(
        {
            "verdict": "WARN" if marked else "PASS",
            "findings": marked,
            "counts": record["counts"],
            "log": str(log),
        }
    )
    return EXIT_OK


def summarize(log_dir: Path) -> dict:
    """Total every run file in ``log_dir``."""
    totals = {
        "runs": 0,
        "ok": 0,
        "skipped": 0,
        "unavailable": 0,
        "escalated": 0,
        "kept": 0,
        "dropped": 0,
        "sol_only": 0,
        "overlap": 0,
        "unreadable": 0,
    }
    for path in sorted(log_dir.glob("*.json")) if log_dir.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            totals["unreadable"] += 1
            continue
        totals["runs"] += 1
        status = record.get("status", "")
        if status in totals:
            totals[status] += 1
        for key in ("kept", "dropped", "sol_only", "overlap"):
            totals[key] += int((record.get("counts") or {}).get(key, 0))
    return totals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one Sol pass after the critic")
    run.add_argument(
        "--critic-findings", required=True, help="file holding the fresh critic's output"
    )
    run.add_argument("--round", type=int, default=1, help=f"review round, 1 to {MAX_ROUNDS}")
    run.add_argument("--base", default="origin/main", help="diff base ref")
    run.add_argument("--pr", default="", help="PR number, for the log")
    run.add_argument("--repo", default=".", help="repository to review")
    run.add_argument("--model", default="", help="GPT Sol model id")
    run.add_argument(
        "--log-base", default="", help="directory whose .project-toolkit holds the log"
    )
    run.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    run.add_argument("--disable", action="store_true", help="skip the pass and log a skipped run")
    summ = sub.add_parser("summarize", help="total the run logs")
    summ.add_argument("--repo", default=".")
    summ.add_argument("--log-base", default="")
    return parser


def main(argv: list[str] | None = None, runner: Runner = codex_runner) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "summarize":
        repo = Path(args.repo).resolve()
        base = Path(args.log_base).resolve() if args.log_base else default_log_base(repo)
        _emit(summarize(paths.artifact_dir(LOG_SUBDIR, base=base)))
        return EXIT_OK
    return run_pass(args, runner)


if __name__ == "__main__":
    sys.exit(main())
