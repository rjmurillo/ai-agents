#!/usr/bin/env python3
"""Eval Suite: Unified test orchestrator for prompt, skill, and command changes.

Detects what changed via git diff, classifies changes, and routes to the
appropriate evaluator. Single entry point for all eval types.

Evaluator routing:
    - Prompt structural changes  -> Pester tests (ADR-023)
    - Prompt behavioral changes  -> eval-prompt-change.py (ADR-057)
    - Agent definition changes   -> eval-agents.py (quality assessment)
    - Skill definition changes   -> eval-knowledge-integration.py (knowledge eval)

Usage:
    # Auto-detect from git diff against main:
    python3 scripts/eval/eval-suite.py

    # Against a specific ref:
    python3 scripts/eval/eval-suite.py --base-ref origin/main

    # Specific scope only:
    python3 scripts/eval/eval-suite.py --scope prompts
    python3 scripts/eval/eval-suite.py --scope agents
    python3 scripts/eval/eval-suite.py --scope skills

    # Dry run (detect and classify only):
    python3 scripts/eval/eval-suite.py --dry-run

    # Output results to file:
    python3 scripts/eval/eval-suite.py --output eval-results.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent

# Security-critical path patterns (ADR-057: 5 runs, 100% pass)
SECURITY_PATTERNS = [
    ".agents/security/",
    "pr-quality-gate-security",
    "security-review",
    "security-scan",
]


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def detect_changed_files(base_ref: str) -> list[str]:
    """Get files changed between base_ref and working tree (staged + unstaged)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            capture_output=True, text=True, check=True,
            cwd=str(REPO_ROOT),
        )
        committed = result.stdout.strip().splitlines()
    except subprocess.CalledProcessError:
        committed = []

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, check=True,
            cwd=str(REPO_ROOT),
        )
        staged = result.stdout.strip().splitlines()
    except subprocess.CalledProcessError:
        staged = []

    return sorted(set(committed + staged))


# ---------------------------------------------------------------------------
# Change classification
# ---------------------------------------------------------------------------

PROMPT_PATTERNS = [
    ".claude/commands/",
    ".github/prompts/",
    ".agents/security/prompts/",
]

AGENT_PATTERNS = [
    ".claude/agents/",
]

SKILL_PATTERNS = [
    ".claude/skills/",
]

SCENARIO_DIRS = [
    "tests/evals/",
    ".agents/security/benchmarks/",
]


def classify_changes(files: list[str]) -> dict[str, list[str]]:
    """Classify changed files into categories for eval routing."""
    classified: dict[str, list[str]] = {
        "prompts": [],
        "agents": [],
        "skills": [],
        "scenarios": [],
        "structural_test_targets": [],
        "other": [],
    }

    for f in files:
        matched = False

        for pattern in PROMPT_PATTERNS:
            if f.startswith(pattern) and f.endswith(".md"):
                classified["prompts"].append(f)
                matched = True
                break

        if not matched:
            for pattern in AGENT_PATTERNS:
                if f.startswith(pattern) and f.endswith(".md"):
                    name = Path(f).name
                    if name not in ("CLAUDE.md", "README.md", "INDEX.md"):
                        classified["agents"].append(f)
                        matched = True
                    break

        if not matched:
            for pattern in SKILL_PATTERNS:
                if f.startswith(pattern):
                    classified["skills"].append(f)
                    matched = True
                    break

        if not matched:
            for pattern in SCENARIO_DIRS:
                if f.startswith(pattern):
                    classified["scenarios"].append(f)
                    matched = True
                    break

        # Structural test targets (quality gate prompts per ADR-023)
        if f.startswith(".github/prompts/pr-quality-gate-"):
            classified["structural_test_targets"].append(f)

        if not matched:
            classified["other"].append(f)

    return classified


def is_security_critical(path: str) -> bool:
    """Check if a path matches security-critical patterns."""
    return any(pattern in path for pattern in SECURITY_PATTERNS)


def find_scenarios_for_prompt(prompt_path: str) -> str | None:
    """Find scenario file for a prompt using naming convention.

    Convention: for prompt at `path/to/name.md`, look for:
    1. tests/evals/name-scenarios.json
    2. .agents/security/benchmarks/name-scenarios.json
    """
    stem = Path(prompt_path).stem

    for scenario_dir in SCENARIO_DIRS:
        candidate = REPO_ROOT / scenario_dir / f"{stem}-scenarios.json"
        if candidate.exists():
            return str(candidate.relative_to(REPO_ROOT))

    return None


# ---------------------------------------------------------------------------
# Individual eval runners
# ---------------------------------------------------------------------------

def run_structural_tests(targets: list[str], dry_run: bool) -> dict[str, Any]:
    """Run Pester structural tests (ADR-023)."""
    test_file = REPO_ROOT / "tests" / "QualityGatePrompts.Tests.ps1"
    if not test_file.exists():
        return {"skipped": True, "reason": "Test file not found", "targets": targets}

    if dry_run:
        return {"skipped": True, "reason": "dry-run", "targets": targets}

    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-Command",
             f"Invoke-Pester '{test_file}' -Output Detailed -PassThru | "
             "ConvertTo-Json -Depth 3"],
            capture_output=True, text=True, timeout=60,
            cwd=str(REPO_ROOT),
        )
        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "targets": targets,
            "output_preview": result.stdout[:500] if result.stdout else "",
            "stderr_preview": result.stderr[:500] if result.stderr else "",
        }
    except FileNotFoundError:
        return {"skipped": True, "reason": "pwsh not found", "targets": targets}
    except subprocess.TimeoutExpired:
        return {"passed": False, "reason": "timeout (60s)", "targets": targets}


def run_behavioral_for_prompt(
    prompt_path: str,
    scenario_path: str,
    base_ref: str,
    security_critical: bool,
    model: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Run ADR-057 behavioral comparison via eval-prompt-change.py."""
    cmd = [
        sys.executable, str(SCRIPT_DIR / "eval-prompt-change.py"),
        "--prompt", prompt_path,
        "--scenarios", scenario_path,
        "--base-ref", base_ref,
        "--model", model,
    ]
    if security_critical:
        cmd.append("--security-critical")
    if dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            cwd=str(REPO_ROOT),
        )
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = {"raw_output": result.stdout[:1000]}

        return {
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "prompt": prompt_path,
            "scenarios": scenario_path,
            "security_critical": security_critical,
            "results": parsed,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "reason": "timeout (600s)", "prompt": prompt_path}


def run_agent_quality(
    agents: list[str], model: str, dry_run: bool
) -> dict[str, Any]:
    """Run agent quality assessment via eval-agents.py."""
    agent_names = [Path(a).stem for a in agents]
    results: dict[str, Any] = {"agents": {}}

    for name in agent_names:
        cmd = [
            sys.executable, str(SCRIPT_DIR / "eval-agents.py"),
            "--agent", name, "--model", model,
        ]
        if dry_run:
            cmd.append("--dry-run")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                cwd=str(REPO_ROOT),
            )
            try:
                parsed = json.loads(result.stdout)
            except json.JSONDecodeError:
                parsed = {"raw_output": result.stdout[:500]}

            results["agents"][name] = {
                "passed": result.returncode == 0,
                "exit_code": result.returncode,
                "results": parsed,
            }
        except subprocess.TimeoutExpired:
            results["agents"][name] = {"passed": False, "reason": "timeout (300s)"}

    results["passed"] = all(a.get("passed", False) for a in results["agents"].values())
    return results


def run_skill_knowledge(
    skills: list[str], model: str, dry_run: bool
) -> dict[str, Any]:
    """Run skill knowledge integration via eval-knowledge-integration.py."""
    skill_names = set()
    for s in skills:
        parts = Path(s).parts
        try:
            idx = parts.index("skills")
            if idx + 1 < len(parts):
                skill_names.add(parts[idx + 1])
        except ValueError:
            continue

    results: dict[str, Any] = {"skills": {}}
    for name in sorted(skill_names):
        cmd = [
            sys.executable, str(SCRIPT_DIR / "eval-knowledge-integration.py"),
            "--skill", name, "--model", model,
        ]
        if dry_run:
            cmd.append("--dry-run")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                cwd=str(REPO_ROOT),
            )
            try:
                parsed = json.loads(result.stdout)
            except json.JSONDecodeError:
                parsed = {"raw_output": result.stdout[:500]}

            results["skills"][name] = {
                "passed": result.returncode == 0,
                "exit_code": result.returncode,
                "results": parsed,
            }
        except subprocess.TimeoutExpired:
            results["skills"][name] = {"passed": False, "reason": "timeout (300s)"}

    results["passed"] = all(s.get("passed", False) for s in results["skills"].values())
    return results


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified eval orchestrator for prompt, skill, and agent changes"
    )
    parser.add_argument("--base-ref", type=str, default="main",
                        help="Git ref to compare against (default: main)")
    parser.add_argument("--scope", type=str,
                        choices=["prompts", "agents", "skills", "all"],
                        default="all", help="Limit to specific scope")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-20250514",
                        help="Model for LLM-based assessments")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect and classify only, no API calls")
    parser.add_argument("--output", type=str, help="Write results to file")
    args = parser.parse_args()

    start_time = time.time()

    # Phase 1: Detect
    print(f"{'='*60}", file=sys.stderr)
    print(f"  EVAL SUITE: Detecting changes vs {args.base_ref}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    changed_files = detect_changed_files(args.base_ref)
    if not changed_files:
        print("  No changes detected.", file=sys.stderr)
        sys.exit(0)

    print(f"  Changed files: {len(changed_files)}", file=sys.stderr)

    # Phase 2: Classify
    classified = classify_changes(changed_files)
    for category, files in classified.items():
        if files:
            print(f"  {category}: {len(files)} files", file=sys.stderr)

    # Phase 3: Route and run
    output: dict[str, Any] = {
        "suite_version": "1.0.0",
        "base_ref": args.base_ref,
        "model": args.model,
        "scope": args.scope,
        "changed_files": len(changed_files),
        "classification": {k: v for k, v in classified.items() if v},
        "results": {},
    }

    any_failure = False

    # 3a: Structural tests (ADR-023)
    if classified["structural_test_targets"] and args.scope in ("prompts", "all"):
        print(f"\n--- Structural Tests (ADR-023) ---", file=sys.stderr)
        result = run_structural_tests(classified["structural_test_targets"], args.dry_run)
        output["results"]["structural"] = result
        if not result.get("skipped") and not result.get("passed"):
            any_failure = True

    # 3b: Behavioral (ADR-057)
    if classified["prompts"] and args.scope in ("prompts", "all"):
        print(f"\n--- Behavioral Assessment (ADR-057) ---", file=sys.stderr)
        behavioral_results = []
        for prompt_path in classified["prompts"]:
            scenario_path = find_scenarios_for_prompt(prompt_path)
            if scenario_path:
                security = is_security_critical(prompt_path)
                print(f"  {prompt_path} -> {scenario_path}"
                      f"{' [SECURITY]' if security else ''}", file=sys.stderr)
                result = run_behavioral_for_prompt(
                    prompt_path, scenario_path, args.base_ref,
                    security, args.model, args.dry_run,
                )
                behavioral_results.append(result)
                if not result.get("passed"):
                    any_failure = True
            else:
                print(f"  {prompt_path}: no scenarios found (skipped)", file=sys.stderr)
                behavioral_results.append({
                    "skipped": True,
                    "prompt": prompt_path,
                    "reason": "no scenario file found",
                })

        output["results"]["behavioral"] = behavioral_results

    # 3c: Agent quality
    if classified["agents"] and args.scope in ("agents", "all"):
        print(f"\n--- Agent Quality Assessment ---", file=sys.stderr)
        result = run_agent_quality(classified["agents"], args.model, args.dry_run)
        output["results"]["agents"] = result
        if not result.get("passed"):
            any_failure = True

    # 3d: Skill knowledge
    if classified["skills"] and args.scope in ("skills", "all"):
        print(f"\n--- Skill Knowledge Assessment ---", file=sys.stderr)
        result = run_skill_knowledge(classified["skills"], args.model, args.dry_run)
        output["results"]["skills"] = result
        if not result.get("passed"):
            any_failure = True

    # Phase 4: Summary
    elapsed = round(time.time() - start_time, 1)
    output["elapsed_seconds"] = elapsed
    output["passed"] = not any_failure

    json_output = json.dumps(output, indent=2)

    if args.output:
        Path(args.output).write_text(json_output, encoding="utf-8")
        print(f"\n  Results written to {args.output}", file=sys.stderr)
    else:
        print(json_output)

    # Summary table
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  EVAL SUITE RESULTS ({elapsed}s)", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  {'Category':<25} {'Status':>10}", file=sys.stderr)
    print(f"  {'-'*35}", file=sys.stderr)

    for name, data in output["results"].items():
        if isinstance(data, list):
            passed_count = sum(1 for r in data if r.get("passed"))
            skipped = sum(1 for r in data if r.get("skipped"))
            total = len(data)
            status = f"{passed_count}/{total - skipped} pass"
            if skipped:
                status += f" ({skipped} skip)"
        elif data.get("skipped"):
            status = "SKIPPED"
        elif data.get("passed"):
            status = "PASS"
        else:
            status = "FAIL"

        print(f"  {name:<25} {status:>10}", file=sys.stderr)

    verdict = "PASS" if not any_failure else "FAIL"
    print(f"\n  Overall: {verdict}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    sys.exit(0 if not any_failure else 1)


if __name__ == "__main__":
    main()
