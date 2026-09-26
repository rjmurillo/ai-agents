#!/usr/bin/env python3
"""Roll model sweeps up into a per-agent routing table.

``eval-model-sweep.py`` evaluates one agent across candidate models and leaves
one child ``report.json`` per model under
``evals/<agent>-spike/reports/sweep-<model>-<suffix>/``. This script reads
those child reports for every agent and every vendor ladder, applies
``decide_routing`` (the cheapest model whose recall stays within the margin of
the best model), and writes the routing table the orchestrator and autoplan
guidance cite.

A ladder is one vendor's models, cheapest to most capable. Ladders are routed
separately because a harness routes within one vendor: the question is which
rung of that vendor's ladder a task needs, not which vendor wins.

Exactly one child report must match each (agent, model) pair on the agent's
current fixture set. Zero or several matches fail the rollup instead of
guessing which run is the evidence.

Exit codes (AGENTS.md): 0 ok, 1 logic (some pair undecided: missing,
ambiguous, or degraded reports; the artifacts still record each reason),
2 config (bad arguments).

Usage:
    eval_model_routing.py \\
        --agents analyst,critic \\
        --skill analyze=analyst \\
        --ladder claude=claude-haiku-4-5,claude-sonnet-5,claude-opus-5-5 \\
        --ladder gpt6=gpt-6-luna,gpt-6-sol,gpt-6-astra \\
        --out-dir evals/model-routing
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

from _eval_common import MODEL_PRICING_RATES_USD_PER_1K_TOKENS
from _model_sweep_core import (
    DEFAULT_ROUTING_MARGIN,
    DEFAULT_SEED,
    ModelResult,
    SweepDecisionError,
    decide_routing,
    routing_report,
)

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
REPORTS_DIR_TEMPLATE = "evals/{agent}-spike/reports"
FIXTURES_DIR_TEMPLATE = "evals/{agent}-spike/fixtures"


class ReportParser(Protocol):
    """``eval-model-sweep.parse_report``: a report dict to a ``ModelResult``."""

    def __call__(self, report: dict[str, Any], *, model_id: str) -> ModelResult: ...


class RollupError(Exception):
    """A child report is missing, ambiguous, or unreadable."""


@dataclass(frozen=True)
class Ladder:
    name: str
    models: tuple[str, ...]


def _load_sweep_module() -> ModuleType:
    """Import ``eval-model-sweep.py`` (hyphenated, so not a plain import)."""
    path = EVAL_DIR / "eval-model-sweep.py"
    spec = importlib.util.spec_from_file_location("eval_model_sweep", path)
    if spec is None or spec.loader is None:
        raise RollupError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_ladder(value: str) -> Ladder:
    """Parse ``name=model,model,...`` into a ``Ladder``."""
    name, sep, models = value.partition("=")
    ids = tuple(m.strip() for m in models.split(",") if m.strip())
    if not sep or not name.strip() or len(ids) < 2:
        raise argparse.ArgumentTypeError(
            f"--ladder must look like name=model,model (got {value!r})"
        )
    return Ladder(name=name.strip(), models=ids)


def fixture_set_sha(fixtures_dir: Path) -> str:
    """Same identity the base evaluator records as ``fixture_set_sha``."""
    lines = []
    for path in sorted(fixtures_dir.glob("*.json")):
        digest = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        lines.append(f"{path.name}:{digest}")
    joined = "\n".join(sorted(lines))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Subject:
    """What a routing row measures: an agent prompt, or a skill on an agent's fixtures."""

    name: str
    agent: str
    variant: str

    @property
    def run_prefix(self) -> str:
        return f"sweep-skill-{self.name}-" if self.variant == "skill" else "sweep-"


def parse_skill(value: str) -> Subject:
    """Parse ``skill=agent``: route SKILL.md over that agent's fixtures."""
    skill, sep, agent = value.partition("=")
    if not sep or not skill.strip() or not agent.strip():
        raise argparse.ArgumentTypeError(f"--skill must look like skill=agent (got {value!r})")
    return Subject(name=skill.strip(), agent=agent.strip(), variant="skill")


def _is_candidate(path: Path, subject: Subject) -> bool:
    run_id = path.parent.name
    if not run_id.startswith(subject.run_prefix):
        return False
    return subject.variant == "skill" or not run_id.startswith("sweep-skill-")


def find_report(reports_dir: Path, subject: Subject, model_id: str, sha: str) -> dict[str, Any]:
    """Return the single child report for ``model_id`` on fixture set ``sha``."""
    matches = []
    for path in sorted(reports_dir.glob("sweep-*/report.json")):
        if not _is_candidate(path, subject):
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("model_id") == model_id and report.get("fixture_set_sha") == sha:
            matches.append((path, report))
    if len(matches) != 1:
        found = [str(p.relative_to(REPO_ROOT)) for p, _ in matches]
        where = reports_dir.relative_to(REPO_ROOT)
        raise RollupError(
            f"expected one {subject.variant} report for {subject.name} on {model_id} "
            f"under {where} on the current fixtures, found {len(matches)}: {found}"
        )
    path, report = matches[0]
    report["_path"] = path.parent.relative_to(REPO_ROOT).as_posix()
    return include_flaky(as_variant(report, subject.variant))


def include_flaky(report: dict[str, Any]) -> dict[str, Any]:
    """Score every fixture, flaky ones included.

    The base evaluator drops fixtures whose pass rate varies across runs,
    because its question is whether a prompt beats a baseline. Routing asks
    whether a model can be trusted with the task, and run-to-run variance is
    part of that answer. The per-fixture mean over runs already prices it in,
    so nothing is excluded here. The dropped count is kept for the report.
    """
    view = dict(report)
    view["_flaky_count"] = len(report.get("flaky_fixtures_excluded") or [])
    view["flaky_fixtures_excluded"] = []
    return view


def variant_rates(runs_path: Path, variant: str) -> dict[str, list[float]]:
    """Per-fixture, per-run pass rates for one variant, read from ``runs.jsonl``.

    The report's ``per_fixture_pass_rates`` carries only the headline agent
    and baseline variants, so the skill variant is rebuilt here with the
    aggregator's formula: the share of a record's assertions that passed,
    and 0.0 for an errored record.
    """
    rates: dict[str, dict[int, float]] = {}
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("variant") != variant:
            continue
        assertions = record.get("assertions") or []
        ok = record.get("outcome") != "error" and assertions
        rate = sum(1 for a in assertions if a.get("passed")) / len(assertions) if ok else 0.0
        rates.setdefault(str(record["fixture_id"]), {})[int(record["run_index"])] = rate
    return {fid: [by_run[i] for i in sorted(by_run)] for fid, by_run in rates.items()}


def as_variant(report: dict[str, Any], variant: str) -> dict[str, Any]:
    """Present the ``skill`` variant in the ``agent`` slots ``parse_report`` reads."""
    if variant == "agent":
        return report
    form_factor = report.get("form_factor")
    if not isinstance(form_factor, dict) or "skill_recall" not in form_factor:
        raise RollupError(f"{report['_path']} has no skill variant (run with --skill-path)")
    run_dir = Path(report["_path"])
    runs_path = REPO_ROOT / run_dir.parent.parent / "runs" / run_dir.name / "runs.jsonl"
    if not runs_path.is_file():
        raise RollupError(f"{runs_path.relative_to(REPO_ROOT).as_posix()} is missing")
    rates = variant_rates(runs_path, "skill")
    if not rates:
        raise RollupError(f"{runs_path.relative_to(REPO_ROOT)} has no skill records")
    view = dict(report)
    view["agent_recall"] = form_factor["skill_recall"]
    view["per_fixture_pass_rates"] = {fid: {"agent": r} for fid, r in rates.items()}
    return view


def _model_row(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": report["model_id"],
        "run": report["_path"],
        "agent_recall": report["agent_recall"],
        "baseline_recall": report.get("baseline_recall"),
        "cost_usd": report.get("cost_estimate_usd"),
        "cost_basis": report.get("cost_basis", "usd"),
        "error_count": report["error_count"],
        "flaky_fixtures_rescored": report["_flaky_count"],
    }


def route_subject(
    subject: Subject, ladder: Ladder, *, parse: ReportParser, margin: float, seed: int
) -> dict[str, Any]:
    """Route one subject on one ladder; returns the rollup entry."""
    fixtures = REPO_ROOT / FIXTURES_DIR_TEMPLATE.format(agent=subject.agent)
    reports_dir = REPO_ROOT / REPORTS_DIR_TEMPLATE.format(agent=subject.agent)
    sha = fixture_set_sha(fixtures)
    reports = [find_report(reports_dir, subject, m, sha) for m in ladder.models]
    results: list[ModelResult] = [parse(r, model_id=r["model_id"]) for r in reports]
    decision = decide_routing(
        results, prices=MODEL_PRICING_RATES_USD_PER_1K_TOKENS, margin=margin, seed=seed
    )
    return {
        "subject": subject.name,
        "kind": subject.variant,
        "fixtures_agent": subject.agent,
        "ladder": ladder.name,
        "fixture_set_sha": sha,
        "models": [_model_row(r) for r in reports],
        "routing": routing_report(decision),
    }


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def _summary_cells(entry: dict[str, Any] | None) -> list[str]:
    if entry is None:
        return ["not run", "not run"]
    if "error" in entry:
        return ["undecided", "undecided"]
    routing = entry["routing"]
    lightest = routing["lightest_sufficient_model"]
    if not routing["resolved"]:
        lightest += " (gap unproven)"
    return [lightest, routing["best_model"]]


def _summary_lines(entries: list[dict[str, Any]], ladders: list[Ladder]) -> list[str]:
    by_key = {(e["subject"], e["kind"], e["ladder"]): e for e in entries}
    subjects = sorted({(e["kind"], e["subject"], e["fixtures_agent"]) for e in entries})
    lines = [
        "| Kind | Subject | Fixtures | "
        + " | ".join(f"{lad.name} lightest | {lad.name} best" for lad in ladders)
        + " |",
        "|---|---|---|" + "---|---|" * len(ladders),
    ]
    for kind, name, agent in subjects:
        cells: list[str] = []
        for lad in ladders:
            cells += _summary_cells(by_key.get((name, kind, lad.name)))
        lines.append(f"| {kind} | {name} | {agent} | " + " | ".join(cells) + " |")
    return lines


def _detail_lines(entries: list[dict[str, Any]]) -> list[str]:
    """Per-model rows. Routed recall is the metric behind the verdict.

    Headline and baseline recall are the base evaluator's figures, with flaky
    fixtures excluded; they are shown for reference and do not gate routing.
    """
    lines = [
        "| Subject | Ladder | Model | Routed recall | Headline recall "
        "| Headline baseline | Cost USD | Sufficient |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for entry in sorted(entries, key=lambda e: (e["kind"], e["subject"], e["ladder"])):
        if "error" in entry:
            lines.append(
                f"| {entry['subject']} | {entry['ladder']} "
                f"| undecided: {entry['error']} | | | | | |"
            )
            continue
        routed = {c["model_id"]: c for c in entry["routing"]["candidates"]}
        for row in entry["models"]:
            candidate = routed[row["model_id"]]
            lines.append(
                f"| {entry['subject']} | {entry['ladder']} | {row['model_id']} "
                f"| {_fmt(candidate['mean_recall'])} | {_fmt(row['agent_recall'])} "
                f"| {_fmt(row['baseline_recall'])} | {_fmt(row['cost_usd'])} "
                f"| {candidate['sufficient']} |"
            )
    return lines


def render_markdown(entries: list[dict[str, Any]], ladders: list[Ladder], margin: float) -> str:
    """Human summary: one row per subject, one column pair per ladder."""
    lines = [
        "# Model routing by agent and skill",
        "",
        f"Lightest sufficient is the cheapest model whose mean recall trails the "
        f"best model on the same ladder by at most {margin:.2f}. A cheaper model "
        "is kept unless the measured gap exceeds the margin. `(gap unproven)` "
        "marks a verdict the corpus cannot prove: the lower bound of the paired "
        "bootstrap CI on the gap (95%, Bonferroni-split across the non-best swept "
        "models) falls below the negative margin.",
        "",
        *_summary_lines(entries, ladders),
        "",
        "## Per-model recall",
        "",
        *_detail_lines(entries),
    ]
    return "\n".join(lines) + "\n"


def render_json(entries: list[dict[str, Any]], *, margin: float, seed: int) -> str:
    """``routing.json`` with one entry per line.

    Pretty-printing every nested field runs past 3,000 lines for 46 entries.
    One compact line per entry keeps the file valid JSON and keeps each diff
    hunk to the subject whose verdict changed.
    """
    head = json.dumps({"schemaVersion": "1", "margin": margin, "seed": seed}, sort_keys=True)
    rows = ",\n".join(json.dumps(e, sort_keys=True) for e in entries)
    return f'{head[:-1]}, "entries": [\n{rows}\n]}}\n'


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval_model_routing", description=__doc__.splitlines()[0])
    parser.add_argument("--agents", default="", help="comma-separated agent names")
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        type=parse_skill,
        help="skill=agent: route the skill variant on that agent's fixtures (repeatable)",
    )
    parser.add_argument("--ladder", action="append", required=True, type=parse_ladder)
    parser.add_argument("--margin", type=float, default=DEFAULT_ROUTING_MARGIN)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "evals" / "model-routing")
    return parser


def _subjects(args: argparse.Namespace) -> list[Subject]:
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    return [Subject(name=a, agent=a, variant="agent") for a in agents] + list(args.skill)


def _route_or_error(
    subject: Subject, ladder: Ladder, args: argparse.Namespace, parse: ReportParser
) -> dict[str, Any]:
    try:
        return route_subject(subject, ladder, parse=parse, margin=args.margin, seed=args.seed)
    except (RollupError, SweepDecisionError, KeyError, ValueError, OSError) as exc:
        return {
            "subject": subject.name,
            "kind": subject.variant,
            "fixtures_agent": subject.agent,
            "ladder": ladder.name,
            "error": str(exc),
        }


def run(args: argparse.Namespace) -> int:
    subjects = _subjects(args)
    if not subjects:
        print("error: pass --agents or at least one --skill", file=sys.stderr)
        return EXIT_CONFIG
    if not math.isfinite(args.margin) or args.margin < 0:
        print(f"error: --margin must be finite and >= 0 (got {args.margin!r})", file=sys.stderr)
        return EXIT_CONFIG
    parse = _load_sweep_module().parse_report
    entries = [_route_or_error(s, lad, args, parse) for s in subjects for lad in args.ladder]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "routing.json").write_text(
        render_json(entries, margin=args.margin, seed=args.seed), encoding="utf-8"
    )
    (args.out_dir / "REPORT.md").write_text(
        render_markdown(entries, args.ladder, args.margin), encoding="utf-8"
    )
    failed = [e for e in entries if "error" in e]
    for entry in failed:
        reason = f"undecided: {entry['subject']} on {entry['ladder']}: {entry['error']}"
        print(reason, file=sys.stderr)
    routed = len(entries) - len(failed)
    print(f"routed {routed} of {len(entries)} subject-ladder pairs into {args.out_dir}")
    return EXIT_LOGIC if failed else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    return run(_build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
