#!/usr/bin/env python3
"""Capability eval for skill-bootstrap: before/after on real repository tasks.

Runs each frozen task in `evals/skill-bootstrap-capability/fixtures/tasks.json` through
the Claude CLI inside a checkout that carries one version of the skill, then
grades the final JSON answer against gold fixed before implementation. The
condition differs only by the checkout, so the score difference measures the
capability the skill version gives the agent, not what the agent knows alone.

Usage:
    python3 scripts/eval/eval_skill_bootstrap_capability.py run \\
        --checkout <worktree> --condition before --reps 3 --out before.jsonl
    python3 scripts/eval/eval_skill_bootstrap_capability.py score \\
        --runs before.jsonl after.jsonl --out report.json

Exit codes:
    0 ok
    1 logic (a scored condition has no gradable run)
    2 config (bad tasks file, missing checkout, unreadable runs file,
      or runs that do not cover every task under both before and after)
    3 external (Claude CLI missing)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = REPO_ROOT / "evals" / "skill-bootstrap-capability" / "fixtures" / "tasks.json"
DEFAULT_MODEL = "claude-haiku-5-5"
RUN_TIMEOUT_S = 1200
# Narrow grant, not a sandbox. Print mode denies any tool outside this list, so
# Edit, Write, and unlisted shell commands are refused (an unlisted `touch` was).
# A prefix grant still accepts extra flags: `git log --output=<file>` writes a file,
# and a skill script can write where its own flags send it. Run every evaluation in
# a disposable worktree; the recorded runs did.
_SKILL_SCRIPTS = (
    "bootstrap_mine",
    "bootstrap_forms",
    "bootstrap_eval",
    "bootstrap_drift",
    "bootstrap_boundary",
)
READ_ONLY_TOOLS = (
    "Read",
    "Grep",
    "Glob",
    "Bash(git log:*)",
    "Bash(git show:*)",
    "Bash(git ls-tree:*)",
    "Bash(git rev-parse:*)",
    "Bash(git rev-list:*)",
    "Bash(git diff-tree:*)",
    *(
        f"Bash(python3 .claude/skills/skill-bootstrap/scripts/{name}.py:*)"
        for name in _SKILL_SCRIPTS
    ),
)
CONDITIONS = ("before", "after")
JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def load_tasks(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("tasks"), list) or not data["tasks"]:
        raise ValueError(f"{path}: 'tasks' must be a non-empty list")
    for task in data["tasks"]:
        for key in ("id", "prompt", "grader", "gold", "answer_key"):
            if key not in task:
                raise ValueError(f"{path}: task missing '{key}'")
    return data


def extract_answer(text: str) -> dict[str, Any] | None:
    """Return the last fenced JSON object in `text`, or None."""
    for raw in reversed(JSON_BLOCK.findall(text or "")):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _f1(predicted: set[str], gold: set[str]) -> dict[str, float]:
    hits = len(predicted & gold)
    precision = hits / len(predicted) if predicted else 0.0
    recall = hits / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if hits else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _norm_path(value: str) -> str:
    return re.split(r"::|:\d", value.strip().strip("`"), maxsplit=1)[0].rstrip("/")


def grade(task: dict[str, Any], answer: dict[str, Any] | None) -> dict[str, float]:
    # Only the field the task's prompt names counts; any other key earns nothing.
    values = (answer or {}).get(task["answer_key"])
    if not isinstance(values, list):
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    kind = task["grader"]
    if kind == "pairs_f1":
        fields = task.get("answer_fields", ["skill", "path"])

        def key(item: dict[str, Any]) -> str:
            parts = [str(item.get(f, "")).strip() for f in fields]
            if fields[-1] == "path":
                parts[-1] = _norm_path(parts[-1])
            return "|".join(parts)

        ignore = {key(i) for i in task.get("ignore", [])}
        gold = {key(g) for g in task["gold"]}
        predicted = {key(i) for i in values if isinstance(i, dict)} - ignore
        return _f1(predicted, gold)
    if kind == "set_f1_prefix":
        predicted = {str(v).strip().lower()[:9] for v in values if len(str(v).strip()) >= 7}
        gold = {g[:9] for g in task["gold"]}

        def hits(a: str, b: str) -> bool:
            return a.startswith(b) or b.startswith(a)

        matched_gold = {g for g in gold if any(hits(g, p) for p in predicted)}
        matched_pred = {p for p in predicted if any(hits(p, g) for g in gold)}
        precision = len(matched_pred) / len(predicted) if predicted else 0.0
        recall = len(matched_gold) / len(gold)
        f1 = 2 * precision * recall / (precision + recall) if matched_gold else 0.0
        return {"precision": precision, "recall": recall, "f1": f1}
    if kind == "set_f1":
        return _f1({_norm_path(str(v)) for v in values}, set(task["gold"]))
    raise ValueError(f"unknown grader '{kind}'")


def run_one(checkout: Path, prompt: str, model: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--model",
                model,
                "--output-format",
                "json",
                "--allowedTools",
                *READ_ONLY_TOOLS,
                "--disallowedTools",
                "Edit",
                "Write",
                "NotebookEdit",
            ],
            cwd=checkout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUN_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        return {
            "result": "",
            "is_error": True,
            "num_turns": None,
            "cost_usd": None,
            "output_tokens": None,
            "wall_s": round(elapsed, 1),
        }
    elapsed = time.monotonic() - started
    try:
        meta = json.loads(proc.stdout)
    except json.JSONDecodeError:
        meta = None
    if not isinstance(meta, dict):
        meta = {"is_error": True, "result": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}
    usage = meta.get("usage") or {}
    return {
        "result": meta.get("result", ""),
        "is_error": bool(meta.get("is_error")) or proc.returncode != 0,
        "num_turns": meta.get("num_turns"),
        "cost_usd": meta.get("total_cost_usd"),
        "output_tokens": usage.get("output_tokens"),
        "wall_s": round(elapsed, 1),
    }


def cmd_run(args: argparse.Namespace) -> int:
    if shutil.which("claude") is None:
        print("ERROR: claude CLI not found", file=sys.stderr)
        return 3
    checkout = Path(args.checkout).resolve()
    if not (checkout / ".claude" / "skills" / "skill-bootstrap" / "SKILL.md").is_file():
        print(f"ERROR: {checkout} carries no skill-bootstrap", file=sys.stderr)
        return 2
    data = load_tasks(Path(args.tasks))
    unknown = sorted(set(args.task or ()) - {t["id"] for t in data["tasks"]})
    if unknown or args.reps < 1:
        print(
            f"ERROR: unknown task(s) {unknown}" if unknown else "ERROR: --reps must be >= 1",
            file=sys.stderr,
        )
        return 2
    selected = [t for t in data["tasks"] if not args.task or t["id"] in args.task]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout.strip()
    with Path(args.out).open("a", encoding="utf-8") as out:
        for rep in range(args.reps):
            for task in selected:
                prompt = f"{data['preamble']}\n\n{task['prompt']}"
                record = run_one(checkout, prompt, args.model)
                answer = extract_answer(record["result"])
                record.update(
                    condition=args.condition,
                    task=task["id"],
                    rep=rep,
                    model=args.model,
                    checkout_head=head,
                    answer=answer,
                    score=grade(task, answer),
                )
                out.write(json.dumps(record) + "\n")
                out.flush()
                print(
                    f"{args.condition} {task['id']} rep{rep} f1={record['score']['f1']:.2f} "
                    f"turns={record['num_turns']} wall={record['wall_s']}s",
                    flush=True,
                )
    return 0


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


# Field -> accepted types. `bool` is excluded from the numeric fields explicitly below.
RECORD_TYPES: dict[str, tuple[type, ...]] = {
    "task": (str,),
    "condition": (str,),
    "model": (str,),
    "checkout_head": (str,),
    "answer": (dict, type(None)),
    "is_error": (bool,),
    "num_turns": (int, type(None)),
    "cost_usd": (int, float, type(None)),
    "wall_s": (int, float),
}


def _record_error(rec: object) -> str | None:
    if not isinstance(rec, dict):
        return "not a run record"
    for key, types in RECORD_TYPES.items():
        if key not in rec:
            return f"missing '{key}'"
        value = rec[key]
        if not isinstance(value, types) or (bool not in types and isinstance(value, bool)):
            return f"'{key}' has type {type(value).__name__}"
    return None


def load_records(path: str, task_ids: set[str]) -> list[dict[str, Any]]:
    """Parse one run file; raise ValueError on any line that is not a usable record."""
    text = Path(path).read_text(encoding="utf-8")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        rec = json.loads(line)
        if error := _record_error(rec):
            raise ValueError(f"{path}:{number}: {error}")
        if rec["task"] not in task_ids:
            raise ValueError(f"{path}:{number}: unknown task {rec['task']!r}")
        records.append(rec)
    return records


def _matrix_error(records: list[dict[str, Any]], tasks: dict[str, Any]) -> str | None:
    """Name the first gap in the task x condition matrix, or None when it is complete."""
    unexpected = sorted({str(r["condition"]) for r in records} - set(CONDITIONS))
    if unexpected:
        return f"unexpected condition(s) {unexpected}; expected {list(CONDITIONS)}"
    present = {(r["task"], r["condition"]) for r in records}
    missing = [f"{t}/{c}" for t in sorted(tasks) for c in CONDITIONS if (t, c) not in present]
    if missing:
        return f"no runs for {', '.join(missing)}"
    return _confound_error(records)


def _confound_error(records: list[dict[str, Any]]) -> str | None:
    """Refuse a comparison that varies anything but the checkout between conditions.

    One model across every run, one checkout per task and condition, and a
    different checkout for `before` and `after` on each task. Different tasks may
    use different `after` checkouts, as the recorded T4 runs did.
    """
    models = sorted({r["model"] for r in records})
    if len(models) > 1:
        return f"runs mix models {models}"
    heads: dict[tuple[str, str], set[str]] = {}
    for r in records:
        heads.setdefault((r["task"], r["condition"]), set()).add(r["checkout_head"])
    for (task, condition), seen in sorted(heads.items()):
        if len(seen) > 1:
            return f"{task}/{condition} ran on {len(seen)} checkouts"
    for task in sorted({t for t, _ in heads}):
        if heads[(task, "before")] == heads[(task, "after")]:
            return f"{task} ran before and after on the same checkout"
    return None


def cmd_score(args: argparse.Namespace) -> int:
    tasks = {t["id"]: t for t in load_tasks(Path(args.tasks))["tasks"]}
    records: list[dict[str, Any]] = []
    for path in args.runs:
        try:
            records.extend(load_records(path, set(tasks)))
        except (OSError, ValueError) as exc:
            print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
            return 2
    if error := _matrix_error(records, tasks):
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    # Re-grade stored answers so a gold correction applies to every condition alike.
    for rec in records:
        answer = rec["answer"] if isinstance(rec["answer"], dict) else None
        rec["score"] = grade(tasks[rec["task"]], answer)
    report: dict[str, Any] = {}
    for rec in records:
        cell = report.setdefault(rec["task"], {}).setdefault(rec["condition"], [])
        cell.append(rec)
    summary: dict[str, Any] = {}
    for task, conditions in sorted(report.items()):
        summary[task] = {}
        for condition, recs in sorted(conditions.items()):
            # A failed CLI call is a harness error, not a wrong answer: count it, score the rest.
            graded = [r for r in recs if not r["is_error"]]
            summary[task][condition] = {
                "runs": len(recs),
                "errors": len(recs) - len(graded),
                "f1": _mean([r["score"]["f1"] for r in graded]),
                "precision": _mean([r["score"]["precision"] for r in graded]),
                "recall": _mean([r["score"]["recall"] for r in graded]),
                "turns": _mean([r["num_turns"] for r in graded if r["num_turns"] is not None]),
                "cost_usd": _mean([r["cost_usd"] for r in graded if r["cost_usd"] is not None]),
                "wall_s": _mean([r["wall_s"] for r in graded]),
            }
    text = json.dumps(summary, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    empty = any(c["runs"] == c["errors"] for t in summary.values() for c in t.values())
    return 1 if empty else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="run tasks in one checkout")
    p_run.add_argument("--checkout", required=True)
    p_run.add_argument("--condition", required=True, choices=CONDITIONS)
    p_run.add_argument("--tasks", default=str(DEFAULT_TASKS))
    p_run.add_argument("--task", action="append", help="limit to these task ids")
    p_run.add_argument("--model", default=DEFAULT_MODEL)
    p_run.add_argument("--reps", type=int, default=3)
    p_run.add_argument("--out", required=True)
    p_score = sub.add_parser("score", help="aggregate run records")
    p_score.add_argument("--runs", nargs="+", required=True)
    p_score.add_argument("--tasks", default=str(DEFAULT_TASKS))
    p_score.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        return cmd_run(args) if args.cmd == "run" else cmd_score(args)
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
