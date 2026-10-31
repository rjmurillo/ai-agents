#!/usr/bin/env python3
"""Bounded longitudinal pilot: vendor-only vs vendor plus validated local context (issue #6993).

Extends `eval_skill_bootstrap_capability.py` (grading helpers and the print-mode
runner) and `_human_minutes.py` (timed correction minutes). Adds no framework.

    eval_longitudinal_pilot.py estimate --reps 3
    eval_longitudinal_pilot.py verify-gold --checkout <repo> --phase pre
    eval_longitudinal_pilot.py dry-run --out-dir OUT
    eval_longitudinal_pilot.py prepare-post --checkout <post-worktree>
    eval_longitudinal_pilot.py live --checkout-pre A --checkout-post B \\
        --ceiling-usd 5 --out-dir OUT

`estimate`, `verify-gold`, `dry-run`, and `prepare-post` never call a model. `live`
spawns `claude -p` (a paid call) and refuses to start without `--ceiling-usd`. It
stops before the call that could cross the ceiling and reports the run incomplete.
Published files hold hashes, counts, and scores only: no transcript, no answer text.

Exit codes: 0 ok, 1 logic (a cell errored, or gold does not match the checkout),
2 config (bad pilot file, ceiling, minutes file, or checkout), 3 external (claude
CLI or git missing).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _longitudinal_pilot as lp
import _longitudinal_report as rep
import eval_skill_bootstrap_capability as cap
from _human_minutes import HumanMinutesError, load_human_minutes, lookup, unmatched

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PILOT = REPO_ROOT / "evals" / "longitudinal-pilot" / "fixtures" / "pilot.json"
PRIOR_RUNS = "evals/skill-bootstrap-capability/runs/*/cap-*.jsonl"
TEMPLATE = "templates/skills/skill-bootstrap.SKILL.md.tmpl"
DEFAULT_RESERVE_USD = 0.25  # above the largest per-call cost in PRIOR_RUNS (about 0.21)
PRICING_BASIS = (
    "docs/SKILL-AUTHORING.md model pricing table (haiku $1/$5 per MTok); "
    "measured cost_usd in PRIOR_RUNS"
)
EXIT_OK, EXIT_LOGIC, EXIT_CONFIG, EXIT_EXTERNAL = 0, 1, 2, 3

# (condition, task, prompt, checkout, model) -> run_one-shaped record
Runner = Callable[[str, dict[str, Any], str, Path, str], dict[str, Any]]


def _git(checkout: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=checkout, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def scripted_runner(pilot: dict[str, Any]) -> Runner:
    """Deterministic runner for the dry run. Costs are unmeasured (None), never invented."""
    script = pilot["dry_run_script"]

    def run(
        condition: str, task: dict[str, Any], prompt: str, checkout: Path, model: str
    ) -> dict[str, Any]:
        paths = script[condition][task["id"]]
        text = f"Scripted answer.\n```json\n{json.dumps({task['answer_key']: paths})}\n```"
        return {"result": text, "is_error": False, "cost_usd": None, "wall_s": 0.0}

    return run


def live_runner(
    condition: str, task: dict[str, Any], prompt: str, checkout: Path, model: str
) -> dict[str, Any]:
    """One fresh `claude -p` session per call. Paid. Only `live` reaches this."""
    record: dict[str, Any] = cap.run_one(checkout, prompt, model)
    return record


def execute(
    pilot: dict[str, Any],
    runner: Runner,
    checkouts: dict[str, Path],
    model: str,
    reps: int,
    ledger: lp.Ledger | None,
    minutes: dict[tuple[str, str, int], float] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the frozen sequence. Conditions interleave per task so a stop leaves both comparable."""
    records: list[dict[str, Any]] = []
    started = time.monotonic()
    start_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for repeat in range(reps):
        states = {c: lp.PilotState() for c in lp.CONDITIONS}
        for task in pilot["tasks"]:
            root = checkouts[task["phase"]]
            for condition in lp.CONDITIONS:
                ctx = lp.build_context(pilot, condition, task, states[condition], root)
                base = {
                    "condition": condition,
                    "task_id": task["id"],
                    "role": task["role"],
                    "phase": task["phase"],
                    "repeat": repeat,
                    "model": model,
                    "context": {
                        "fact_ids": ctx.fact_ids,
                        "stale_fact_ids": ctx.stale_fact_ids,
                        "correction_ids": ctx.correction_ids,
                        "tokens_est": ctx.tokens_est,
                    },
                }
                if ledger is not None and not ledger.allow():
                    records.append({**base, "skipped": "ceiling"})
                    continue
                res = runner(condition, task, lp.build_prompt(pilot, task, ctx), root, model)
                if ledger is not None:
                    ledger.charge(res.get("cost_usd"))
                text = res.get("result") or ""
                common = {
                    **base,
                    "cost_usd": res.get("cost_usd"),
                    "active_s": float(res.get("wall_s") or 0.0),
                    "human_minutes": lookup(minutes, condition, task["id"], repeat),
                    "decision_points": task["decision_points"],
                    "clarification_requests": lp.count_clarifications(text),
                    "answer_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                }
                if res.get("is_error"):
                    records.append(
                        {**common, "is_error": True, "error_kind": res.get("error_kind", "error")}
                    )
                else:
                    graded = lp.grade_task(task, cap.extract_answer(text))
                    records.append({**common, "is_error": False, **graded})
                if condition == "local_context":
                    states[condition].retain(task)
    window = {
        "start_utc": start_iso,
        "end_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    return records, window


def _config(
    pilot: dict[str, Any], pre: Path, model: str, harness: str, reps: int
) -> dict[str, Any]:
    return {
        "model": model,
        "harness": harness,
        "reps": reps,
        "pilot_revision": pilot["revision"],
        "template_revision": _git(pre, "log", "-1", "--format=%H", "--", TEMPLATE) or "unknown",
        "local_context_revision": lp.context_revision(pilot),
    }


def _write(out_dir: Path, records: list[dict[str, Any]], report: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "records.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8"
    )
    (out_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _load_minutes(
    path: str | None, pilot: dict[str, Any], reps: int
) -> dict[tuple[str, str, int], float] | None:
    if path is None:
        return None
    minutes = load_human_minutes(Path(path), known_controls=lp.CONDITIONS)
    produced = {(c, t["id"], r) for c in lp.CONDITIONS for t in pilot["tasks"] for r in range(reps)}
    stray = unmatched(minutes, produced)
    if stray:
        raise lp.PilotError(f"minutes rows match no planned cell: {stray}")
    return dict(minutes)


def _verify_gold(pilot: dict[str, Any], root: Path, phase: str) -> list[str]:
    bad = []
    for task in pilot["tasks"]:
        if task["phase"] == phase and lp.derive_gold(task, root) != sorted(task["gold"]):
            bad.append(task["id"])
    return bad


def cmd_estimate(args: argparse.Namespace) -> int:
    pilot = lp.load_pilot(Path(args.pilot))
    costs, tokens = [], []
    for path in sorted(glob.glob(str(REPO_ROOT / PRIOR_RUNS))):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            row = json.loads(line) if line.strip() else {}
            if isinstance(row.get("cost_usd"), (int, float)):
                costs.append(float(row["cost_usd"]))
            if isinstance(row.get("output_tokens"), int):
                tokens.append(row["output_tokens"])
    calls = len(pilot["tasks"]) * len(lp.CONDITIONS) * args.reps
    out: dict[str, Any] = {
        "calls": calls,
        "reps": args.reps,
        "pricing_basis": PRICING_BASIS,
        "prior_cells": len(costs),
        "input_tokens": "unknown: prior records do not carry input tokens",
    }
    if costs:
        low, mid, high = min(costs), statistics.mean(costs), max(costs)
        out["per_call_usd"] = {"min": round(low, 4), "mean": round(mid, 4), "max": round(high, 4)}
        out["total_usd"] = {
            "low": round(calls * low, 2),
            "mid": round(calls * mid, 2),
            "high": round(calls * high, 2),
        }
        out["output_tokens"] = {
            "per_call_mean": round(statistics.mean(tokens)),
            "total_mid": round(calls * statistics.mean(tokens)),
        }
        out["caveat"] = (
            "Prior cells ran different, heavier tasks on claude-haiku-5-5; "
            "this sequence is grep-sized, so the real cost is likely nearer the low end."
        )
    else:
        out["total_usd"] = "unknown: no prior cost records found"
    print(json.dumps(out, indent=2))
    return EXIT_OK


def cmd_verify_gold(args: argparse.Namespace) -> int:
    pilot = lp.load_pilot(Path(args.pilot))
    bad = _verify_gold(pilot, Path(args.checkout), args.phase)
    print(json.dumps({"phase": args.phase, "mismatched": bad}))
    return EXIT_LOGIC if bad else EXIT_OK


def cmd_prepare_post(args: argparse.Namespace) -> int:
    pilot = lp.load_pilot(Path(args.pilot))
    root, (old, new) = Path(args.checkout), pilot["repo_change"]["rename"]
    if not (root / old).is_file() or (root / new).exists():
        print(f"ERROR: {root} must hold {old} and not {new}", file=sys.stderr)
        return EXIT_CONFIG
    return (
        EXIT_OK
        if subprocess.run(["git", "mv", old, new], cwd=root, check=False).returncode == 0
        else EXIT_EXTERNAL
    )


def cmd_dry_run(args: argparse.Namespace) -> int:
    pilot = lp.load_pilot(Path(args.pilot))
    root = Path(args.checkout)
    minutes = _load_minutes(args.minutes, pilot, args.reps)
    records, window = execute(
        pilot,
        scripted_runner(pilot),
        {"pre": root, "post": root},
        "scripted",
        args.reps,
        None,
        minutes,
    )
    report = rep.build_report(
        pilot,
        records,
        _config(pilot, root, "scripted", "scripted-dry-run", args.reps),
        window,
        None,
        None,
        "dry_run",
    )
    _write(Path(args.out_dir), records, report)
    print(json.dumps({"verdict": report["verdict"], "out_dir": args.out_dir}))
    return EXIT_OK


def cmd_live(args: argparse.Namespace) -> int:
    pilot = lp.load_pilot(Path(args.pilot))
    ledger = lp.Ledger(args.ceiling_usd, args.reserve_usd, args.max_calls)
    if shutil.which("claude") is None:
        print("ERROR: claude CLI not found", file=sys.stderr)
        return EXIT_EXTERNAL
    pre, post = Path(args.checkout_pre), Path(args.checkout_post)
    for phase, root in (("pre", pre), ("post", post)):
        if not root.is_dir():
            raise lp.PilotError(f"--checkout-{phase} {root} is not a directory")
        bad = _verify_gold(pilot, root, phase)
        if bad:
            raise lp.PilotError(
                f"gold does not match the {phase} checkout for {bad}; no spend started"
            )
    minutes = _load_minutes(args.minutes, pilot, args.reps)
    version = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    records, window = execute(
        pilot, live_runner, {"pre": pre, "post": post}, args.model, args.reps, ledger, minutes
    )
    report = rep.build_report(
        pilot,
        records,
        _config(pilot, pre, args.model, f"claude-cli {version or 'unknown'}", args.reps),
        window,
        ledger,
        args.bootstrap_cost_usd,
        "live",
    )
    _write(Path(args.out_dir), records, report)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "complete": report["complete"],
                "ceiling": report["ceiling"],
            }
        )
    )
    return EXIT_LOGIC if any(r.get("is_error") for r in records) else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, fn: Callable[[argparse.Namespace], int]) -> argparse.ArgumentParser:
        sp = sub.add_parser(name)
        sp.add_argument("--pilot", default=str(DEFAULT_PILOT))
        sp.set_defaults(fn=fn)
        return sp

    add("estimate", cmd_estimate).add_argument("--reps", type=int, default=1)
    vg = add("verify-gold", cmd_verify_gold)
    vg.add_argument("--checkout", required=True)
    vg.add_argument("--phase", choices=lp.PHASES, required=True)
    add("prepare-post", cmd_prepare_post).add_argument("--checkout", required=True)
    dr = add("dry-run", cmd_dry_run)
    dr.add_argument("--checkout", default=str(REPO_ROOT))
    dr.add_argument("--out-dir", required=True)
    dr.add_argument("--reps", type=int, default=1)
    dr.add_argument("--minutes")
    lv = add("live", cmd_live)
    lv.add_argument("--checkout-pre", required=True)
    lv.add_argument("--checkout-post", required=True)
    lv.add_argument("--ceiling-usd", type=float, required=True, help="hard spend ceiling; required")
    lv.add_argument("--reserve-usd", type=float, default=DEFAULT_RESERVE_USD)
    lv.add_argument("--max-calls", type=int)
    lv.add_argument("--reps", type=int, default=1)
    lv.add_argument("--model", default=cap.DEFAULT_MODEL)
    lv.add_argument("--minutes")
    lv.add_argument("--bootstrap-cost-usd", type=float)
    lv.add_argument("--out-dir", required=True)
    args = p.parse_args(argv)
    if getattr(args, "reps", 1) < 1:
        print("ERROR: --reps must be >= 1", file=sys.stderr)
        return EXIT_CONFIG
    try:
        code: int = args.fn(args)
        return code
    except (lp.PilotError, HumanMinutesError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
