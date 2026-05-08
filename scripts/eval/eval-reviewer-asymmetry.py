#!/usr/bin/env python3
"""Reviewer-asymmetry behavioral evaluator.

Measures whether the new reviewer-asymmetry framing in templates/agents/
{critic,qa,implementer}.shared.md produces a statistically significant
behavioral delta vs the origin/main control versions.

Design:
    - Each fixture targets one agent (critic / qa / implementer) and embeds
      a planted-issue scenario plus a controlled-vocabulary verdict
      contract (`expected_verdict` + `verdict_options`).
    - For each fixture, run N trials per condition (control template from
      origin/main, treatment template from working copy).
    - Outcome per trial: pass = verdict matches `expected_verdict` AND
      reason contains `expected_reason_contains` (when set).
    - Aggregate to a 2x2 table: (control_pass, control_fail) vs
      (treatment_pass, treatment_fail). Apply Fisher's exact test +
      two-proportion z-test for the p-value. Report effect size.

Cost:
    Default: 6 fixtures * 5 trials * 2 conditions = 60 calls.
    With judge: same (we use direct verdict extraction; no separate judge).
    At ~3500 tokens / call -> ~210K input tokens, ~30K output. ~$1.50 USD.

Exit codes:
    0 - significance achieved (p < ALPHA AND treatment > control)
    1 - no significant delta (treatment did not beat control reliably)
    2 - config / fixture invalid / API not configured
    3 - external (API) failure
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _anthropic_api import call_api, load_api_key  # noqa: E402

DEFAULT_MODEL = "claude-sonnet-4-5"  # Released model id; 4.6 is a newer variant.
DEFAULT_TRIALS = 5
ALPHA = 0.05
BASE_REF = "main"
RATE_LIMIT_SLEEP_SEC = 1.0

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = {
    "critic": "templates/agents/critic.shared.md",
    "qa": "templates/agents/qa.shared.md",
    "implementer": "templates/agents/implementer.shared.md",
}


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def load_fixtures(fixture_dir: Path) -> list[dict[str, Any]]:
    fixtures = []
    for path in sorted(fixture_dir.glob("F*.json")):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if data.get("agent") not in TEMPLATES:
            raise RuntimeError(
                f"{path}: agent={data.get('agent')!r} not in {sorted(TEMPLATES)}"
            )
        for required in ("id", "input", "expected_verdict", "verdict_options"):
            if required not in data:
                raise RuntimeError(f"{path}: missing field {required!r}")
        fixtures.append(data)
    if not fixtures:
        raise RuntimeError(f"No fixtures matched F*.json in {fixture_dir}")
    return fixtures


# ---------------------------------------------------------------------------
# Template loading (control = origin/main, treatment = working copy)
# ---------------------------------------------------------------------------


def load_template(rel_path: str, ref: str | None) -> str:
    abs_path = REPO_ROOT / rel_path
    if ref is None:
        return abs_path.read_text(encoding="utf-8")
    result = subprocess.run(
        ["git", "show", f"{ref}:{rel_path}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git show {ref}:{rel_path} failed: {result.stderr.strip()}"
        )
    return result.stdout


# ---------------------------------------------------------------------------
# Trial: run one fixture against one template, return (passed, raw verdict)
# ---------------------------------------------------------------------------


def run_trial(
    api_key: str,
    template_text: str,
    fixture: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    options = [str(o).strip().upper() for o in fixture["verdict_options"]]
    options_str = ", ".join(options)
    min_findings = fixture.get("min_findings_count")
    findings_clause = ""
    json_template = '{"verdict": "<one label>", "reason": "<<=120 words>"}'
    if min_findings is not None:
        findings_clause = (
            "Also produce a `findings` array with one short string per "
            "distinct issue you identified.\n"
        )
        json_template = (
            '{"verdict": "<one label>", "findings": ["<issue 1>", '
            '"<issue 2>", ...], "reason": "<<=120 words>"}'
        )
    user_message = (
        f"Scenario: {fixture['input']}\n\n"
        f"Based on the agent definition above, classify your response.\n"
        f"Your verdict MUST be exactly one of: {options_str}.\n"
        f"{findings_clause}"
        "Respond with JSON only, no surrounding prose:\n"
        f"{json_template}"
    )
    raw = call_api(
        api_key,
        [{"role": "user", "content": user_message}],
        system=template_text,
        model=model,
        max_tokens=1024,
    )
    parsed = _parse_verdict(raw)
    expected = str(fixture["expected_verdict"]).strip().upper()
    actual = str(parsed.get("verdict", "")).strip().upper()
    verdict_match = actual == expected

    reason_match = True
    expected_substr = fixture.get("expected_reason_contains")
    if expected_substr:
        reason_match = (
            str(expected_substr).lower()
            in str(parsed.get("reason", "")).lower()
        )

    findings_match = True
    findings_count = None
    if min_findings is not None:
        findings = parsed.get("findings")
        if isinstance(findings, list):
            findings_count = len(findings)
            findings_match = findings_count >= int(min_findings)
        else:
            findings_match = False

    return {
        "passed": verdict_match and reason_match and findings_match,
        "verdict": actual,
        "expected": expected,
        "reason_excerpt": str(parsed.get("reason", ""))[:200],
        "verdict_match": verdict_match,
        "reason_match": reason_match,
        "findings_match": findings_match,
        "findings_count": findings_count,
        "raw": raw,
    }


def _parse_verdict(raw: str) -> dict[str, str]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if not obj_match:
        return {"verdict": "PARSE_ERROR", "reason": raw[:200]}
    try:
        return json.loads(obj_match.group())
    except json.JSONDecodeError:
        return {"verdict": "PARSE_ERROR", "reason": raw[:200]}


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------


def fishers_exact_one_sided(a: int, b: int, c: int, d: int) -> float:
    """One-sided p-value (treatment > control) via Fisher's exact test.

    Table:
        |          | pass | fail |
        | control  | a    | b    |
        | treatment| c    | d    |

    H0: P(pass | treatment) <= P(pass | control)
    H1: P(pass | treatment) >  P(pass | control)
    p = P(treatment >= c | margins fixed)
    """
    n = a + b + c + d
    row1 = a + b
    row2 = c + d
    col1 = a + c
    col2 = b + d
    if min(row1, row2, col1, col2) == 0:
        return 1.0

    def _binom(n: int, k: int) -> int:
        return math.comb(n, k)

    def _prob(c_val: int) -> float:
        a_val = col1 - c_val
        b_val = row1 - a_val
        d_val = row2 - c_val
        if any(v < 0 for v in (a_val, b_val, c_val, d_val)):
            return 0.0
        return (_binom(row1, a_val) * _binom(row2, c_val)) / _binom(n, col1)

    c_max = min(row2, col1)
    p = 0.0
    for c_val in range(c, c_max + 1):
        p += _prob(c_val)
    return min(1.0, p)


def two_proportion_z(a: int, b: int, c: int, d: int) -> tuple[float, float]:
    """Two-proportion z-test (one-sided, treatment > control).

    Returns (z, p_one_sided).
    """
    n1 = a + b
    n2 = c + d
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0
    p1 = a / n1
    p2 = c / n2
    pooled = (a + c) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2)) if pooled not in (0, 1) else 0.0
    if se == 0:
        return 0.0, 0.5
    z = (p2 - p1) / se
    p_one_sided = 1 - _phi(z)
    return z, p_one_sided


def _phi(z: float) -> float:
    """Standard-normal CDF via erf."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def cohen_h(p1: float, p2: float) -> float:
    """Effect size for two proportions: 2*(arcsin(sqrt(p1)) - arcsin(sqrt(p2)))."""
    def phi_arcsin(p: float) -> float:
        p = max(0.0, min(1.0, p))
        return 2 * math.asin(math.sqrt(p))
    return phi_arcsin(p2) - phi_arcsin(p1)


def mann_whitney_u(x: list[float], y: list[float]) -> tuple[float, float, float]:
    """Mann-Whitney U one-sided test (y > x). Returns (U_y, z, p_one_sided).

    Uses normal approximation with tie correction. Suitable when min(n1, n2) >= 8.
    """
    n1, n2 = len(x), len(y)
    if min(n1, n2) == 0:
        return 0.0, 0.0, 1.0
    combined = sorted(
        [(v, "x") for v in x] + [(v, "y") for v in y], key=lambda t: t[0],
    )
    ranks: list[float] = []
    i = 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for _ in range(j - i + 1):
            ranks.append(avg_rank)
        i = j + 1
    rank_y = sum(r for r, (_, lbl) in zip(ranks, combined) if lbl == "y")
    u_y = rank_y - n2 * (n2 + 1) / 2
    n = n1 + n2
    from collections import Counter as _C
    counts = _C(combined[i][0] for i in range(n))
    tie_sum = sum(t * (t * t - 1) for t in counts.values() if t > 1)
    mean_u = n1 * n2 / 2
    var_u = (n1 * n2 / 12) * ((n + 1) - tie_sum / (n * (n - 1))) if n > 1 else 0.0
    if var_u <= 0:
        return u_y, 0.0, 0.5
    z = (u_y - mean_u - 0.5) / math.sqrt(var_u)
    p = 1 - 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return u_y, z, p


# ---------------------------------------------------------------------------
# Main eval loop
# ---------------------------------------------------------------------------


def run_eval(
    api_key: str,
    fixtures: list[dict[str, Any]],
    trials: int,
    model: str,
    base_ref: str,
) -> dict[str, Any]:
    # Cache templates: one per (agent, condition).
    template_cache: dict[tuple[str, str], str] = {}

    def get_template(agent: str, condition: str) -> str:
        key = (agent, condition)
        if key not in template_cache:
            ref = base_ref if condition == "control" else None
            template_cache[key] = load_template(TEMPLATES[agent], ref)
        return template_cache[key]

    per_fixture: list[dict[str, Any]] = []
    api_calls = 0
    for fixture in fixtures:
        agent = fixture["agent"]
        ctrl_template = get_template(agent, "control")
        trt_template = get_template(agent, "treatment")
        ctrl_runs: list[dict[str, Any]] = []
        trt_runs: list[dict[str, Any]] = []
        for trial_idx in range(trials):
            print(
                f"  [{fixture['id']} {agent}] trial {trial_idx + 1}/{trials}",
                file=sys.stderr,
            )
            ctrl = run_trial(api_key, ctrl_template, fixture, model)
            api_calls += 1
            time.sleep(RATE_LIMIT_SLEEP_SEC)
            trt = run_trial(api_key, trt_template, fixture, model)
            api_calls += 1
            time.sleep(RATE_LIMIT_SLEEP_SEC)
            ctrl_runs.append(ctrl)
            trt_runs.append(trt)
            print(
                f"    control={'PASS' if ctrl['passed'] else 'FAIL'} "
                f"treatment={'PASS' if trt['passed'] else 'FAIL'}",
                file=sys.stderr,
            )
        per_fixture.append({
            "id": fixture["id"],
            "agent": agent,
            "control_passes": sum(1 for r in ctrl_runs if r["passed"]),
            "control_fails": sum(1 for r in ctrl_runs if not r["passed"]),
            "treatment_passes": sum(1 for r in trt_runs if r["passed"]),
            "treatment_fails": sum(1 for r in trt_runs if not r["passed"]),
            "control_runs": ctrl_runs,
            "treatment_runs": trt_runs,
        })

    # Aggregate at agent and overall levels.
    agents = sorted({f["agent"] for f in fixtures})
    by_agent: dict[str, dict[str, int]] = {
        a: {"a": 0, "b": 0, "c": 0, "d": 0} for a in agents
    }
    overall = {"a": 0, "b": 0, "c": 0, "d": 0}
    for pf in per_fixture:
        ag = pf["agent"]
        by_agent[ag]["a"] += pf["control_passes"]
        by_agent[ag]["b"] += pf["control_fails"]
        by_agent[ag]["c"] += pf["treatment_passes"]
        by_agent[ag]["d"] += pf["treatment_fails"]
        overall["a"] += pf["control_passes"]
        overall["b"] += pf["control_fails"]
        overall["c"] += pf["treatment_passes"]
        overall["d"] += pf["treatment_fails"]

    def _stats(table: dict[str, int]) -> dict[str, Any]:
        a, b, c, d = table["a"], table["b"], table["c"], table["d"]
        n_ctrl = a + b
        n_trt = c + d
        p_ctrl = a / n_ctrl if n_ctrl else 0.0
        p_trt = c / n_trt if n_trt else 0.0
        fisher_p = fishers_exact_one_sided(a, b, c, d)
        z, z_p = two_proportion_z(a, b, c, d)
        return {
            "n_control": n_ctrl,
            "n_treatment": n_trt,
            "control_pass_rate": round(p_ctrl, 4),
            "treatment_pass_rate": round(p_trt, 4),
            "delta": round(p_trt - p_ctrl, 4),
            "fisher_exact_p_one_sided": round(fisher_p, 6),
            "z_score": round(z, 4),
            "z_test_p_one_sided": round(z_p, 6),
            "cohen_h": round(cohen_h(p_ctrl, p_trt), 4),
            "significant_at_alpha_0.05":
                fisher_p < ALPHA and p_trt > p_ctrl,
        }

    # Findings-count Mann-Whitney U (per-agent, when fixtures use the
    # min_findings_count rubric). Pools all (fixture x trial) findings
    # counts within an agent.
    findings_by_agent: dict[str, dict[str, list[float]]] = {
        a: {"control": [], "treatment": []} for a in agents
    }
    for pf in per_fixture:
        ag = pf["agent"]
        for run in pf["control_runs"]:
            fc = run.get("findings_count")
            if isinstance(fc, int):
                findings_by_agent[ag]["control"].append(fc)
        for run in pf["treatment_runs"]:
            fc = run.get("findings_count")
            if isinstance(fc, int):
                findings_by_agent[ag]["treatment"].append(fc)

    findings_stats: dict[str, dict[str, Any]] = {}
    for ag, data in findings_by_agent.items():
        if not data["control"] and not data["treatment"]:
            continue
        u, z, p = mann_whitney_u(data["control"], data["treatment"])
        findings_stats[ag] = {
            "n_control": len(data["control"]),
            "n_treatment": len(data["treatment"]),
            "control_mean": round(
                sum(data["control"]) / len(data["control"]), 3
            ) if data["control"] else None,
            "treatment_mean": round(
                sum(data["treatment"]) / len(data["treatment"]), 3
            ) if data["treatment"] else None,
            "u_y_treatment": round(u, 1),
            "z_score": round(z, 3),
            "p_one_sided": round(p, 6),
            "significant_at_alpha_0.05":
                p < ALPHA and (
                    sum(data["treatment"]) / max(1, len(data["treatment"]))
                    > sum(data["control"]) / max(1, len(data["control"]))
                ),
        }

    return {
        "model": model,
        "base_ref": base_ref,
        "trials_per_fixture": trials,
        "alpha": ALPHA,
        "api_calls": api_calls,
        "fixtures": per_fixture,
        "by_agent": {a: _stats(by_agent[a]) for a in agents},
        "overall": _stats(overall),
        "findings_count_stats": findings_stats,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=str,
        default="evals/reviewer-asymmetry-spike/fixtures",
        help="Directory of F*.json fixtures (default: evals/reviewer-asymmetry-spike/fixtures)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=DEFAULT_TRIALS,
        help=f"Trials per fixture per condition (default: {DEFAULT_TRIALS})",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--base-ref",
        type=str,
        default=BASE_REF,
        help=f"Git ref for control templates (default: {BASE_REF})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write JSON results to this path (default: print to stdout)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and templates only; no API calls",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture_dir = (REPO_ROOT / args.fixtures).resolve()
    if not fixture_dir.is_dir():
        print(f"ERROR: fixture dir not found: {fixture_dir}", file=sys.stderr)
        return 2
    try:
        fixtures = load_fixtures(fixture_dir)
    except RuntimeError as exc:
        print(f"ERROR loading fixtures: {exc}", file=sys.stderr)
        return 2

    print(
        f"  fixtures={len(fixtures)} trials={args.trials} model={args.model} "
        f"base_ref={args.base_ref} alpha={ALPHA}",
        file=sys.stderr,
    )
    print(
        f"  estimated API calls: {len(fixtures) * args.trials * 2}",
        file=sys.stderr,
    )

    # Validate templates load on both conditions.
    seen_agents = sorted({f["agent"] for f in fixtures})
    for agent in seen_agents:
        try:
            ctrl_text = load_template(TEMPLATES[agent], args.base_ref)
            trt_text = load_template(TEMPLATES[agent], None)
        except RuntimeError as exc:
            print(f"ERROR loading template for {agent}: {exc}", file=sys.stderr)
            return 2
        if ctrl_text == trt_text:
            print(
                f"  WARNING: control and treatment templates for {agent} "
                "are identical; eval will show no delta",
                file=sys.stderr,
            )
        print(
            f"    {agent}: control={len(ctrl_text)}ch treatment={len(trt_text)}ch",
            file=sys.stderr,
        )

    if args.dry_run:
        print(json.dumps({
            "dry_run": True,
            "fixtures": len(fixtures),
            "trials": args.trials,
            "estimated_api_calls": len(fixtures) * args.trials * 2,
            "agents": seen_agents,
        }, indent=2))
        return 0

    try:
        api_key = load_api_key()
    except RuntimeError as exc:
        print(f"ERROR loading API key: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_eval(api_key, fixtures, args.trials, args.model, args.base_ref)
    except RuntimeError as exc:
        print(f"ERROR during eval: {exc}", file=sys.stderr)
        return 3

    output = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"  results written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Verdict
    overall = result["overall"]
    print("", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("REVIEWER-ASYMMETRY EVAL RESULTS", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(
        f"  Overall: control={overall['control_pass_rate']:.0%}  "
        f"treatment={overall['treatment_pass_rate']:.0%}  "
        f"delta={overall['delta']:+.0%}",
        file=sys.stderr,
    )
    print(
        f"  Fisher's exact (one-sided): p={overall['fisher_exact_p_one_sided']:.4f}",
        file=sys.stderr,
    )
    print(
        f"  Two-proportion z-test:      z={overall['z_score']:.3f}  "
        f"p={overall['z_test_p_one_sided']:.4f}",
        file=sys.stderr,
    )
    print(
        f"  Cohen's h:                  {overall['cohen_h']:.3f}",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    for agent, stats in result["by_agent"].items():
        sig = "[SIGNIFICANT]" if stats["significant_at_alpha_0.05"] else ""
        print(
            f"  {agent}: control={stats['control_pass_rate']:.0%}  "
            f"treatment={stats['treatment_pass_rate']:.0%}  "
            f"delta={stats['delta']:+.0%}  "
            f"fisher_p={stats['fisher_exact_p_one_sided']:.4f} {sig}",
            file=sys.stderr,
        )
    print("", file=sys.stderr)
    if result.get("findings_count_stats"):
        print("  Findings-count distribution (Mann-Whitney U, one-sided):", file=sys.stderr)
        for agent, fs in result["findings_count_stats"].items():
            sig = "[SIGNIFICANT]" if fs["significant_at_alpha_0.05"] else ""
            print(
                f"    {agent}: ctrl_mean={fs['control_mean']:.2f}  "
                f"trt_mean={fs['treatment_mean']:.2f}  "
                f"z={fs['z_score']:.2f}  p={fs['p_one_sided']:.6f} {sig}",
                file=sys.stderr,
            )
        print("", file=sys.stderr)

    sig_overall = overall["significant_at_alpha_0.05"]
    # Per-agent significance: pass if either the binary verdict-rate test
    # OR the continuous findings-count test is significant.
    sig_per_agent_count = 0
    for agent in result["by_agent"]:
        binary_sig = result["by_agent"][agent]["significant_at_alpha_0.05"]
        count_sig = result.get("findings_count_stats", {}).get(agent, {}).get(
            "significant_at_alpha_0.05", False
        )
        if binary_sig or count_sig:
            sig_per_agent_count += 1
    print(
        f"  Significant at alpha=0.05: overall={'YES' if sig_overall else 'NO'}  "
        f"per-agent={sig_per_agent_count}/{len(result['by_agent'])}",
        file=sys.stderr,
    )
    return 0 if sig_overall and sig_per_agent_count == len(result["by_agent"]) else 1


if __name__ == "__main__":
    sys.exit(main())
