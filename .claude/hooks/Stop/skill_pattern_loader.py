#!/usr/bin/env python3
"""
Dynamic skill pattern loader for invoke_skill_learning.py.

Scans SKILL.md files at runtime to build detection maps, eliminating
hardcoded pattern dictionaries that drift when skills change.

Scans four skill source paths covering both harness ecosystems:
- Claude Code: .claude/skills/ (repo) + ~/.claude/skills/ (user)
- Copilot/GitHub: .github/skills/ (repo) + ~/.copilot/skills/ (user)

Uses stat-based caching: invalidates when any source SKILL.md mtime changes.

Performance budget:
- Cold start: ~40ms (42 files x ~2KB each)
- Warm cache: ~2ms (one JSON read + stat checks)
"""

import json
import re
from pathlib import Path

CACHE_VERSION = 1
CACHE_FILENAME = ".skill_pattern_cache.json"

# Regex to extract backtick-wrapped phrases from markdown table cells.
# Matches: | `phrase here` | ... |
# The phrase is captured in group 1.
_TRIGGER_CELL_RE = re.compile(r"\|\s*`([^`]+)`\s*\|")

# Regex to extract frontmatter name field.
_FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(.+)$", re.MULTILINE)


def scan_skill_directories(project_dir: Path) -> list[Path]:
    """Scan skill sources in priority order and return deduplicated SKILL.md paths.

    Priority (lower wins for same skill name):
    1. {project_dir}/.claude/skills/*/SKILL.md   (Claude Code repo)
    2. {project_dir}/.github/skills/*/SKILL.md   (Copilot/GitHub repo)
    3. ~/.claude/skills/*/SKILL.md                (Claude Code user)
    4. ~/.copilot/skills/*/SKILL.md               (Copilot CLI user)

    Returns list of Path objects for discovered SKILL.md files.
    """
    home = Path.home()
    search_roots = [
        project_dir / ".claude" / "skills",
        project_dir / ".github" / "skills",
        home / ".claude" / "skills",
        home / ".copilot" / "skills",
    ]

    seen_names: set[str] = set()
    result: list[Path] = []

    for root in search_roots:
        if not root.is_dir():
            continue

        # Case-insensitive: try SKILL.md then skill.md
        for filename in ("SKILL.md", "skill.md"):
            for skill_md in sorted(root.glob(f"*/{filename}")):
                skill_name = skill_md.parent.name.lower()
                if skill_name in seen_names:
                    continue
                seen_names.add(skill_name)
                result.append(skill_md)

    return result


def parse_skill_triggers(skill_md_path: Path) -> dict:
    """Parse a SKILL.md file and extract trigger phrases and slash commands.

    Returns dict with:
    - name: str (from frontmatter or directory name)
    - triggers: list[str] (backtick-wrapped phrases from Triggers tables)
    - slash_commands: list[str] (trigger phrases starting with /)
    """
    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return {
            "name": skill_md_path.parent.name,
            "triggers": [],
            "slash_commands": [],
        }

    # Extract name from frontmatter, fallback to directory name
    name = skill_md_path.parent.name
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            match = _FRONTMATTER_NAME_RE.search(parts[1])
            if match:
                name = match.group(1).strip()

    # Find trigger sections and extract backtick phrases from tables.
    # Strategy: find lines containing "Trigger" as a heading, then scan
    # subsequent table rows until the next heading or horizontal rule.
    triggers: list[str] = []
    slash_commands: list[str] = []

    lines = content.split("\n")
    in_trigger_section = False

    for line in lines:
        stripped = line.strip()

        # Detect trigger section headings (## Triggers, ### HIGH Priority Triggers, etc.)
        if stripped.startswith("#") and "trigger" in stripped.lower():
            in_trigger_section = True
            continue

        # End trigger section on next heading or horizontal rule (but not table separator)
        if in_trigger_section:
            if stripped.startswith("#"):
                # New heading that isn't a trigger heading ends the section
                if "trigger" not in stripped.lower():
                    in_trigger_section = False
                continue
            if stripped == "---":
                in_trigger_section = False
                continue

        if not in_trigger_section:
            continue

        # Extract backtick-wrapped phrases from table rows
        for match in _TRIGGER_CELL_RE.finditer(line):
            phrase = match.group(1).strip()
            if not phrase:
                continue
            triggers.append(phrase)
            if phrase.startswith("/"):
                slash_commands.append(phrase)

    return {
        "name": name,
        "triggers": triggers,
        "slash_commands": slash_commands,
    }


def build_detection_maps(
    skills: list[dict],
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Build detection maps from parsed skill data.

    Returns:
    - skill_patterns: {skill_name: [trigger phrases + name + skill path]}
    - command_to_skill: {command_name: skill_name} from slash commands

    Auto-adds:
    - Skill name as a pattern (e.g., "github" for the github skill)
    - Skill path pattern (e.g., ".claude/skills/github")
    - Identity slash command mappings (e.g., /reflect -> reflect)
    """
    skill_patterns: dict[str, list[str]] = {}
    command_to_skill: dict[str, str] = {}

    for skill in skills:
        name = skill["name"]
        patterns = list(skill["triggers"])

        # Add skill name and path as patterns
        patterns.append(name)
        patterns.append(f".claude/skills/{name}")

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_patterns: list[str] = []
        for p in patterns:
            lower = p.lower()
            if lower not in seen:
                seen.add(lower)
                unique_patterns.append(p)

        skill_patterns[name] = unique_patterns

        # Map slash commands to skill names
        for cmd in skill["slash_commands"]:
            # Strip leading / to get command name
            cmd_name = cmd.lstrip("/")
            if cmd_name:
                command_to_skill[cmd_name] = name

        # Auto-add identity mapping: skill name -> skill name
        # This handles /reflect -> reflect, /analyze -> analyze, etc.
        if name not in command_to_skill:
            command_to_skill[name] = name

    return skill_patterns, command_to_skill


def _get_cache_path(project_dir: Path) -> Path:
    """Return the cache file path within the hooks directory."""
    return project_dir / ".claude" / "hooks" / "Stop" / CACHE_FILENAME


def _read_cache(cache_path: Path) -> dict | None:
    """Read and validate cache file. Returns None if invalid or missing."""
    if not cache_path.is_file():
        return None

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None
    if data.get("version") != CACHE_VERSION:
        return None
    if "source_mtimes" not in data:
        return None
    if "skill_patterns" not in data:
        return None
    if "command_to_skill" not in data:
        return None

    return data


def _check_cache_freshness(
    cache_data: dict, skill_files: list[Path]
) -> bool:
    """Return True if cache mtimes match current file mtimes."""
    stored_mtimes = cache_data.get("source_mtimes", {})

    # Build current mtime map keyed by resolved path string
    current_mtimes: dict[str, float] = {}
    for f in skill_files:
        try:
            current_mtimes[str(f)] = f.stat().st_mtime
        except OSError:
            return False

    # Check that the sets of files match and all mtimes agree
    if set(stored_mtimes.keys()) != set(current_mtimes.keys()):
        return False

    for path_str, mtime in current_mtimes.items():
        if stored_mtimes.get(path_str) != mtime:
            return False

    return True


def _write_cache(
    cache_path: Path,
    skill_files: list[Path],
    skill_patterns: dict[str, list[str]],
    command_to_skill: dict[str, str],
) -> None:
    """Write cache file. Fails silently on error."""
    source_mtimes: dict[str, float] = {}
    for f in skill_files:
        try:
            source_mtimes[str(f)] = f.stat().st_mtime
        except OSError:
            pass

    cache_data = {
        "version": CACHE_VERSION,
        "source_mtimes": source_mtimes,
        "skill_patterns": skill_patterns,
        "command_to_skill": command_to_skill,
    }

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(cache_data, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def load_skill_patterns(
    project_dir: Path,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Load skill patterns with stat-based caching.

    1. Scan skill directories for SKILL.md files
    2. Check cache: if all source mtimes match, return cached data
    3. Otherwise: parse all SKILL.md files, build maps, write cache
    4. Return (skill_patterns, command_to_skill)

    Returns empty dicts on any error (graceful degradation).
    """
    try:
        skill_files = scan_skill_directories(project_dir)

        if not skill_files:
            return {}, {}

        cache_path = _get_cache_path(project_dir)
        cache_data = _read_cache(cache_path)

        if cache_data and _check_cache_freshness(cache_data, skill_files):
            return (
                cache_data["skill_patterns"],
                cache_data["command_to_skill"],
            )

        # Cache miss: parse all SKILL.md files
        parsed_skills = [parse_skill_triggers(f) for f in skill_files]
        skill_patterns, command_to_skill = build_detection_maps(parsed_skills)

        _write_cache(cache_path, skill_files, skill_patterns, command_to_skill)

        return skill_patterns, command_to_skill

    except Exception:
        return {}, {}
