#!/usr/bin/env python3
"""Rule Activation Eval: measure whether `.claude/rules/*.md` files actually fire.

Tests how a rule activates across loading mechanisms:
  - baseline       : no rule context (control)
  - description    : only the rule's frontmatter description in system prompt
  - full           : entire rule body in system prompt (mimics @import or alwaysApply: true)

Each scenario is graded by an LLM judge on three dimensions (1-5):
  - activation_score : did the response apply rule-specific guidance vs generic advice?
  - citation_score   : did the response use the rule's specific vocabulary?
  - behavior_score   : did the response gate behavior on the rule's preconditions?

Compares mechanisms per scenario, aggregates to per-rule verdict.

Usage:
    # Eval one rule
    python3 scripts/eval/eval-rule-activation.py \
        --scenarios tests/evals/rule-scenarios/working-with-legacy-code.json

    # Dry run (skip API calls)
    python3 scripts/eval/eval-rule-activation.py \
        --scenarios tests/evals/rule-scenarios/working-with-legacy-code.json --dry-run

    # Multiple rules at once
    python3 scripts/eval/eval-rule-activation.py \
        --scenarios tests/evals/rule-scenarios/*.json

    # Save results
    python3 scripts/eval/eval-rule-activation.py \
        --scenarios tests/evals/rule-scenarios/working-with-legacy-code.json \
        --output rule-activation-results.json

Exit codes:
    0 ok
    1 logic (one or more rules failed activation gate)
    2 config (missing rule, scenarios file invalid)
    3 external (API failure)
    4 auth   (missing ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from _anthropic_api import call_api as _call_api
from _anthropic_api import load_api_key as _load_api_key
from _eval_common import EST_TOKENS_PER_CALL

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL = "claude-sonnet-4-20250514"
RATE_LIMIT_SLEEP_SEC = 1.0
MECHANISMS = ("baseline", "description", "full")

# Rule passes activation gate if avg(activation+citation+behavior) >= this for the
# best mechanism on each non-negative-case scenario, AND baseline scores below it.
MIN_ACTIVATION_SCORE = 3.5
MIN_DELTA_VS_BASELINE = 0.5


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------


def parse_rule(rule_path: Path) -> dict[str, str]:
    """Split a rule file into frontmatter description and body."""
    text = rule_path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not fm_match:
        return {"description": "", "body": text, "frontmatter": ""}

    frontmatter = fm_match.group(1)
    body = fm_match.group(2)

    desc_match = re.search(r"^description:\s*(.+?)$", frontmatter, re.MULTILINE)
    description = desc_match.group(1).strip() if desc_match else ""

    return {
        "description": description,
        "body": body,
        "frontmatter": frontmatter,
    }


def build_system_prompt(mechanism: str, rule: dict[str, str]) -> str:
    """Construct the system prompt for a given activation mechanism."""
    if mechanism == "baseline":
        return ""
    if mechanism == "description":
        if not rule["description"]:
            return ""
        return (
            "Project rules apply to your work. Available rule:\n\n"
            f"  - working-with-legacy-code: {rule['description']}\n\n"
            "Decide whether to apply rules based on the user's request and apply them when relevant."
        )
    if mechanism == "full":
        return (
            "The following project rule applies to your work. "
            "Apply it when relevant.\n\n"
            f"{rule['body']}"
        )
    raise ValueError(f"Unknown mechanism: {mechanism}")


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------


def score_response(
    api_key: str,
    scenario: dict[str, Any],
    response: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Use the API to score a response on rule activation."""
    expected_signals = scenario.get("expected_signals", [])
    expected_gate = scenario.get("expected_gate", "")
    rationale = scenario.get("rationale", "")

    is_negative = expected_gate == "skip-rule-not-applicable"

    judge_prompt = f"""Score this response on three dimensions (1-5 each).

**Scenario**: {scenario.get("desc", "")}
**Rationale**: {rationale}
**Expected signals (vocabulary the rule prescribes)**: {", ".join(expected_signals) if expected_signals else "none"}
**Expected behavior gate**: {expected_gate or "none"}
**Negative case (rule should NOT activate)**: {"YES" if is_negative else "no"}

**User prompt**: {scenario.get("input", "")}

**Actual response**:
{response}

Score on these dimensions (1=absent, 5=clearly present):

- **activation_score**: did the response apply guidance specific to the scenario's rule, or only generic advice? (negative case: 5 means the response correctly DID NOT activate the rule and gave generic advice instead)
- **citation_score**: did the response use the expected vocabulary or cite specific concepts? (negative case: 5 means absence of these concepts)
- **behavior_score**: did the response gate the behavior on the rule's preconditions (e.g., write tests first, separate commits, refuse deletion)? (negative case: 5 means the response correctly proceeded without the unnecessary gate)

Respond in JSON only, no other text:
{{"activation_score": <int>, "citation_score": <int>, "behavior_score": <int>, "reasoning": "<one sentence>"}}"""

    raw = _call_api(api_key, [{"role": "user", "content": judge_prompt}], model=model)

    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()

    try:
        scores: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        return {
            "activation_score": 0,
            "citation_score": 0,
            "behavior_score": 0,
            "reasoning": f"judge parse error: {text[:200]}",
        }
    return scores


# ---------------------------------------------------------------------------
# Eval driver
# ---------------------------------------------------------------------------


def eval_one_scenario(
    api_key: str,
    rule: dict[str, str],
    scenario: dict[str, Any],
    model: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Run all mechanisms on one scenario."""
    result: dict[str, Any] = {
        "id": scenario["id"],
        "desc": scenario.get("desc", ""),
        "negative_case": scenario.get("expected_gate") == "skip-rule-not-applicable",
        "mechanisms": {},
    }

    for mechanism in MECHANISMS:
        system = build_system_prompt(mechanism, rule)
        if dry_run:
            result["mechanisms"][mechanism] = {
                "response_preview": "(dry-run, no API call)",
                "scores": {"activation_score": 0, "citation_score": 0, "behavior_score": 0},
                "system_prompt_chars": len(system),
            }
            continue

        try:
            response = _call_api(
                api_key,
                [{"role": "user", "content": scenario["input"]}],
                system=system,
                model=model,
                max_tokens=600,
            )
        except RuntimeError as e:
            result["mechanisms"][mechanism] = {
                "error": str(e),
                "scores": {"activation_score": 0, "citation_score": 0, "behavior_score": 0},
            }
            continue

        time.sleep(RATE_LIMIT_SLEEP_SEC)
        scores = score_response(api_key, scenario, response, model=model)
        time.sleep(RATE_LIMIT_SLEEP_SEC)
        result["mechanisms"][mechanism] = {
            "response_preview": response[:400] + ("..." if len(response) > 400 else ""),
            "scores": scores,
            "system_prompt_chars": len(system),
        }
    return result


def aggregate(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-mechanism averages across scenarios (positive cases only)."""
    summary: dict[str, Any] = {"per_mechanism": {}}
    pos_scenarios = [s for s in scenarios if not s["negative_case"]]
    neg_scenarios = [s for s in scenarios if s["negative_case"]]

    for mech in MECHANISMS:
        all_scores: list[float] = []
        for s in pos_scenarios:
            sc = s["mechanisms"].get(mech, {}).get("scores", {})
            triple = [
                sc.get("activation_score", 0),
                sc.get("citation_score", 0),
                sc.get("behavior_score", 0),
            ]
            if any(triple):
                all_scores.append(sum(triple) / 3)
        avg = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0
        summary["per_mechanism"][mech] = {
            "avg_score": avg,
            "scenario_count": len(all_scores),
        }

    # Negative case (rule should NOT fire). Higher score = response correctly stayed generic.
    summary["negative_case_per_mechanism"] = {}
    for mech in MECHANISMS:
        all_scores = []
        for s in neg_scenarios:
            sc = s["mechanisms"].get(mech, {}).get("scores", {})
            triple = [
                sc.get("activation_score", 0),
                sc.get("citation_score", 0),
                sc.get("behavior_score", 0),
            ]
            if any(triple):
                all_scores.append(sum(triple) / 3)
        avg = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0
        summary["negative_case_per_mechanism"][mech] = {
            "avg_score": avg,
            "scenario_count": len(all_scores),
        }

    # Verdict: full and description should beat baseline by MIN_DELTA on positive cases,
    # and at least one mechanism must clear MIN_ACTIVATION_SCORE.
    baseline_avg = summary["per_mechanism"]["baseline"]["avg_score"]
    desc_avg = summary["per_mechanism"]["description"]["avg_score"]
    full_avg = summary["per_mechanism"]["full"]["avg_score"]

    best_mech = max(MECHANISMS, key=lambda m: summary["per_mechanism"][m]["avg_score"])
    best_avg = summary["per_mechanism"][best_mech]["avg_score"]

    summary["best_mechanism"] = best_mech
    summary["best_avg_score"] = best_avg
    summary["baseline_avg"] = baseline_avg
    summary["delta_full_vs_baseline"] = round(full_avg - baseline_avg, 2)
    summary["delta_description_vs_baseline"] = round(desc_avg - baseline_avg, 2)

    if pos_scenarios:
        passes_threshold = best_avg >= MIN_ACTIVATION_SCORE
        beats_baseline = (full_avg - baseline_avg) >= MIN_DELTA_VS_BASELINE or (
            desc_avg - baseline_avg
        ) >= MIN_DELTA_VS_BASELINE
        summary["verdict"] = (
            "PASS"
            if passes_threshold and beats_baseline
            else "FAIL_THRESHOLD"
            if not passes_threshold
            else "FAIL_NO_DELTA"
        )
    else:
        summary["verdict"] = "NO_POSITIVE_CASES"

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def render_table(rule_id: str, summary: dict[str, Any]) -> str:
    rows = [
        f"\nRule: {rule_id}",
        f"Verdict: {summary['verdict']}",
        f"Best mechanism: {summary['best_mechanism']} (avg {summary['best_avg_score']})",
        "",
        "| Mechanism    | Pos avg | Neg avg | Δ vs baseline |",
        "|--------------|---------|---------|---------------|",
    ]
    for mech in MECHANISMS:
        pos = summary["per_mechanism"][mech]["avg_score"]
        neg = summary["negative_case_per_mechanism"][mech]["avg_score"]
        delta = (
            ""
            if mech == "baseline"
            else f"+{round(pos - summary['baseline_avg'], 2)}"
        )
        rows.append(f"| {mech:<12} | {pos:>7} | {neg:>7} | {delta:>13} |")
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Eval rule activation across loading mechanisms.")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        required=True,
        help="One or more scenario JSON files (tests/evals/rule-scenarios/*.json).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model identifier.")
    parser.add_argument("--output", help="Write detailed JSON results to this path.")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls, print plan.")
    args = parser.parse_args()

    if not args.dry_run:
        try:
            api_key = _load_api_key()
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 4
    else:
        api_key = ""

    all_results: dict[str, Any] = {"rules": {}}
    overall_pass = True
    total_calls = 0

    for scenario_file in args.scenarios:
        spath = Path(scenario_file)
        if not spath.is_file():
            print(f"ERROR: scenario file not found: {spath}", file=sys.stderr)
            return 2
        scenarios_data = json.loads(spath.read_text(encoding="utf-8"))

        rule_path_str = scenarios_data.get("rule_path")
        if not rule_path_str:
            print(f"ERROR: missing rule_path in {spath}", file=sys.stderr)
            return 2
        rule_path = REPO_ROOT / rule_path_str
        if not rule_path.is_file():
            print(f"ERROR: rule not found: {rule_path}", file=sys.stderr)
            return 2

        rule_id = scenarios_data.get("rule_id", rule_path.stem)
        rule = parse_rule(rule_path)

        scenarios = scenarios_data.get("scenarios", [])
        n_scenarios = len(scenarios)
        n_calls = n_scenarios * len(MECHANISMS) * 2  # call + judge
        total_calls += n_calls

        if args.dry_run:
            print(f"[DRY-RUN] {rule_id}: {n_scenarios} scenarios x {len(MECHANISMS)} mechanisms = {n_calls} calls")
            print(f"  description present: {bool(rule['description'])}")
            print(f"  body chars: {len(rule['body'])}")
            continue

        scenario_results: list[dict[str, Any]] = []
        for sc in scenarios:
            print(f"  scenario {sc['id']}: {sc.get('desc','')[:60]}...", file=sys.stderr)
            r = eval_one_scenario(api_key, rule, sc, args.model, dry_run=False)
            scenario_results.append(r)

        summary = aggregate(scenario_results)
        all_results["rules"][rule_id] = {
            "rule_path": rule_path_str,
            "summary": summary,
            "scenarios": scenario_results,
        }
        print(render_table(rule_id, summary))
        if summary["verdict"] not in ("PASS", "NO_POSITIVE_CASES"):
            overall_pass = False

    if args.dry_run:
        est_tokens = total_calls * EST_TOKENS_PER_CALL
        print(f"\nTotal calls planned: {total_calls}")
        print(f"Estimated tokens: ~{est_tokens:,} (~${est_tokens / 1_000_000 * 3:.2f} sonnet input rate)")
        return 0

    if args.output:
        Path(args.output).write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        print(f"\nWrote results: {args.output}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
