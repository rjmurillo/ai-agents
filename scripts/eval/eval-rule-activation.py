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


def build_system_prompt(mechanism: str, rule: dict[str, str], rule_id: str) -> str:
    """Construct the system prompt for a given activation mechanism."""
    if mechanism == "baseline":
        return ""
    if mechanism == "description":
        if not rule["description"]:
            return ""
        return (
            "Project rules apply to your work. Available rule:\n\n"
            f"  - {rule_id}: {rule['description']}\n\n"
            "Decide whether to apply rules based on the user's request "
            "and apply them when relevant."
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
    signals_str = ", ".join(expected_signals) if expected_signals else "none"
    negative_flag = "YES" if is_negative else "no"

    activation_doc = (
        "did the response apply guidance specific to the scenario's rule, "
        "or only generic advice? "
        "(negative case: 5 means the response correctly did NOT activate "
        "the rule and gave generic advice instead)"
    )
    citation_doc = (
        "did the response use the expected vocabulary or cite specific "
        "concepts? (negative case: 5 means absence of these concepts)"
    )
    behavior_doc = (
        "did the response gate the behavior on the rule's preconditions "
        "(e.g., write tests first, separate commits, refuse deletion)? "
        "(negative case: 5 means the response correctly proceeded without "
        "the unnecessary gate)"
    )
    json_schema = (
        '{"activation_score": <int>, "citation_score": <int>, '
        '"behavior_score": <int>, "reasoning": "<one sentence>"}'
    )

    judge_prompt = f"""Score this response on three dimensions (1-5 each).

**Scenario**: {scenario.get("desc", "")}
**Rationale**: {rationale}
**Expected signals (vocabulary the rule prescribes)**: {signals_str}
**Expected behavior gate**: {expected_gate or "none"}
**Negative case (rule should NOT activate)**: {negative_flag}

**User prompt**: {scenario.get("input", "")}

**Actual response**:
{response}

Score on these dimensions (1=absent, 5=clearly present):

- **activation_score**: {activation_doc}
- **citation_score**: {citation_doc}
- **behavior_score**: {behavior_doc}

Respond in JSON only, no other text:
{json_schema}"""

    raw = _call_api(api_key, [{"role": "user", "content": judge_prompt}], model=model)

    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()

    try:
        parsed: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        return {
            "activation_score": 0,
            "citation_score": 0,
            "behavior_score": 0,
            "reasoning": f"judge parse error: {text[:200]}",
            "judge_failed": True,
        }
    return {
        "activation_score": _clamp_score(parsed.get("activation_score")),
        "citation_score": _clamp_score(parsed.get("citation_score")),
        "behavior_score": _clamp_score(parsed.get("behavior_score")),
        "reasoning": str(parsed.get("reasoning", ""))[:300],
        "judge_failed": False,
    }


def _clamp_score(value: object) -> int:
    """Coerce a judge-supplied score to int in [0, 5]. Strings/None/out-of-range -> 0 or clamped."""
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, n))


# ---------------------------------------------------------------------------
# Eval driver
# ---------------------------------------------------------------------------


def eval_one_scenario(
    api_key: str,
    rule: dict[str, str],
    rule_id: str,
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
        system = build_system_prompt(mechanism, rule, rule_id)
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
        try:
            scores = score_response(api_key, scenario, response, model=model)
        except RuntimeError as e:
            result["mechanisms"][mechanism] = {
                "error": f"judge API failure: {e}",
                "response_preview": response[:400] + ("..." if len(response) > 400 else ""),
                "scores": {"activation_score": 0, "citation_score": 0, "behavior_score": 0},
            }
            continue
        time.sleep(RATE_LIMIT_SLEEP_SEC)
        result["mechanisms"][mechanism] = {
            "response_preview": response[:400] + ("..." if len(response) > 400 else ""),
            "scores": scores,
            "system_prompt_chars": len(system),
        }
    return result


def _scenario_score_triple(scenario: dict[str, Any], mech: str) -> tuple[float, bool]:
    """Return (mean_score, judge_failed) for one scenario at one mechanism.

    Every scenario contributes to the average, including failed evaluations.
    A failed judge or API call yields mean=0 and judge_failed=True so callers
    can surface failures rather than silently filtering them.
    """
    mech_data = scenario["mechanisms"].get(mech, {})
    sc = mech_data.get("scores", {})
    triple = [
        sc.get("activation_score", 0),
        sc.get("citation_score", 0),
        sc.get("behavior_score", 0),
    ]
    failed = bool(sc.get("judge_failed")) or "error" in mech_data
    return sum(triple) / 3, failed


def _mechanism_summary(
    pool: list[dict[str, Any]], mech: str
) -> dict[str, Any]:
    """Compute avg_score across every scenario for one mechanism."""
    scores: list[float] = []
    failures = 0
    for s in pool:
        score, failed = _scenario_score_triple(s, mech)
        scores.append(score)
        if failed:
            failures += 1
    avg = round(sum(scores) / len(scores), 2) if scores else 0.0
    return {
        "avg_score": avg,
        "scenario_count": len(scores),
        "judge_failures": failures,
    }


def aggregate(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-mechanism averages across scenarios.

    Counts every scenario in the average. Failed evaluations contribute their
    zero scores rather than being filtered, preventing false PASS verdicts when
    the judge or API breaks. The summary exposes per-mechanism judge_failures
    so the caller can fail loudly when failures are non-zero.
    """
    summary: dict[str, Any] = {"per_mechanism": {}, "negative_case_per_mechanism": {}}
    pos_scenarios = [s for s in scenarios if not s["negative_case"]]
    neg_scenarios = [s for s in scenarios if s["negative_case"]]

    for mech in MECHANISMS:
        summary["per_mechanism"][mech] = _mechanism_summary(pos_scenarios, mech)
        summary["negative_case_per_mechanism"][mech] = _mechanism_summary(
            neg_scenarios, mech
        )

    baseline_avg = summary["per_mechanism"]["baseline"]["avg_score"]
    desc_avg = summary["per_mechanism"]["description"]["avg_score"]
    full_avg = summary["per_mechanism"]["full"]["avg_score"]

    # `best_mechanism` is what the rule author should ship. Baseline is the
    # control; selecting it as best would say "the rule is not needed" and
    # mask a real activation failure as FAIL_NO_DELTA. Pick from rule-enhanced
    # mechanisms only.
    rule_enhanced = [m for m in MECHANISMS if m != "baseline"]
    best_mech = max(
        rule_enhanced, key=lambda m: summary["per_mechanism"][m]["avg_score"]
    )
    best_avg = summary["per_mechanism"][best_mech]["avg_score"]

    total_judge_failures = sum(
        summary["per_mechanism"][m]["judge_failures"] for m in MECHANISMS
    ) + sum(
        summary["negative_case_per_mechanism"][m]["judge_failures"]
        for m in MECHANISMS
    )

    summary["best_mechanism"] = best_mech
    summary["best_avg_score"] = best_avg
    summary["baseline_avg"] = baseline_avg
    summary["delta_full_vs_baseline"] = round(full_avg - baseline_avg, 2)
    summary["delta_description_vs_baseline"] = round(desc_avg - baseline_avg, 2)
    summary["total_judge_failures"] = total_judge_failures

    if total_judge_failures > 0:
        summary["verdict"] = "FAIL_JUDGE_ERRORS"
    elif not pos_scenarios:
        summary["verdict"] = "NO_POSITIVE_CASES"
    else:
        passes_threshold = best_avg >= MIN_ACTIVATION_SCORE
        beats_baseline = (full_avg - baseline_avg) >= MIN_DELTA_VS_BASELINE or (
            desc_avg - baseline_avg
        ) >= MIN_DELTA_VS_BASELINE
        if passes_threshold and beats_baseline:
            summary["verdict"] = "PASS"
        elif not passes_threshold:
            summary["verdict"] = "FAIL_THRESHOLD"
        else:
            summary["verdict"] = "FAIL_NO_DELTA"

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
        if mech == "baseline":
            delta = ""
        else:
            delta_val = round(pos - summary["baseline_avg"], 2)
            delta = f"{delta_val:+}"
        rows.append(f"| {mech:<12} | {pos:>7} | {neg:>7} | {delta:>13} |")
    return "\n".join(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eval rule activation across loading mechanisms."
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        required=True,
        help="One or more scenario JSON files (tests/evals/rule-scenarios/*.json).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model identifier.")
    parser.add_argument("--output", help="Write detailed JSON results to this path.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip API calls, print plan.",
    )
    return parser.parse_args()


def _load_scenarios_file(scenario_file: str) -> tuple[dict[str, Any], Path] | int:
    """Return (scenarios_data, resolved rule_path) on success, exit code on error.

    Validates that rule_path stays inside the repository root so a crafted
    scenario file cannot exfiltrate files outside `.claude/rules/`.
    """
    spath = Path(scenario_file)
    if not spath.is_file():
        print(f"ERROR: scenario file not found: {spath}", file=sys.stderr)
        return 2

    try:
        scenarios_data = json.loads(spath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {spath}: {exc}", file=sys.stderr)
        return 2

    rule_path_str = scenarios_data.get("rule_path")
    if not rule_path_str:
        print(f"ERROR: missing rule_path in {spath}", file=sys.stderr)
        return 2

    repo_root_resolved = REPO_ROOT.resolve()
    rule_path = (REPO_ROOT / rule_path_str).resolve()
    try:
        rule_path.relative_to(repo_root_resolved)
    except ValueError:
        print(
            f"ERROR: rule_path escapes repository root: {rule_path_str}",
            file=sys.stderr,
        )
        return 2
    if not rule_path.is_file():
        print(f"ERROR: rule not found: {rule_path}", file=sys.stderr)
        return 2
    return scenarios_data, rule_path


def _process_one_rule(
    api_key: str,
    scenarios_data: dict[str, Any],
    rule_path: Path,
    args: argparse.Namespace,
) -> tuple[str, dict[str, Any] | None, int]:
    """Run all scenarios for one rule. Return (rule_id, result_dict_or_none, n_calls)."""
    rule_id = scenarios_data.get("rule_id", rule_path.stem)
    rule = parse_rule(rule_path)
    scenarios = scenarios_data.get("scenarios", [])
    n_calls = len(scenarios) * len(MECHANISMS) * 2  # call + judge

    if args.dry_run:
        print(
            f"[DRY-RUN] {rule_id}: {len(scenarios)} scenarios x "
            f"{len(MECHANISMS)} mechanisms x 2 (call + judge) = {n_calls} calls"
        )
        print(f"  description present: {bool(rule['description'])}")
        print(f"  body chars: {len(rule['body'])}")
        return rule_id, None, n_calls

    scenario_results: list[dict[str, Any]] = []
    for sc in scenarios:
        preview = sc.get("desc", "")[:60]
        print(f"  scenario {sc['id']}: {preview}...", file=sys.stderr)
        r = eval_one_scenario(api_key, rule, rule_id, sc, args.model, dry_run=False)
        scenario_results.append(r)

    summary = aggregate(scenario_results)
    print(render_table(rule_id, summary))
    return rule_id, {
        "rule_path": str(rule_path.relative_to(REPO_ROOT)),
        "summary": summary,
        "scenarios": scenario_results,
    }, n_calls


def main() -> int:
    args = _parse_args()

    if args.dry_run:
        api_key = ""
    else:
        try:
            api_key = _load_api_key()
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 4

    all_results: dict[str, Any] = {"rules": {}}
    overall_pass = True
    total_calls = 0

    for scenario_file in args.scenarios:
        loaded = _load_scenarios_file(scenario_file)
        if isinstance(loaded, int):
            return loaded
        scenarios_data, rule_path = loaded

        rule_id, result, n_calls = _process_one_rule(
            api_key, scenarios_data, rule_path, args
        )
        total_calls += n_calls

        if result is not None:
            all_results["rules"][rule_id] = result
            if result["summary"]["verdict"] not in ("PASS", "NO_POSITIVE_CASES"):
                overall_pass = False

    if args.dry_run:
        est_tokens = total_calls * EST_TOKENS_PER_CALL
        est_cost = est_tokens / 1_000_000 * 3
        print(f"\nTotal calls planned: {total_calls}")
        print(f"Estimated tokens: ~{est_tokens:,} (~${est_cost:.2f} sonnet input rate)")
        return 0

    if args.output:
        Path(args.output).write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        print(f"\nWrote results: {args.output}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
