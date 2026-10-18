#!/usr/bin/env python3
# taste-lint: ignore file-size (ruff format pushed this file past 500 lines)
"""
discover_skills.py - Scan all skill sources and build a searchable index

Part of the skillrecommender skill.

Responsibilities:
- Scan custom skills, superpowers, and plugin marketplaces
- Scan plugin-installed skills: CLAUDE_PLUGIN_ROOT, COPILOT_PLUGIN_ROOT, the
  skills folder that holds this script, --extra-root, SKILLFORGE_EXTRA_ROOTS
- Extract skill metadata (name, triggers, keywords, domain)
- Keep one entry per skill name, from the lowest-priority-number source
- Build searchable JSON index for fast matching

Usage:
    python discover_skills.py
    python discover_skills.py --verbose
    python discover_skills.py --output custom_path.json
    python discover_skills.py --extra-root /opt/plugins/acme/skills

Exit Codes:
    0  - Success
    1  - General failure
    3  - Every skill source is missing and no skill was found. The folder that
         holds this script is always a source, so the CLI does not reach this
         code while that folder exists.
"""

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Import shared constants (optional - used for validation if available)
try:
    from _constants import SEMVER_REGEX, VALID_AGENT_TYPES

    HAS_CONSTANTS = True
except ImportError:
    HAS_CONSTANTS = False
    SEMVER_REGEX = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$"
    VALID_AGENT_TYPES = {"Explore", "Plan", "general-purpose"}


# ===========================================================================
# RESULT TYPES
# ===========================================================================


@dataclass
class Result:
    """Standard result object for script operations."""

    success: bool
    message: str
    data: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "errors": self.errors,
            "warnings": self.warnings,
            "timestamp": datetime.now().isoformat(),
        }


# ===========================================================================
# SKILL SOURCES
# ===========================================================================

SKILL_SOURCES: list[dict[str, Any]] = [
    {
        "name": "custom",
        "path": Path.home() / ".claude" / "skills",
        "pattern": "*/[Ss][Kk][Ii][Ll][Ll].[Mm][Dd]",  # Case-insensitive: SKILL.md or skill.md
        "priority": 1,
    },
    {
        "name": "superpowers",
        "path": Path.home() / ".claude" / "plugins" / "cache" / "superpowers" / "skills",
        "pattern": "*/*.md",
        "priority": 2,
    },
    {
        "name": "anthropic-agent-skills",
        "path": Path.home() / ".claude" / "plugins" / "marketplaces" / "anthropic-agent-skills",
        "pattern": "skills/*/skill.md",
        "priority": 3,
    },
    {
        "name": "claude-code-workflows",
        "path": Path.home() / ".claude" / "plugins" / "marketplaces" / "claude-code-workflows",
        "pattern": "plugins/*/skills/*/skill.md",
        "priority": 4,
    },
    {
        "name": "claude-code-plugins",
        "path": Path.home() / ".claude" / "plugins" / "marketplaces" / "claude-code-plugins",
        "pattern": "*/skills/*/skill.md",
        "priority": 5,
    },
]

# Case-insensitive: SKILL.md or skill.md, one folder below the root.
RUNTIME_SKILL_PATTERN = "*/[Ss][Kk][Ii][Ll][Ll].[Mm][Dd]"

# Runtime roots rank after the fixed sources above.
RUNTIME_PRIORITY_START = len(SKILL_SOURCES) + 1

# Environment variable holding extra skill roots, separated by os.pathsep.
EXTRA_ROOTS_ENV = "SKILLFORGE_EXTRA_ROOTS"


def _runtime_roots(
    extra_roots: Sequence[Path] | None,
    env: Mapping[str, str],
    script_path: Path,
) -> list[tuple[str, Path]]:
    """Return (name, skills directory) pairs found at run time, in rank order."""
    roots: list[tuple[str, Path]] = []

    for var, name in (
        ("CLAUDE_PLUGIN_ROOT", "plugin-claude"),
        ("COPILOT_PLUGIN_ROOT", "plugin-copilot"),
    ):
        value = env.get(var, "").strip()
        if value:
            roots.append((name, Path(value).expanduser() / "skills"))

    # <skills dir>/skillforge/scripts/discover_skills.py -> <skills dir>
    roots.append(("plugin-local", script_path.resolve().parents[2]))

    for index, root in enumerate(extra_roots or [], start=1):
        roots.append((f"extra-{index}", Path(root).expanduser()))

    env_value = env.get(EXTRA_ROOTS_ENV, "")
    env_entries = [e.strip() for e in env_value.split(os.pathsep) if e.strip()]
    for index, entry in enumerate(env_entries, start=1):
        roots.append((f"env-extra-{index}", Path(entry).expanduser()))

    return roots


def build_skill_sources(
    extra_roots: Sequence[Path] | None = None,
    env: Mapping[str, str] | None = None,
    script_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return SKILL_SOURCES plus the roots found at run time.

    Runtime roots cover skills installed through a plugin cache: the plugin
    root named by CLAUDE_PLUGIN_ROOT or COPILOT_PLUGIN_ROOT, the skills folder
    that holds this script, each ``--extra-root``, and each SKILLFORGE_EXTRA_ROOTS
    entry. A root that resolves to an earlier source is dropped.
    """
    sources = [dict(s) for s in SKILL_SOURCES]
    seen = {_resolved(s["path"]) for s in sources}

    roots = _runtime_roots(
        extra_roots,
        os.environ if env is None else env,
        Path(__file__) if script_path is None else script_path,
    )
    priority = RUNTIME_PRIORITY_START
    for name, path in roots:
        key = _resolved(path)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {"name": name, "path": path, "pattern": RUNTIME_SKILL_PATTERN, "priority": priority}
        )
        priority += 1

    return sources


def _resolved(path: Path) -> Path:
    """Resolve a path for comparison without requiring it to exist."""
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


# ===========================================================================
# UNIVERSAL DOMAIN CLASSIFICATION
# ===========================================================================
# These domain names MUST match the DOMAIN_SYNONYMS in triage_skill_request.py
# for consistent matching across discovery and triage.

DOMAIN_KEYWORDS = {
    # Document types (aligns with spreadsheet, document, presentation, pdf domains)
    "spreadsheet": ["excel", "xlsx", "xls", "csv", "spreadsheet", "workbook", "tabular"],
    "document": ["word", "docx", "doc", "document", "report", "write"],
    "presentation": ["powerpoint", "pptx", "slides", "presentation", "deck", "keynote"],
    "pdf": ["pdf", "portable document"],
    # Development domains
    "debugging": [
        "debug",
        "error",
        "trace",
        "exception",
        "stack trace",
        "fix bug",
        "investigate",
        "root cause",
    ],
    "testing": [
        "test",
        "tdd",
        "coverage",
        "e2e",
        "unit",
        "integration",
        "cypress",
        "jest",
        "pytest",
        "spec",
    ],
    "security": ["security", "owasp", "vulnerability", "audit", "pentest", "xss", "injection"],
    "code_quality": [
        "review",
        "refactor",
        "lint",
        "code smell",
        "solid",
        "pr review",
        "code review",
    ],
    "database": [
        "database",
        "db",
        "sql",
        "postgres",
        "mysql",
        "mongodb",
        "migration",
        "schema",
        "orm",
    ],
    "api": ["api", "rest", "graphql", "openapi", "endpoint", "swagger", "http"],
    "frontend": ["ui", "ux", "frontend", "react", "vue", "angular", "component", "css", "styling"],
    "accessibility": ["accessibility", "a11y", "wcag", "screen reader", "aria"],
    "performance": ["performance", "optimize", "slow", "speed", "cache", "profiling", "bottleneck"],
    "authentication": ["auth", "login", "authentication", "oauth", "jwt", "session", "password"],
    "deployment": ["deploy", "release", "ship", "hosting", "production"],
    "devops": [
        "ci",
        "cd",
        "docker",
        "kubernetes",
        "k8s",
        "container",
        "helm",
        "terraform",
        "pipeline",
    ],
    "documentation": ["documentation", "docs", "readme", "changelog", "jsdoc"],
    "architecture": ["architecture", "system design", "microservices", "monolith", "pattern"],
    "workflow": ["flowchart", "diagram", "workflow", "process", "swimlane", "sequence"],
    # Specialized domains
    "ai_ml": ["ai", "ml", "llm", "rag", "langchain", "prompt", "embedding", "model"],
    "visual": ["visual", "image", "graphic", "art", "canvas", "brand"],
    "meta": ["orchestrate", "compose", "skill", "maker", "proactive", "chain"],
}


# ===========================================================================
# PARSING FUNCTIONS
# ===========================================================================


def extract_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content."""
    frontmatter = {}

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            yaml_content = parts[1].strip()

            # Try proper YAML parsing first
            try:
                import yaml

                parsed = yaml.safe_load(yaml_content)
                if isinstance(parsed, dict):
                    frontmatter = parsed
                # else: non-dict YAML (e.g., scalar) - keep empty dict
            except ImportError:
                # PyYAML not installed - use fallback parser below
                pass
            except Exception:
                # Malformed YAML - use fallback parser below
                pass

            # Fallback to basic parsing if YAML parsing failed or returned non-dict
            if not frontmatter:
                current_key = None
                for line in yaml_content.split("\n"):
                    if ":" in line and not line.startswith(" "):
                        key, value = line.split(":", 1)
                        current_key = key.strip()
                        frontmatter[current_key] = value.strip()
                    elif line.startswith("  ") and current_key == "metadata":
                        # Basic nested parsing for metadata
                        if "metadata" not in frontmatter or not isinstance(
                            frontmatter["metadata"], dict
                        ):
                            frontmatter["metadata"] = {}
                        if ":" in line:
                            key, value = line.strip().split(":", 1)
                            frontmatter["metadata"][key.strip()] = value.strip()

    return frontmatter


def get_version(frontmatter: dict[str, Any]) -> str:
    """Extract version from frontmatter, checking both root and metadata."""
    # First check root level (legacy/deprecated)
    if "version" in frontmatter:
        return str(frontmatter["version"])

    # Then check metadata.version (preferred location)
    if "metadata" in frontmatter and isinstance(frontmatter["metadata"], dict):
        version = frontmatter["metadata"].get("version")
        if version:
            return str(version)

    # Default fallback
    return "1.0.0"


def extract_triggers(content: str) -> list[str]:
    """Extract trigger phrases from skill content."""
    triggers = []

    # Look for triggers in frontmatter or content
    trigger_patterns = [
        r"\*\*Triggers?:\*\*\s*`([^`]+)`",
        r"Triggers?:\s*`([^`]+)`",
        r"\|\s*`([^`]+)`\s*\|.*trigger",
        r"trigger[s]?.*`([^`]+)`",
    ]

    for pattern in trigger_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        triggers.extend(matches)

    # Also extract from trigger tables
    table_pattern = r"\|\s*`([^`]+)`\s*\|"
    trigger_start = content.find("Trigger")
    if trigger_start != -1:
        # Guard against find() returning -1
        end_marker = content.find("---", trigger_start)
        if end_marker == -1:
            end_marker = len(content)  # Use end of content if no delimiter found
        table_section = content[trigger_start:end_marker]
        matches = re.findall(table_pattern, table_section)
        triggers.extend(matches)

    return list(set(triggers))


def extract_keywords(content: str, name: str) -> list[str]:
    """Extract keywords from skill content."""
    keywords = []

    # Add name variations
    keywords.append(name.lower())
    keywords.extend(name.lower().replace("-", " ").split())

    # Look for keywords in tables
    keyword_pattern = r"\|\s*\*\*[^*]+\*\*\s*\|[^|]+\|\s*([^|]+)\s*\|"
    matches = re.findall(keyword_pattern, content)
    for match in matches:
        keywords.extend([k.strip().lower() for k in match.split(",")])

    # Extract from purpose/description
    purpose_pattern = r"(?:Purpose|Description)[:\s]+([^\n]+)"
    matches = re.findall(purpose_pattern, content, re.IGNORECASE)
    for match in matches:
        words = re.findall(r"\b[a-z]{4,}\b", match.lower())
        keywords.extend(words)

    return list(set(keywords))


def classify_domain(keywords: list[str], content: str) -> list[str]:
    """Classify skill into domains based on keywords."""
    domains = []
    content_lower = content.lower()

    for domain, domain_keywords in DOMAIN_KEYWORDS.items():
        score = 0
        for kw in domain_keywords:
            if kw in keywords or kw in content_lower:
                score += 1
        if score >= 2:
            domains.append(domain)

    if not domains:
        domains.append("general")

    return domains


def parse_skill_file(path: Path, source_name: str, priority: int) -> dict | None:
    """Parse a skill file and extract metadata."""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return None

    # Extract skill name from path or frontmatter
    frontmatter = extract_frontmatter(content)
    name = frontmatter.get("name", path.parent.name)

    # Extract metadata
    triggers = extract_triggers(content)
    keywords = extract_keywords(content, name)
    domains = classify_domain(keywords, content)

    # Get description
    description = frontmatter.get("description", "")
    if not description:
        # Try to extract from first paragraph
        lines = content.split("\n")
        for line in lines:
            if line.strip() and not line.startswith("#") and not line.startswith("-"):
                description = line.strip()[:200]
                break

    return {
        "name": name,
        "source": source_name,
        "path": str(path),
        "priority": priority,
        "description": description,
        "triggers": triggers,
        "keywords": keywords,
        "domains": domains,
        "version": get_version(frontmatter),
    }


# ===========================================================================
# DISCOVERY
# ===========================================================================


def _skill_sort_key(skill: dict[str, Any]) -> tuple[int, str, bool, str, str]:
    """Order skills so the dedupe keeps the real SKILL.md within one source.

    A ``*/*.md`` source parses every markdown file in a skill folder, and a
    file with no frontmatter takes its folder name. Sibling files such as
    CREATION-LOG.md would then outrank SKILL.md by path order, so SKILL.md
    sorts first among entries with the same normalized name.
    """
    path = Path(str(skill["path"]))
    return (
        skill["priority"],
        str(skill["name"]).strip().lower(),
        path.name.lower() != "skill.md",
        str(skill["name"]),
        str(path),
    )


def _empty_root_warning(source: dict[str, Any]) -> str:
    """Explain why a runtime root that exists produced no skill files."""
    root = source["path"]
    try:
        holds_skill = any(c.is_file() and c.name.lower() == "skill.md" for c in root.iterdir())
    except OSError:
        holds_skill = False
    if holds_skill:
        hint = "it holds SKILL.md itself, so pass its parent directory"
    else:
        hint = "each skill must sit in a subfolder holding SKILL.md"
    return f"No skills found in {source['name']} ({root}): {hint}"


def _dedupe_by_name(skills: list[dict[str, Any]], verbose: bool = False) -> list[dict[str, Any]]:
    """Keep one entry per skill name: the one from the lowest priority number.

    ``skills`` must already be sorted by priority. Each hidden copy's path is
    recorded on the kept entry as ``shadowed_paths``, so one skill cannot fill
    several recommendation slots in triage_skill_request.py.
    """
    kept: dict[str, dict[str, Any]] = {}
    for skill in skills:
        key = str(skill["name"]).strip().lower()
        winner = kept.get(key)
        if winner is None:
            skill["shadowed_paths"] = []
            kept[key] = skill
            continue
        winner["shadowed_paths"].append(skill["path"])
        if verbose:
            print(
                f"  Shadowed: {skill['name']} ({skill['source']}) by {winner['source']}",
                file=sys.stderr,
            )
    return list(kept.values())


def discover_skills(
    verbose: bool = False, sources: Sequence[dict[str, Any]] | None = None
) -> Result:
    """Scan all skill sources and build index.

    ``sources`` defaults to ``build_skill_sources()``, the fixed sources plus
    the plugin and extra roots found at run time.
    """
    if sources is None:
        sources = build_skill_sources()

    skills = []
    errors = []
    warnings = []
    missing_sources = []
    seen_files: set[Path] = set()

    for source in sources:
        source_path = source["path"]

        if not source_path.exists():
            warnings.append(f"Source not found: {source['name']} ({source_path})")
            missing_sources.append(source["name"])
            continue

        if verbose:
            print(f"Scanning {source['name']}: {source_path}", file=sys.stderr)

        # Find skill files
        pattern_parts = source["pattern"].split("/")

        if len(pattern_parts) == 2:
            # Simple pattern like */skill.md or */[Ss][Kk][Ii][Ll][Ll].[Mm][Dd]
            skill_files = list(source_path.glob(source["pattern"]))
        else:
            # Complex pattern - use recursive glob (case-insensitive for skill files)
            skill_files = list(source_path.glob("**/*.md"))
            skill_files = [f for f in skill_files if f.name.lower() in ("skill.md", "skills.md")]

        if not skill_files and source["priority"] >= RUNTIME_PRIORITY_START:
            warnings.append(_empty_root_warning(source))

        for skill_file in skill_files:
            file_key = _resolved(skill_file)
            if file_key in seen_files:
                continue
            seen_files.add(file_key)
            skill_data = parse_skill_file(skill_file, source["name"], source["priority"])
            if skill_data:
                skills.append(skill_data)
                if verbose:
                    print(f"  Found: {skill_data['name']}", file=sys.stderr)
            else:
                warnings.append(f"Failed to parse: {skill_file}")

    # Sort by priority (lower = higher priority), then keep one entry per skill name.
    skills.sort(key=_skill_sort_key)
    skills = _dedupe_by_name(skills, verbose)

    # Build domain index
    domain_index = {}
    for skill in skills:
        for domain in skill["domains"]:
            if domain not in domain_index:
                domain_index[domain] = []
            domain_index[domain].append(skill["name"])

    return Result(
        success=True,
        message=f"Discovered {len(skills)} skills from {len(sources)} sources",
        data={
            "skills": skills,
            "domains": domain_index,
            "sources": {s["name"]: str(s["path"]) for s in sources},
            "source_count": len(sources),
            "missing_sources": missing_sources,
            "total_count": len(skills),
        },
        warnings=warnings,
        errors=errors,
    )


# ===========================================================================
# STATE MANAGEMENT
# ===========================================================================


def get_index_path() -> Path:
    """Get the skill index file path."""
    cache_dir = Path.home() / ".cache" / "skillrecommender"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "skill_index.json"


def save_index(result: Result, output_path: Path | None = None) -> None:
    """Save skill index to disk."""
    path = output_path or get_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    index_data = {
        "version": "2.0.0",
        "generated_at": datetime.now().isoformat(),
        "skills": result.data["skills"],
        "domains": result.data["domains"],
        "sources": result.data["sources"],
        "total_count": result.data["total_count"],
    }

    path.write_text(json.dumps(index_data, indent=2))


# ===========================================================================
# CLI
# ===========================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Discover and index all available skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file path (default: ~/.cache/skillrecommender/skill_index.json)",
    )

    parser.add_argument(
        "--extra-root",
        action="append",
        type=Path,
        default=[],
        metavar="PATH",
        help=(
            "Extra skills directory to scan: a directory whose subfolders hold SKILL.md. "
            f"Repeatable. {EXTRA_ROOTS_ENV} adds more, separated by the OS path separator."
        ),
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    # Discover skills
    result = discover_skills(
        verbose=args.verbose, sources=build_skill_sources(extra_roots=args.extra_root)
    )

    # Save index
    save_index(result, args.output)

    # Output
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Discovered {result.data['total_count']} skills")
        print(f"Domains: {', '.join(result.data['domains'].keys())}")
        print(f"Index saved to: {args.output or get_index_path()}")

        if result.warnings:
            print("\nWarnings:")
            for warning in result.warnings:
                print(f"  - {warning}")

    # Exit codes: 0 = success, 1 = general failure, 3 = no sources found
    if not result.success:
        sys.exit(1)
    elif (
        result.data["total_count"] == 0
        and len(result.data["missing_sources"]) == (result.data["source_count"])
    ):
        # All sources were missing - this is exit code 3 per docstring
        sys.exit(3)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
