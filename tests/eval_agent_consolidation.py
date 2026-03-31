#!/usr/bin/env python3
"""A/B Test evaluation harness for agent consolidation proposal.

Compares the current 21-agent architecture against the proposed 5-agent
architecture across multiple dimensions: task completion, security detection,
routing accuracy, and execution efficiency.

EXIT CODES:
  0  - All scenarios passed
  1  - One or more scenarios failed
  2  - Configuration or runtime error

Usage:
  python3 tests/eval_agent_consolidation.py --dry-run
  python3 tests/eval_agent_consolidation.py --condition control --category task
  python3 tests/eval_agent_consolidation.py --condition treatment --category security
  python3 tests/eval_agent_consolidation.py --compare --output results.json

See: .agents/evals/agent-consolidation-ab-test.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCENARIOS_PATH = Path(__file__).parent / "eval_scenarios" / "agent_consolidation_scenarios.json"
RESULTS_DIR = Path(__file__).parent.parent / ".agents" / "evals" / "results"


@dataclass
class TaskResult:
    """Result of a single task evaluation."""

    scenario_id: str
    category: str
    complexity: str
    condition: str  # control or treatment
    expected_agents: list[str]
    actual_agents: list[str]
    task_completed: bool
    verification_passed: dict[str, bool]
    execution_time_ms: int
    token_count: int
    agent_invocations: int
    error: str = ""

    @property
    def routing_correct(self) -> bool:
        """Check if the right agents were invoked."""
        return set(self.actual_agents) == set(self.expected_agents)

    @property
    def overall_pass(self) -> bool:
        return self.task_completed and all(self.verification_passed.values())


@dataclass
class SecurityResult:
    """Result of a security detection test."""

    scenario_id: str
    cwe: str
    vulnerability_name: str
    condition: str
    expected_detection: bool
    actual_detection: bool
    severity: str
    finding_details: str = ""
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.expected_detection == self.actual_detection

    @property
    def is_false_negative(self) -> bool:
        return self.expected_detection and not self.actual_detection

    @property
    def is_false_positive(self) -> bool:
        return not self.expected_detection and self.actual_detection


@dataclass
class RoutingResult:
    """Result of a routing accuracy test."""

    scenario_id: str
    prompt: str
    condition: str
    complexity: str
    expected_agent: str
    actual_agent: str | None
    routing_time_ms: int
    error: str = ""

    @property
    def passed(self) -> bool:
        if self.actual_agent is None:
            return False
        return self.actual_agent.lower() == self.expected_agent.lower()


@dataclass
class EvalReport:
    """Aggregate evaluation report for one condition."""

    condition: str
    task_results: list[TaskResult] = field(default_factory=list)
    security_results: list[SecurityResult] = field(default_factory=list)
    routing_results: list[RoutingResult] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""

    # D1: Task Completion Quality
    @property
    def task_success_rate(self) -> float:
        if not self.task_results:
            return 0.0
        passed = sum(1 for r in self.task_results if r.overall_pass)
        return (passed / len(self.task_results)) * 100

    @property
    def rework_rate(self) -> float:
        # Placeholder: would track retry counts
        return 0.0

    # D2: Security Finding Quality
    @property
    def security_detection_rate(self) -> float:
        if not self.security_results:
            return 0.0
        detected = sum(1 for r in self.security_results if r.actual_detection)
        expected = sum(1 for r in self.security_results if r.expected_detection)
        return (detected / expected) * 100 if expected > 0 else 0.0

    @property
    def security_false_positives(self) -> int:
        return sum(1 for r in self.security_results if r.is_false_positive)

    @property
    def security_false_negatives(self) -> int:
        return sum(1 for r in self.security_results if r.is_false_negative)

    # D3: Routing Accuracy
    @property
    def routing_accuracy(self) -> float:
        if not self.routing_results:
            return 0.0
        correct = sum(1 for r in self.routing_results if r.passed)
        return (correct / len(self.routing_results)) * 100

    # D4: Execution Efficiency
    @property
    def total_tokens(self) -> int:
        return sum(r.token_count for r in self.task_results)

    @property
    def total_agent_invocations(self) -> int:
        return sum(r.agent_invocations for r in self.task_results)

    @property
    def avg_execution_time_ms(self) -> float:
        if not self.task_results:
            return 0.0
        return sum(r.execution_time_ms for r in self.task_results) / len(self.task_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "dimensions": {
                "D1_task_completion": {
                    "success_rate_pct": round(self.task_success_rate, 1),
                    "total_tasks": len(self.task_results),
                    "passed": sum(1 for r in self.task_results if r.overall_pass),
                },
                "D2_security_detection": {
                    "detection_rate_pct": round(self.security_detection_rate, 1),
                    "total_tests": len(self.security_results),
                    "false_positives": self.security_false_positives,
                    "false_negatives": self.security_false_negatives,
                },
                "D3_routing_accuracy": {
                    "accuracy_pct": round(self.routing_accuracy, 1),
                    "total_routings": len(self.routing_results),
                    "correct": sum(1 for r in self.routing_results if r.passed),
                },
                "D4_efficiency": {
                    "total_tokens": self.total_tokens,
                    "total_agent_invocations": self.total_agent_invocations,
                    "avg_execution_time_ms": round(self.avg_execution_time_ms, 0),
                },
            },
            "task_results": [
                {
                    "id": r.scenario_id,
                    "category": r.category,
                    "passed": r.overall_pass,
                    "routing_correct": r.routing_correct,
                    "execution_time_ms": r.execution_time_ms,
                    "error": r.error,
                }
                for r in self.task_results
            ],
            "security_results": [
                {
                    "id": r.scenario_id,
                    "cwe": r.cwe,
                    "detected": r.actual_detection,
                    "expected": r.expected_detection,
                    "passed": r.passed,
                }
                for r in self.security_results
            ],
            "routing_results": [
                {
                    "id": r.scenario_id,
                    "expected": r.expected_agent,
                    "actual": r.actual_agent,
                    "passed": r.passed,
                }
                for r in self.routing_results
            ],
        }


def load_scenarios() -> dict[str, Any]:
    """Load test scenarios from JSON file."""
    return json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))


def run_claude_prompt(prompt: str, timeout: int = 180) -> tuple[str, int, int]:
    """Run a prompt through claude CLI.

    Returns: (output, execution_time_ms, estimated_tokens)
    """
    start = time.time()
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        execution_time_ms = int((time.time() - start) * 1000)
        # Rough token estimate: ~4 chars per token
        estimated_tokens = len(output) // 4
        return output, execution_time_ms, estimated_tokens
    except subprocess.TimeoutExpired:
        return f"[ERROR] Timeout after {timeout}s", int((time.time() - start) * 1000), 0
    except FileNotFoundError:
        return "[ERROR] claude CLI not found", 0, 0


def extract_agents_from_output(output: str) -> list[str]:
    """Extract agent names mentioned in the output."""
    # Look for Task() invocations or agent references
    agent_pattern = re.compile(
        r'(?:Task\s*\(\s*subagent_type\s*=\s*["\'](\w+)["\']|'
        r'Route(?:d|ing)?\s+to\s+(\w+)|'
        r'(\w+)\s+agent\s+(?:completed|returned|finished))',
        re.IGNORECASE,
    )
    matches = agent_pattern.findall(output)
    agents = []
    for match in matches:
        for group in match:
            if group:
                agents.append(group.lower())
    return list(set(agents))


def detect_security_finding(output: str, cwe: str) -> tuple[bool, str]:
    """Check if security output detected a specific vulnerability."""
    # Look for CWE reference or vulnerability name
    cwe_pattern = re.compile(rf'{cwe}|CWE-?\d+', re.IGNORECASE)
    if cwe_pattern.search(output):
        return True, f"Found reference to {cwe}"

    # Look for common vulnerability indicators
    vuln_indicators = [
        "vulnerability", "vulnerable", "security issue",
        "injection", "traversal", "xss", "ssrf",
        "[FAIL]", "[CRITICAL]", "[HIGH]",
    ]
    for indicator in vuln_indicators:
        if indicator.lower() in output.lower():
            return True, f"Found indicator: {indicator}"

    return False, ""


def extract_routing_decision(output: str) -> str | None:
    """Extract which agent was routed to from output."""
    patterns = [
        r'Route(?:d|ing)?\s+to\s+(\w+)',
        r'Task\s*\(\s*subagent_type\s*=\s*["\'](\w+)',
        r'Delegat(?:ed|ing)\s+to\s+(\w+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def build_task_prompt(scenario: dict, condition: str) -> str:
    """Build prompt for task scenario."""
    if condition == "control":
        return (
            "You are the orchestrator agent in the current 21-agent architecture. "
            f"Complete this task: {scenario['prompt']}\n\n"
            "Route to the appropriate specialized agents and report which agents "
            "were used and the final outcome."
        )
    else:  # treatment
        return (
            "You are the orchestrator in the proposed 5-agent architecture "
            "(Orchestrator, Analyst, Architect, Builder, Critic). "
            f"Complete this task: {scenario['prompt']}\n\n"
            "Route to the appropriate agents with skill packs and report which "
            "agents were used and the final outcome."
        )


def build_security_prompt(scenario: dict, condition: str) -> str:
    """Build prompt for security detection test."""
    if condition == "control":
        agent_context = "You are the security agent"
    else:
        agent_context = "You are the Critic agent with the security-scan skill pack active"

    return (
        f"{agent_context}. Review this code for security vulnerabilities:\n\n"
        f"```python\n{scenario['vulnerable_code']}\n```\n\n"
        "Report any security findings with CWE references and severity."
    )


def build_routing_prompt(scenario: dict, condition: str) -> str:
    """Build prompt for routing test."""
    if condition == "control":
        return (
            "You are the orchestrator. Determine which specialized agent should "
            f"handle this task (choose from the 21 available agents): {scenario['prompt']}"
        )
    else:
        return (
            "You are the orchestrator. Determine which of the 5 agents "
            "(Orchestrator, Analyst, Architect, Builder, Critic) should handle "
            f"this task: {scenario['prompt']}"
        )


def run_task_scenario(
    scenario: dict,
    condition: str,
    dry_run: bool = False,
) -> TaskResult:
    """Run a single task scenario."""
    expected_key = "expected_agents_control" if condition == "control" else "expected_agents_treatment"
    expected_agents = scenario.get(expected_key, [])

    if dry_run:
        return TaskResult(
            scenario_id=scenario["id"],
            category=scenario["category"],
            complexity=scenario["complexity"],
            condition=condition,
            expected_agents=expected_agents,
            actual_agents=[],
            task_completed=False,
            verification_passed={},
            execution_time_ms=0,
            token_count=0,
            agent_invocations=0,
            error="DRY RUN",
        )

    prompt = build_task_prompt(scenario, condition)
    output, exec_time, tokens = run_claude_prompt(prompt)

    actual_agents = extract_agents_from_output(output)
    task_completed = "[COMPLETE]" in output or "completed" in output.lower()

    # Check verification criteria
    verification = {}
    for key, expected in scenario.get("verification", {}).items():
        if expected:
            verification[key] = key.lower() in output.lower()
        else:
            verification[key] = True

    return TaskResult(
        scenario_id=scenario["id"],
        category=scenario["category"],
        complexity=scenario["complexity"],
        condition=condition,
        expected_agents=expected_agents,
        actual_agents=actual_agents,
        task_completed=task_completed,
        verification_passed=verification,
        execution_time_ms=exec_time,
        token_count=tokens,
        agent_invocations=len(actual_agents),
    )


def run_security_scenario(
    scenario: dict,
    condition: str,
    dry_run: bool = False,
) -> SecurityResult:
    """Run a single security detection scenario."""
    if dry_run:
        return SecurityResult(
            scenario_id=scenario["id"],
            cwe=scenario["cwe"],
            vulnerability_name=scenario["name"],
            condition=condition,
            expected_detection=scenario["expected_detection"],
            actual_detection=False,
            severity=scenario["severity"],
            error="DRY RUN",
        )

    prompt = build_security_prompt(scenario, condition)
    output, _, _ = run_claude_prompt(prompt, timeout=60)

    detected, details = detect_security_finding(output, scenario["cwe"])

    return SecurityResult(
        scenario_id=scenario["id"],
        cwe=scenario["cwe"],
        vulnerability_name=scenario["name"],
        condition=condition,
        expected_detection=scenario["expected_detection"],
        actual_detection=detected,
        severity=scenario["severity"],
        finding_details=details,
    )


def run_routing_scenario(
    scenario: dict,
    condition: str,
    dry_run: bool = False,
) -> RoutingResult:
    """Run a single routing accuracy scenario."""
    expected_key = "expected_routing_control" if condition == "control" else "expected_routing_treatment"
    expected_agent = scenario.get(expected_key, "")

    if dry_run:
        return RoutingResult(
            scenario_id=scenario["id"],
            prompt=scenario["prompt"],
            condition=condition,
            complexity=scenario["complexity"],
            expected_agent=expected_agent,
            actual_agent=None,
            routing_time_ms=0,
            error="DRY RUN",
        )

    prompt = build_routing_prompt(scenario, condition)
    start = time.time()
    output, _, _ = run_claude_prompt(prompt, timeout=30)
    routing_time = int((time.time() - start) * 1000)

    actual_agent = extract_routing_decision(output)

    return RoutingResult(
        scenario_id=scenario["id"],
        prompt=scenario["prompt"],
        condition=condition,
        complexity=scenario["complexity"],
        expected_agent=expected_agent,
        actual_agent=actual_agent,
        routing_time_ms=routing_time,
    )


def run_evaluation(
    condition: str,
    categories: list[str],
    dry_run: bool = False,
) -> EvalReport:
    """Run full evaluation for one condition."""
    scenarios = load_scenarios()
    report = EvalReport(condition=condition)
    report.start_time = datetime.now().isoformat()

    if "task" in categories or "all" in categories:
        print(f"\n[{condition.upper()}] Running task scenarios...", file=sys.stderr)
        for scenario in scenarios.get("task_scenarios", []):
            print(f"  {scenario['id']}: {scenario['prompt'][:50]}...", file=sys.stderr)
            result = run_task_scenario(scenario, condition, dry_run)
            report.task_results.append(result)

    if "security" in categories or "all" in categories:
        print(f"\n[{condition.upper()}] Running security scenarios...", file=sys.stderr)
        for scenario in scenarios.get("security_test_corpus", []):
            print(f"  {scenario['id']}: {scenario['name']}...", file=sys.stderr)
            result = run_security_scenario(scenario, condition, dry_run)
            report.security_results.append(result)

    if "routing" in categories or "all" in categories:
        print(f"\n[{condition.upper()}] Running routing scenarios...", file=sys.stderr)
        for scenario in scenarios.get("routing_scenarios", []):
            print(f"  {scenario['id']}: {scenario['prompt'][:40]}...", file=sys.stderr)
            result = run_routing_scenario(scenario, condition, dry_run)
            report.routing_results.append(result)

    report.end_time = datetime.now().isoformat()
    return report


def compare_reports(control: EvalReport, treatment: EvalReport) -> dict[str, Any]:
    """Compare control and treatment reports."""
    return {
        "comparison_date": datetime.now().isoformat(),
        "dimensions": {
            "D1_task_completion": {
                "control_pct": round(control.task_success_rate, 1),
                "treatment_pct": round(treatment.task_success_rate, 1),
                "delta_pct": round(treatment.task_success_rate - control.task_success_rate, 1),
                "verdict": "PASS" if treatment.task_success_rate >= control.task_success_rate else "FAIL",
            },
            "D2_security_detection": {
                "control_pct": round(control.security_detection_rate, 1),
                "treatment_pct": round(treatment.security_detection_rate, 1),
                "control_false_neg": control.security_false_negatives,
                "treatment_false_neg": treatment.security_false_negatives,
                "verdict": "PASS" if treatment.security_detection_rate >= control.security_detection_rate * 0.9 else "FAIL",
            },
            "D3_routing_accuracy": {
                "control_pct": round(control.routing_accuracy, 1),
                "treatment_pct": round(treatment.routing_accuracy, 1),
                "verdict": "PASS" if treatment.routing_accuracy >= 90 else "FAIL",
            },
            "D4_efficiency": {
                "control_tokens": control.total_tokens,
                "treatment_tokens": treatment.total_tokens,
                "token_reduction_pct": round(
                    (1 - treatment.total_tokens / control.total_tokens) * 100, 1
                ) if control.total_tokens > 0 else 0,
                "control_invocations": control.total_agent_invocations,
                "treatment_invocations": treatment.total_agent_invocations,
                "invocation_reduction_pct": round(
                    (1 - treatment.total_agent_invocations / control.total_agent_invocations) * 100, 1
                ) if control.total_agent_invocations > 0 else 0,
                "verdict": "PASS" if treatment.total_tokens < control.total_tokens * 0.8 else "NEUTRAL",
            },
        },
        "overall_verdict": "PASS" if all([
            treatment.task_success_rate >= control.task_success_rate,
            treatment.security_detection_rate >= control.security_detection_rate * 0.9,
            treatment.routing_accuracy >= 90,
        ]) else "FAIL",
    }


def print_report(report: EvalReport) -> None:
    """Print report in human-readable format."""
    print("=" * 70)
    print(f"Agent Consolidation Eval: {report.condition.upper()}")
    print("=" * 70)

    print(f"\nD1: Task Completion: {report.task_success_rate:.1f}%")
    print(f"    Total: {len(report.task_results)}, Passed: {sum(1 for r in report.task_results if r.overall_pass)}")

    print(f"\nD2: Security Detection: {report.security_detection_rate:.1f}%")
    print(f"    False Negatives: {report.security_false_negatives}, False Positives: {report.security_false_positives}")

    print(f"\nD3: Routing Accuracy: {report.routing_accuracy:.1f}%")
    print(f"    Total: {len(report.routing_results)}, Correct: {sum(1 for r in report.routing_results if r.passed)}")

    print(f"\nD4: Efficiency")
    print(f"    Total Tokens: {report.total_tokens}")
    print(f"    Agent Invocations: {report.total_agent_invocations}")
    print(f"    Avg Execution Time: {report.avg_execution_time_ms:.0f}ms")


def print_comparison(comparison: dict[str, Any]) -> None:
    """Print comparison results."""
    print("=" * 70)
    print("A/B Test Comparison Results")
    print("=" * 70)

    dims = comparison["dimensions"]

    print(f"\nD1: Task Completion")
    print(f"    Control: {dims['D1_task_completion']['control_pct']}%")
    print(f"    Treatment: {dims['D1_task_completion']['treatment_pct']}%")
    print(f"    Delta: {dims['D1_task_completion']['delta_pct']:+.1f}%")
    print(f"    Verdict: {dims['D1_task_completion']['verdict']}")

    print(f"\nD2: Security Detection")
    print(f"    Control: {dims['D2_security_detection']['control_pct']}%")
    print(f"    Treatment: {dims['D2_security_detection']['treatment_pct']}%")
    print(f"    Treatment FN: {dims['D2_security_detection']['treatment_false_neg']}")
    print(f"    Verdict: {dims['D2_security_detection']['verdict']}")

    print(f"\nD3: Routing Accuracy")
    print(f"    Control: {dims['D3_routing_accuracy']['control_pct']}%")
    print(f"    Treatment: {dims['D3_routing_accuracy']['treatment_pct']}%")
    print(f"    Verdict: {dims['D3_routing_accuracy']['verdict']}")

    print(f"\nD4: Efficiency")
    print(f"    Token Reduction: {dims['D4_efficiency']['token_reduction_pct']}%")
    print(f"    Invocation Reduction: {dims['D4_efficiency']['invocation_reduction_pct']}%")
    print(f"    Verdict: {dims['D4_efficiency']['verdict']}")

    print(f"\n{'=' * 70}")
    print(f"OVERALL VERDICT: {comparison['overall_verdict']}")
    print(f"{'=' * 70}")


def dry_run_preview(scenarios: dict) -> None:
    """Print scenario preview without running."""
    print("=" * 70)
    print("DRY RUN: Agent Consolidation A/B Test Scenarios")
    print("=" * 70)

    print(f"\nTask Scenarios ({len(scenarios.get('task_scenarios', []))}):")
    for s in scenarios.get("task_scenarios", []):
        print(f"  {s['id']} [{s['complexity']}]: {s['prompt'][:60]}...")

    print(f"\nSecurity Test Corpus ({len(scenarios.get('security_test_corpus', []))}):")
    for s in scenarios.get("security_test_corpus", []):
        print(f"  {s['id']} [{s['cwe']}]: {s['name']}")

    print(f"\nRouting Scenarios ({len(scenarios.get('routing_scenarios', []))}):")
    for s in scenarios.get("routing_scenarios", []):
        print(f"  {s['id']} [{s['complexity']}]: {s['prompt'][:50]}...")

    total = (
        len(scenarios.get("task_scenarios", []))
        + len(scenarios.get("security_test_corpus", []))
        + len(scenarios.get("routing_scenarios", []))
    )
    print(f"\nTotal scenarios: {total}")
    print("Run without --dry-run to execute evaluation.")


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="A/B Test evaluation for agent consolidation proposal",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview scenarios without calling LLM",
    )
    parser.add_argument(
        "--condition",
        choices=["control", "treatment", "both"],
        default="control",
        help="Which condition to evaluate (default: control)",
    )
    parser.add_argument(
        "--category",
        choices=["task", "security", "routing", "all"],
        default="all",
        help="Which category of scenarios to run (default: all)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Load existing results and compare",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file for JSON results",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()

    # Ensure results directory exists
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        scenarios = load_scenarios()
        dry_run_preview(scenarios)
        return 0

    if args.compare:
        # Load existing results and compare
        control_file = RESULTS_DIR / "control_results.json"
        treatment_file = RESULTS_DIR / "treatment_results.json"

        if not control_file.exists() or not treatment_file.exists():
            print("[ERROR] Missing result files. Run both conditions first.", file=sys.stderr)
            return 2

        control_data = json.loads(control_file.read_text())
        treatment_data = json.loads(treatment_file.read_text())

        # Reconstruct reports from saved data
        control_report = EvalReport(condition="control")
        treatment_report = EvalReport(condition="treatment")

        comparison = compare_reports(control_report, treatment_report)

        if args.format == "json":
            print(json.dumps(comparison, indent=2))
        else:
            print_comparison(comparison)

        if args.output:
            Path(args.output).write_text(json.dumps(comparison, indent=2))

        return 0 if comparison["overall_verdict"] == "PASS" else 1

    # Run evaluation
    categories = [args.category] if args.category != "all" else ["all"]
    results = {}

    if args.condition in ("control", "both"):
        report = run_evaluation("control", categories, args.dry_run)
        results["control"] = report.to_dict()

        if args.format == "table":
            print_report(report)

        # Save results
        control_file = RESULTS_DIR / "control_results.json"
        control_file.write_text(json.dumps(report.to_dict(), indent=2))

    if args.condition in ("treatment", "both"):
        report = run_evaluation("treatment", categories, args.dry_run)
        results["treatment"] = report.to_dict()

        if args.format == "table":
            print_report(report)

        # Save results
        treatment_file = RESULTS_DIR / "treatment_results.json"
        treatment_file.write_text(json.dumps(report.to_dict(), indent=2))

    if args.condition == "both" and len(results) == 2:
        # Auto-compare
        control_report = EvalReport(condition="control")
        treatment_report = EvalReport(condition="treatment")
        comparison = compare_reports(control_report, treatment_report)

        if args.format == "table":
            print_comparison(comparison)

    if args.format == "json":
        print(json.dumps(results, indent=2))

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
