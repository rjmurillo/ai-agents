#!/usr/bin/env python3
"""ADR-057 Compliant Prompt Change Evaluator.

Validates behavioral correctness of prompt changes using scenario-based
LLM judgment with before/after comparison. Implements the acceptance gate,
security-critical tier, and flakiness protocol from ADR-057.

Usage:
    # Compare working copy against base branch:
    python3 scripts/eval/eval-prompt-change.py \\
        --prompt .claude/commands/research.md \\
        --scenarios tests/evals/research-scenarios.json \\
        --base-ref main

    # Explicit before/after files:
    python3 scripts/eval/eval-prompt-change.py \\
        --before prompt-old.md --after prompt-new.md \\
        --scenarios tests/evals/research-scenarios.json

    # Security-critical prompt (5 runs, 100% pass):
    python3 scripts/eval/eval-prompt-change.py \\
        --prompt .agents/security/prompts/security-review.md \\
        --scenarios tests/evals/security-review-scenarios.json \\
        --base-ref main --security-critical

    # Dry run (validate scenario file, no API calls):
    python3 scripts/eval/eval-prompt-change.py \\
        --prompt .claude/commands/research.md \\
        --scenarios tests/evals/research-scenarios.json \\
        --dry-run

Scenario file format (JSON):
    {
        "scenarios": [
            {
                "id": "S1",
                "desc": "Budget exhausted stops execution",
                "input": "...simulated context...",
                "expected_verdict": "STOP",
                "verdict_options": ["STOP", "CONTINUE", "ESCALATE"],
                "expected_reason_contains": "budget",
                "rationale": "Stop condition fires before next phase"
            }
        ]
    }

Verdict matching contract:
    - The judge prompt instructs the LLM to emit a verdict from a fixed set of
      canonical labels (the controlled vocabulary).
    - If `verdict_options` is supplied, those are the allowed labels; the LLM
      is told to pick exactly one. `expected_verdict` MUST appear in the list.
    - If `verdict_options` is omitted, the labels default to
      `[expected_verdict, "OTHER"]`. This forces a binary classification when
      the scenario only cares about one outcome.
    - Verdicts are uppercased before comparison; `check_scenario_pass` does an
      exact match against `expected_verdict`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from _anthropic_api import call_api, load_api_key
from _eval_common import EST_TOKENS_PER_CALL

RATE_LIMIT_SLEEP_SEC = 1.0
DEFAULT_RUNS = 3
SECURITY_RUNS = 5
FLAKINESS_BLOCK_THRESHOLD = 0.4


# ---------------------------------------------------------------------------
# Scenario loading and validation
# ---------------------------------------------------------------------------

REQUIRED_SCENARIO_FIELDS = {"id", "desc", "input", "expected_verdict"}
OPTIONAL_SCENARIO_FIELDS = {"expected_reason_contains", "rationale", "verdict_options"}
DEFAULT_FALLBACK_VERDICT = "OTHER"


def load_scenarios(path: str) -> list[dict[str, Any]]:
    """Load and validate scenario file.

    Raises RuntimeError with actionable message on invalid input.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Scenario file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in scenario file {path}: {exc.msg} at line {exc.lineno}. "
            f"Expected format: {{\"scenarios\": [{{\"id\": \"S1\", \"desc\": \"...\", "
            f"\"input\": \"...\", \"expected_verdict\": \"...\"}}]}}"
        ) from exc

    scenarios = data.get("scenarios", data) if isinstance(data, dict) else data
    if not isinstance(scenarios, list):
        raise RuntimeError(
            f"Invalid scenario file {path}: expected 'scenarios' array "
            f"or top-level array."
        )

    if not scenarios:
        raise RuntimeError(
            f"Scenario file {path} has 0 scenarios. "
            f"ADR-057 requires at least 1 per decision branch."
        )

    for i, s in enumerate(scenarios):
        if not isinstance(s, dict):
            raise RuntimeError(
                f"Scenario at index {i} in {path} is not a JSON object "
                f"(got {type(s).__name__}). Each scenario must be an object "
                f"with at least these fields: {REQUIRED_SCENARIO_FIELDS}."
            )
        missing = REQUIRED_SCENARIO_FIELDS - set(s.keys())
        if missing:
            raise RuntimeError(
                f"Scenario {i} in {path} missing required fields: {missing}. "
                f"Required: {REQUIRED_SCENARIO_FIELDS}"
            )
        opts = s.get("verdict_options")
        if opts is not None:
            if not isinstance(opts, list) or not opts:
                raise RuntimeError(
                    f"Scenario {s['id']} in {path}: 'verdict_options' must be a "
                    f"non-empty list when present."
                )
            opts_upper: list[str] = []
            seen_opts: set[str] = set()
            for opt in opts:
                normalized_opt = str(opt).strip().upper()
                if not normalized_opt:
                    raise RuntimeError(
                        f"Scenario {s['id']} in {path}: 'verdict_options' contains "
                        f"an empty label after normalization. Remove blank or "
                        f"whitespace-only entries."
                    )
                if normalized_opt in seen_opts:
                    raise RuntimeError(
                        f"Scenario {s['id']} in {path}: 'verdict_options' contains "
                        f"duplicate label {normalized_opt!r} after normalization. "
                        f"Ensure labels are unique ignoring case and surrounding "
                        f"whitespace."
                    )
                seen_opts.add(normalized_opt)
                opts_upper.append(normalized_opt)
            if str(s["expected_verdict"]).strip().upper() not in opts_upper:
                raise RuntimeError(
                    f"Scenario {s['id']} in {path}: expected_verdict "
                    f"{s['expected_verdict']!r} is not in verdict_options "
                    f"{opts}. Add it or remove verdict_options."
                )

    return scenarios


def _verdict_options(scenario: dict[str, Any]) -> list[str]:
    """Return the controlled vocabulary for a scenario, uppercased and stripped.

    Uses `verdict_options` if present; otherwise falls back to
    `[expected_verdict, DEFAULT_FALLBACK_VERDICT]` to force binary classification.
    Whitespace is stripped from labels to keep the LLM-facing vocabulary clean.
    """
    raw = scenario.get("verdict_options")
    if raw:
        return [str(o).strip().upper() for o in raw]
    expected = str(scenario["expected_verdict"]).strip().upper()
    if expected == DEFAULT_FALLBACK_VERDICT:
        return [expected]
    return [expected, DEFAULT_FALLBACK_VERDICT]


# ---------------------------------------------------------------------------
# Prompt loading (before/after)
# ---------------------------------------------------------------------------

def load_prompt_from_ref(prompt_path: str, ref: str) -> str:
    """Load prompt text from a git ref (branch, commit, tag).

    Raises RuntimeError if the file does not exist at that ref.
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{prompt_path}"],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Cannot load {prompt_path} from ref '{ref}': {e.stderr.strip()}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"Timed out loading {prompt_path} from ref '{ref}' after {e.timeout}s. "
            f"Check that the git ref exists and the repository is accessible."
        ) from e


def load_prompt_from_file(path: str) -> str:
    """Load prompt text from a file path."""
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"Prompt file not found: {path}")
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Scenario judgment
# ---------------------------------------------------------------------------

def judge_scenario(
    api_key: str,
    prompt_text: str,
    scenario: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    """Invoke the LLM with prompt as system + scenario input as user message.

    Returns parsed verdict dict with verdict, reason, and raw response.
    """
    system_prompt = prompt_text
    options = _verdict_options(scenario)
    options_str = ", ".join(options)

    fallback_hint = ""
    if len(options) > 1 and DEFAULT_FALLBACK_VERDICT in options:
        fallback_hint = (
            f"Use {DEFAULT_FALLBACK_VERDICT} only if no other label fits.\n"
        )

    user_message = (
        f"Scenario: {scenario['desc']}\n\n"
        f"Context:\n{scenario['input']}\n\n"
        "Based on your instructions, classify your action.\n"
        f"Your verdict MUST be exactly one of these labels (uppercase, "
        f"no extra words): {options_str}.\n"
        f"{fallback_hint}"
        "Respond with a JSON object only, no surrounding prose: "
        '{"verdict": "<one of the labels>", "reason": "<brief explanation>"}'
    )

    raw = call_api(
        api_key,
        [{"role": "user", "content": user_message}],
        system=system_prompt,
        model=model,
        max_tokens=1024,
    )

    # Parse JSON from response
    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # Try to find JSON object in response (handles nested objects)
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            return {
                "verdict": str(parsed.get("verdict", "UNKNOWN")).upper(),
                "reason": str(parsed.get("reason", "")),
                "raw": raw,
            }
        except json.JSONDecodeError:
            pass

    return {"verdict": "PARSE_ERROR", "reason": f"Could not parse: {text[:200]}", "raw": raw}


def check_scenario_pass(result: dict[str, Any], scenario: dict[str, Any]) -> bool:
    """Check if a single scenario result matches expectations.

    Match rules (controlled vocabulary; see module docstring):
        - Verdict matches if `result["verdict"]` equals `expected_verdict`
          (uppercased).
        - If `expected_reason_contains` is set, the substring must appear in
          `result["reason"]` (case-insensitive).
        - Both checks must pass.
    """
    expected_upper = str(scenario["expected_verdict"]).strip().upper()
    actual_upper = str(result.get("verdict", "")).strip().upper()
    verdict_match = actual_upper == expected_upper

    reason_match = True
    expected_substr = scenario.get("expected_reason_contains")
    if expected_substr:
        reason_match = str(expected_substr).lower() in str(result.get("reason", "")).lower()

    return verdict_match and reason_match


# ---------------------------------------------------------------------------
# Multi-run with flakiness protocol (ADR-057)
# ---------------------------------------------------------------------------

def run_scenario_multi(
    api_key: str,
    prompt_text: str,
    scenario: dict[str, Any],
    model: str,
    runs: int,
) -> dict[str, Any]:
    """Run a scenario multiple times and aggregate per ADR-057 flakiness protocol.

    Non-security: passes if >= 2/3 runs succeed.
    Security-critical: passes if 100% of runs succeed (enforced by caller).
    """
    run_results = []
    for _ in range(runs):
        result = judge_scenario(api_key, prompt_text, scenario, model)
        result["passed"] = check_scenario_pass(result, scenario)
        result["model_used"] = model
        run_results.append(result)
        time.sleep(RATE_LIMIT_SLEEP_SEC)

    passes = sum(1 for r in run_results if r["passed"])
    pass_rate = passes / runs

    return {
        "scenario_id": scenario["id"],
        "passes": passes,
        "runs": runs,
        "pass_rate": pass_rate,
        "passed": passes >= max(1, (runs * 2) // 3),  # 2/3 threshold
        "flaky": 0 < passes < runs,
        "per_run": run_results,
    }


# ---------------------------------------------------------------------------
# Before/after comparison
# ---------------------------------------------------------------------------

def run_comparison(
    api_key: str,
    before_text: str,
    after_text: str,
    scenarios: list[dict[str, Any]],
    model: str,
    runs: int,
) -> dict[str, Any]:
    """Run all scenarios against before and after prompt text.

    Returns comparison results with scores and per-scenario detail.
    """
    before_results = []
    after_results = []
    api_call_count = 0

    total = len(scenarios)
    for i, scenario in enumerate(scenarios):
        print(f"  [{i+1}/{total}] {scenario['id']}: {scenario['desc'][:60]}...", file=sys.stderr)

        print(f"    BEFORE ({runs} runs)...", file=sys.stderr)
        before = run_scenario_multi(api_key, before_text, scenario, model, runs)
        before_results.append(before)
        api_call_count += runs

        print(f"    AFTER  ({runs} runs)...", file=sys.stderr)
        after = run_scenario_multi(api_key, after_text, scenario, model, runs)
        after_results.append(after)
        api_call_count += runs

        b_tag = "PASS" if before["passed"] else "FAIL"
        a_tag = "PASS" if after["passed"] else "FAIL"
        flaky_b = " [FLAKY]" if before["flaky"] else ""
        flaky_a = " [FLAKY]" if after["flaky"] else ""
        print(f"    {b_tag}{flaky_b} -> {a_tag}{flaky_a}", file=sys.stderr)

    before_score = sum(1 for r in before_results if r["passed"]) / total
    after_score = sum(1 for r in after_results if r["passed"]) / total

    est_tokens = api_call_count * EST_TOKENS_PER_CALL
    print(f"\n  Cost: {api_call_count} API calls, ~{est_tokens:,} tokens", file=sys.stderr)

    return {
        "before_score": round(before_score, 4),
        "after_score": round(after_score, 4),
        "delta": round(after_score - before_score, 4),
        "scenario_count": total,
        "api_calls": api_call_count,
        "est_tokens": est_tokens,
        "model": model,
        "before_results": before_results,
        "after_results": after_results,
    }


# ---------------------------------------------------------------------------
# Acceptance gate (ADR-057 three criteria)
# ---------------------------------------------------------------------------

def acceptance_gate(
    comparison: dict[str, Any],
    security_critical: bool = False,
) -> dict[str, Any]:
    """Apply ADR-057 three-criteria acceptance gate.

    Criteria:
    1. after_score >= before_score (no regression)
    2. Any targeted scenario moves from fail to pass
    3. No scenario flips pass->fail without justification

    Security-critical tier: all runs must pass (100% pass rate).
    """
    before_results = comparison["before_results"]
    after_results = comparison["after_results"]

    # Criterion 1: no regression
    no_regression = comparison["after_score"] >= comparison["before_score"]

    # Criterion 2: at least one improvement (or no failures to begin with)
    improvements = []
    regressions = []
    flaky_scenarios = []

    for b, a in zip(before_results, after_results, strict=True):
        sid = b["scenario_id"]
        if not b["passed"] and a["passed"]:
            improvements.append(sid)
        elif b["passed"] and not a["passed"]:
            regressions.append(sid)
        if a.get("flaky"):
            flaky_scenarios.append(sid)

    has_improvement = len(improvements) > 0 or comparison["before_score"] == 1.0

    # Criterion 3: no unexplained regressions
    no_unexplained_regressions = len(regressions) == 0

    # Security-critical: require 100% pass rate across all runs
    security_pass = True
    if security_critical:
        for a in after_results:
            if a["pass_rate"] < 1.0:
                security_pass = False
                break

    # Criterion 4: flakiness threshold (ADR-057 enforced)
    high_flakiness_scenarios = []
    for a in after_results:
        if a.get("flaky") and a["runs"] > 1:
            fail_rate = 1.0 - a["pass_rate"]
            if fail_rate > FLAKINESS_BLOCK_THRESHOLD:
                high_flakiness_scenarios.append(a["scenario_id"])

    no_high_flakiness = len(high_flakiness_scenarios) == 0

    passed = (no_regression and has_improvement
              and no_unexplained_regressions and no_high_flakiness)
    if security_critical:
        passed = passed and security_pass

    verdict = "PASS" if passed else "FAIL"

    gate = {
        "verdict": verdict,
        "passed": passed,
        "security_critical": security_critical,
        "criteria": {
            "no_regression": no_regression,
            "has_improvement": has_improvement,
            "no_unexplained_regressions": no_unexplained_regressions,
            "no_high_flakiness": no_high_flakiness,
        },
        "improvements": improvements,
        "regressions": regressions,
        "flaky_scenarios": flaky_scenarios,
        "high_flakiness_scenarios": high_flakiness_scenarios,
        "before_score": comparison["before_score"],
        "after_score": comparison["after_score"],
        "delta": comparison["delta"],
    }

    if security_critical:
        gate["criteria"]["security_all_runs_pass"] = security_pass

    return gate


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description="ADR-057 prompt change evaluator (before/after behavioral comparison)"
    )

    prompt_group = parser.add_argument_group("prompt source")
    prompt_group.add_argument(
        "--prompt", type=str,
        help="Path to prompt file (uses working copy as 'after', --base-ref as 'before')"
    )
    prompt_group.add_argument(
        "--base-ref", type=str, default="main",
        help="Git ref for 'before' version (default: main)"
    )
    prompt_group.add_argument("--before", type=str, help="Explicit 'before' prompt file")
    prompt_group.add_argument("--after", type=str, help="Explicit 'after' prompt file")

    parser.add_argument("--scenarios", type=str, required=True, help="Path to scenario JSON file")
    parser.add_argument(
        "--runs", type=int, default=DEFAULT_RUNS,
        help=f"Runs per scenario (default: {DEFAULT_RUNS}, security: {SECURITY_RUNS})"
    )
    parser.add_argument(
        "--security-critical", action="store_true",
        help=f"Security-critical tier: {SECURITY_RUNS} runs, 100%% pass required"
    )
    parser.add_argument(
        "--model", type=str, default="claude-sonnet-4-20250514",
        help="Model for evaluation"
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs, no API calls")
    parser.add_argument("--output", type=str, help="Write results to file")

    args = parser.parse_args()

    has_explicit = args.before and args.after
    has_git = args.prompt is not None
    if not has_explicit and not has_git:
        parser.error("Provide either --prompt or both --before and --after")
    if has_explicit and has_git:
        parser.error("Use --prompt OR --before/--after, not both")
    if (args.before and not args.after) or (args.after and not args.before):
        parser.error("--before and --after must be used together")

    if args.runs < 1:
        parser.error("--runs must be at least 1")

    if not args.security_critical and args.runs < DEFAULT_RUNS:
        parser.error(
            f"--runs must be >= {DEFAULT_RUNS} for non-security "
            f"prompts (flakiness protocol)"
        )

    if args.security_critical and args.runs < SECURITY_RUNS:
        args.runs = SECURITY_RUNS
        print(f"  Security-critical: overriding runs to {SECURITY_RUNS}", file=sys.stderr)

    return args


def _load_prompts(args: argparse.Namespace) -> tuple[str, str, str]:
    """Load before/after prompt text and return (before_text, after_text, source)."""
    has_explicit = args.before and args.after
    if has_explicit:
        before_text = load_prompt_from_file(args.before)
        after_text = load_prompt_from_file(args.after)
        source = f"explicit: {args.before} -> {args.after}"
    else:
        before_text = load_prompt_from_ref(args.prompt, args.base_ref)
        after_text = load_prompt_from_file(args.prompt)
        source = f"git: {args.base_ref}:{args.prompt} -> working copy"
    return before_text, after_text, source


def _run_and_report(
    api_key: str,
    before_text: str,
    after_text: str,
    scenarios: list[dict[str, Any]],
    args: argparse.Namespace,
    source: str,
) -> None:
    """Run comparison, apply gate, and output results."""
    print(f"\n{'='*60}", file=sys.stderr)
    msg = f"  RUNNING BEHAVIORAL EVAL ({len(scenarios)} scenarios x {args.runs} runs)"
    print(msg, file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    comparison = run_comparison(api_key, before_text, after_text, scenarios, args.model, args.runs)
    gate = acceptance_gate(comparison, security_critical=args.security_critical)

    output = {
        "eval_type": "prompt-change",
        "adr": "ADR-057",
        "model": args.model,
        "source": source,
        "runs_per_scenario": args.runs,
        "security_critical": args.security_critical,
        "comparison": {
            "before_score": comparison["before_score"],
            "after_score": comparison["after_score"],
            "delta": comparison["delta"],
            "scenario_count": comparison["scenario_count"],
            "api_calls": comparison["api_calls"],
            "est_tokens": comparison["est_tokens"],
        },
        "gate": gate,
        "detail": {"before": comparison["before_results"], "after": comparison["after_results"]},
    }

    json_output = json.dumps(output, indent=2)
    if args.output:
        Path(args.output).write_text(json_output, encoding="utf-8")
        print(f"\n  Results written to {args.output}", file=sys.stderr)
    else:
        print(json_output)

    _print_gate_summary(gate)
    sys.exit(0 if gate["passed"] else 1)


def _print_gate_summary(gate: dict[str, Any]) -> None:
    """Print acceptance gate summary to stderr."""
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  ACCEPTANCE GATE: {gate['verdict']}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Before: {gate['before_score']:.0%}  After: {gate['after_score']:.0%}  "
          f"Delta: {gate['delta']:+.0%}", file=sys.stderr)
    print("  Criteria:", file=sys.stderr)
    for criterion, passed in gate["criteria"].items():
        mark = "PASS" if passed else "FAIL"
        print(f"    {criterion}: {mark}", file=sys.stderr)

    if gate["improvements"]:
        print(f"  Improvements: {gate['improvements']}", file=sys.stderr)
    if gate["regressions"]:
        print(f"  Regressions: {gate['regressions']}", file=sys.stderr)
    if gate["flaky_scenarios"]:
        print(f"  Flaky: {gate['flaky_scenarios']}", file=sys.stderr)
    if gate.get("high_flakiness_scenarios"):
        print(f"  BLOCKED (>40% flaky): {gate['high_flakiness_scenarios']}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)


def main() -> None:
    args = _parse_args()

    try:
        scenarios = load_scenarios(args.scenarios)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"  Scenarios: {len(scenarios)} loaded from {args.scenarios}", file=sys.stderr)
    print(f"  Runs per scenario: {args.runs}", file=sys.stderr)
    print(f"  Security-critical: {args.security_critical}", file=sys.stderr)
    print(f"  Model: {args.model}", file=sys.stderr)

    try:
        before_text, after_text, source = _load_prompts(args)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"  Source: {source}", file=sys.stderr)
    print(f"  Before: {len(before_text)} chars, After: {len(after_text)} chars", file=sys.stderr)

    if before_text == after_text:
        print("  WARNING: before and after prompt text are identical", file=sys.stderr)

    if args.dry_run:
        print("\n  DRY RUN: inputs validated, no API calls made", file=sys.stderr)
        print(json.dumps({
            "dry_run": True, "scenarios": len(scenarios),
            "before_chars": len(before_text), "after_chars": len(after_text),
            "runs": args.runs, "security_critical": args.security_critical,
            "est_api_calls": len(scenarios) * 2 * args.runs,
        }, indent=2))
        sys.exit(0)

    try:
        api_key = load_api_key()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        _run_and_report(api_key, before_text, after_text, scenarios, args, source)
    except RuntimeError as e:
        print(f"ERROR: eval failed: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":  # pragma: no cover
    main()
