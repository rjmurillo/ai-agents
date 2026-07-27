#!/usr/bin/env python3
"""Held-out-gated optimization rails for agents, rules, hooks, and prompts.

The optimizing agent proposes the edits. This CLI decides whether they
survive. Splitting that responsibility is the whole point: an author who
scores an edit on the material they were reading while making it learns
nothing about whether the edit generalizes, and the existing eval harness
scores exactly that way.

A loop step looks like this. Every command reads and writes JSON on stdout,
so the loop is drivable from a shell or from an agent's tool calls.

    optimize-artifact.py extract --kind agent --input report.json > base.json
    optimize-artifact.py split --results base.json --seed run-7 > split.json
    optimize-artifact.py budget --step 3 --total 12
    optimize-artifact.py buffer-check --buffer rejected.json --patches p.json
    optimize-artifact.py apply --file target.md --patches p.json --budget 3
    # rerun the real scorer here, then extract its output to cand.json
    optimize-artifact.py gate --incumbent base.json --candidate cand.json \\
        --split split.json --incumbent-fingerprint "$FP"

`gate` scores both sides itself from the split's held-out `sel` group rather
than accepting two numbers. Taking bare numbers would make the loop's most
damaging mistake, gating on optimize-set scores, a typo away at every step.

Exit codes follow ADR-035:

    0  accept, novel, or plain success
    1  reject, already-rejected, or a refused patch
    2  bad arguments, unreadable input, or malformed data

A REJECT is exit 1 because it is a decision, not a crash, and a shell loop
wants to branch on it. Every path still prints JSON, so a caller that needs
to tell REJECT from a config failure can read `decision` instead of guessing
from the code.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _optimizer_adapters import (  # noqa: E402
    AdapterError,
    agent_results,
    pytest_results,
    rule_results,
)
from _optimizer_core import (  # noqa: E402
    Patch,
    apply_patches,
    buffer_contains,
    edit_budget,
    gate,
    patch_fingerprint,
    score,
    split_tasks,
)

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

_GROUPS = ("opt", "sel", "test")


class ConfigError(Exception):
    """Input was unreadable or malformed. Maps to exit 2."""


def _emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"no such file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"no such file: {path}") from exc
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc


def _read_results(path: Path) -> dict[str, bool]:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a JSON object of task id to boolean")
    bad = [k for k, v in data.items() if not isinstance(v, bool)]
    if bad:
        raise ConfigError(
            f"{path} has non-boolean results for: {', '.join(sorted(bad)[:5])}"
        )
    return data


def _read_patches(path: Path) -> list[Patch]:
    data = _read_json(path)
    if not isinstance(data, list):
        raise ConfigError(f"{path} must hold a JSON array of patches")
    patches: list[Patch] = []
    for index, raw in enumerate(data):
        if not isinstance(raw, dict) or "op" not in raw:
            raise ConfigError(f"{path} patch {index} needs an 'op' key")
        patches.append(
            Patch(op=raw["op"], anchor=raw.get("anchor"), text=raw.get("text"))
        )
    if not patches:
        raise ConfigError(f"{path} holds no patches")
    return patches


def _read_split(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a split object")
    missing = [key for key in (*_GROUPS, "fingerprint") if key not in data]
    if missing:
        raise ConfigError(f"{path} is missing split keys: {', '.join(missing)}")
    return data


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


def _extract_rule(payload: object, args: argparse.Namespace) -> dict[str, bool]:
    # eval-rule-activation.py writes either a bare scenario array or an object
    # wrapping one, depending on whether the caller asked for the summary.
    scenarios = payload.get("scenarios") if isinstance(payload, dict) else payload
    if not isinstance(scenarios, list):
        raise ConfigError("rule input must be a scenario array or an object with 'scenarios'")
    return rule_results(scenarios, args.mechanism, min_score=args.min_score)


def cmd_extract(args: argparse.Namespace) -> int:
    if args.kind == "hook":
        results = pytest_results(_read_text(args.input), on_skip=args.on_skip)
    elif args.kind == "agent":
        report = _read_json(args.input)
        if not isinstance(report, Mapping):
            raise ConfigError(f"{args.input} must hold an agent report object")
        results = agent_results(
            report,
            args.variant,
            reduce=args.reduce,
            pass_threshold=args.pass_threshold,
        )
    else:
        results = _extract_rule(_read_json(args.input), args)
    _emit(results)
    return EXIT_OK


# ---------------------------------------------------------------------------
# split, budget, score
# ---------------------------------------------------------------------------


def cmd_split(args: argparse.Namespace) -> int:
    if args.results:
        task_ids = sorted(_read_results(args.results))
    else:
        task_ids = [
            line.strip() for line in _read_text(args.tasks).splitlines() if line.strip()
        ]
    try:
        result = split_tasks(
            task_ids,
            seed=args.seed,
            sel_ratio=args.sel_ratio,
            test_ratio=args.test_ratio,
            min_sel=args.min_sel,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    _emit(
        {
            "opt": list(result.opt),
            "sel": list(result.sel),
            "test": list(result.test),
            "fingerprint": result.fingerprint,
            "seed": args.seed,
        }
    )
    return EXIT_OK


def cmd_budget(args: argparse.Namespace) -> int:
    try:
        value = edit_budget(
            args.step, args.total, max_edits=args.max_edits, min_edits=args.min_edits
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    _emit({"budget": value, "step": args.step, "total": args.total})
    return EXIT_OK


def _score_group(results: dict[str, bool], split: dict[str, Any], group: str) -> float:
    try:
        return score(results, split[group])
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def cmd_score(args: argparse.Namespace) -> int:
    split = _read_split(args.split)
    results = _read_results(args.results)
    value = _score_group(results, split, args.group)
    _emit({"score": value, "group": args.group, "n": len(split[args.group])})
    return EXIT_OK


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def cmd_apply(args: argparse.Namespace) -> int:
    document = _read_text(args.file)
    patches = _read_patches(args.patches)
    try:
        updated = apply_patches(document, patches, budget=args.budget)
    except ValueError as exc:
        # A refused patch is a decision the loop branches on, not a crash. The
        # file is left untouched so the caller can propose a different edit.
        _emit({"applied": 0, "error": str(exc), "type": type(exc).__name__})
        return EXIT_LOGIC
    if args.dry_run:
        _emit({"applied": len(patches), "result": updated, "written": False})
        return EXIT_OK
    args.file.write_text(updated, encoding="utf-8")
    _emit({"applied": len(patches), "written": True, "path": str(args.file)})
    return EXIT_OK


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


def cmd_gate(args: argparse.Namespace) -> int:
    split = _read_split(args.split)
    incumbent = _score_group(_read_results(args.incumbent), split, args.group)
    candidate = _score_group(_read_results(args.candidate), split, args.group)
    try:
        result = gate(
            candidate,
            incumbent,
            sel_consultations=args.consultations,
            max_consultations=args.max_consultations,
            split_fingerprint=split["fingerprint"],
            incumbent_fingerprint=args.incumbent_fingerprint,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    _emit(
        {
            "decision": result.decision,
            "reason": result.reason,
            "candidate": result.candidate,
            "incumbent": result.incumbent,
            # What to pass as --consultations next time. A refusal that never
            # weighed the scores costs the held-out split nothing, so it does
            # not advance the counter.
            "sel_consultations": args.consultations + (1 if result.compared else 0),
            "compared": result.compared,
            "group": args.group,
            "fingerprint": split["fingerprint"],
        }
    )
    return EXIT_OK if result.decision == "ACCEPT" else EXIT_LOGIC


# ---------------------------------------------------------------------------
# buffer
# ---------------------------------------------------------------------------


def _read_buffer(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        # A first run has no ledger yet. Treating that as empty keeps the loop
        # from needing a separate init step.
        return []
    data = _read_json(path)
    if not isinstance(data, list):
        raise ConfigError(f"{path} must hold a JSON array of rejection entries")
    return data


def cmd_buffer_check(args: argparse.Namespace) -> int:
    entries = _read_buffer(args.buffer)
    patches = _read_patches(args.patches)
    seen = buffer_contains(entries, patches)
    _emit({"seen": seen, "fingerprint": patch_fingerprint(patches)})
    return EXIT_LOGIC if seen else EXIT_OK


def cmd_buffer_add(args: argparse.Namespace) -> int:
    entries = _read_buffer(args.buffer)
    patches = _read_patches(args.patches)
    fingerprint = patch_fingerprint(patches)
    if any(e.get("fingerprint") == fingerprint for e in entries):
        _emit({"added": False, "fingerprint": fingerprint, "entries": len(entries)})
        return EXIT_OK
    entries.append(
        {
            "fingerprint": fingerprint,
            "reason": args.reason,
            "patches": [
                {"op": p.op, "anchor": p.anchor, "text": p.text} for p in patches
            ],
        }
    )
    args.buffer.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    _emit({"added": True, "fingerprint": fingerprint, "entries": len(entries)})
    return EXIT_OK


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optimize-artifact.py",
        description="Held-out-gated optimization rails for agents, rules, and hooks.",
    )
    sub = parser.add_subparsers(dest="command")

    extract = sub.add_parser("extract", help="convert a scorer's output to task pass or fail")
    extract.add_argument("--kind", choices=("agent", "rule", "hook"), required=True)
    extract.add_argument("--input", type=Path, required=True)
    extract.add_argument("--variant", default="agent", help="agent eval variant column")
    extract.add_argument("--reduce", default="mean", choices=("mean", "min", "max", "median"))
    extract.add_argument("--pass-threshold", type=float, default=1.0)
    extract.add_argument("--mechanism", default="full", help="rule eval mechanism column")
    extract.add_argument("--min-score", type=float, default=3.5)
    extract.add_argument("--on-skip", default="fail", choices=("fail", "exclude"))
    extract.set_defaults(func=cmd_extract)

    split = sub.add_parser("split", help="partition tasks into opt, sel, and test")
    source = split.add_mutually_exclusive_group(required=True)
    source.add_argument("--results", type=Path, help="extract output; task ids are its keys")
    source.add_argument("--tasks", type=Path, help="newline-delimited task ids")
    split.add_argument("--seed", required=True)
    split.add_argument("--sel-ratio", type=float, default=0.4)
    split.add_argument("--test-ratio", type=float, default=0.0)
    split.add_argument("--min-sel", type=int, default=3)
    split.set_defaults(func=cmd_split)

    budget = sub.add_parser("budget", help="edits allowed at this step")
    budget.add_argument("--step", type=int, required=True)
    budget.add_argument("--total", type=int, required=True)
    budget.add_argument("--max-edits", type=int, default=5)
    budget.add_argument("--min-edits", type=int, default=1)
    budget.set_defaults(func=cmd_budget)

    score_cmd = sub.add_parser("score", help="fraction of one split group passing")
    score_cmd.add_argument("--results", type=Path, required=True)
    score_cmd.add_argument("--split", type=Path, required=True)
    score_cmd.add_argument("--group", default="sel", choices=_GROUPS)
    score_cmd.set_defaults(func=cmd_score)

    apply_cmd = sub.add_parser("apply", help="apply bounded patches to an artifact")
    apply_cmd.add_argument("--file", type=Path, required=True)
    apply_cmd.add_argument("--patches", type=Path, required=True)
    apply_cmd.add_argument("--budget", type=int, required=True)
    apply_cmd.add_argument("--dry-run", action="store_true")
    apply_cmd.set_defaults(func=cmd_apply)

    gate_cmd = sub.add_parser("gate", help="decide whether a candidate replaces the incumbent")
    gate_cmd.add_argument("--incumbent", type=Path, required=True)
    gate_cmd.add_argument("--candidate", type=Path, required=True)
    gate_cmd.add_argument("--split", type=Path, required=True)
    gate_cmd.add_argument("--group", default="sel", choices=_GROUPS)
    gate_cmd.add_argument("--consultations", type=int, default=0)
    gate_cmd.add_argument("--max-consultations", type=int, default=None)
    gate_cmd.add_argument("--incumbent-fingerprint", default=None)
    gate_cmd.set_defaults(func=cmd_gate)

    check = sub.add_parser("buffer-check", help="has this edit already been rejected")
    check.add_argument("--buffer", type=Path, required=True)
    check.add_argument("--patches", type=Path, required=True)
    check.set_defaults(func=cmd_buffer_check)

    add = sub.add_parser("buffer-add", help="record a rejected edit")
    add.add_argument("--buffer", type=Path, required=True)
    add.add_argument("--patches", type=Path, required=True)
    add.add_argument("--reason", required=True)
    add.set_defaults(func=cmd_buffer_add)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return EXIT_CONFIG
    try:
        return args.func(args)
    except (ConfigError, AdapterError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
