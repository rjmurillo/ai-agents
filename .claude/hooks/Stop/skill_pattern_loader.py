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

import contextlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path


@contextlib.contextmanager
def _suppress_os_error():
    """Suppress OSError in cleanup paths."""
    try:
        yield
    except OSError:
        pass

# Maximum SKILL.md file size to read (100 KB). Legitimate files are ~2 KB.
_MAX_SKILL_FILE_BYTES = 100 * 1024

CACHE_VERSION = 1
CACHE_FILENAME = ".skill_pattern_cache.json"

# Regex to extract backtick-wrapped phrases from markdown table cells.
# Matches: | `phrase here` | ... |
# The phrase is captured in group 1.
_TRIGGER_CELL_RE = re.compile(r"\|\s*`([^`]+)`\s*\|")

# Regex to extract frontmatter name field.
_FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(.+)$", re.MULTILINE)


def _glob_contained_skills(root: Path, filename: str) -> list[Path]:
    """Glob for skill files within root, rejecting symlinks that escape."""
    resolved_root = str(root.resolve()) + os.sep
    results = []
    for skill_md in sorted(root.glob(f"*/{filename}")):
        if str(skill_md.resolve()).startswith(resolved_root):
            results.append(skill_md)
    return results


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
            for skill_md in _glob_contained_skills(root, filename):
                skill_name = skill_md.parent.name.lower()
                if skill_name not in seen_names:
                    seen_names.add(skill_name)
                    result.append(skill_md)

    return result


def _extract_frontmatter_name(content: str, default: str) -> str:
    """Extract skill name from YAML frontmatter, or return default."""
    if not content.startswith("---"):
        return default
    parts = content.split("---", 2)
    if len(parts) < 3:
        return default
    match = _FRONTMATTER_NAME_RE.search(parts[1])
    return match.group(1).strip() if match else default


def _extract_trigger_phrases(content: str) -> tuple[list[str], list[str]]:
    """Scan markdown for trigger sections and extract backtick phrases.

    Finds headings containing "trigger", then extracts backtick-wrapped
    phrases from subsequent table rows until the next non-trigger heading
    or horizontal rule.

    Returns (triggers, slash_commands).
    """
    triggers: list[str] = []
    slash_commands: list[str] = []
    in_trigger_section = False

    for line in content.split("\n"):
        stripped = line.strip()
        in_trigger_section = _update_section_state(
            stripped, in_trigger_section
        )
        if not in_trigger_section or stripped.startswith("#"):
            continue
        _collect_phrases(line, triggers, slash_commands)

    return triggers, slash_commands


def _update_section_state(stripped: str, in_section: bool) -> bool:
    """Determine whether we are inside a trigger section after this line."""
    if stripped.startswith("#") and "trigger" in stripped.lower():
        return True
    if in_section and stripped.startswith("#"):
        return "trigger" in stripped.lower()
    if in_section and stripped == "---":
        return False
    return in_section


def _collect_phrases(
    line: str, triggers: list[str], slash_commands: list[str]
) -> None:
    """Append backtick-wrapped phrases from a table row."""
    for match in _TRIGGER_CELL_RE.finditer(line):
        phrase = match.group(1).strip()
        if not phrase:
            continue
        triggers.append(phrase)
        if phrase.startswith("/"):
            slash_commands.append(phrase)


def parse_skill_triggers(skill_md_path: Path) -> dict:
    """Parse a SKILL.md file and extract trigger phrases and slash commands.

    Returns dict with:
    - name: str (from frontmatter or directory name)
    - triggers: list[str] (backtick-wrapped phrases from Triggers tables)
    - slash_commands: list[str] (trigger phrases starting with /)
    """
    default_name = skill_md_path.parent.name
    try:
        size = skill_md_path.stat().st_size
        if size > _MAX_SKILL_FILE_BYTES:
            return {"name": default_name, "triggers": [], "slash_commands": []}
        content = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return {"name": default_name, "triggers": [], "slash_commands": []}

    name = _extract_frontmatter_name(content, default_name)
    triggers, slash_commands = _extract_trigger_phrases(content)
    return {"name": name, "triggers": triggers, "slash_commands": slash_commands}


def _deduplicate_patterns(patterns: list[str]) -> list[str]:
    """Remove duplicate patterns (case-insensitive) while preserving order."""
    seen: set[str] = set()
    unique: list[str] = []
    for p in patterns:
        lower = p.lower()
        if lower not in seen:
            seen.add(lower)
            unique.append(p)
    return unique


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
        patterns.append(name)
        patterns.append(f".claude/skills/{name}")
        skill_patterns[name] = _deduplicate_patterns(patterns)

        # Map slash commands to skill names
        for cmd in skill["slash_commands"]:
            cmd_name = cmd.lstrip("/")
            if cmd_name:
                command_to_skill[cmd_name] = name

        # Auto-add identity mapping (e.g., /reflect -> reflect)
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


def _atomic_json_write(path: Path, data: dict) -> None:
    """Write JSON data atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        with _suppress_os_error():
            os.unlink(tmp_path)


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
        _atomic_json_write(cache_path, cache_data)
    except OSError as exc:
        print(f"Warning: Failed to write skill cache: {exc}", file=sys.stderr)


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

    except Exception as exc:
        print(f"Skill pattern loading error: {exc}", file=sys.stderr)
        return {}, {}
