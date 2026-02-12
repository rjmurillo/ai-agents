#!/usr/bin/env python3
"""Split bundled skill files into individual files per ADR-017.

Reads bundled skill files containing multiple skills and splits them into
individual files following the naming convention: domain-###-topic.md

EXIT CODES:
  0  - Success
  1  - Error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BUNDLED_FILES = [
    "documentation-fallback-pattern.md",
    "documentation-migration-search.md",
    "documentation-self-contained.md",
    "implementation-test-discovery.md",
    "iteration-5-checkpoint-skills.md",
    "labeler-matcher-types.md",
    "labeler-negation-patterns.md",
    "phase3-consistency-skills.md",
    "phase4-handoff-validation-skills.md",
    "planning-self-contained.md",
    "pr-review-bot-triage.md",
    "pr-review-false-positives.md",
    "pr-review-noise-skills.md",
    "security-defensive-coding.md",
    "security-review-enforcement.md",
    "security-toctou-defense.md",
    "skills-agent-workflow-phase3.md",
    "skills-analysis.md",
    "skills-architecture.md",
    "skills-definition-of-done.md",
    "skills-design.md",
    "skills-edit.md",
    "skills-execution.md",
    "skills-github-actions-labeler.md",
    "skills-governance.md",
    "skills-implementation.md",
    "skills-jq-json-parsing.md",
    "skills-maintenance.md",
    "skills-orchestration.md",
    "skills-planning.md",
    "skills-powershell.md",
    "skills-qa.md",
    "skills-review.md",
    "skills-security.md",
    "skills-session-initialization.md",
    "skills-utilities.md",
    "skills-validation.md",
]

SKILL_PATTERN = re.compile(r"(?m)^## (Skill-([A-Za-z\-]+)-(\d+)):\s*([^\n]+)")


def process_bundled_file(file_path: Path, output_dir: Path, dry_run: bool) -> int:
    content = file_path.read_text(encoding="utf-8")
    matches = list(SKILL_PATTERN.finditer(content))

    if not matches:
        print(f"  No skills found in {file_path.name}")
        return 0

    print(f"  Found {len(matches)} skills")
    count = 0

    for i, match in enumerate(matches):
        domain = match.group(2).lower()
        number = match.group(3).zfill(3)
        statement = match.group(4).strip()

        start_index = match.start()
        if i < len(matches) - 1:
            end_index = matches[i + 1].start()
        else:
            related = re.search(r"(?m)^## Related", content[start_index:])
            end_index = start_index + related.start() if related else len(content)

        skill_content = content[start_index:end_index].strip()

        topic = re.sub(r"[^a-zA-Z0-9\s]", "", statement)
        topic = re.sub(r"\s+", "-", topic).strip("-").lower()
        if len(topic) > 50:
            topic = topic[:50].rstrip("-")

        output_file = f"{domain}-{number}-{topic}.md"
        output_path = output_dir / output_file

        domain_title = domain.replace("-", " ").title()
        topic_title = topic.replace("-", " ").title()
        file_header = f"# {domain_title}: {topic_title}\n\n"
        final_content = file_header + skill_content

        if dry_run:
            print(f"    Would create: {output_file}")
        else:
            output_path.write_text(final_content, encoding="utf-8")
            print(f"    Created: {output_file}")
        count += 1

    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Split bundled skill files into individual files")
    parser.add_argument("--bundled-files-dir", type=Path, default=Path(".serena/memories"))
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args(argv)

    total_skills = 0
    files_to_delete: list[Path] = []

    for filename in BUNDLED_FILES:
        file_path = args.bundled_files_dir / filename
        if not file_path.exists():
            print(f"WARNING: File not found: {file_path}")
            continue

        print(f"Processing: {filename}")
        count = process_bundled_file(file_path, args.bundled_files_dir, args.dry_run)
        total_skills += count
        files_to_delete.append(file_path)

    print(f"\nSummary:")
    print(f"  Total bundled files processed: {len(BUNDLED_FILES)}")
    print(f"  Total skills extracted: {total_skills}")

    if not args.dry_run:
        print("\nDeleting bundled files...")
        for file_path in files_to_delete:
            if file_path.exists():
                file_path.unlink()
                print(f"  Deleted: {file_path.name}")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
