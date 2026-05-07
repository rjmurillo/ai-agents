#!/usr/bin/env python3
"""Classify push guards into Hook Maturity Model tiers.

Consumes the JSON output of ``aggregate_guard_intercepts.py`` and assigns
each guard one of six tiers based on age, intercept volume, and a fitness
signal derived from block rate.

Tiers (evaluated in order; first match wins):

- ``Harmful``: any age, ≥1 intercept, fitness < ``-0.02``. Remove
  immediately. A guard that mostly fails open or that catches things it
  should not is doing harm; it normalizes bypass.
- ``Proficient``: ≥60 days since first event, ≥10 intercepts, fitness
  ≥ ``+0.02``. Promote and keep.
- ``Mature``: ≥30 days since first event, ≥5 intercepts, fitness ≥ 0.
  Keep and watch.
- ``Inert``: ≥30 days since first event, 0 intercepts. Prune candidate.
  Either no real diff has tripped it, or the validator is too narrow to
  fire.
- ``Growing``: ≥14 days since first event, ≥1 intercept, does not meet
  Mature/Proficient thresholds. Adolescent; too young for promotion, too
  productive to drop.
- ``Budding``: <14 days since first event. New, anything goes.

A guard with no events at all but listed by ``--guard`` falls into
``Budding`` if its days-since-first-event is null (never seen) and
``--treat-unseen-as-inert`` is false; pass that flag to mark guards
that have been registered for some time as Inert when their first event
is null. The default is conservative: a guard that has never fired
might just be brand new.

Fitness rationale: in this codebase a guard EITHER blocks (catches a
real or precautionary issue) OR fails open (the framework or the
validator could not run; see ``push_guard_base.py``'s contract).
``block_rate`` therefore measures "how often did the guard do its job
when it had the chance". Block rate alone is not a fitness *delta*: a
guard that always blocks may be too noisy. The classifier maps block
rate to a centered fitness value:

    fitness = block_rate - 0.5

So a guard that blocks half the time has fitness 0 (neutral); blocking
much more often is positive (doing real work); blocking far less than
half is negative (mostly noise / fail-opens). Thresholds use ``±0.02``
to capture meaningful positive or negative signal without rounding
small samples to zero.

Future work: the wiki's Hook Maturity Model concept references a
fitness score derived from "true positive vs noisy positive" signals
that this codebase does not capture today. When per-event ground-truth
labels exist, swap the fitness formula in ``compute_fitness`` without
changing the threshold table.

Exit codes (per AGENTS.md / ADR-035):
    0 = ok
    1 = logic error (input parsed but wrong shape, e.g. not a JSON object
        keyed by guard name)
    2 = config error (bad --source path, missing input on stdin, or input
        is not parseable JSON; the caller's environment is wrong)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Tier thresholds. Modify here to adjust policy; tests pin the canonical
# transitions so a change here is intentional.
HARMFUL_FITNESS_MAX = -0.02
PROFICIENT_FITNESS_MIN = 0.02
PROFICIENT_AGE_DAYS = 60.0
PROFICIENT_INTERCEPTS = 10
MATURE_AGE_DAYS = 30.0
MATURE_INTERCEPTS = 5
INERT_AGE_DAYS = 30.0
GROWING_AGE_MIN_DAYS = 14.0


def compute_fitness(block_rate: float) -> float:
    """Map block rate to a centered fitness signal.

    See module docstring for the choice. Centered on 0.5 so a balanced
    guard reads as neutral; positive values reward catching, negative
    values penalize fail-open dominance.
    """
    return block_rate - 0.5


def classify_one(summary: dict, treat_unseen_as_inert: bool = False) -> str:
    """Return the tier for a single guard summary.

    The summary shape matches ``aggregate_guard_intercepts.py`` output:
    keys ``total_events``, ``blocks``, ``fail_opens``, ``block_rate``,
    ``days_since_first_event``.
    """
    intercepts = int(summary.get("blocks", 0)) + int(summary.get("fail_opens", 0))
    block_rate = float(summary.get("block_rate", 0.0))
    fitness = compute_fitness(block_rate)
    age = summary.get("days_since_first_event")

    # Harmful first: a known-bad guard at any age is a remove-on-sight.
    if intercepts >= 1 and fitness < HARMFUL_FITNESS_MAX:
        return "Harmful"

    if age is None:
        # Never observed firing.
        if treat_unseen_as_inert:
            return "Inert"
        return "Budding"

    # Inert: been around long enough to fire, never did. Prune candidate.
    if age >= INERT_AGE_DAYS and intercepts == 0:
        return "Inert"

    # Proficient: mature, productive, positive fitness.
    if (age >= PROFICIENT_AGE_DAYS
            and intercepts >= PROFICIENT_INTERCEPTS
            and fitness >= PROFICIENT_FITNESS_MIN):
        return "Proficient"

    # Mature: settled and net-positive.
    if (age >= MATURE_AGE_DAYS
            and intercepts >= MATURE_INTERCEPTS
            and fitness >= 0):
        return "Mature"

    # Growing: adolescent age, has fired at least once but doesn't meet
    # Mature/Proficient thresholds.
    if age >= GROWING_AGE_MIN_DAYS and intercepts >= 1:
        return "Growing"

    # Budding: too young to assess, or in a quiet patch.
    return "Budding"


def classify(summaries: dict, treat_unseen_as_inert: bool = False) -> dict:
    """Classify every guard summary; return name -> {tier, fitness, ...}."""
    out: dict = {}
    for name, s in summaries.items():
        block_rate = float(s.get("block_rate", 0.0))
        intercepts = int(s.get("blocks", 0)) + int(s.get("fail_opens", 0))
        out[name] = {
            "guard": name,
            "tier": classify_one(s, treat_unseen_as_inert=treat_unseen_as_inert),
            "fitness": compute_fitness(block_rate),
            "intercepts": intercepts,
            "blocks": int(s.get("blocks", 0)),
            "fail_opens": int(s.get("fail_opens", 0)),
            "block_rate": block_rate,
            "days_since_first_event": s.get("days_since_first_event"),
            "days_since_last_event": s.get("days_since_last_event"),
        }
    return out


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify push guards by Hook Maturity Model tier.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Path to aggregator JSON output. Defaults to stdin.",
    )
    parser.add_argument(
        "--treat-unseen-as-inert",
        action="store_true",
        help=("Mark guards with null days_since_first_event as Inert "
              "instead of Budding. Use after enough wall-clock time has "
              "passed to expect at least one event."),
    )
    return parser


def _load_input(path_arg: str | None) -> dict:
    if path_arg:
        return json.loads(Path(path_arg).read_text(encoding="utf-8"))
    if sys.stdin.isatty():
        raise ValueError("no --source and no stdin")
    return json.loads(sys.stdin.read())


def main(argv: list[str] | None = None) -> int:
    parser = _build_argparser()
    args = parser.parse_args(argv)
    try:
        summaries = _load_input(args.source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot read aggregator JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(summaries, dict):
        print("error: aggregator JSON must be an object keyed by guard name.",
              file=sys.stderr)
        return 1
    classified = classify(summaries, treat_unseen_as_inert=args.treat_unseen_as_inert)
    json.dump(classified, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
