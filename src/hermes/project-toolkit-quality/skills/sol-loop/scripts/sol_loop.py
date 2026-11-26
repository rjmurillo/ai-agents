#!/usr/bin/env python3
"""Deterministic steps around a sol-loop round: gate, record, warn, ledger, totals.

The agent starts Sol itself (T3 ``delegate_task`` or a native Sol subagent).
This script holds the parts that must not depend on model judgment:

- ``gate``: before a round. Checks the off switch, the Sol route, the author's
  model family, the Sol model id, the fresh critic's output, and the 2-round cap.
- ``record``: after a round. Parses Sol's reply, drops findings without a
  file, line, or repro, drops nits, marks ``sol_only`` against the critic,
  and writes the round's run log (the ledger).
- ``unavailable``: Sol was started but failed. Prints the review model
  policy's WARN and logs it. Never names another reviewer.
- ``outcome``: records fixed, disagree, or declined for one finding.
- ``summarize``: totals every run log.

Stricter/looser/different than canonical: the review-model failure circuit
breaker in the governance AI review model policy names five failure classes
(timeout, 5xx, rate-limit, invalid-output, quota). A delegated agent fails in
more ways, so ``unavailable`` also accepts ``model-unsupported``, ``auth``,
``cancelled`` and ``unknown``. The reason string and user message are shared
with the policy; ``tests/skills/sol-loop/test_sol_loop_guards.py`` reads the
policy and fails when they drift.

Exit codes: 0 proceed or done (including a quiet skip), 1 round cap hit
(escalate to a human), 2 config error (bad model, missing or stale critic
output, unreadable input, run log not written), 3 Sol unavailable (WARN,
defer to a human).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_BOOTSTRAP = Path(__file__).resolve().parents[3] / "lib" / "bootstrap.py"
if not _BOOTSTRAP.is_file():
    raise ImportError(f"Cannot load skill bootstrap from {_BOOTSTRAP}")
_spec = spec_from_file_location("_skill_bootstrap", _BOOTSTRAP)
assert _spec is not None and _spec.loader is not None
_bootstrap = module_from_spec(_spec)
_spec.loader.exec_module(_bootstrap)
paths = _bootstrap.load_skill_paths(_BOOTSTRAP.parent, __file__)

from sol_cli import DEFAULT_TIMEOUT_SECONDS, available_runner, run_sol  # noqa: E402
from sol_findings import (  # noqa: E402
    OVERLAP_LINE_WINDOW,
    ReplyError,
    filter_findings,
    mark_sol_only,
    parse_reply,
)
from sol_git import (  # noqa: E402
    _critic_is_stale,
    _git,
    _repo_relative,
    default_log_base,
    resolve_commit,
)
from sol_ledger import (  # noqa: E402
    OUTCOMES,
    prior_rounds,
    replace_run_log,
    summarize,
    write_run_log,
)

SOL_MODEL_PATTERN = re.compile(r"^gpt-\d+(?:\.\d+)?-sol$")
MAX_ROUNDS = 2
UNAVAILABLE_REASON = "review-model-unavailable"
LOG_SUBDIR = "metrics/sol-loop"
SCHEMA_VERSION = 2
OFF_VALUES = frozenset({"0", "off", "false", "no", "disabled"})
ROUTES = ("t3", "native", "cli", "none")
AUTHOR_FAMILIES = ("anthropic", "openai", "unknown")
FAILURE_CLASSES = (
    "timeout",
    "5xx",
    "rate-limit",
    "invalid-output",
    "quota",
    "model-unsupported",
    "auth",
    "cancelled",
    "unknown",
)

EXIT_OK, EXIT_ESCALATE, EXIT_CONFIG, EXIT_UNAVAILABLE = 0, 1, 2, 3


def validate_model(model: str) -> str | None:
    """Return an error message when ``model`` is not a GPT Sol id."""
    if SOL_MODEL_PATTERN.fullmatch(model.strip()):
        return None
    return (
        f"model {model!r} refused: sol-loop accepts only a GPT Sol id such as "
        "gpt-6.1-sol. Gemini, Grok, Claude, and mixed Fusion ids are not allowed."
    )


def _read_text(path: Path, label: str) -> tuple[str, str]:
    """Return (text, error) for a required non-empty UTF-8 input file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return "", f"cannot read {label} {path}: {exc}"
    if not text.strip():
        return "", f"{label} {path} is empty"
    return text, ""


def _emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


@dataclasses.dataclass
class Run:
    """One invocation: its validated inputs, its log record, and where it logs."""

    critic_text: str
    record: dict
    log_dir: Path

    def finish(self, status: str, payload: dict, exit_code: int, **fields: object) -> int:
        """Log the run, print the result, and return the exit code.

        The result prints even when the log write fails, so a WARN is never
        lost; a run that reviewed but could not log exits 2.
        """
        self.record.update(status=status, **fields)
        log = write_run_log(self.record, self.log_dir)
        _emit({**payload, "log": str(log) if log else None})
        return EXIT_CONFIG if log is None and exit_code == EXIT_OK else exit_code


def _log_dir(args: argparse.Namespace, repo: Path) -> Path:
    base = Path(args.log_base).resolve() if args.log_base else default_log_base(repo)
    return paths.artifact_dir(LOG_SUBDIR, base=base)


def _base_record(args: argparse.Namespace, repo: Path, log_dir: Path, critic_text: str) -> dict:
    branch = _git(repo, "branch", "--show-current")
    # Key on the branch so rounds before and after the PR opens share one count.
    key = branch or (f"pr-{args.pr}" if args.pr else "local")
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "key": key,
        "pr": args.pr,
        "branch": branch,
        "head_sha": _git(repo, "rev-parse", "HEAD"),
        "round": prior_rounds(log_dir, key) + 1,
        "model": args.model,
        "author_family": args.author_family,
        "critic_sha256": hashlib.sha256(critic_text.encode("utf-8")).hexdigest()
        if critic_text
        else "",
        "overlap_rule": f"same file and line within {OVERLAP_LINE_WINDOW} of a critic path:line or range",
        "verdict": "",
        "failure_class": "",
        "findings": [],
        "dropped": [],
        "counts": {"raw": 0, "kept": 0, "dropped": 0, "sol_only": 0, "overlap": 0},
    }


def _start(
    args: argparse.Namespace,
    *,
    check_fresh: bool,
    require_critic: bool = True,
    skip_paths: tuple[Path, ...] = (),
) -> tuple[Run | None, str]:
    """Validate shared inputs and build the run record. Returns (run, error).

    Only ``gate`` checks critic freshness: it runs before Sol starts, so it is
    the step that enforces "after the critic". ``record`` and ``unavailable``
    run after Sol answered or failed, when edits in the checkout are expected.
    ``skip_paths`` are loop-owned files (the review brief) that never count as changes.
    """
    repo = Path(args.repo).resolve()
    critic = Path(args.critic_findings)
    log_dir = _log_dir(args, repo)
    error = validate_model(args.model)
    critic_text, critic_error = ("", "")
    if not error:
        critic_text, critic_error = _read_text(critic, "critic output")
        error = critic_error if require_critic else ""
    if not error and check_fresh and _critic_is_stale(repo, critic, log_dir, skip_paths):
        error = (
            "critic output is older than HEAD or an uncommitted change; "
            "rerun the fresh critic on the current code first"
        )
    if error:
        return None, error
    run = Run(
        critic_text=critic_text,
        record=_base_record(args, repo, log_dir, critic_text),
        log_dir=log_dir,
    )
    if critic_error:
        run.record["critic_error"] = critic_error
    return run, ""


def _skip_run(args: argparse.Namespace) -> int | None:
    """Log a skip, which needs no critic or model check, and return its exit code, else None."""
    if os.environ.get("AI_AGENTS_SOL_PASS", "").strip().lower() in OFF_VALUES:
        skip = "switched off by AI_AGENTS_SOL_PASS"
    elif args.author_family == "openai":
        skip = "same-family: a GPT model wrote this change, so Sol would not be a second family"
    else:
        return None
    repo = Path(args.repo).resolve()
    log_dir = _log_dir(args, repo)
    run = Run(critic_text="", record=_base_record(args, repo, log_dir, ""), log_dir=log_dir)
    return run.finish("skipped", {"verdict": "SKIPPED", "reason": skip}, EXIT_OK, skip_reason=skip)


def cmd_gate(args: argparse.Namespace) -> int:
    """Decide whether a Sol round may start."""
    no_route = {"none": "no Sol route in this harness", "cli": "no codex or droid CLI on PATH"}
    if args.route in no_route and (args.route == "none" or not available_runner()):
        _emit({"verdict": "SKIPPED", "reason": no_route[args.route], "log": None})
        return EXIT_OK
    if (skipped := _skip_run(args)) is not None:
        return skipped
    run, error = _start(args, check_fresh=True)
    if run is None:
        print(f"sol_loop: {error}", file=sys.stderr)
        return EXIT_CONFIG
    if run.record["round"] > MAX_ROUNDS:
        reason = f"{MAX_ROUNDS} Sol rounds already logged for {run.record['key']}; hand open findings to a human"
        return run.finish("escalated", {"verdict": "ESCALATE", "reason": reason}, EXIT_ESCALATE)
    payload = {
        "verdict": "PROCEED",
        "head_sha": run.record["head_sha"],
        "round": run.record["round"],
        "frozen": run.record["round"] >= 2,
        "author_family_flag": "unknown author family; overlap may be same-family"
        if args.author_family == "unknown"
        else "",
    }
    _emit(payload)
    return EXIT_OK


def _unavailable(run: Run, failure_class: str, detail: str) -> int:
    message = f"Review model unavailable, deferring to human.\nModel: {run.record['model']} | Failure: {failure_class}"
    payload = {
        "verdict": "WARN",
        "reason": UNAVAILABLE_REASON,
        "message": message,
        "detail": detail,
    }
    return run.finish("unavailable", payload, EXIT_UNAVAILABLE, failure_class=failure_class)


def cmd_unavailable(args: argparse.Namespace) -> int:
    """Log a started Sol round that failed, and print the policy WARN.

    An unreadable critic file does not block the WARN; it is noted in the log.
    """
    run, error = _start(args, check_fresh=False, require_critic=False)
    if run is None:
        print(f"sol_loop: {error}", file=sys.stderr)
        return EXIT_CONFIG
    return _unavailable(run, args.failure_class, args.detail)


def _started(
    args: argparse.Namespace, *, check_fresh: bool, skip_paths: tuple[Path, ...] = ()
) -> tuple[Run | None, int]:
    """Start a round that will produce a reply. Returns (run, exit code if it must stop)."""
    run, error = _start(args, check_fresh=check_fresh, skip_paths=skip_paths)
    if run is None:
        print(f"sol_loop: {error}", file=sys.stderr)
        return None, EXIT_CONFIG
    if run.record["round"] > MAX_ROUNDS:
        reason = f"{MAX_ROUNDS} Sol rounds already logged for {run.record['key']}"
        return None, run.finish(
            "escalated", {"verdict": "ESCALATE", "reason": reason}, EXIT_ESCALATE
        )
    return run, EXIT_OK


def _apply_reviewed_head(run: Run, args: argparse.Namespace) -> str:
    """Log the revision Sol reviewed. Returns an error message, "" when fine.

    Sol may review a commit while HEAD moves on; ``head_sha`` then names the
    reviewed commit and ``head_at_record`` the HEAD when the record was written.
    """
    if not args.reviewed_head:
        return ""
    reviewed = resolve_commit(Path(args.repo).resolve(), args.reviewed_head.strip())
    if not reviewed:
        return f"--reviewed-head {args.reviewed_head!r} is not a commit in {args.repo}"
    if reviewed != run.record["head_sha"]:
        run.record.update(head_at_record=run.record["head_sha"], head_sha=reviewed)
    return ""


def cmd_record(args: argparse.Namespace) -> int:
    """Parse Sol's reply for this round and write the ledger."""
    run, code = _started(args, check_fresh=False)
    if run is None:
        return code
    error = _apply_reviewed_head(run, args)
    if error:
        print(f"sol_loop: {error}", file=sys.stderr)
        return EXIT_CONFIG
    reply, error = _read_text(Path(args.reply), "Sol reply")
    if error:
        return _unavailable(run, "invalid-output", error)
    return _record_reply(run, args, reply)


def cmd_review(args: argparse.Namespace) -> int:
    """Last-resort route: run Sol through a native CLI, then record the reply.

    This step starts Sol, so it honors the same skip switches and checks critic
    freshness like ``gate``.
    """
    if (skipped := _skip_run(args)) is not None:
        return skipped
    run, code = _started(args, check_fresh=True, skip_paths=(Path(args.brief_file),))
    if run is None:
        return code
    brief, error = _read_text(Path(args.brief_file), "brief")
    if error:
        print(f"sol_loop: {error}", file=sys.stderr)
        return EXIT_CONFIG
    runner = available_runner()
    if not runner:
        print(
            "sol_loop: no codex or droid CLI on PATH; use gate --route cli first", file=sys.stderr
        )
        return EXIT_CONFIG
    run.record["runner"] = runner
    result = run_sol(runner, args.model, brief, Path(args.repo).resolve(), args.timeout)
    if not result.ok:
        return _unavailable(run, result.failure_class, result.detail)
    return _record_reply(run, args, result.text)


def _record_reply(run: Run, args: argparse.Namespace, reply: str) -> int:
    """Parse one reply into the ledger, or take the WARN path when it is not a review."""
    try:
        verdict, raw = parse_reply(reply)
    except ReplyError as exc:
        return _unavailable(run, "invalid-output", str(exc))
    if verdict == "CHANGES" and not raw:
        return _unavailable(
            run, "invalid-output", "verdict CHANGES with no S<n> [severity] finding lines"
        )
    kept, dropped = filter_findings([_repo_relative(Path(args.repo).resolve(), f) for f in raw])
    marked = [{**f, "outcome": "open"} for f in mark_sol_only(kept, run.critic_text)]
    sol_only = sum(1 for f in marked if f["sol_only"])
    counts = {
        "raw": len(raw),
        "kept": len(marked),
        "dropped": len(dropped),
        "sol_only": sol_only,
        "overlap": len(marked) - sol_only,
    }
    payload: dict[str, object] = {"verdict": verdict, "findings": marked, "counts": counts}
    if "head_at_record" in run.record:
        payload["head_moved"] = True
    return run.finish(
        "ok", payload, EXIT_OK, verdict=verdict, findings=marked, dropped=dropped, counts=counts
    )


def cmd_outcome(args: argparse.Namespace) -> int:
    """Record what happened to one finding in a run log."""
    path = Path(args.run)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"sol_loop: cannot read run log {path}: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    finding = next((f for f in record.get("findings", []) if f.get("id") == args.id), None)
    if finding is None:
        print(f"sol_loop: no finding {args.id!r} in {path}", file=sys.stderr)
        return EXIT_CONFIG
    finding.update(outcome=args.outcome, evidence=args.evidence)
    if error := replace_run_log(path, record):
        print(f"sol_loop: cannot write run log {path}: {error}", file=sys.stderr)
        return EXIT_CONFIG
    _emit({"id": args.id, "outcome": args.outcome, "log": str(path)})
    return EXIT_OK


def cmd_summarize(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    base = Path(args.log_base).resolve() if args.log_base else default_log_base(repo)
    _emit(summarize(paths.artifact_dir(LOG_SUBDIR, base=base)))
    return EXIT_OK


def _add_shared(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--critic-findings", required=True, help="file holding the fresh critic's output"
    )
    parser.add_argument("--model", required=True, help="GPT Sol model id resolved for this round")
    parser.add_argument(
        "--author-family",
        required=True,
        choices=AUTHOR_FAMILIES,
        help="family of the model that wrote the change",
    )
    parser.add_argument("--pr", default="", help="PR number, for the log")
    parser.add_argument("--repo", default=".", help="checkout under review")
    parser.add_argument(
        "--log-base", default="", help="directory whose artifact root holds the log"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic steps around a sol-loop round.")
    sub = parser.add_subparsers(dest="command", required=True)
    gate = sub.add_parser("gate", help="decide whether a Sol round may start")
    _add_shared(gate)
    gate.add_argument("--route", required=True, choices=ROUTES, help="how this harness reaches Sol")
    record = sub.add_parser("record", help="parse Sol's reply and write the ledger")
    _add_shared(record)
    record.add_argument("--reply", required=True, help="file holding Sol's reply text")
    record.add_argument(
        "--reviewed-head", default="", help="commit Sol reviewed, when HEAD moved since"
    )
    review = sub.add_parser(
        "review", help="last resort: run Sol through codex or droid, then record"
    )
    _add_shared(review)
    review.add_argument("--brief-file", required=True, help="file holding the round brief")
    review.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    unavailable = sub.add_parser("unavailable", help="log a started Sol round that failed")
    _add_shared(unavailable)
    unavailable.add_argument("--failure-class", required=True, choices=FAILURE_CLASSES)
    unavailable.add_argument("--detail", default="", help="error text from the failed round")
    outcome = sub.add_parser("outcome", help="record what happened to one finding")
    outcome.add_argument("--run", required=True, help="run log file from record")
    outcome.add_argument("--id", required=True, help="finding id, such as S1")
    outcome.add_argument("--outcome", required=True, choices=OUTCOMES)
    outcome.add_argument(
        "--evidence", default="", help="file:line, test, or output that backs the outcome"
    )
    summ = sub.add_parser("summarize", help="total the run logs")
    summ.add_argument("--repo", default=".")
    summ.add_argument("--log-base", default="")
    return parser


COMMANDS = {
    "gate": cmd_gate,
    "record": cmd_record,
    "review": cmd_review,
    "unavailable": cmd_unavailable,
    "outcome": cmd_outcome,
    "summarize": cmd_summarize,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (OSError, ValueError) as exc:
        print(f"sol_loop: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
