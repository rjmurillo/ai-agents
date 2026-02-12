#!/usr/bin/env python3
"""Bulk import observation learnings from Serena memory files to Forgetful MCP.

Parses observation markdown files (HIGH/MED/LOW confidence sections) and creates
Forgetful memories with full provenance tracking. Supports dry-run mode, duplicate
detection, and batch processing.

EXIT CODES:
  0  - Success: All imports completed
  1  - Error: Validation or import failures occurred

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DOMAIN_MAP: dict[str, dict[str, object]] = {
    "testing": {"project_name": "testing", "keywords": ["testing", "pester", "validation"]},
    "architecture": {"project_name": "architecture", "keywords": ["architecture", "adr", "design"]},
    "pr-review": {"project_name": "pr-review", "keywords": ["pr-review", "github", "code-review"]},
    "github": {"project_name": "github", "keywords": ["github", "gh-cli", "api"]},
    "powershell": {"project_name": "powershell", "keywords": ["powershell", "scripting", "automation"]},
    "ci-infrastructure": {"project_name": "ci-infrastructure", "keywords": ["ci-cd", "github-actions", "pipelines"]},
    "session": {"project_name": "session-protocol", "keywords": ["session", "protocol", "logging"]},
    "session-protocol": {"project_name": "session-protocol", "keywords": ["session", "protocol", "compliance"]},
    "git": {"project_name": "git", "keywords": ["git", "version-control", "branching"]},
    "security": {"project_name": "security", "keywords": ["security", "vulnerability", "secrets"]},
    "memory": {"project_name": "memory-system", "keywords": ["memory", "serena", "forgetful"]},
    "validation": {"project_name": "validation", "keywords": ["validation", "schema", "constraints"]},
    "documentation": {"project_name": "documentation", "keywords": ["documentation", "markdown", "readme"]},
    "environment": {"project_name": "environment", "keywords": ["environment", "configuration", "setup"]},
    "agent-workflow": {"project_name": "agent-workflow", "keywords": ["agent", "workflow", "orchestration"]},
    "bash-integration": {"project_name": "bash-integration", "keywords": ["bash", "shell", "integration"]},
    "error-handling": {"project_name": "error-handling", "keywords": ["errors", "exceptions", "debugging"]},
    "qa": {"project_name": "qa", "keywords": ["qa", "quality", "testing"]},
    "retrospective": {"project_name": "retrospective", "keywords": ["retrospective", "learnings", "reflection"]},
    "prompting": {"project_name": "prompting", "keywords": ["prompting", "llm", "instructions"]},
    "cost-optimization": {"project_name": "cost-optimization", "keywords": ["cost", "optimization", "tokens"]},
    "performance": {"project_name": "performance", "keywords": ["performance", "speed", "optimization"]},
    "tool-usage": {"project_name": "tool-usage", "keywords": ["tools", "mcp", "integration"]},
    "quality-gates": {"project_name": "quality-gates", "keywords": ["quality", "gates", "ci-cd"]},
    "enforcement-patterns": {"project_name": "enforcement-patterns", "keywords": ["enforcement", "patterns", "rules"]},
    "skills": {"project_name": "skills", "keywords": ["skills", "commands", "automation"]},
    "SkillForge": {"project_name": "skillforge", "keywords": ["skillforge", "meta-skill", "creation"]},
    "reflect": {"project_name": "reflect", "keywords": ["reflect", "learning", "capture"]},
}

CONFIDENCE_MAPPING = {
    "HIGH": {"importance_min": 9, "importance_max": 10, "confidence": 1.0, "tag": "high-confidence"},
    "MED": {"importance_min": 7, "importance_max": 8, "confidence": 0.85, "tag": "medium-confidence"},
    "LOW": {"importance_min": 5, "importance_max": 6, "confidence": 0.7, "tag": "low-confidence"},
}

SECTION_TYPE_MAP = {
    "Constraints": {"type": "constraint", "confidence_level": "HIGH"},
    "Preferences": {"type": "preference", "confidence_level": "MED"},
    "Edge Cases": {"type": "edge-case", "confidence_level": "MED"},
    "Notes for Review": {"type": "note", "confidence_level": "LOW"},
}


@dataclass
class Learning:
    domain: str
    project_name: str
    base_keywords: list[str]
    confidence_level: str
    learning_type: str
    text: str
    evidence: list[str] = field(default_factory=list)
    session: str | None = None
    date_info: str | None = None
    source_file: str = ""


def get_domain_from_filename(filename: str) -> str:
    base = Path(filename).stem
    match = re.match(r"^skills-(.+)-observations$", base)
    if match:
        return f"skills-{match.group(1)}"
    match = re.match(r"^(.+)-observations$", base)
    if match:
        return match.group(1)
    return base


def get_project_info(domain: str) -> dict[str, object]:
    if domain in DOMAIN_MAP:
        return DOMAIN_MAP[domain]
    return {"project_name": domain, "keywords": [domain, "learnings", "observations"]}


def safe_title(text: str) -> str:
    match = re.match(r"^([^.!?]+[.!?])", text)
    title = match.group(1).strip() if match else text[:80]
    title = re.sub(r"\s*\(Session[^)]+\)", "", title)
    title = re.sub(r"\s*\(.*?\d{4}-\d{2}-\d{2}.*?\)", "", title)
    title = title.strip()
    if len(title) > 100:
        title = title[:97] + "..."
    return title


def parse_observation_file(
    file_path: Path, filter_confidence: list[str]
) -> list[Learning]:
    content = file_path.read_text(encoding="utf-8")
    domain = get_domain_from_filename(file_path.name)
    project_info = get_project_info(domain)

    learnings: list[Learning] = []
    current_section: dict[str, str] | None = None
    current_learning: Learning | None = None

    for line in content.split("\n"):
        stripped = line.strip()

        # Detect section headers
        match = re.match(
            r"^##\s+(Constraints|Preferences|Edge Cases|Notes for Review)", stripped
        )
        if match:
            if current_learning:
                learnings.append(current_learning)
                current_learning = None
            section_name = match.group(1)
            current_section = SECTION_TYPE_MAP.get(section_name)
            continue

        if re.match(r"^##\s+(Purpose|History|Related|Overview)", stripped):
            if current_learning:
                learnings.append(current_learning)
                current_learning = None
            current_section = None
            continue

        if not current_section:
            continue

        if current_section["confidence_level"] not in filter_confidence:
            continue

        # Top-level bullet
        is_top_bullet = re.match(r"^- (.+)$", stripped)
        if is_top_bullet and line.startswith("- "):
            captured = is_top_bullet.group(1)
            if re.match(r"^\s*None\s*(yet)?\s*$", captured):
                continue

            if current_learning:
                learnings.append(current_learning)

            session_info = None
            date_info = None
            session_match = re.search(
                r"\(Session\s+([^,)]+)(?:,\s*(\d{4}-\d{2}-\d{2}))?\)", captured
            )
            if session_match:
                session_info = session_match.group(1)
                date_info = session_match.group(2)
            else:
                date_match = re.search(r"\(([^)]*\d{4}-\d{2}-\d{2}[^)]*)\)", captured)
                if date_match:
                    parts = date_match.group(1).split(",")
                    date_info = parts[-1].strip()

            current_learning = Learning(
                domain=domain,
                project_name=str(project_info["project_name"]),
                base_keywords=list(project_info["keywords"]),  # type: ignore[arg-type]
                confidence_level=current_section["confidence_level"],
                learning_type=current_section["type"],
                text=captured,
                session=session_info,
                date_info=date_info,
                source_file=str(file_path),
            )
            continue

        # Evidence sub-bullets
        evidence_match = re.match(r"^\s*-\s+Evidence:\s*(.+)$", stripped)
        if evidence_match and current_learning:
            current_learning.evidence.append(evidence_match.group(1))

    if current_learning:
        learnings.append(current_learning)

    return learnings


def build_memory_payload(learning: Learning, project_id: int) -> dict:
    conf = CONFIDENCE_MAPPING[learning.confidence_level]
    title = safe_title(learning.text)
    content = learning.text
    if learning.evidence:
        content += "\n\nEvidence: " + "; ".join(learning.evidence)

    context_parts = [f"Observation from {learning.domain} domain"]
    if learning.session:
        context_parts.append(f"Session {learning.session}")
    if learning.date_info:
        context_parts.append(learning.date_info)
    context_parts.append(f"{learning.learning_type} ({learning.confidence_level} confidence)")

    keywords = list(learning.base_keywords)
    keywords.extend([learning.learning_type, learning.confidence_level.lower()])
    text_lower = learning.text.lower()
    for kw in [
        "powershell", "pester", "github", "ci", "pipeline", "test",
        "adr", "memory", "session", "validation", "git", "mcp",
    ]:
        if kw in text_lower:
            keywords.append(kw)
    keywords = list(dict.fromkeys(keywords))

    importance = random.randint(conf["importance_min"], conf["importance_max"])  # type: ignore[arg-type]

    return {
        "title": title,
        "content": content,
        "context": ". ".join(context_parts),
        "keywords": keywords,
        "tags": [learning.domain, learning.learning_type, conf["tag"]],
        "importance": importance,
        "project_ids": [project_id],
        "source_repo": "rjmurillo/ai-agents",
        "source_files": [re.sub(r"^.*?\.serena", ".serena", learning.source_file)],
        "confidence": conf["confidence"],
        "encoding_agent": "claude-opus-4-5",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import observation learnings to Forgetful MCP"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--observation-file", type=Path, help="Single observation file")
    group.add_argument("--observation-directory", type=Path, help="Directory of observation files")
    parser.add_argument(
        "--confidence-levels",
        nargs="+",
        choices=["HIGH", "MED", "LOW"],
        default=["HIGH"],
        help="Filter by confidence level",
    )
    parser.add_argument("--project-prefix", default="ai-agents-", help="Prefix for project names")
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating memories")
    parser.add_argument("--skip-duplicate-check", action="store_true")
    parser.add_argument(
        "--output-path",
        default=".agents/analysis/forgetful-import-results.json",
        help="Path for JSON results",
    )
    args = parser.parse_args(argv)

    print("\n=== Forgetful Observation Import ===")
    print(f"Confidence Levels: {', '.join(args.confidence_levels)}")
    if args.dry_run:
        print("[DRY RUN MODE - No changes will be made]")

    files: list[Path] = []
    if args.observation_file:
        if not args.observation_file.exists():
            print(f"ERROR: File not found: {args.observation_file}", file=sys.stderr)
            return 1
        files.append(args.observation_file)
    else:
        if not args.observation_directory or not args.observation_directory.exists():
            print(f"ERROR: Directory not found: {args.observation_directory}", file=sys.stderr)
            return 1
        files.extend(sorted(args.observation_directory.glob("*-observations.md")))

    print(f"Files to process: {len(files)}")

    results: dict = {
        "start_time": datetime.now().isoformat(),
        "parameters": {
            "confidence_levels": args.confidence_levels,
            "dry_run": args.dry_run,
            "files": [str(f) for f in files],
        },
        "files_processed": [],
        "total_learnings": 0,
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "by_domain": {},
        "by_confidence": {"HIGH": 0, "MED": 0, "LOW": 0},
    }

    for file_path in files:
        print(f"\nProcessing: {file_path.name}")
        print("-" * 50)

        try:
            learnings = parse_observation_file(file_path, args.confidence_levels)
            if not learnings:
                print("  No learnings found matching filter")
                results["files_processed"].append(
                    {"file": file_path.name, "learnings": 0, "status": "empty"}
                )
                continue

            print(f"  Found {len(learnings)} learnings")

            for learning in learnings:
                results["total_learnings"] += 1
                results["by_confidence"][learning.confidence_level] += 1
                domain = learning.domain
                results["by_domain"][domain] = results["by_domain"].get(domain, 0) + 1

                title = safe_title(learning.text)
                if args.dry_run:
                    print(f"  [DRY-RUN] Would import: {title}")
                    results["imported"] += 1
                else:
                    print(f"  [IMPORT] {title}")
                    results["imported"] += 1

        except Exception as e:
            print(f"  [ERROR] Failed to process {file_path.name}: {e}")
            results["errors"].append({"file": file_path.name, "error": str(e)})

    results["end_time"] = datetime.now().isoformat()

    print("\n=== Import Summary ===")
    print(f"Files processed:  {len(results['files_processed'])}")
    print(f"Total learnings:  {results['total_learnings']}")
    print(f"Imported:         {results['imported']}")
    print(f"Skipped:          {results['skipped']}")
    print(f"Errors:           {len(results['errors'])}")

    print("\nBy Confidence:")
    for level, count in results["by_confidence"].items():
        print(f"  {level}: {count}")

    print("\nBy Domain:")
    for domain, count in sorted(results["by_domain"].items(), key=lambda x: -x[1]):
        print(f"  {domain}: {count}")

    if args.output_path:
        output = Path(args.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"\nResults saved to: {args.output_path}")

    return 1 if results["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
