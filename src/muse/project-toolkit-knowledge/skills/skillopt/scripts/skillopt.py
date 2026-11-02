#!/usr/bin/env python3
"""SkillOpt deterministic harness: the accept/reject gate for skill evolution.

SkillOpt (Yang et al., arXiv:2605.23904) treats an agent skill document as the
external trainable state of a frozen target model and optimizes it in text
space. An optimizer model proposes bounded edits from scored rollouts; a
held-out validation gate accepts a candidate ONLY if it strictly beats the
incumbent best score. Rejected edits go into a buffer so the same failure is not
re-proposed, and a fenced "slow section" of longitudinal guidance is protected
from step-level edits.

This module is the DETERMINISTIC half of that loop, the half that must be exact,
reproducible, and testable. The agent (target + optimizer) does the rollouts and
the reflection; this script does the parts that decide whether an edit is
allowed to exist:

  - edit budget         : cosine-decayed learning rate (max atomic edits per step)
  - patch applier       : applies bounded atomic edits, refusing to touch the
                          protected slow-section, refusing ambiguous anchors,
                          and never writing over the incumbent file
  - validation gates    : scalar strict-greater, and per-task strict Pareto with
                          unverified-result and null-control checks
  - rejected-edit buffer: stable-signature dedup so known-bad edits are blocked
  - hash                : sha256 byte identity for incumbent, null control, and
                          deployed copy; a directory hashes as a whole bundle
  - run                 : executes eval.json argv commands against a bundle and
                          writes the per-task results files (see _skillopt_runner)

Pure stdlib, no third-party deps. It is harness-agnostic and runs under any
Python 3.10+. Exit codes: 0 = success / accept, 1 = reject / mismatch,
2 = usage or validation error.

buffer-check is the one inverted command, kept from the source contract on
purpose: it exits 0 for KNOWN-BAD (already rejected) and 1 for NOVEL (not yet
tried). Callers must branch on the stdout word or on the exit code explicitly,
never chain it with `&&` as if 0 meant "safe to proceed".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from _skillopt_buffer import (
    append_rejected,
    edit_signature,
    file_sha256,
    is_known_bad,
)
from _skillopt_bundle import (
    BUNDLE_DOC,
    bundle_sha256,
    copy_bundle,
    is_inside,
    list_bundle_files,
    overlaps,
    path_sha256,
)
from _skillopt_gates import (
    BAD_TASK_STATUSES,
    _split_task_ids,
    gate,
    pair_gate,
    score_results,
)
from _skillopt_patching import (
    SLOW_END,
    SLOW_START,
    VALID_OPS,
    SkillOptError,
    apply_patches,
    edit_budget,
    protected_ranges,
)
from _skillopt_runner import UNVERIFIED, run_bundle

RESULT_ROLES = ("incumbent", "candidate", "null")

__all__ = [
    "BAD_TASK_STATUSES",
    "SLOW_END",
    "SLOW_START",
    "VALID_OPS",
    "SkillOptError",
    "append_rejected",
    "apply_patches",
    "build_parser",
    "bundle_sha256",
    "edit_budget",
    "edit_signature",
    "file_sha256",
    "gate",
    "is_known_bad",
    "main",
    "pair_gate",
    "protected_ranges",
    "score_results",
]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def _load_object(path: str, label: str) -> dict[str, Any]:
    """Load a JSON file that must hold an object."""
    value = _load_json(path)
    if not isinstance(value, dict):
        raise SkillOptError(f"{label} must be a JSON object")
    return value


def _same_file(a: Path, b: Path) -> bool:
    """True if both paths name the same file (resolved path or same inode)."""
    if a.resolve() == b.resolve():
        return True
    return a.exists() and b.exists() and os.path.samefile(a, b)


def _cmd_budget(args: argparse.Namespace) -> int:
    print(edit_budget(args.step, args.total, args.max, args.min))
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    skill = Path(args.skill)
    _split_task_ids(_load_object(args.eval, "apply eval input"), "sel")
    is_bundle = skill.is_dir()
    doc_path = skill / BUNDLE_DOC if is_bundle else skill
    if is_bundle:
        list_bundle_files(skill)
    if not args.dry_run:
        if not args.out:
            raise SkillOptError("apply requires --out unless --dry-run")
        if _same_file(skill, Path(args.out)) or (is_bundle and overlaps(skill, Path(args.out))):
            raise SkillOptError(
                "refusing to overwrite the incumbent; write the candidate to a separate --out path"
            )
    doc = doc_path.read_bytes().decode("utf-8")
    patches = _load_json(args.patches)
    result = apply_patches(doc, patches, args.budget)
    if args.dry_run:
        sys.stderr.write(
            f"OK: {len(patches)} patch(es) apply cleanly within budget {args.budget}\n"
        )
        return 0
    out = Path(args.out)
    if is_bundle:
        copy_bundle(skill, out, {BUNDLE_DOC: result.encode("utf-8")})
        sys.stderr.write(
            f"applied {len(patches)} patch(es) -> {out} (bundle sha256 {bundle_sha256(out)})\n"
        )
        return 0
    out.write_bytes(result.encode("utf-8"))
    sys.stderr.write(f"applied {len(patches)} patch(es) -> {out}\n")
    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    accepted = gate(args.candidate, args.incumbent)
    verdict = "ACCEPT" if accepted else "REJECT"
    sys.stderr.write(f"{verdict}: candidate {args.candidate} vs incumbent best {args.incumbent}\n")
    print(verdict)
    return 0 if accepted else 1


def _cmd_pair_gate(args: argparse.Namespace) -> int:
    eval_set = _load_object(args.eval, "pair-gate eval input")
    incumbent_results = _load_object(args.incumbent_results, "pair-gate incumbent results")
    candidate_results = _load_object(args.candidate_results, "pair-gate candidate results")
    null_results = (
        _load_object(args.null_results, "pair-gate null results") if args.null_results else None
    )
    report = pair_gate(
        eval_set,
        incumbent_results,
        candidate_results,
        args.split,
        null_results,
        incumbent_sha256=args.incumbent_sha256,
        null_sha256=args.null_sha256,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 1


def _cmd_score(args: argparse.Namespace) -> int:
    eval_set = _load_object(args.eval, "score eval input")
    results = _load_object(args.results, "score results")
    print(f"{score_results(eval_set, results, args.split):.6f}")
    return 0


def _cmd_hash(args: argparse.Namespace) -> int:
    if args.expect is not None and len(args.files) != 1:
        raise SkillOptError("--expect needs exactly one file")
    digests = [(path_sha256(path), path) for path in args.files]
    for digest, path in digests:
        print(f"{digest}  {path}")
    if args.expect is not None and digests[0][0] != args.expect.strip().lower():
        print(f"MISMATCH: {digests[0][1]} is {digests[0][0]}, expected {args.expect}")
        return 1
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    eval_set = _load_object(args.eval, "run eval input")
    bundle = Path(args.bundle)
    out_dir = Path(args.out_dir)
    if is_inside(out_dir, bundle):
        raise SkillOptError("--out-dir must not sit inside the bundle")
    outcomes, skipped, digest = run_bundle(eval_set, bundle, args.split)
    results = {task_id: outcome.value for task_id, outcome in outcomes.items()}
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / f"{args.role}_results.json"
    staged = results_path.with_name(f".{results_path.name}.tmp")
    staged.write_bytes((json.dumps(results, indent=2) + "\n").encode("utf-8"))
    os.replace(staged, results_path)
    unverified = [t for t, o in outcomes.items() if o.value == UNVERIFIED]
    summary = {
        "role": args.role,
        "bundle_sha256": digest,
        "results_file": str(results_path),
        "passed": sum(1 for o in outcomes.values() if o.value is True),
        "failed": sum(1 for o in outcomes.values() if o.value is False),
        "unverified": unverified,
        "skipped_no_command": skipped,
        "tasks": {t: {"result": o.value, "reason": o.reason} for t, o in outcomes.items()},
    }
    print(json.dumps(summary, indent=2))
    return 1 if unverified else 0


def _cmd_buffer_check(args: argparse.Namespace) -> int:
    patches = _load_json(args.patches)
    if is_known_bad(Path(args.buffer), patches):
        sys.stderr.write("KNOWN-BAD: this edit was already rejected; do not re-propose\n")
        print("KNOWN-BAD")
        return 0
    sys.stderr.write("NOVEL: edit not in rejected buffer\n")
    print("NOVEL")
    return 1


def _cmd_buffer_add(args: argparse.Namespace) -> int:
    patches = _load_json(args.patches)
    append_rejected(Path(args.buffer), patches, args.score, args.incumbent, args.note, args.step)
    sys.stderr.write(f"recorded rejected edit (step {args.step}, score {args.score})\n")
    return 0


def _add_apply_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("apply", help="apply bounded atomic patches to a skill doc")
    p.add_argument("--skill", required=True, help="SKILL.md file, or a bundle directory")
    p.add_argument(
        "--eval", required=True, help="eval manifest; refuses a missing or empty sel split"
    )
    p.add_argument("--patches", required=True, help="JSON file: list of patch objects")
    p.add_argument("--budget", type=int, required=True)
    p.add_argument(
        "--out",
        help="candidate path: a new directory for a bundle (required unless --dry-run)",
    )
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=_cmd_apply)


def _add_run_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "run",
        help="run eval.json argv commands against a bundle and write <role>_results.json",
        description=(
            "SECURITY: eval.json commands run as you and may start any binary on PATH. "
            "Run only an eval.json you wrote or reviewed."
        ),
    )
    p.add_argument("--eval", required=True)
    p.add_argument("--bundle", required=True, help="skill directory; commands run with it as cwd")
    p.add_argument("--role", required=True, choices=RESULT_ROLES)
    p.add_argument("--out-dir", default=".", help="where <role>_results.json is written")
    p.add_argument("--split", help="run only this split (default: every split)")
    p.set_defaults(func=_cmd_run)


def _add_gate_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("gate", help="accept iff candidate strictly beats incumbent")
    p.add_argument("--candidate", type=float, required=True)
    p.add_argument("--incumbent", type=float, required=True)
    p.set_defaults(func=_cmd_gate)

    p = sub.add_parser(
        "pair-gate",
        help="accept iff candidate adds a held-out pass with zero regressions",
    )
    p.add_argument("--eval", required=True)
    p.add_argument("--incumbent-results", required=True)
    p.add_argument("--candidate-results", required=True)
    p.add_argument("--null-results", help="no-op rerun of the byte-identical incumbent")
    p.add_argument(
        "--incumbent-sha256", help="sha256 of the incumbent (required with --null-results)"
    )
    p.add_argument("--null-sha256", help="sha256 of the file the null run used (must match)")
    p.add_argument("--split", default="sel")
    p.set_defaults(func=_cmd_pair_gate)

    p = sub.add_parser("score", help="pass-rate on a held-out split")
    p.add_argument("--eval", required=True)
    p.add_argument("--results", required=True)
    p.add_argument("--split", default="sel")
    p.set_defaults(func=_cmd_score)


def _add_buffer_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("buffer-check", help="is this edit already known-bad?")
    p.add_argument("--buffer", required=True)
    p.add_argument("--patches", required=True)
    p.set_defaults(func=_cmd_buffer_check)

    p = sub.add_parser("buffer-add", help="record a rejected edit")
    p.add_argument("--buffer", required=True)
    p.add_argument("--patches", required=True)
    p.add_argument("--score", type=float, required=True)
    p.add_argument("--incumbent", type=float, required=True)
    p.add_argument("--note", default="")
    p.add_argument(
        "--step",
        type=int,
        default=0,
        help="0-based step index of the rejected edit (the same T passed to budget)",
    )
    p.set_defaults(func=_cmd_buffer_add)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skillopt", description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("budget", help="cosine-decayed edit budget for a step")
    p.add_argument(
        "--step",
        type=int,
        required=True,
        help="0-based step index, from 0 to N-1 where N is --total",
    )
    p.add_argument(
        "--total",
        type=int,
        required=True,
        help="total number of steps N; --step must be less than N",
    )
    p.add_argument("--max", type=int, default=5)
    p.add_argument("--min", type=int, default=1)
    p.set_defaults(func=_cmd_budget)

    _add_apply_parser(sub)
    _add_run_parser(sub)
    _add_gate_parsers(sub)

    p = sub.add_parser(
        "hash", help="sha256 of file bytes or a whole bundle directory; --expect checks one path"
    )
    p.add_argument("files", nargs="+", help="files or bundle directories")
    p.add_argument("--expect", help="expected sha256; exit 1 on mismatch (one file only)")
    p.set_defaults(func=_cmd_hash)

    _add_buffer_parsers(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (SkillOptError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"skillopt: {exc}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
