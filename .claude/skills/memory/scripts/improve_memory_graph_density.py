#!/usr/bin/env python3
"""Improve graph density of Serena memories by adding Related sections.

Analyzes memory files and adds Related sections based on naming patterns
and topic domain grouping. Index files (*-index.md) are excluded per
ADR-017 requirement for pure lookup table format (token efficiency).

Exit Codes:
    0  - Success: Processing completed
    1  - Error: Git repository or path error

See: ADR-035 Exit Code Standardization
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path


# Domain patterns. More specific prefixes MUST come before shorter ones
# because matching breaks on first match.
DOMAIN_PATTERNS = OrderedDict([
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


def get_project_root() -> str:
    """Find project root via git or directory traversal."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent

    print("Could not find project root", file=sys.stderr)
    sys.exit(1)


def validate_path_containment(path: str, project_root: str) -> bool:
    """CWE-22: Ensure path is within project root."""
    resolved = os.path.realpath(path)
    root = os.path.realpath(project_root)
    root_with_sep = root.rstrip(os.sep) + os.sep
    return resolved.startswith(root_with_sep) or resolved == root


def find_related_files(
    base_name: str,
    all_memory_files: list[Path],
    memory_names: dict[str, str],
) -> list[str]:
    """Find related files based on naming pattern."""
    related: list[str] = []

    for pattern in DOMAIN_PATTERNS:
        if base_name.startswith(pattern):
            domain_files = [
                f.stem for f in all_memory_files
                if f.stem.startswith(pattern) and f.stem != base_name
            ][:5]
            related.extend(domain_files)
            break

    domain_name = base_name.split("-")[0]
    index_file = f"{domain_name}s-index"
    if index_file in memory_names and base_name != index_file:
        related.append(index_file)

    seen: set[str] = set()
    unique: list[str] = []
    for r in related:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique[:5]


def process_files(
    memories_path: Path,
    files_to_process: list[Path] | None,
    output_json: bool,
    dry_run: bool,
) -> dict:
    """Process memory files and add Related sections."""
    all_memory_files = sorted(memories_path.glob("*.md"))

    if files_to_process:
        normalized = {os.path.realpath(str(f)) for f in files_to_process}
        memory_files = [
            f for f in all_memory_files
            if os.path.realpath(str(f)) in normalized
        ]
    else:
        memory_files = all_memory_files

    memory_names: dict[str, str] = {}
    for f in all_memory_files:
        memory_names[f.stem] = str(f)

    stats = {
        "FilesProcessed": 0,
        "FilesModified": 0,
        "RelationshipsAdded": 0,
        "Errors": [],
    }

    if not output_json:
        print(f"Analyzing {len(memory_files)} memory files...")

    for file_path in memory_files:
        stats["FilesProcessed"] += 1

        try:
            base_name = file_path.stem

            if base_name.endswith("-index"):
                if not output_json:
                    print(f"Skipping index file (ADR-017): {file_path.name}")
                continue

            content = file_path.read_text(encoding="utf-8")
            if not content.strip():
                continue

            has_related = bool(re.search(r"(?m)^## Related", content))

            related_files = find_related_files(base_name, all_memory_files, memory_names)

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
                        print(f"[DRY RUN] Would add Related section to: {file_path.name}")

                stats["FilesModified"] += 1
                stats["RelationshipsAdded"] += len(related_files)

        except Exception as e:
            error_msg = f"Error processing {file_path.name}: {e}"
            stats["Errors"].append(error_msg)
            if not output_json:
                print(f"Warning: {error_msg}", file=sys.stderr)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Improve graph density of Serena memories."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--memories-path", type=str, default="")
    parser.add_argument("--files-to-process", nargs="*", default=None)
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--skip-path-validation", action="store_true")
    args = parser.parse_args()

    project_root = get_project_root()

    if args.memories_path:
        if not args.skip_path_validation:
            if not validate_path_containment(args.memories_path, project_root):
                print(
                    "Security: MemoriesPath must be within project directory.",
                    file=sys.stderr,
                )
                sys.exit(1)
        memories_path = Path(os.path.realpath(args.memories_path))
    else:
        memories_path = Path(project_root) / ".serena" / "memories"

    files_to_process = None
    if args.files_to_process:
        files_to_process = [Path(f) for f in args.files_to_process]

    stats = process_files(memories_path, files_to_process, args.output_json, args.dry_run)

    if args.output_json:
        print(json.dumps(stats))
    else:
        print(f"\n=== Summary ===")
        print(f"Files updated: {stats['FilesModified']}")
        print(f"Relationships added: {stats['RelationshipsAdded']}")
        if args.dry_run:
            print("\nThis was a dry run. Use without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
