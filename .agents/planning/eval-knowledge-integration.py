#!/usr/bin/env python3
"""M3 Kill Gate Eval: Generate prompts and expected answers for manual scoring.

Since we can't call the Anthropic API directly (no API key in env),
this script generates the eval harness that Claude Code subagents will execute.

Usage:
    python3 eval-knowledge-integration.py > quality-eval-prompts.json
"""

import json
from pathlib import Path

SKILLS = ["cva-analysis", "decision-critic", "golden-principles", "threat-modeling", "analyze"]

PROMPTS = {
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

if __name__ == "__main__":
    output = {"skills": SKILLS, "prompts": PROMPTS, "total_prompts": 30}
    print(json.dumps(output, indent=2))

    # Also write to file
    out_path = Path(__file__).parent / "quality-eval-prompts.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nWritten to {out_path}", file=__import__("sys").stderr)
