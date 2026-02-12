#!/usr/bin/env python3
"""Improve graph density of Serena memories by adding Related sections.

Analyzes memory files and adds Related sections based on:
- Naming patterns (shared prefixes like security-, git-, ci-)
- Topic domain grouping (files with same prefix are related)
- Index file discovery (links to domain-specific index files)

Index files (*-index.md) are excluded from Related section addition
per ADR-017 requirement for pure lookup table format (token efficiency).

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (processing failure)
    2 - Configuration error (invalid path)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any


def _find_project_root(fallback_dir: Path | None = None) -> Path:
    """Find project root via git or directory traversal."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except FileNotFoundError:
        pass

    search = fallback_dir or Path(__file__).resolve().parent
    while search != search.parent:
        if (search / ".git").exists():
            return search
        search = search.parent
    raise SystemExit("Could not find project root (no .git directory found)")


def _validate_path_within_project(
    memories_path: str, project_root: Path
) -> Path:
    """Validate that a path is within the project root (CWE-22 mitigation)."""
    resolved = Path(memories_path).resolve()
    root_resolved = project_root.resolve()
    root_prefix = str(root_resolved) + "/"
    if not (str(resolved).startswith(root_prefix) or resolved == root_resolved):
        raise SystemExit(
            f"Security: MemoriesPath must be within project directory. "
            f"Provided: {resolved}, Project root: {root_resolved}"
        )
    return resolved


# Domain patterns for grouping related memories.
# More specific prefixes MUST come before shorter ones (first-match-wins).
DOMAIN_PATTERNS: OrderedDict[str, str] = OrderedDict([
    ("adr-", "Architecture Decision Records"),
    ("agent-workflow-", "Agent Workflow"),
    ("analysis-", "Analysis Patterns"),
    ("architecture-", "Architecture"),
    ("autonomous-", "Autonomous Execution"),
    ("bash-integration-", "Bash Integration"),
    ("ci-infrastructure-", "CI Infrastructure"),
    ("claude-", "Claude Code"),
    ("coderabbit-", "CodeRabbit"),
    ("copilot-", "GitHub Copilot"),
    ("creator-", "Skill Creator"),
    ("design-", "Design Patterns"),
    ("devops-", "DevOps"),
    ("documentation-", "Documentation"),
    ("gh-extensions-", "GitHub Extensions"),
    ("git-hooks-", "Git Hooks"),
    ("git-", "Git Operations"),
    ("github-cli-", "GitHub CLI"),
    ("github-", "GitHub"),
    ("graphql-", "GraphQL"),
    ("implementation-", "Implementation"),
    ("jq-", "JQ"),
    ("labeler-", "GitHub Labeler"),
    ("linting-", "Linting"),
    ("memory-", "Memory Management"),
    ("merge-resolver-", "Merge Resolution"),
    ("orchestration-", "Orchestration"),
    ("parallel-", "Parallel Execution"),
    ("pattern-", "Patterns"),
    ("pester-", "Pester Testing"),
    ("planning-", "Planning"),
    ("powershell-", "PowerShell"),
    ("pr-comment-", "PR Comments"),
    ("pr-review-", "PR Review"),
    ("pr-", "Pull Request"),
    ("protocol-", "Session Protocol"),
    ("qa-", "Quality Assurance"),
    ("quality-", "Quality"),
    ("retrospective-", "Retrospective"),
    ("security-", "Security"),
    ("session-init-", "Session Initialization"),
    ("session-", "Session"),
    ("skills-", "Skills Index"),
    ("testing-", "Testing"),
    ("triage-", "Triage"),
    ("utilities-", "Utilities"),
    ("validation-", "Validation"),
    ("workflow-", "Workflow Patterns"),
])


def _find_related_files(
    base_name: str,
    all_memory_files: list[Path],
    memory_names: dict[str, str],
) -> list[str]:
    """Find related files based on naming patterns and index lookup."""
    related: list[str] = []

    for prefix in DOMAIN_PATTERNS:
        if base_name.startswith(prefix):
            domain_files = [
                f.stem
                for f in all_memory_files
                if f.stem.startswith(prefix) and f.stem != base_name
            ]
            related.extend(domain_files[:5])
            break

    domain_name = base_name.split("-")[0]
    index_file = f"{domain_name}s-index"
    if index_file in memory_names and base_name != index_file:
        related.append(index_file)

    seen: set[str] = set()
    unique: list[str] = []
    for name in related:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique[:5]


def process_files(
    memories_path: Path,
    files_to_process: list[Path] | None = None,
    dry_run: bool = False,
    output_json: bool = False,
) -> dict:
    """Process memory files and add Related sections.

    Returns statistics dict with FilesProcessed, FilesModified,
    RelationshipsAdded, Errors.
    """
    all_memory_files = sorted(memories_path.glob("*.md"))

    memory_names: dict[str, str] = {}
    for f in all_memory_files:
        memory_names[f.stem] = str(f)

    if files_to_process:
        normalized = {f.resolve() for f in files_to_process}
        target_files = [f for f in all_memory_files if f.resolve() in normalized]
    else:
        target_files = all_memory_files

    if not output_json:
        print(f"Analyzing {len(target_files)} memory files...")

    stats: dict[str, Any] = {
        "FilesProcessed": 0,
        "FilesModified": 0,
        "RelationshipsAdded": 0,
        "Errors": [],
    }

    for file_path in target_files:
        stats["FilesProcessed"] += 1
        try:
            base_name = file_path.stem

            if base_name.endswith("-index"):
                if not output_json:
                    print(f"Skipping index file (ADR-017): {file_path.name}")
                continue

            content = file_path.read_text(encoding="utf-8")
            if not content:
                continue

            has_related = bool(re.search(r"^## Related", content, re.MULTILINE))

            related_files = _find_related_files(
                base_name, all_memory_files, memory_names
            )

            if not has_related and related_files:
                related_section = "\n## Related\n\n"
                for rf in related_files:
                    related_section += f"- [{rf}]({rf}.md)\n"

                new_content = content.rstrip() + "\n" + related_section

                if not dry_run:
                    file_path.write_text(new_content, encoding="utf-8")
                    if not output_json:
                        print(f"Added Related section to: {file_path.name}")
                else:
                    if not output_json:
                        print(
                            f"[DRY RUN] Would add Related section to: {file_path.name}"
                        )

                stats["FilesModified"] += 1
                stats["RelationshipsAdded"] += len(related_files)

        except Exception as exc:
            msg = f"Error processing {file_path.name}: {exc}"
            stats["Errors"].append(msg)
            if not output_json:
                print(f"WARNING: {msg}", file=sys.stderr)

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Improve graph density of Serena memories by adding Related sections.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files.",
    )
    parser.add_argument(
        "--memories-path",
        help="Path to memories directory. Defaults to .serena/memories.",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help="Specific files to process. Defaults to all *.md files.",
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output machine-parseable JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--skip-path-validation",
        action="store_true",
        help="Skip CWE-22 path validation (for testing only).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    project_root = _find_project_root()

    if args.memories_path:
        if args.skip_path_validation:
            memories_path = Path(args.memories_path).resolve()
        else:
            memories_path = _validate_path_within_project(
                args.memories_path, project_root
            )
    else:
        memories_path = project_root / ".serena" / "memories"

    files_to_process = [Path(f) for f in args.files] if args.files else None

    stats = process_files(
        memories_path,
        files_to_process,
        dry_run=args.dry_run,
        output_json=args.output_json,
    )

    if args.output_json:
        print(json.dumps(stats, separators=(",", ":")))
    else:
        print("\n=== Summary ===")
        print(f"Files updated: {stats['FilesModified']}")
        print(f"Relationships added: {stats['RelationshipsAdded']}")
        if args.dry_run:
            print("\nThis was a dry run. Use without --dry-run to apply changes.")

    return 1 if stats["Errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
