#!/usr/bin/env python3
"""M3 Kill Gate Eval: Evaluate skill knowledge integration quality.

Loads SKILL.md + references/ for each skill, runs prompts against the Anthropic API,
scores responses on accuracy/depth/specificity, and compares baseline vs enhanced.

Usage:
    python3 .agents/planning/eval-knowledge-integration.py
    python3 .agents/planning/eval-knowledge-integration.py --skill cva-analysis
    python3 .agents/planning/eval-knowledge-integration.py --prompts-file custom.json
    python3 .agents/planning/eval-knowledge-integration.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# API key loading
# ---------------------------------------------------------------------------

def _load_api_key() -> str:
    """Load ANTHROPIC_API_KEY from environment or .env file. Never prints the key."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()

    # Walk up from script location to find .env
    search = Path(__file__).resolve().parent
    for _ in range(10):
        env_path = search / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "ANTHROPIC_API_KEY":
                    return v.strip()
        search = search.parent

    print("ERROR: ANTHROPIC_API_KEY not found in environment or .env", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Skill context loading
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SKILL_PATHS: dict[str, Path] = {
    "cva-analysis": REPO_ROOT / ".claude" / "skills" / "cva-analysis",
    "decision-critic": REPO_ROOT / ".claude" / "skills" / "decision-critic",
    "golden-principles": REPO_ROOT / ".claude" / "skills" / "golden-principles",
    "threat-modeling": REPO_ROOT / ".claude" / "skills" / "threat-modeling",
    "analyze": REPO_ROOT / ".claude" / "skills" / "analyze",
}


def load_skill_context(skill_name: str) -> str:
    """Load SKILL.md and all references/ files for a skill."""
    skill_dir = SKILL_PATHS.get(skill_name)
    if not skill_dir or not skill_dir.exists():
        return ""

    parts: list[str] = []

    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        parts.append(f"# SKILL.md\n\n{skill_md.read_text()}")

    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        for ref_file in sorted(refs_dir.iterdir()):
            if ref_file.is_file():
                parts.append(f"# Reference: {ref_file.name}\n\n{ref_file.read_text()}")

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Built-in prompts (30 total, 6 per skill)
# ---------------------------------------------------------------------------

PROMPTS: dict[str, list[dict[str, str]]] = {
    "cva-analysis": [
        {"prompt": "I have a system that handles payments in USD, EUR, and GBP with different tax rules per currency. How would you build the CVA matrix for this?",
         "expected": "Matrix with currencies as columns, tax/payment concepts as rows. Rows map to Strategies, columns to Abstract Factory."},
        {"prompt": "When should I use a Bridge pattern vs an Abstract Factory based on CVA results?",
         "expected": "Bridge for two independent variation axes. Abstract Factory for co-dependent column items."},
        {"prompt": "My CVA matrix has 40% empty cells. What does that tell me?",
         "expected": "Forcing unrelated concerns into one dimension. Split into separate matrices. Empty cells are questions."},
        {"prompt": "How does Coplien's multi-paradigm design relate to CVA?",
         "expected": "Commonality analysis discovers natural abstractions. Variability analysis discovers differences. CVA-to-pattern pipeline."},
        {"prompt": "I have a row in my CVA matrix where all cells are identical. What should I do?",
         "expected": "Remove from matrix. Not a variability. Make it a constant in the base class."},
        {"prompt": "What are the three perspectives I should keep separate during CVA analysis?",
         "expected": "Conceptual (what you want), Specification (interfaces), Implementation (code). Mixing produces wrong abstractions."},
    ],
    "decision-critic": [
        {"prompt": "A team wants to remove a legacy caching layer that 'nobody uses anymore'. How should I challenge this?",
         "expected": "Chesterton's Fence: understand why built before removing. Check usage, historical context, edge cases."},
        {"prompt": "We're designing a new microservices architecture from scratch. What mental model warns against this?",
         "expected": "Gall's Law: complex systems that work evolved from simple ones. Start simple, evolve."},
        {"prompt": "Our A/B test shows 30% engagement increase. Should I trust this result?",
         "expected": "Survivorship bias: only measuring users who stayed? Check for selection effects, missing data."},
        {"prompt": "How should I evaluate a decision where the immediate fix looks good but long-term effects are unclear?",
         "expected": "Systems thinking: feedback loops, second-order effects, delays. Map the system, not the component."},
        {"prompt": "A developer says 'while fixing this bug, I should also refactor this messy code'. Appropriate?",
         "expected": "Boy Scout Rule: leave code better. But scope to area you're touching. Don't expand blast radius."},
        {"prompt": "Three competing proposals for auth system. How do I stress-test each?",
         "expected": "Decompose into assumptions. Verify independently. Look for hidden coupling, single points of failure, reversibility."},
    ],
    "golden-principles": [
        {"prompt": "A class has 15 public methods. What code quality issue and how to fix?",
         "expected": "Low cohesion. Too many responsibilities. Split by SRP. One reason to change."},
        {"prompt": "Explain programming by intention with a concrete example.",
         "expected": "Sergeant methods direct workflow via well-named private methods. Public method reads like intent, not implementation."},
        {"prompt": "Duplicate validation logic in 3 controllers. Should I extract it?",
         "expected": "DRY applies. Extract. But verify true duplication (same concept) not coincidental similarity."},
        {"prompt": "How do I know if my code violates Open-Closed Principle?",
         "expected": "Adding requirement requires modifying existing code instead of extending. Strategy makes code open-closed."},
        {"prompt": "What's the relationship between testability and encapsulation?",
         "expected": "Hard to test indicates poor encapsulation, tight coupling, Law of Demeter violation. Testability is a design signal."},
        {"prompt": "When is it acceptable to violate Separation of Concerns?",
         "expected": "Cross-cutting concerns (logging, auth, caching). Use aspects/middleware. Never for business logic."},
    ],
    "threat-modeling": [
        {"prompt": "How does defense in depth apply to a web API with a database backend?",
         "expected": "Multiple independent layers: WAF, input validation, auth, authz, parameterized queries, encryption, network segmentation."},
        {"prompt": "We're implementing zero trust for internal services. Core principles?",
         "expected": "Never trust, always verify. Verify explicitly. Least privilege. Assume breach. No implicit trust from network."},
        {"prompt": "Map STRIDE threats to OWASP Top 10.",
         "expected": "Spoofing->Broken Auth. Tampering->Injection. Repudiation->Insufficient Logging. Info Disclosure->Sensitive Data Exposure."},
        {"prompt": "Apply principle of least privilege to a CI/CD pipeline.",
         "expected": "Separate build/deploy creds. Time-limited tokens. No persistent admin. Each stage gets only needed permissions."},
        {"prompt": "Difference between defense in depth and zero trust?",
         "expected": "DiD: multiple layers assuming outer may fail. ZT: no layer trusted, every request verified. Complementary."},
        {"prompt": "Developer wants admin endpoint without auth 'because internal'. What's wrong?",
         "expected": "Violates zero trust. Internal networks get breached. Defense in depth requires auth at every layer."},
    ],
    "analyze": [
        {"prompt": "Investigating a performance regression. How to structure using OODA loop?",
         "expected": "Observe: metrics/logs/traces. Orient: compare baseline. Decide: hypothesis. Act: test with targeted measurement."},
        {"prompt": "Inherited legacy codebase with no tests. Where to start?",
         "expected": "Identify change/inflection points. Add characterization tests at boundaries. Sprout Method/Class. Don't rewrite, strangle."},
        {"prompt": "Service has getters returning internal state for caller decisions. What design problem?",
         "expected": "Tell Don't Ask violation. Feature envy. Move decision logic into the object that owns the data."},
        {"prompt": "How to decide whether to fix adjacent code while fixing a bug?",
         "expected": "Boy Scout Rule: improve code you touch but scope to area of change. Don't expand blast radius."},
        {"prompt": "Three pillars of observability and when to use each?",
         "expected": "Logs (events, debugging), Metrics (aggregates, alerting), Traces (request flow, latency). Use all three together."},
        {"prompt": "Found a code smell but unsure if it's a real problem. How to decide?",
         "expected": "Is it hard to test? Violates cohesion/coupling? Would a stranger understand? If yes, it's real."},
    ],
}

SKILLS = list(PROMPTS.keys())


# ---------------------------------------------------------------------------
# Anthropic API interaction
# ---------------------------------------------------------------------------

def _call_api(api_key: str, messages: list[dict], system: str = "", model: str = "claude-sonnet-4-20250514") -> str:
    """Call the Anthropic Messages API. Returns the assistant text response."""
    import urllib.request

    body: dict[str, Any] = {
        "model": model,
        "max_tokens": 1024,
        "messages": messages,
    }
    if system:
        body["system"] = system

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())

    # Extract text from content blocks
    text_parts = [block["text"] for block in result.get("content", []) if block.get("type") == "text"]
    return "\n".join(text_parts)


def run_prompt(api_key: str, prompt: str, system_context: str = "", model: str = "claude-sonnet-4-20250514") -> str:
    """Run a single prompt with optional system context."""
    messages = [{"role": "user", "content": prompt}]
    return _call_api(api_key, messages, system=system_context, model=model)


def score_response(api_key: str, prompt: str, response: str, expected: str, model: str = "claude-sonnet-4-20250514") -> dict[str, Any]:
    """Use the API to score a response on accuracy, depth, specificity (1-5)."""
    scoring_prompt = f"""Score the following response on three dimensions (1-5 each).

**Original prompt**: {prompt}

**Expected answer**: {expected}

**Actual response**: {response}

Score each dimension:
- **Accuracy** (1-5): Does the response contain the correct concepts from the expected answer?
- **Depth** (1-5): Does the response go beyond surface-level and show understanding?
- **Specificity** (1-5): Does the response use precise terminology and concrete examples?

Respond in JSON only, no other text:
{{"accuracy": <int>, "depth": <int>, "specificity": <int>, "reasoning": "<brief explanation>"}}"""

    raw = _call_api(api_key, [{"role": "user", "content": scoring_prompt}], model=model)

    # Parse JSON from response (handle markdown code blocks)
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])

    try:
        scores = json.loads(text)
    except json.JSONDecodeError:
        scores = {"accuracy": 0, "depth": 0, "specificity": 0, "reasoning": f"Failed to parse: {text[:200]}"}

    return scores


# ---------------------------------------------------------------------------
# Kill gate criteria
# ---------------------------------------------------------------------------

def apply_kill_gate(results: dict[str, Any]) -> dict[str, Any]:
    """Apply kill gate: enhanced must beat baseline by >= 0.5 avg across dimensions."""
    gate = {"passed": True, "failures": [], "summary": {}}

    for skill, data in results.items():
        baseline_avg = _avg_scores(data.get("baseline", []))
        enhanced_avg = _avg_scores(data.get("enhanced", []))
        delta = {dim: enhanced_avg[dim] - baseline_avg[dim] for dim in baseline_avg}
        overall_delta = sum(delta.values()) / len(delta) if delta else 0

        skill_result = {
            "baseline_avg": baseline_avg,
            "enhanced_avg": enhanced_avg,
            "delta": delta,
            "overall_delta": round(overall_delta, 2),
            "passed": overall_delta >= 0.5,
        }
        gate["summary"][skill] = skill_result

        if not skill_result["passed"]:
            gate["passed"] = False
            gate["failures"].append(f"{skill}: delta {overall_delta:.2f} < 0.5 threshold")

    return gate


def _avg_scores(score_list: list[dict]) -> dict[str, float]:
    """Average accuracy, depth, specificity across a list of score dicts."""
    if not score_list:
        return {"accuracy": 0.0, "depth": 0.0, "specificity": 0.0}

    dims = ["accuracy", "depth", "specificity"]
    return {
        dim: round(sum(s.get(dim, 0) for s in score_list) / len(score_list), 2)
        for dim in dims
    }


# ---------------------------------------------------------------------------
# Main eval runner
# ---------------------------------------------------------------------------

def run_eval(
    api_key: str,
    skills: list[str],
    prompts: dict[str, list[dict[str, str]]],
    model: str = "claude-sonnet-4-20250514",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the full eval: baseline (no context) vs enhanced (with skill context)."""
    results: dict[str, Any] = {}
    total = sum(len(prompts.get(s, [])) for s in skills)
    current = 0

    for skill in skills:
        skill_prompts = prompts.get(skill, [])
        if not skill_prompts:
            print(f"  SKIP {skill}: no prompts", file=sys.stderr)
            continue

        context = load_skill_context(skill)
        context_size = len(context)
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  Skill: {skill} ({len(skill_prompts)} prompts, context: {context_size} chars)", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        baseline_scores: list[dict] = []
        enhanced_scores: list[dict] = []

        for i, item in enumerate(skill_prompts):
            current += 1
            prompt_text = item["prompt"]
            expected = item["expected"]
            print(f"  [{current}/{total}] {prompt_text[:70]}...", file=sys.stderr)

            if dry_run:
                baseline_scores.append({"accuracy": 0, "depth": 0, "specificity": 0, "reasoning": "dry-run"})
                enhanced_scores.append({"accuracy": 0, "depth": 0, "specificity": 0, "reasoning": "dry-run"})
                continue

            # Baseline: no skill context
            baseline_resp = run_prompt(api_key, prompt_text, model=model)
            baseline_score = score_response(api_key, prompt_text, baseline_resp, expected, model=model)
            baseline_scores.append(baseline_score)
            print(f"    Baseline: A={baseline_score.get('accuracy',0)} D={baseline_score.get('depth',0)} S={baseline_score.get('specificity',0)}", file=sys.stderr)

            # Rate limit pause
            time.sleep(1)

            # Enhanced: with skill context
            system_ctx = f"You are a software engineering expert. Use the following skill knowledge to answer:\n\n{context}"
            enhanced_resp = run_prompt(api_key, prompt_text, system_context=system_ctx, model=model)
            enhanced_score = score_response(api_key, prompt_text, enhanced_resp, expected, model=model)
            enhanced_scores.append(enhanced_score)
            print(f"    Enhanced: A={enhanced_score.get('accuracy',0)} D={enhanced_score.get('depth',0)} S={enhanced_score.get('specificity',0)}", file=sys.stderr)

            time.sleep(1)

        results[skill] = {
            "baseline": baseline_scores,
            "enhanced": enhanced_scores,
            "context_chars": context_size,
        }

    return results


def load_custom_prompts(path: str) -> dict[str, list[dict[str, str]]]:
    """Load prompts from a JSON file.

    Expected format:
    {
        "skill-name": [
            {"prompt": "...", "expected": "..."},
            ...
        ]
    }
    """
    with open(path) as f:
        data = json.load(f)

    # Support both {"prompts": {...}} wrapper and direct dict
    if "prompts" in data and isinstance(data["prompts"], dict):
        return data["prompts"]
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval skill knowledge integration quality")
    parser.add_argument("--skill", type=str, help="Eval a single skill instead of all 5")
    parser.add_argument("--prompts-file", type=str, help="Load custom prompts from a JSON file")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-20250514", help="Model to use for eval")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without calling the API")
    parser.add_argument("--output", type=str, help="Write results to file instead of stdout")
    args = parser.parse_args()

    api_key = _load_api_key()
    print(f"API key loaded (length: {len(api_key)})", file=sys.stderr)

    # Determine which skills to eval
    if args.skill:
        if args.skill not in SKILL_PATHS:
            print(f"ERROR: Unknown skill '{args.skill}'. Available: {', '.join(SKILLS)}", file=sys.stderr)
            sys.exit(1)
        skills = [args.skill]
    else:
        skills = SKILLS

    # Load prompts
    if args.prompts_file:
        prompts = load_custom_prompts(args.prompts_file)
        print(f"Loaded custom prompts from {args.prompts_file}", file=sys.stderr)
    else:
        prompts = PROMPTS

    prompt_count = sum(len(prompts.get(s, [])) for s in skills)
    api_calls = prompt_count * 4 if not args.dry_run else 0  # 2 runs + 2 scores per prompt
    print(f"Skills: {skills}", file=sys.stderr)
    print(f"Prompts: {prompt_count}, API calls: {api_calls}", file=sys.stderr)

    if not args.dry_run:
        print(f"Starting eval (est. {api_calls * 2}s with rate limiting)...", file=sys.stderr)

    results = run_eval(api_key, skills, prompts, model=args.model, dry_run=args.dry_run)

    # Apply kill gate
    gate = apply_kill_gate(results)

    output = {
        "model": args.model,
        "skills_evaluated": skills,
        "total_prompts": prompt_count,
        "results": {},
        "kill_gate": gate,
    }

    # Add per-skill summaries
    for skill in skills:
        if skill in results:
            output["results"][skill] = {
                "context_chars": results[skill]["context_chars"],
                "baseline_avg": _avg_scores(results[skill]["baseline"]),
                "enhanced_avg": _avg_scores(results[skill]["enhanced"]),
                "baseline_detail": results[skill]["baseline"],
                "enhanced_detail": results[skill]["enhanced"],
            }

    json_output = json.dumps(output, indent=2)

    if args.output:
        Path(args.output).write_text(json_output)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(json_output)

    # Print summary table
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"  KILL GATE: {'PASS' if gate['passed'] else 'FAIL'}", file=sys.stderr)
    print(f"  Threshold: enhanced must beat baseline by >= 0.5 avg", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    print(f"  {'Skill':<20} {'Baseline':>10} {'Enhanced':>10} {'Delta':>10} {'Status':>8}", file=sys.stderr)
    print(f"  {'-'*58}", file=sys.stderr)
    for skill, summary in gate.get("summary", {}).items():
        b = sum(summary["baseline_avg"].values()) / 3
        e = sum(summary["enhanced_avg"].values()) / 3
        d = summary["overall_delta"]
        status = "PASS" if summary["passed"] else "FAIL"
        print(f"  {skill:<20} {b:>10.2f} {e:>10.2f} {d:>10.2f} {status:>8}", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)

    if gate.get("failures"):
        for f in gate["failures"]:
            print(f"  FAILURE: {f}", file=sys.stderr)

    sys.exit(0 if gate["passed"] else 1)


if __name__ == "__main__":
    main()
