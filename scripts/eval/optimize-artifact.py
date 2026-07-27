#!/usr/bin/env python3
"""Held-out-gated optimization rails for agents, rules, and hooks.

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
wants to branch on it. Every path this module reaches prints JSON, so a
caller that needs to tell REJECT from a config failure can read `decision`
instead of guessing from the code, and a config failure prints an `error`
field the same way. Argparse rejects a malformed command line before this
module runs and prints its own plain-text usage to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
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
    guard_refusal,
    mcnemar_exact,
    patch_fingerprint,
    score,
    split_tasks,
)

_GATE_GROUP = "sel"

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
    except UnicodeDecodeError as exc:
        # UnicodeDecodeError subclasses ValueError, not OSError, so the arm
        # below never caught it and a binary artifact crashed the loop.
        raise ConfigError(f"{path} is not valid UTF-8: {exc}") from exc
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
    required = (*_GROUPS, "fingerprint", "seed", "sel_ratio", "test_ratio")
    missing = [key for key in required if key not in data]
    if missing:
        raise ConfigError(
            f"{path} is missing split keys: {', '.join(missing)}. A split file "
            "that cannot be re-fingerprinted cannot be verified; re-run split."
        )
    return data


def _split_drifted(split: Mapping[str, Any]) -> bool:
    """Has the split file changed since it was written?

    Redrawn from the file's own recorded inputs rather than compared against a
    value the caller passes, because a caller who forgets the flag would
    otherwise get no check at all.

    Both halves are needed and neither is redundant. The fingerprint covers the
    split's inputs (seed, task set, ratios), so it catches an added or removed
    task. It cannot catch a task moved between groups, because the union it
    hashes is unchanged by a move. Redrawing the split catches that: the draw is
    seeded, so the groups are a pure function of the inputs, and any membership
    that the recorded inputs would not produce is drift.
    """
    try:
        tasks = [str(t) for group in _GROUPS for t in split[group]]
        redrawn = split_tasks(
            tasks,
            seed=str(split["seed"]),
            sel_ratio=float(split["sel_ratio"]),
            test_ratio=float(split["test_ratio"]),
            min_sel=int(split.get("min_sel", 3)),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"split file holds unusable seed or ratios: {exc}") from exc
    if redrawn.fingerprint != split["fingerprint"]:
        return True
    return any(sorted(getattr(redrawn, g)) != sorted(split[g]) for g in _GROUPS)


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


def _rule_scenarios(payload: object) -> list[Any]:
    """Pull scenarios from a bare array or a 'scenarios' wrapper."""
    scenarios = payload.get("scenarios") if isinstance(payload, dict) else payload
    if not isinstance(scenarios, list):
        raise ConfigError("rule input must be a scenario array or an object with 'scenarios'")
    typed: list[Any] = scenarios
    return typed


def _extract_rules_envelope(rules: object, args: argparse.Namespace) -> dict[str, bool]:
    """Extract the multi-rule shape eval-rule-activation.py --output writes.

    Scenario ids restart at S1 inside every rule, so they are namespaced as
    `<rule>::<scenario-id>`. A live run over the seven scenario files in
    tests/evals/rule-scenarios/ produced 24 scenarios carrying only 4 distinct
    ids; merging them raw would silently drop 20 tasks, and a smaller
    denominator reads as a higher score.
    """
    if not isinstance(rules, Mapping) or not rules:
        raise ConfigError("'rules' must be a non-empty mapping of rule name to result")
    out: dict[str, bool] = {}
    for name, entry in rules.items():
        if not isinstance(entry, Mapping) or "scenarios" not in entry:
            raise ConfigError(f"rule {name!r} has no 'scenarios' list")
        scored: dict[str, bool] = rule_results(
            _rule_scenarios(entry), args.mechanism, min_score=args.min_score
        )
        for sid, passed in scored.items():
            out[f"{name}::{sid}"] = passed
    return out


def _extract_rule(payload: object, args: argparse.Namespace) -> dict[str, bool]:
    # eval-rule-activation.py --output writes {"rules": {name: {...}}}. A bare
    # scenario array and a {"scenarios": [...]} wrapper are also accepted so a
    # caller can gate one rule without the envelope.
    if isinstance(payload, dict) and "rules" in payload:
        return _extract_rules_envelope(payload["rules"], args)
    # Annotated locals here and below: the sibling modules are imported by
    # path (this file is a hyphenated script), so mypy resolves them as Any
    # under ignore_missing_imports. The annotation restates the contract the
    # tests already enforce.
    extracted: dict[str, bool] = rule_results(
        _rule_scenarios(payload), args.mechanism, min_score=args.min_score
    )
    return extracted


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
    record = {
        "opt": list(result.opt),
        "sel": list(result.sel),
        "test": list(result.test),
        "fingerprint": result.fingerprint,
        "seed": args.seed,
        "sel_ratio": args.sel_ratio,
        "test_ratio": args.test_ratio,
        "min_sel": args.min_sel,
    }
    _write_atomic(args.out, json.dumps(record, indent=2, sort_keys=True) + "\n")
    # The full record goes to the file the gate reads. Stdout, which is what
    # the optimizing agent sees, gets the optimize ids and the sizes and
    # fingerprint it needs to verify the split was not redrawn. Publishing
    # held-out membership here would make the withholding nominal: an agent
    # could read the answers it is being measured against for free.
    _emit(
        {
            "opt": list(result.opt),
            "n_sel": len(result.sel),
            "n_test": len(result.test),
            "fingerprint": result.fingerprint,
            "seed": args.seed,
            "split": str(args.out),
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


def _group_ids(split: dict[str, Any], group: str) -> list[str]:
    ids: list[str] = list(split[group])
    return ids


def _score_group(results: dict[str, bool], split: dict[str, Any], group: str) -> float:
    try:
        fraction: float = score(results, split[group])
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return fraction


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
    _write_atomic(args.file, updated)
    _emit({"applied": len(patches), "written": True, "path": str(args.file)})
    return EXIT_OK


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


def cmd_gate(args: argparse.Namespace) -> int:
    split = _read_split(args.split)
    if _split_drifted(split):
        _emit(
            {
                "decision": "REJECT",
                "reason": (
                    "split fingerprint does not match the split file's own "
                    "contents; the groups or the seed were edited after the "
                    "split was drawn. Re-split and re-baseline."
                ),
                "consultations": args.consultations,
            }
        )
        return EXIT_OK

    # Guards first, scoring second. Both refusals are decidable from
    # bookkeeping alone, and scoring before asking would read the held-out
    # group to produce a verdict that says the held-out group must not be read.
    refusal = guard_refusal(
        sel_consultations=args.consultations,
        max_consultations=args.max_consultations,
        split_fingerprint=split["fingerprint"],
        incumbent_fingerprint=args.incumbent_fingerprint,
    )
    if refusal is not None:
        _emit(
            {
                "decision": "REJECT",
                "reason": refusal,
                "sel_consultations": args.consultations,
                "compared": False,
                "group": _GATE_GROUP,
                "fingerprint": split["fingerprint"],
            }
        )
        return EXIT_LOGIC

    incumbent_results = _read_results(args.incumbent)
    candidate_results = _read_results(args.candidate)
    sel_ids = _group_ids(split, _GATE_GROUP)
    incumbent = _score_group(incumbent_results, split, _GATE_GROUP)
    candidate = _score_group(candidate_results, split, _GATE_GROUP)
    try:
        gain, loss, p_value = mcnemar_exact(incumbent_results, candidate_results, sel_ids)
        result = gate(
            candidate,
            incumbent,
            sel_consultations=args.consultations,
            max_consultations=args.max_consultations,
            split_fingerprint=split["fingerprint"],
            incumbent_fingerprint=args.incumbent_fingerprint,
            discordant_loss=loss,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    _emit(
        {
            "decision": result.decision,
            "reason": result.reason,
            "candidate": result.candidate,
            "incumbent": result.incumbent,
            # Discordant pairs are the only tasks that carry evidence about the
            # edit. p is the one-sided exact McNemar tail, reported rather than
            # enforced: a three-task held-out group cannot reach 0.05, so
            # enforcing a conventional floor would make the common case
            # unpassable instead of informative.
            "discordant_gain": gain,
            "discordant_loss": loss,
            "p_value": p_value,
            # What to pass as --consultations next time. A refusal that never
            # weighed the scores costs the held-out split nothing, so it does
            # not advance the counter.
            "sel_consultations": args.consultations + (1 if result.compared else 0),
            "compared": result.compared,
            "group": _GATE_GROUP,
            "fingerprint": split["fingerprint"],
        }
    )
    return EXIT_OK if result.decision == "ACCEPT" else EXIT_LOGIC


# ---------------------------------------------------------------------------
# buffer
# ---------------------------------------------------------------------------


def _write_atomic(path: Path, text: str) -> None:
    """Replace `path` with `text` so no reader ever sees a partial file.

    `apply` overwrites the artifact the loop is optimizing. A direct write
    truncates before it fills, so an interrupt or a full disk mid-write
    destroys the artifact and leaves the loop nothing to fall back to. The
    temp file is created beside the target so os.replace stays on one
    filesystem and therefore stays atomic.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise ConfigError(f"could not write {path}: {exc}") from exc


def _read_buffer(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        # A first run has no ledger yet. Treating that as empty keeps the loop
        # from needing a separate init step.
        return []
    data = _read_json(path)
    if not isinstance(data, list):
        raise ConfigError(f"{path} must hold a JSON array of rejection entries")
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ConfigError(f"{path} entry {index} must be an object, got {entry!r}")
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
    split.add_argument(
        "--out",
        type=Path,
        required=True,
        help="file the gate reads; holds the full split including held-out ids",
    )
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
    # Only the optimize group. The gate scores the selection group itself,
    # inside a decision that consumes a consultation. A free-standing score on
    # a held-out group is exactly the unmetered read the budget exists to
    # count, so the flag does not offer one.
    score_cmd.add_argument("--group", default="opt", choices=("opt",))
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
    # No --group. A gate reads the held-out group by definition, and offering
    # the choice let a caller gate on the group it had already optimized against.
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
        # argparse.Namespace attributes are Any; every registered handler
        # returns an exit code.
        exit_code: int = args.func(args)
    except (ConfigError, AdapterError) as exc:
        # JSON, not a bare message, because the module docstring promises a
        # caller can tell a REJECT from a config failure by reading a field
        # rather than guessing from the exit code. A plain-text error breaks
        # that promise for any driver piping stdout through a JSON reader.
        _emit({"error": str(exc), "type": type(exc).__name__})
        return EXIT_CONFIG
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
