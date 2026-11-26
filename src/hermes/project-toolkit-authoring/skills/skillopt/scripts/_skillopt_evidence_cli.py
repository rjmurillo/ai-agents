"""CLI subcommands for the evidence checks in _skillopt_evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from _skillopt_bundle import overlaps
from _skillopt_evidence import (
    TIER_HINT,
    check_manifesto,
    check_pins,
    check_weakness,
    make_pins,
    proposer_tier,
    verify_manifesto,
)
from _skillopt_patching import SkillOptError


def _load(path: str) -> Any:
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def _load_object(path: str, label: str) -> dict[str, Any]:
    value = _load(path)
    if not isinstance(value, dict):
        raise SkillOptError(f"{label} must be a JSON object")
    return value


def _cmd_weakness_check(args: argparse.Namespace) -> int:
    report = check_weakness(
        _load_object(args.eval, "eval input"),
        _load_object(args.incumbent_results, "incumbent results"),
        _load(args.weakness),
    )
    print(json.dumps(report, indent=2))
    return 0


def _cmd_manifesto_check(args: argparse.Namespace) -> int:
    report = check_manifesto(
        _load_object(args.eval, "eval input"),
        _load_object(args.incumbent_results, "incumbent results"),
        _load(args.weakness),
        _load(args.manifesto),
        _load(args.patches),
    )
    for warning in report["warnings"]:
        sys.stderr.write(f"WARN: {warning}\n")
    print(json.dumps(report, indent=2))
    return 0


def _cmd_manifesto_verify(args: argparse.Namespace) -> int:
    report = verify_manifesto(
        _load_object(args.eval, "eval input"),
        _load(args.manifesto),
        _load_object(args.incumbent_results, "incumbent results"),
        _load_object(args.candidate_results, "candidate results"),
    )
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "PREDICTIONS_HELD" else 1


def _parse_surface(text: str) -> tuple[str, Path]:
    name, sep, path = text.partition("=")
    if not sep or not name.strip() or not path.strip():
        raise SkillOptError(f"--surface must be NAME=PATH, got {text!r}")
    return name.strip(), Path(path.strip())


def _cmd_pin(args: argparse.Namespace) -> int:
    surfaces: dict[str, Path] = {}
    for text in args.surface or []:
        name, path = _parse_surface(text)
        if name in surfaces:
            raise SkillOptError(f"--surface name {name!r} given twice; each name pins one path")
        surfaces[name] = path
    if "eval" in surfaces:
        raise SkillOptError("pass the eval manifest with --eval, not --surface eval=...")
    surfaces["eval"] = Path(args.eval)
    pins = make_pins(surfaces, args.model)
    out = Path(args.out)
    if any(overlaps(out, p) for p in surfaces.values()):
        raise SkillOptError("--out must not overwrite or sit inside a pinned surface")
    out.write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
    sys.stderr.write(f"pinned {len(pins['surfaces'])} read-only surface(s) -> {out}\n")
    return 0


def _cmd_pin_check(args: argparse.Namespace) -> int:
    report = check_pins(_load(args.pins), args.model)
    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] == "MATCH" else 1


def _cmd_proposer_check(args: argparse.Namespace) -> int:
    tier = proposer_tier(args.model)
    print(tier.upper())
    if tier != "capable":
        sys.stderr.write(f"WARN: proposer tier {tier}: {TIER_HINT}\n")
        return 1
    return 0


def add_evidence_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register weakness-check, manifesto-check, manifesto-verify, pin, pin-check, proposer-check."""
    p = sub.add_parser(
        "weakness-check", help="validate failing train tasks clustered into patterns"
    )
    p.add_argument("--eval", required=True)
    p.add_argument("--incumbent-results", required=True)
    p.add_argument("--weakness", required=True, help="skillopt-weakness/1 file")
    p.set_defaults(func=_cmd_weakness_check)

    p = sub.add_parser("manifesto-check", help="require one evidence entry per proposed patch")
    p.add_argument("--eval", required=True)
    p.add_argument("--incumbent-results", required=True)
    p.add_argument("--weakness", required=True)
    p.add_argument("--manifesto", required=True, help="skillopt-manifesto/1 file")
    p.add_argument("--patches", required=True)
    p.set_defaults(func=_cmd_manifesto_check)

    p = sub.add_parser("manifesto-verify", help="score manifesto predictions on train results")
    p.add_argument("--eval", required=True)
    p.add_argument("--manifesto", required=True)
    p.add_argument("--incumbent-results", required=True)
    p.add_argument("--candidate-results", required=True)
    p.set_defaults(func=_cmd_manifesto_verify)

    p = sub.add_parser("pin", help="record sha256 of the read-only surfaces at baseline")
    p.add_argument("--eval", required=True)
    p.add_argument(
        "--surface", action="append", help="NAME=PATH, e.g. verifier=check.py (repeatable)"
    )
    p.add_argument("--model", required=True, help="model configuration the rollouts use")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_pin)

    p = sub.add_parser("pin-check", help="confirm no read-only surface changed")
    p.add_argument("--pins", required=True)
    p.add_argument("--model", help="model in use now; a different value is a mismatch")
    p.set_defaults(func=_cmd_pin_check)

    p = sub.add_parser("proposer-check", help="warn on a lightweight-tier proposer model")
    p.add_argument("--model", required=True)
    p.set_defaults(func=_cmd_proposer_check)
