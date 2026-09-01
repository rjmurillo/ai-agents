#!/usr/bin/env python3
# taste-lint: ignore file-size, orchestrator keeps routing and its runners together.
# taste-lint: ignore naming, hyphenated CLI name is the shipped entrypoint.
"""Eval Suite: Unified test orchestrator for prompt, skill, and command changes.

Detects what changed via git diff, classifies changes, and routes to the
appropriate evaluator. Single entry point for all eval types.

Routing is table-driven (`ROUTING_RULES`), ordered narrowest first, first match
wins. See `.claude/rules/code-quality.md`, section "Table-Driven Logic": "When
branching grows past three or four cases, replace conditional code with a table."

Evaluator routing:
    - Prompt structural changes  -> Pester tests (ADR-023)
    - Prompt behavioral changes  -> eval-prompt-change.py (ADR-057)
    - Agent definition changes   -> eval-agents.py (quality assessment)
    - Skill definition changes   -> eval-knowledge-integration.py (knowledge eval)
    - Skill reference changes    -> eval-knowledge-integration.py (parent skill)
    - Canonical rule changes     -> eval-rule-activation.py (scenario-gated)
    - Instruction mirror changes -> eval-rule-activation.py (via canonical rule)

Every classified category either names a runner or carries an explicit
`not_evaluated` reason in the routing plan. No context-bearing category falls
silently into `other` (issue #4882, required work item 2).

Usage:
    # Auto-detect from git diff against main:
    python3 scripts/eval/eval-suite.py

    # Against a specific ref:
    python3 scripts/eval/eval-suite.py --base-ref origin/main

    # Specific scope only:
    python3 scripts/eval/eval-suite.py --scope prompts
    python3 scripts/eval/eval-suite.py --scope agents
    python3 scripts/eval/eval-suite.py --scope skills
    python3 scripts/eval/eval-suite.py --scope rules

    # Dry run (classify and print the routing plan; no subprocess, no model):
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
from typing import Any, NamedTuple

from _anthropic_api import DEFAULT_MODEL

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

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

class ChangeDetectionError(RuntimeError):
    """Git change detection failed, so the suite cannot know what to run."""


def detect_changed_files(base_ref: str) -> list[str]:
    """Get files changed between base_ref and working tree (staged + unstaged)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            cwd=str(REPO_ROOT),
        )
        committed = result.stdout.strip().splitlines()
    except subprocess.CalledProcessError as e:
        raise ChangeDetectionError(
            f"git diff against {base_ref} failed: {e}"
        ) from e

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            cwd=str(REPO_ROOT),
        )
        staged = result.stdout.strip().splitlines()
    except subprocess.CalledProcessError as e:
        raise ChangeDetectionError("git diff --cached failed") from e

    return sorted(set(committed + staged))


def _parse_child_json(stdout: str, context: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, f"JSON parse failed for {context}: {exc}"
    if not isinstance(parsed, dict):
        return None, f"JSON schema failed for {context}: output is not an object"
    return parsed, None


def _contains_external_failure(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("exit_code") == EXIT_EXTERNAL:
            return True
        return any(_contains_external_failure(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_external_failure(item) for item in value)
    return False


# ---------------------------------------------------------------------------
# Change classification
# ---------------------------------------------------------------------------

PROMPT_PATTERNS = [
    ".claude/commands/",
    ".github/prompts/",
    ".agents/security/prompts/",
]

# Agent definition trees. Narrowed from a bare `src/copilot-cli/` prefix, which
# captured every Markdown file in that tree (issue #4882). `src/copilot-cli/`
# also holds `instructions/`, `skills/`, `docs/`, and `lib/`, none of which are
# agents.
AGENT_PATTERNS = [
    ".claude/agents/",
    "src/claude/",
    "src/copilot-cli/agents/",
    "src/vs-code-agents/",
]

SKILL_PATTERNS = [
    ".claude/skills/",
    "src/copilot-cli/skills/",
]

# Canonical rules. `build/scripts/generate_rules.py` mirrors these into the two
# instruction trees below.
RULE_PATTERNS = [
    ".claude/rules/",
]

INSTRUCTION_PATTERNS = [
    ".github/instructions/",
    "src/copilot-cli/instructions/",
]

INSTRUCTION_SUFFIX = ".instructions.md"

SCENARIO_DIRS = [
    "tests/evals/",
    ".agents/security/benchmarks/",
]

# Preserved verbatim from the pre-#4882 agent branch, which read:
#     skip = ("CLAUDE.md", "README.md", "INDEX.md", "AGENTS.md")
#     if name not in skip and ".template." not in name:
AGENT_EXCLUDED_BASENAMES = frozenset({"CLAUDE.md", "README.md", "INDEX.md", "AGENTS.md"})
AGENT_EXCLUDED_SUBSTRINGS = (".template.",)

# Path-local and root harness entrypoints. Two of the four basenames the agent
# branch excluded are context-bearing, so they get a category instead of
# dropping into `other`.
ENTRYPOINT_BASENAMES = frozenset({"AGENTS.md", "CLAUDE.md"})

REFERENCE_SEGMENT = "references"


class RoutingRule(NamedTuple):
    """One row of the routing table: a path shape mapped to a category.

    A path matches when every constraint set on the row holds. Unset
    constraints do not filter.

    prefix              path must start with this string
    suffix              path must end with this string ("" disables)
    segment             this directory component must appear in the path,
                        excluding the basename
    basenames           basename must be one of these
    exclude_basenames   basename must not be one of these
    exclude_substrings  basename must contain none of these
    """

    category: str
    prefix: str = ""
    suffix: str = ".md"
    segment: str | None = None
    basenames: frozenset[str] = frozenset()
    exclude_basenames: frozenset[str] = frozenset()
    exclude_substrings: tuple[str, ...] = ()

    def matches(self, path: str) -> bool:
        if self.prefix and not path.startswith(self.prefix):
            return False
        if self.suffix and not path.endswith(self.suffix):
            return False
        parts = path.split("/")
        name = parts[-1]
        if self.basenames and name not in self.basenames:
            return False
        if name in self.exclude_basenames:
            return False
        if any(token in name for token in self.exclude_substrings):
            return False
        if self.segment is not None and self.segment not in parts[:-1]:
            return False
        return True


def _rules_for(
    category: str,
    prefixes: list[str],
    suffix: str = ".md",
    segment: str | None = None,
    exclude_basenames: frozenset[str] = frozenset(),
    exclude_substrings: tuple[str, ...] = (),
) -> tuple[RoutingRule, ...]:
    """Expand one category across several path prefixes, one row per prefix."""
    return tuple(
        RoutingRule(
            category,
            prefix=prefix,
            suffix=suffix,
            segment=segment,
            exclude_basenames=exclude_basenames,
            exclude_substrings=exclude_substrings,
        )
        for prefix in prefixes
    )


# Ordered narrowest first; the first matching row wins. Ordering is the whole
# contract here: issue #4882 was a broad `src/copilot-cli/` agent prefix placed
# ahead of the skill rows, so Copilot skills, skill references, and instruction
# mirrors were all sent to `eval-agents.py`, which then exited 1 with empty
# stdout and turned the suite's dry run into a JSON parse failure.
#
# `tests/eval/test_eval_suite_routing.py` pins this order two ways: every row
# must win for its own representative path (no row may be shadowed), and a
# negative control replays the broad prefix to prove the tests catch a
# reintroduction.
ROUTING_RULES: tuple[RoutingRule, ...] = (
    *_rules_for("prompts", PROMPT_PATTERNS),
    # References must precede the trees that contain them.
    *_rules_for("skill_references", SKILL_PATTERNS, segment=REFERENCE_SEGMENT),
    *_rules_for("skills", SKILL_PATTERNS, suffix=""),
    *_rules_for("references", AGENT_PATTERNS, segment=REFERENCE_SEGMENT),
    *_rules_for("rules", RULE_PATTERNS),
    *_rules_for("instructions", INSTRUCTION_PATTERNS, suffix=INSTRUCTION_SUFFIX),
    *_rules_for(
        "agents",
        AGENT_PATTERNS,
        exclude_basenames=AGENT_EXCLUDED_BASENAMES,
        exclude_substrings=AGENT_EXCLUDED_SUBSTRINGS,
    ),
    RoutingRule("entrypoints", basenames=ENTRYPOINT_BASENAMES),
    *_rules_for("scenarios", SCENARIO_DIRS, suffix=""),
)

CATEGORIES: tuple[str, ...] = (
    "prompts",
    "agents",
    "skills",
    "skill_references",
    "references",
    "rules",
    "instructions",
    "entrypoints",
    "scenarios",
    "structural_test_targets",
    "other",
)

# Category -> the evaluator that consumes it. A category absent from this map
# carries a reason in NOT_EVALUATED_REASONS instead. Every entry in CATEGORIES
# must appear in exactly one of the two (pinned by the routing tests).
RUNNER_BY_CATEGORY: dict[str, str] = {
    "prompts": "eval-prompt-change.py",
    "agents": "eval-agents.py",
    "skills": "eval-knowledge-integration.py",
    "skill_references": "eval-knowledge-integration.py",
    "rules": "eval-rule-activation.py",
    "instructions": "eval-rule-activation.py",
    "structural_test_targets": "Invoke-Pester",
}

NOT_EVALUATED_REASONS: dict[str, str] = {
    "references": (
        "reference material for a non-skill artifact; no evaluator consumes it"
    ),
    "entrypoints": (
        "no behavioral evaluator exists for AGENTS.md/CLAUDE.md entrypoints"
    ),
    "scenarios": "scenario corpora are eval inputs, not evaluated artifacts",
    "other": "no routing rule claims this path",
}


def classify_path(path: str) -> str:
    """Return the routing category for one path via first match in ROUTING_RULES."""
    for rule in ROUTING_RULES:
        if rule.matches(path):
            return rule.category
    return "other"


def classify_changes(files: list[str]) -> dict[str, list[str]]:
    """Classify changed files into categories for eval routing.

    Categories are exclusive except `structural_test_targets`, which is an
    additional tag applied to quality-gate prompts per ADR-023 and which the
    pre-#4882 code also applied alongside the exclusive category.
    """
    classified: dict[str, list[str]] = {category: [] for category in CATEGORIES}

    for f in files:
        classified[classify_path(f)].append(f)

        # Structural test targets (quality gate prompts per ADR-023)
        if f.startswith(".github/prompts/pr-quality-gate-"):
            classified["structural_test_targets"].append(f)

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


RULE_SCENARIO_DIR = "tests/evals/rule-scenarios"


def rule_id_for_path(path: str) -> str | None:
    """Map a canonical rule or generated instruction mirror to its rule id.

    The rule id is the canonical rule's file stem. This mirrors
    `scripts/validation/check_rule_activation_coverage.py`, whose
    `discover_rules` reads:

        ids = {p.stem for p in rules_dir.glob("*.md") if p.is_file()}

    and whose `_resolve_target` derives the same id from a scenario target:

        if kind == "rule":
            if resolved.suffix != ".md":
                raise CoverageConfigError(
                    f"rule_path must be a .md file: {target_str}"
                )
            artifact_id = resolved.stem

    Stricter/looser/different than canonical: the canonical functions read only
    `.claude/rules/`. This one additionally accepts a generated instruction
    mirror and strips the `.instructions.md` suffix that
    `build/scripts/generate_rules.py` appends, because a mirror change is a
    change to the same rule. It performs no filesystem or traversal
    validation; the canonical checker owns that.
    """
    name = Path(path).name
    if classify_path(path) == "rules":
        return name[: -len(".md")] if name.endswith(".md") else None
    if classify_path(path) == "instructions" and name.endswith(INSTRUCTION_SUFFIX):
        return name[: -len(INSTRUCTION_SUFFIX)]
    return None


def find_rule_scenarios() -> dict[str, str]:
    """Map rule id -> scenario file, read from each scenario's `rule_path`.

    Read rather than inferred from the filename: `tests/evals/rule-scenarios/`
    also holds skill-targeted scenarios (ADR-088 reference scenarios carry
    `skill_path` and no `rule_path`), so a stem convention would claim rule ids
    that do not exist.
    """
    scenarios: dict[str, str] = {}
    scenario_dir = REPO_ROOT / RULE_SCENARIO_DIR
    if not scenario_dir.is_dir():
        return scenarios

    for candidate in sorted(scenario_dir.glob("*.json")):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        rule_path = data.get("rule_path")
        if not isinstance(rule_path, str) or not rule_path.strip():
            continue
        scenarios[Path(rule_path).stem] = str(candidate.relative_to(REPO_ROOT))

    return scenarios


# ---------------------------------------------------------------------------
# Routing plan (issue #4882, required work items 2 and 4)
# ---------------------------------------------------------------------------

# Three evidence states, kept distinct so a consumer cannot read structural
# coverage as efficacy. Baseline membership in
# `scripts/validation/check_rule_activation_coverage.py` is not one of these:
# that ratchet records whether an artifact has a scenario at all, which is
# state STRUCTURAL here, never SCORED.
EVIDENCE_STRUCTURAL = "structurally_covered"
EVIDENCE_SCENARIO = "scenario_defined_not_scored"
EVIDENCE_SCORED = "scored"
EVIDENCE_NONE = "not_evaluated"


def _rule_plan_entries(files: list[str]) -> tuple[list[str], list[str]]:
    """Split rule and instruction paths into (with scenario, without scenario)."""
    scenarios = find_rule_scenarios()
    with_scenario: list[str] = []
    without_scenario: list[str] = []
    for path in files:
        rule_id = rule_id_for_path(path)
        if rule_id is not None and rule_id in scenarios:
            with_scenario.append(path)
        else:
            without_scenario.append(path)
    return with_scenario, without_scenario


def build_routing_plan(classified: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Describe what each classified category routes to, and its evidence state.

    Deterministic: entries follow CATEGORIES order and files are sorted. This
    is what `--dry-run` prints, and it is produced without invoking any
    evaluator or parsing any model output.
    """
    plan: list[dict[str, Any]] = []

    for category in CATEGORIES:
        files = sorted(classified.get(category, []))
        if not files:
            continue

        runner = RUNNER_BY_CATEGORY.get(category)
        if runner is None:
            plan.append({
                "category": category,
                "files": files,
                "runner": None,
                "evidence": EVIDENCE_NONE,
                "reason": NOT_EVALUATED_REASONS[category],
            })
            continue

        if category in ("rules", "instructions"):
            with_scenario, without_scenario = _rule_plan_entries(files)
            if with_scenario:
                plan.append({
                    "category": category,
                    "files": with_scenario,
                    "runner": runner,
                    "evidence": EVIDENCE_SCENARIO,
                    "reason": "activation scenario defined; run without --dry-run to score",
                })
            if without_scenario:
                plan.append({
                    "category": category,
                    "files": without_scenario,
                    "runner": None,
                    "evidence": EVIDENCE_NONE,
                    "reason": f"no activation scenario under {RULE_SCENARIO_DIR}/",
                })
            continue

        plan.append({
            "category": category,
            "files": files,
            "runner": runner,
            "evidence": EVIDENCE_STRUCTURAL,
            "reason": "routed to a runner; scoring requires a non-dry run",
        })

    return plan


def _print_routing_plan(plan: list[dict[str, Any]]) -> None:
    print("\n--- Routing Plan ---", file=sys.stderr)
    if not plan:
        print("  (nothing to route)", file=sys.stderr)
        return
    for entry in plan:
        runner = entry["runner"] or "(none)"
        print(
            f"  {entry['category']:<24} {len(entry['files']):>3} file(s)"
            f"  -> {runner}  [{entry['evidence']}]",
            file=sys.stderr,
        )
        print(f"      reason: {entry['reason']}", file=sys.stderr)
        for path in entry["files"]:
            print(f"      - {path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Individual eval runners
# ---------------------------------------------------------------------------

def run_rule_activation(files: list[str], model: str) -> dict[str, Any]:
    """Score rule and instruction changes via eval-rule-activation.py.

    Reuses the existing activation evaluator rather than adding a parallel
    harness (issue #4882, required work item 6). A rule with no scenario file
    is reported `not_evaluated`, never silently passed.
    """
    scenarios = find_rule_scenarios()
    results: dict[str, Any] = {"rules": {}}

    targets: dict[str, str] = {}
    for path in files:
        rule_id = rule_id_for_path(path)
        if rule_id is None:
            results["rules"][path] = {
                "skipped": True,
                "evidence": EVIDENCE_NONE,
                "reason": "path carries no resolvable rule id",
            }
        elif rule_id not in scenarios:
            results["rules"][rule_id] = {
                "skipped": True,
                "evidence": EVIDENCE_NONE,
                "reason": f"no activation scenario under {RULE_SCENARIO_DIR}/",
            }
        else:
            targets[rule_id] = scenarios[rule_id]

    for rule_id, scenario_path in sorted(targets.items()):
        cmd = [
            sys.executable, str(SCRIPT_DIR / "eval-rule-activation.py"),
            "--scenarios", scenario_path, "--model", model,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                cwd=str(REPO_ROOT),
            )
            parsed, parse_error = _parse_child_json(result.stdout, f"rule {rule_id}")
            passed = result.returncode == 0 and parse_error is None
            exit_code = EXIT_EXTERNAL if parse_error is not None else result.returncode
            if parse_error is not None:
                print(f"WARNING: {parse_error}", file=sys.stderr)
                parsed = {"raw_output": result.stdout[:500], "error": parse_error}

            results["rules"][rule_id] = {
                "passed": passed,
                "exit_code": exit_code,
                "evidence": EVIDENCE_SCORED if passed else EVIDENCE_SCENARIO,
                "scenarios": scenario_path,
                "results": parsed,
            }
        except subprocess.TimeoutExpired:
            results["rules"][rule_id] = {"passed": False, "reason": "timeout (600s)"}

    scored = [r for r in results["rules"].values() if not r.get("skipped")]
    results["passed"] = all(r.get("passed", False) for r in scored)
    return results


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
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
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
        # nosemgrep: dangerous-subprocess-use-tainted-env-args
        # Justification: cmd from sys.executable + fixed script path + argparse
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            cwd=str(REPO_ROOT),
        )
        parsed, parse_error = _parse_child_json(result.stdout, prompt_path)
        passed = result.returncode == 0 and parse_error is None
        exit_code = EXIT_EXTERNAL if parse_error is not None else result.returncode
        if parse_error is not None:
            print(f"WARNING: {parse_error}", file=sys.stderr)
            parsed = {"raw_output": result.stdout[:1000], "error": parse_error}

        return {
            "passed": passed,
            "exit_code": exit_code,
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
            # nosemgrep: dangerous-subprocess-use-tainted-env-args
            # Justification: cmd built from sys.executable + fixed script path + argparse args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                cwd=str(REPO_ROOT),
            )
            parsed, parse_error = _parse_child_json(result.stdout, f"eval-agents for {name}")
            passed = result.returncode == 0 and parse_error is None
            exit_code = EXIT_EXTERNAL if parse_error is not None else result.returncode
            if parse_error is not None:
                print(f"WARNING: {parse_error}", file=sys.stderr)
                parsed = {"raw_output": result.stdout[:500], "error": parse_error}

            results["agents"][name] = {
                "passed": passed,
                "exit_code": exit_code,
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
            # nosemgrep: dangerous-subprocess-use-tainted-env-args
            # Justification: cmd built from sys.executable + fixed script path + argparse args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                cwd=str(REPO_ROOT),
            )
            parsed, parse_error = _parse_child_json(result.stdout, f"skill {name}")
            passed = result.returncode == 0 and parse_error is None
            exit_code = EXIT_EXTERNAL if parse_error is not None else result.returncode
            if parse_error is not None:
                print(f"WARNING: {parse_error}", file=sys.stderr)
                parsed = {"raw_output": result.stdout[:500], "error": parse_error}

            results["skills"][name] = {
                "passed": passed,
                "exit_code": exit_code,
                "results": parsed,
            }
        except subprocess.TimeoutExpired:
            results["skills"][name] = {"passed": False, "reason": "timeout (300s)"}

    results["passed"] = all(s.get("passed", False) for s in results["skills"].values())
    return results


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def _detect_and_classify(base_ref: str) -> dict[str, list[str]]:
    """Detect changed files and classify them by eval category."""
    print(f"{'='*60}", file=sys.stderr)
    print(f"  EVAL SUITE: Detecting changes vs {base_ref}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    changed_files = detect_changed_files(base_ref)
    if not changed_files:
        print("  No changes detected.", file=sys.stderr)
        sys.exit(0)

    print(f"  Changed files: {len(changed_files)}", file=sys.stderr)

    classified = classify_changes(changed_files)
    for category, files in classified.items():
        if files:
            print(f"  {category}: {len(files)} files", file=sys.stderr)

    return classified


def _run_evals(
    classified: dict[str, list[str]],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], bool]:
    """Route classified files to evaluators and collect results."""
    results: dict[str, Any] = {}
    any_failure = False

    if classified["structural_test_targets"] and args.scope in ("prompts", "all"):
        print("\n--- Structural Tests (ADR-023) ---", file=sys.stderr)
        result = run_structural_tests(classified["structural_test_targets"], args.dry_run)
        results["structural"] = result
        if not result.get("skipped") and not result.get("passed"):
            any_failure = True

    if classified["prompts"] and args.scope in ("prompts", "all"):
        print("\n--- Behavioral Assessment (ADR-057) ---", file=sys.stderr)
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
                    "skipped": True, "prompt": prompt_path,
                    "reason": "no scenario file found",
                })
        results["behavioral"] = behavioral_results

    if classified["agents"] and args.scope in ("agents", "all"):
        print("\n--- Agent Quality Assessment ---", file=sys.stderr)
        result = run_agent_quality(classified["agents"], args.model, args.dry_run)
        results["agents"] = result
        if not result.get("passed"):
            any_failure = True

    skill_files = classified["skills"] + classified["skill_references"]
    if skill_files and args.scope in ("skills", "all"):
        print("\n--- Skill Knowledge Assessment ---", file=sys.stderr)
        result = run_skill_knowledge(skill_files, args.model, args.dry_run)
        results["skills"] = result
        if not result.get("passed"):
            any_failure = True

    rule_files = classified["rules"] + classified["instructions"]
    if rule_files and args.scope in ("rules", "all"):
        print("\n--- Rule Activation Assessment ---", file=sys.stderr)
        result = run_rule_activation(rule_files, args.model)
        results["rules"] = result
        if not result.get("passed"):
            any_failure = True

    return results, any_failure


def _print_summary(output: dict[str, Any]) -> None:
    """Print summary table of eval results to stderr."""
    elapsed = output.get("elapsed_seconds", 0)
    any_failure = not output.get("passed", True)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  EVAL SUITE RESULTS ({elapsed}s)", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  {'Category':<25} {'Status':>10}", file=sys.stderr)
    print(f"  {'-'*35}", file=sys.stderr)

    for name, data in output.get("results", {}).items():
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified eval orchestrator for prompt, skill, and agent changes"
    )
    parser.add_argument("--base-ref", type=str, default="main",
                        help="Git ref to compare against (default: main)")
    parser.add_argument("--scope", type=str,
                        choices=["prompts", "agents", "skills", "rules", "all"],
                        default="all", help="Limit to specific scope")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help="Model for LLM-based assessments")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect and classify only, no API calls")
    parser.add_argument("--output", type=str, help="Write results to file")
    args = parser.parse_args()

    start_time = time.time()
    try:
        classified = _detect_and_classify(args.base_ref)
    except ChangeDetectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(EXIT_CONFIG)
    plan = build_routing_plan(classified)

    # A dry run validates routing and planned work only. It invokes no
    # evaluator and parses no model output (issue #4882, required work item 3).
    if args.dry_run:
        _print_routing_plan(plan)
        results: dict[str, Any] = {}
        any_failure = False
    else:
        results, any_failure = _run_evals(classified, args)

    elapsed = round(time.time() - start_time, 1)
    output: dict[str, Any] = {
        "suite_version": "1.1.0",
        "base_ref": args.base_ref,
        "model": args.model,
        "scope": args.scope,
        "dry_run": args.dry_run,
        "changed_files": sum(len(v) for v in classified.values()),
        "classification": {k: v for k, v in classified.items() if v},
        "routing_plan": plan,
        "results": results,
        "elapsed_seconds": elapsed,
        "passed": not any_failure,
    }

    json_output = json.dumps(output, indent=2)
    if args.output:
        Path(args.output).write_text(json_output, encoding="utf-8")
        print(f"\n  Results written to {args.output}", file=sys.stderr)
    else:
        print(json_output)

    _print_summary(output)
    if not any_failure:
        sys.exit(EXIT_OK)
    sys.exit(EXIT_EXTERNAL if _contains_external_failure(results) else EXIT_LOGIC)


if __name__ == "__main__":
    main()
