#!/usr/bin/env python3
"""LLM eval harness for orchestrator Step 3.5 context-retrieval decisions.

Sends curated task prompts to the orchestrator agent and checks the
Classification Summary output for correct INVOKE/SKIP decisions.

EXIT CODES:
  0  - All scenarios passed
  1  - One or more scenarios failed
  2  - Configuration or runtime error

Usage:
  python3 tests/eval_orchestrator_step35.py --dry-run
  python3 tests/eval_orchestrator_step35.py --agent claude
  python3 tests/eval_orchestrator_step35.py --agent copilot --format json

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCENARIOS_PATH = Path(__file__).parent / "eval_scenarios" / "step35_scenarios.json"

# Regex to find "Context Retrieval: INVOKED" or "Context Retrieval: SKIPPED"
# in the LLM output. Allows for markdown formatting and whitespace.
CR_DECISION_RE = re.compile(
    r"Context\s+Retrieval[:\s*]*\*{0,2}\s*(INVOKED|SKIPPED)",
    re.IGNORECASE,
)


@dataclass
class EvalScenario:
    """A single LLM eval scenario."""

    id: str
    prompt: str
    expected_decision: str
    rationale: str


@dataclass
class EvalResult:
    """Result of running one eval scenario."""

    scenario_id: str
    expected: str
    actual: str | None
    passed: bool
    raw_output: str = ""
    error: str = ""


@dataclass
class EvalReport:
    """Aggregate eval report."""

    results: list[EvalResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100

    @property
    def false_positives(self) -> int:
        """Invoked when should have skipped."""
        return sum(
            1 for r in self.results
            if r.expected == "SKIPPED" and r.actual == "INVOKED"
        )

    @property
    def false_negatives(self) -> int:
        """Skipped when should have invoked."""
        return sum(
            1 for r in self.results
            if r.expected == "INVOKED" and r.actual == "SKIPPED"
        )

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "accuracy_percent": round(self.accuracy, 1),
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "results": [
                {
                    "scenario_id": r.scenario_id,
                    "expected": r.expected,
                    "actual": r.actual,
                    "passed": r.passed,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def load_llm_scenarios() -> list[EvalScenario]:
    """Load LLM eval scenarios from the shared JSON file."""
    data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    return [
        EvalScenario(
            id=s["id"],
            prompt=s["prompt"],
            expected_decision=s["expected_decision"],
            rationale=s["rationale"],
        )
        for s in data["llm_scenarios"]
    ]


def parse_decision(output: str) -> str | None:
    """Extract INVOKED or SKIPPED from LLM output."""
    match = CR_DECISION_RE.search(output)
    if match:
        return match.group(1).upper()
    return None


def build_orchestrator_prompt(task_prompt: str) -> str:
    """Build the full prompt sent to the orchestrator agent.

    The prompt asks the orchestrator to classify the task and produce
    the Classification Summary including the Context Retrieval decision.
    """
    return (
        "You are an orchestrator agent. Classify the following task and produce "
        "a Classification Summary. Include all fields: Request, Primary Domain, "
        "Secondary Domains, Domain Count, Complexity, Risk Level, "
        "Classification Confidence, Context Retrieval (INVOKED or SKIPPED), "
        "and Context Retrieval Reason. Follow the Step 3.5 decision logic "
        "from orchestrator.agent.md exactly.\n\n"
        f"Task: {task_prompt}\n\n"
        "Respond with the Classification Summary only."
    )


def run_claude(prompt: str) -> tuple[str, str]:
    """Run a prompt through claude -p and return (stdout, stderr)."""
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout, result.stderr


def run_copilot(prompt: str) -> tuple[str, str]:
    """Run a prompt through gh copilot suggest --yolo."""
    result = subprocess.run(
        ["gh", "copilot", "suggest", "--yolo", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout, result.stderr


def run_scenario(
    scenario: EvalScenario,
    agent: str,
) -> EvalResult:
    """Run a single eval scenario against the specified agent."""
    prompt = build_orchestrator_prompt(scenario.prompt)

    try:
        if agent == "claude":
            stdout, stderr = run_claude(prompt)
        elif agent == "copilot":
            stdout, stderr = run_copilot(prompt)
        else:
            return EvalResult(
                scenario_id=scenario.id,
                expected=scenario.expected_decision,
                actual=None,
                passed=False,
                error=f"Unknown agent: {agent}",
            )
    except subprocess.TimeoutExpired:
        return EvalResult(
            scenario_id=scenario.id,
            expected=scenario.expected_decision,
            actual=None,
            passed=False,
            error="Timeout after 120s",
        )
    except FileNotFoundError as exc:
        return EvalResult(
            scenario_id=scenario.id,
            expected=scenario.expected_decision,
            actual=None,
            passed=False,
            error=f"Command not found: {exc}",
        )

    output = stdout + stderr
    actual = parse_decision(output)
    passed = actual == scenario.expected_decision

    return EvalResult(
        scenario_id=scenario.id,
        expected=scenario.expected_decision,
        actual=actual,
        passed=passed,
        raw_output=output[:500],
    )


def print_table(report: EvalReport) -> None:
    """Print results as a human-readable table."""
    print("=" * 70)
    print("Orchestrator Step 3.5 Eval Results")
    print("=" * 70)
    print(f"{'ID':<6} {'Expected':<10} {'Actual':<10} {'Status':<8} {'Error'}")
    print("-" * 70)

    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        actual = r.actual or "N/A"
        error = r.error[:40] if r.error else ""
        print(f"{r.scenario_id:<6} {r.expected:<10} {actual:<10} {status:<8} {error}")

    print("-" * 70)
    print(f"Accuracy: {report.accuracy:.1f}% ({report.passed}/{report.total})")
    print(f"False positives (invoked when should skip): {report.false_positives}")
    print(f"False negatives (skipped when should invoke): {report.false_negatives}")


def dry_run(scenarios: list[EvalScenario]) -> None:
    """Print scenarios without calling LLM."""
    print("=" * 70)
    print("DRY RUN: Orchestrator Step 3.5 Eval Scenarios")
    print("=" * 70)
    print(f"{'ID':<6} {'Expected':<10} {'Prompt'}")
    print("-" * 70)

    for s in scenarios:
        print(f"{s.id:<6} {s.expected_decision:<10} {s.prompt}")
        print(f"{'':6} {'':10} Rationale: {s.rationale}")
        print()

    print(f"Total scenarios: {len(scenarios)}")
    print("Run without --dry-run to execute against an LLM agent.")


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="LLM eval for orchestrator Step 3.5 context-retrieval decisions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print scenarios without calling LLM",
    )
    parser.add_argument(
        "--agent",
        choices=["claude", "copilot"],
        default="claude",
        help="Agent backend to use (default: claude)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Run a single scenario by ID (e.g. E01)",
    )
    args = parser.parse_args()

    scenarios = load_llm_scenarios()

    if args.scenario:
        scenarios = [s for s in scenarios if s.id == args.scenario]
        if not scenarios:
            print(f"[ERROR] Scenario '{args.scenario}' not found", file=sys.stderr)
            return 2

    if args.dry_run:
        dry_run(scenarios)
        return 0

    report = EvalReport()
    for scenario in scenarios:
        print(f"Running {scenario.id}: {scenario.prompt[:50]}...", file=sys.stderr)
        result = run_scenario(scenario, args.agent)
        report.results.append(result)

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_table(report)

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
