#!/usr/bin/env python3
"""Restructure .serena/memories/ into topic subdirectories.

Keeps index files at top level. Moves atomic memories into subdirectories
grouped by topic prefix. Updates index files to include path prefixes.

This is a one-time migration script.
"""

import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

MEMORIES_DIR = Path(".serena/memories")

# Files that MUST stay at top level regardless of naming
TOP_LEVEL_KEEP = {
    "README.md",
    "memory-index.md",
    "usage-mandatory.md",
}

# Minimum files to justify a subdirectory (otherwise goes to "general")
MIN_GROUP_SIZE = 3

# Mapping of prefix patterns to subdirectory names.
# More specific patterns first; fallback uses first word.
PREFIX_TO_DIR = {
    # PR review domain
    "pr-review": "pr-review",
    "pr-comment": "pr-review",
    "pr-co-mingling": "pr-review",
    "pr-changes": "pr-review",
    "pr-enum": "pr-review",
    "pr-status": "pr-review",
    "pr-template": "pr-review",
    "pr-001": "pr-review",
    "pr-002": "pr-review",
    "pr-003": "pr-review",
    "pr-006": "pr-review",
    "review-": "pr-review",
    "triage-": "pr-review",
    "anti-pattern-pr": "pr-review",
    "anti-pattern-status": "pr-review",
    "cursor-bot-review": "pr-review",
    "stuck-pr-": "pr-review",
    # CI/CD domain
    "ci-infrastructure": "ci",
    "ci-": "ci",
    "devops-": "ci",
    "install-script": "ci",
    "install-scripts": "ci",
    # Skills domain
    "skills-": "skills",
    "skill-activation": "skills",
    "skillcreator-": "skills",
    "SkillForge-": "skills",
    "slashcommand": "skills",
    # Git domain
    "git-hooks": "git",
    "git-": "git",
    "merge-resolver": "git",
    # Security domain
    "security-": "security",
    "cwe-": "security",
    "owasp-": "security",
    "threat-modeling": "security",
    # Workflow domain
    "workflow-": "workflow",
    # Validation domain
    "validation-": "validation",
    "verify-": "validation",
    # GitHub domain
    "github-": "github",
    "gh-extensions": "github",
    "gh-": "github",
    "graphql-": "github",
    # Design domain
    "design-": "design",
    "coupling-types": "design",
    # ADR domain
    "adr-": "adr",
    "adrs-": "adr",
    # PowerShell domain
    "powershell-": "powershell",
    "pester-": "powershell",
    # jq domain
    "jq-": "jq",
    # Cost domain
    "cost-": "cost",
    "artifact-token": "cost",
    # Orchestration domain
    "orchestration-": "orchestration",
    "coordination-": "orchestration",
    # Session domain
    "session-": "session",
    "init-": "session",
    "logging-": "session",
    "recovery-": "session",
    "changelog-": "session",
    # Copilot domain
    "copilot-": "copilot",
    "awesome-copilot": "copilot",
    # Protocol domain
    "protocol-": "protocol",
    # Implementation domain
    "implementation-": "implementation",
    "execution-": "implementation",
    # Documentation domain
    "documentation-": "documentation",
    # Testing domain
    "testing-": "testing",
    "test-citation": "testing",
    # Serena domain
    "serena-": "serena",
    # Claude domain
    "claude-": "claude",
    # Architecture domain
    "architecture-": "architecture",
    "c4-model": "architecture",
    # Retrospective domain
    "retrospective-": "retrospective",
    "reflect-observations": "retrospective",
    "learnings-": "retrospective",
    # Quality domain
    "quality-": "quality",
    "dod-": "quality",
    "code-smells": "quality",
    "code-style": "quality",
    # Agent workflow domain
    "agent-workflow": "agent-workflow",
    "agent-generation": "agent-workflow",
    "agentworkflow": "agent-workflow",
    "agentskills": "agent-workflow",
    # Planning domain
    "planning-": "planning",
    "scope-": "planning",
    "requirement": "planning",
    "roadmap-": "planning",
    # CodeRabbit domain
    "coderabbit-": "coderabbit",
    "bot-config": "coderabbit",
    # QA domain
    "qa-": "qa",
    # Labeler domain
    "labeler-": "labeler",
    # Bash domain
    "bash-": "bash",
    # Autonomous domain
    "autonomous-": "autonomous",
    # Analysis domain
    "analysis-": "analysis",
    # Utilities domain
    "utilities-": "utilities",
    "utility-": "utilities",
    # Patterns domain
    "pattern-": "patterns",
    "patterns-": "patterns",
    "edit-": "patterns",
    # Memory domain
    "memory-": "memory",
    "context-engineering": "memory",
    "context-inference": "memory",
    "forgetful-": "memory",
    "phase2a-memory": "memory",
    # Gemini domain
    "gemini-": "gemini",
    # Creator domain
    "creator-": "creator",
    # Prompting domain
    "prompt-": "prompting",
    "prompting-": "prompting",
    # Error handling domain
    "error-handling": "error-handling",
    # Governance domain
    "governance-": "governance",
    "debate-": "governance",
    "consensus-": "governance",
    # Process domain
    "process-": "process",
    # User preferences
    "user-": "user-preferences",
    # Project domain
    "project-": "project",
    "codebase-": "project",
    "epic-": "project",
    "phase2-": "project",
    "phase2a-status": "project",
    "phase4-": "project",
    "prd-": "project",
    "three-platform": "project",
    # Knowledge domain (engineering concepts, laws, frameworks)
    "antifragility": "knowledge",
    "backpressure-": "knowledge",
    "bounded-contexts": "knowledge",
    "boy-scout-": "knowledge",
    "buy-vs-build": "knowledge",
    "cap-theorem": "knowledge",
    "chaos-engineering": "knowledge",
    "chestertons-fence": "knowledge",
    "conways-law": "knowledge",
    "critical-path": "knowledge",
    "cynefin-": "knowledge",
    "ddd-": "knowledge",
    "expand-contract": "knowledge",
    "fallacies-": "knowledge",
    "feature-toggles": "knowledge",
    "galls-law": "knowledge",
    "hyrums-law": "knowledge",
    "idempotency-": "knowledge",
    "inversion-thinking": "knowledge",
    "law-of-demeter": "knowledge",
    "lifecycle-modeling": "knowledge",
    "lindy-effect": "knowledge",
    "ooda-loop": "knowledge",
    "paved-roads": "knowledge",
    "platform-engineering": "knowledge",
    "poka-yoke": "knowledge",
    "pre-mortems": "knowledge",
    "products-over-projects": "knowledge",
    "resilience-patterns": "knowledge",
    "rumsfeld-matrix": "knowledge",
    "second-order-thinking": "knowledge",
    "second-system-effect": "knowledge",
    "service-reliability": "knowledge",
    "shearing-layers": "knowledge",
    "slsa-supply": "knowledge",
    "slo-sli-sla": "knowledge",
    "sociotechnical-": "knowledge",
    "staff-engineer": "knowledge",
    "strangler-fig": "knowledge",
    "systems-archetypes": "knowledge",
    "team-topologies": "knowledge",
    "technical-debt-": "knowledge",
    "three-horizons": "knowledge",
    "tradeoff-thinking": "knowledge",
    "wardley-mapping": "knowledge",
    "yagni-principle": "knowledge",
    # Debugging domain
    "debugging-": "ci",
    # Maintenance domain
    "maintenance-": "process",
    # Tracking domain
    "tracking-": "process",
    # Monitoring domain
    "monitoring-": "ci",
    # Additional specific file routes (reduce general bucket)
    "deployment-": "ci",
    "audit-": "quality",
    "performance-": "quality",
    "pre-commit-hook": "git",
    "enforcement-patterns": "patterns",
    "verification-003": "validation",
    "passive-context": "memory",
    "retrieval-led-reasoning": "memory",
    "principal-engineering": "knowledge",
    "refactoring-": "quality",
    "organization-": "project",
    "index-selection": "memory",
    "migrations-at-scale": "knowledge",
    "anthropic-legal": "governance",
    "artifacts-005": "cost",
    "automation-priorities": "planning",
    "feat-learning": "skills",
    "focus-001": "planning",
    "historical-reference": "governance",
    "issue-998": "testing",
    "markdown-parsing": "documentation",
    "research-agent": "project",
    "rootcause-": "patterns",
    "skepticism-": "quality",
    "suggested-commands": "skills",
    "task-completion": "quality",
    "tool-usage": "skills",
    "trust-damage": "governance",
    "velocity-analysis": "planning",
    "recurring-frustrations": "quality",
    "environment-observations": "ci",
    "critique-milestone": "planning",
}


def is_index_file(name: str) -> bool:
    """Check if a file is an index (stays at top level)."""
    stem = name.removesuffix(".md")
    return stem.endswith("-index")


def classify_file(name: str) -> str | None:
    """Return subdirectory name for a file, or None to keep at top level."""
    if name in TOP_LEVEL_KEEP:
        return None
    if is_index_file(name):
        return None

    stem = name.removesuffix(".md")

    # Try specific prefix mappings (longest match first)
    for prefix, subdir in sorted(PREFIX_TO_DIR.items(), key=lambda x: -len(x[0])):
        if stem.startswith(prefix):
            return subdir

    # Fallback: use first word as group
    first_word = stem.split("-")[0]
    return first_word


def plan_moves(memories_dir: Path) -> dict[str, list[str]]:
    """Plan which files go where. Returns {subdir: [filenames]}."""
    groups: dict[str, list[str]] = defaultdict(list)

    for f in sorted(memories_dir.iterdir()):
        if not f.is_file() or not f.name.endswith(".md"):
            continue
        subdir = classify_file(f.name)
        if subdir is not None:
            groups[subdir].append(f.name)

    # Consolidate small groups into "general"
    final: dict[str, list[str]] = defaultdict(list)
    for subdir, files in groups.items():
        if len(files) < MIN_GROUP_SIZE:
            final["general"].extend(files)
        else:
            final[subdir] = files

    return dict(final)


def update_index_references(
    memories_dir: Path, move_map: dict[str, str]
) -> list[str]:
    """Update index files to include subdirectory path prefixes.

    Returns list of updated index files.
    """
    updated = []

    for f in sorted(memories_dir.iterdir()):
        if not f.is_file() or not is_index_file(f.name):
            continue

        content = f.read_text(encoding="utf-8")
        original = content

        for old_name, subdir in move_map.items():
            stem = old_name.removesuffix(".md")
            # Match memory references like `memory-name` or `memory-name.md`
            # in markdown links, table cells, backtick references
            # Pattern: the stem as a standalone reference (not already prefixed)
            escaped = re.escape(stem)
            # Replace bare references with subdir-prefixed ones
            # But don't double-prefix if already contains /
            pattern = rf"(?<!/){escaped}(?=\.md|\b|`|\]|\|)"
            replacement = f"{subdir}/{stem}"
            content = re.sub(pattern, replacement, content)

        if content != original:
            f.write_text(content, encoding="utf-8")
            updated.append(f.name)

    return updated


def execute_moves(
    memories_dir: Path, plan: dict[str, list[str]], *, dry_run: bool = False
) -> dict[str, str]:
    """Execute file moves. Returns {filename: subdir} for all moved files."""
    move_map = {}

    for subdir, files in sorted(plan.items()):
        target_dir = memories_dir / subdir
        if not dry_run:
            target_dir.mkdir(exist_ok=True)

        for fname in files:
            src = memories_dir / fname
            dst = target_dir / fname
            move_map[fname] = subdir
            if dry_run:
                print(f"  [DRY RUN] {fname} -> {subdir}/{fname}")
            else:
                shutil.move(str(src), str(dst))

    return move_map


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    # Find repo root
    repo_root = Path.cwd()
    memories_dir = repo_root / MEMORIES_DIR
    if not memories_dir.exists():
        print(f"ERROR: {memories_dir} not found. Run from repo root.")
        return 1

    # Count current state
    all_files = [f for f in memories_dir.iterdir() if f.is_file() and f.name.endswith(".md")]
    index_files = [f for f in all_files if is_index_file(f.name)]
    top_level_keep = [f for f in all_files if f.name in TOP_LEVEL_KEEP]

    print("=== Serena Memory Restructuring ===")
    print(f"Total files: {len(all_files)}")
    print(f"Index files (keep at top): {len(index_files)}")
    print(f"Special files (keep at top): {len(top_level_keep)}")
    print(f"Files to move: {len(all_files) - len(index_files) - len(top_level_keep)}")
    print()

    # Plan
    plan = plan_moves(memories_dir)

    total_moving = sum(len(files) for files in plan.values())
    print(f"Subdirectories to create: {len(plan)}")
    print(f"Files to move: {total_moving}")
    print()

    for subdir, files in sorted(plan.items()):
        print(f"  {subdir}/ ({len(files)} files)")

    print()

    if dry_run:
        print("[DRY RUN] No files will be moved.")
        print()
        execute_moves(memories_dir, plan, dry_run=True)
        return 0

    # Execute moves
    print("Moving files...")
    move_map = execute_moves(memories_dir, plan)
    print(f"Moved {len(move_map)} files into {len(plan)} subdirectories.")
    print()

    # Update index references
    print("Updating index file references...")
    updated = update_index_references(memories_dir, move_map)
    print(f"Updated {len(updated)} index files: {', '.join(updated)}")
    print()

    # Final count
    remaining_top = [
        f for f in memories_dir.iterdir()
        if f.is_file() and f.name.endswith(".md")
    ]
    subdirs = [d for d in memories_dir.iterdir() if d.is_dir()]
    print("=== Result ===")
    print(f"Top-level files: {len(remaining_top)}")
    print(f"Subdirectories: {len(subdirs)}")
    print(f"list_memories will now show: {len(remaining_top)} entries (was {len(all_files)})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
