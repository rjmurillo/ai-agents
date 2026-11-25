#!/usr/bin/env python3
# taste-lint: ignore complexity -- pre-existing debt, unlinted before the ADR-119 source classification
"""
quick_validate.py - Fast validation for Claude Code skills

Validates that a skill meets the packaging requirements for distribution.
This is the minimal validation required before packaging with package_skill.py.

Usage:
    python quick_validate.py <skill_directory> [--root DIR]
    python quick_validate.py ~/.claude/skills/my-skill/
    python quick_validate.py /other/repo/skills/my-skill --root /other/repo

The skill directory must resolve inside the current working directory (CWE-22
guard). Pass --root DIR to opt in to a different trusted root.
"""

import os
import re
import sys
from pathlib import Path
from typing import Any

# ADR-047 keeps this bootstrap inline because imports need sys.path first.
# This file's own plugin lib wins when it holds the shared frontmatter parser,
# so a foreign or older plugin root in the environment cannot shadow it. The
# environment root is the fallback for a script copied outside its plugin.
_PLUGIN_ROOT = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_LIB_DIR = Path(__file__).resolve().parents[3] / "lib"
if _PLUGIN_ROOT and not os.path.isfile(_LIB_DIR / "hook_utilities" / "frontmatter_block.py"):
    _LIB_DIR = Path(_PLUGIN_ROOT) / "lib"

if not os.path.isdir(_LIB_DIR):
    raise RuntimeError(
        "Expected portability helper lib directory not found: "
        f"{_LIB_DIR}. Set COPILOT_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT to the "
        "plugin root, or run from an ai-agents checkout."
    )
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from hook_utilities.frontmatter_block import FrontmatterStatus, parse_frontmatter, split_frontmatter  # noqa: E402

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Import shared path guard (CWE-22 containment and CLI parsing). Same fallback as
# package_skill.py: when this file is loaded from another directory, put its own
# directory on sys.path so the sibling module resolves.
try:
    from _path_guard import contained_realpath as _contained_realpath
    from _path_guard import is_within as _is_within
    from _path_guard import parse_args as _parse_args
    from _path_guard import resolve_root as _resolve_root
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _path_guard import contained_realpath as _contained_realpath
    from _path_guard import is_within as _is_within
    from _path_guard import parse_args as _parse_args
    from _path_guard import resolve_root as _resolve_root

# Import shared constants
try:
    from _constants import (
        ALLOWED_PROPERTIES,
        COMPATIBILITY_MAX_LENGTH,
        DESCRIPTION_MAX_LENGTH,
        NAME_MAX_LENGTH,
        NAME_REGEX,
        REQUIRED_PROPERTIES,
    )
except ImportError:
    # Fallback if _constants.py not available
    ALLOWED_PROPERTIES = {
        "name",
        "description",
        "license",
        "allowed-tools",
        "compatibility",
        "metadata",
        "model",
        "context",
        "agent",
        "hooks",
        "user-invocable",
        "version",
        "argument-hint",
    }
    REQUIRED_PROPERTIES = {"name", "description"}
    NAME_MAX_LENGTH = 64
    DESCRIPTION_MAX_LENGTH = 1024
    COMPATIBILITY_MAX_LENGTH = 500
    NAME_REGEX = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"


try:
    from _yaml_scalars import typed_scalar as _typed_scalar
    from _yaml_scalars import unquote_scalar as _unquote_scalar
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _yaml_scalars import typed_scalar as _typed_scalar
    from _yaml_scalars import unquote_scalar as _unquote_scalar


def _parse_frontmatter_fallback(frontmatter_text: str) -> dict[str, Any]:
    """Fallback YAML parser for when PyYAML is not available.

    Handles folded (>) and literal (|) scalars for multi-line descriptions.
    """
    frontmatter: dict[str, Any] = {}
    lines = frontmatter_text.split("\n")
    current_key = None
    current_value_lines: list[str] = []
    is_folded = False  # Track folded scalar (>)
    is_literal = False  # Track literal scalar (|)

    for line in lines:
        # A YAML comment line is not a key.
        if line.startswith("#"):
            continue
        # Check for top-level key
        if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
            # Save previous key if exists
            if current_key and (is_folded or is_literal):
                frontmatter[current_key] = " ".join(current_value_lines).strip()

            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()

            # Check for folded (>) or literal (|) scalar
            if value == ">" or value == ">-":
                is_folded = True
                is_literal = False
                current_value_lines = []
            elif value == "|" or value == "|-":
                is_literal = True
                is_folded = False
                current_value_lines = []
            else:
                is_folded = False
                is_literal = False
                frontmatter[current_key] = _typed_scalar(value)
                current_value_lines = []

        elif (is_folded or is_literal) and (line.startswith("  ") or line.startswith("\t")):
            # Continuation of folded/literal scalar
            current_value_lines.append(line.strip())

        elif (
            current_key
            and line.lstrip().startswith("- ")
            and isinstance(frontmatter.get(current_key), (list, type(None)))
        ):
            # A block sequence item under a bare key, such as an allowed-tools list
            items = frontmatter.get(current_key)
            if not isinstance(items, list):
                items = frontmatter[current_key] = []
            items.append(_unquote_scalar(line.lstrip()[2:].strip()))

        elif line.startswith("  ") and current_key == "metadata":
            # Basic nested parsing for metadata
            if "metadata" not in frontmatter or not isinstance(frontmatter["metadata"], dict):
                frontmatter["metadata"] = {}
            if ":" in line:
                nested_key, nested_value = line.strip().split(":", 1)
                frontmatter["metadata"][nested_key.strip()] = nested_value.strip()

    # Save final key if it was a folded/literal scalar
    if current_key and (is_folded or is_literal) and current_value_lines:
        frontmatter[current_key] = " ".join(current_value_lines).strip()

    return frontmatter


def validate_skill(skill_path, root: str | None = None):
    """
    Basic validation of a skill for packaging compatibility.

    Checks:
    - SKILL.md exists
    - Valid YAML frontmatter
    - Only allowed properties in frontmatter
    - Required fields present and non-blank (name, description)
    - Name format (hyphen-case, ≤64 chars) and equals the parent directory name
    - Description format (≤1024 chars, no angle brackets)
    - Optional compatibility (string, 1-500 chars)

    Args:
        skill_path: Path to the skill directory containing SKILL.md.
        root: When set, the ``os.path.normcase(os.path.realpath(...))`` trusted
            root. SKILL.md must resolve within it or validation fails (CWE-22
            containment).

    Returns:
        tuple: (is_valid: bool, message: str)
    """
    skill_path = Path(skill_path)

    # Check SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # SECURITY (CWE-22): when a trusted root is supplied, ensure SKILL.md resolves
    # inside it before reading. A descendant SKILL.md symlink can point outside the
    # guarded root even when the skill directory itself is contained; read the
    # resolved real path so the check and the read target cannot diverge.
    read_target = skill_md
    if root is not None:
        contained = _contained_realpath(skill_md, root)
        if contained is None:
            return False, "SKILL.md resolves outside the permitted root"
        read_target = Path(contained)

    # Read and validate frontmatter (explicit UTF-8 encoding)
    content = read_target.read_text(encoding="utf-8")
    split = split_frontmatter(content)
    if split.status is FrontmatterStatus.ABSENT:
        return False, "No YAML frontmatter found"
    if not split.found:
        return False, "Invalid frontmatter format"

    # Parse YAML frontmatter
    if HAS_YAML:
        result = parse_frontmatter(content, yaml, allow_duplicate_keys=True)
        if result.status is FrontmatterStatus.NOT_A_MAPPING:
            return False, "Frontmatter must be a YAML dictionary"
        if result.status is FrontmatterStatus.MALFORMED:
            detail = (result.error or "").removeprefix("invalid YAML frontmatter: ")
            return False, f"Invalid YAML in frontmatter: {detail}"
        frontmatter = result.metadata or {}
    else:
        # Basic parsing without yaml library (handles folded scalars)
        frontmatter = _parse_frontmatter_fallback(split.raw.strip("\r\n"))

    # Check for unexpected properties
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return False, (
            f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}. "
            f"Allowed properties are: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    # Check required fields
    for field in REQUIRED_PROPERTIES:
        if field not in frontmatter:
            return False, f"Missing '{field}' in frontmatter"

    # Validate name field
    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if not name:
        return False, "Name must not be empty"
    # Check naming convention (lowercase letters, digits, hyphens; no edge hyphens)
    if not re.match(NAME_REGEX, name):
        return False, (
            f"Name '{name}' should be hyphen-case "
            "(lowercase letters, digits, and hyphens only; no leading or trailing hyphen)"
        )
    if "--" in name:
        return False, f"Name '{name}' cannot contain consecutive hyphens"
    # Check name length
    if len(name) > NAME_MAX_LENGTH:
        return False, (
            f"Name is too long ({len(name)} characters). Maximum is {NAME_MAX_LENGTH} characters."
        )
    # Name must equal the parent directory name (agentskills.io specification)
    dir_name = skill_path.name or skill_path.resolve().name
    if name != dir_name:
        return False, f"Name '{name}' must match its directory name '{dir_name}'"

    # Validate description field
    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if not description:
        return False, "Description must not be empty"
    # Check for angle brackets
    if "<" in description or ">" in description:
        return False, "Description cannot contain angle brackets (< or >)"
    # Check description length (agentskills.io spec: max 1024 characters)
    if len(description) > DESCRIPTION_MAX_LENGTH:
        return False, (
            f"Description is too long ({len(description)} characters). "
            f"Maximum is {DESCRIPTION_MAX_LENGTH} characters."
        )

    # Validate optional compatibility field (agentskills.io spec: 1-500 characters)
    if "compatibility" in frontmatter:
        compatibility = frontmatter["compatibility"]
        if not isinstance(compatibility, str):
            return False, f"Compatibility must be a string, got {type(compatibility).__name__}"
        compatibility = compatibility.strip()
        if not compatibility:
            return False, "Compatibility must not be empty"
        if len(compatibility) > COMPATIBILITY_MAX_LENGTH:
            return False, (
                f"Compatibility is too long ({len(compatibility)} characters). "
                f"Maximum is {COMPATIBILITY_MAX_LENGTH} characters."
            )

    return True, "Skill is valid!"


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--help":
        print("Usage: python quick_validate.py <skill_directory> [--root DIR]")
        print("\nValidate a skill's frontmatter. The skill directory must be under the")
        print("current directory, or under DIR when --root DIR is given.")
        print("\nExamples:")
        print("  python quick_validate.py skills/my-skill")
        print("  python quick_validate.py /other/repo/skills/my-skill --root /other/repo")
        print(
            "\nExit codes: 0 valid, 1 invalid, path escapes the root, or path not found,"
            " 2 usage error (bad or missing arguments, --root not a directory)."
        )
        sys.exit(0)

    parsed = _parse_args(sys.argv[1:])
    if parsed is None:
        print("Usage: python quick_validate.py <skill_directory> [--root DIR]", file=sys.stderr)
        print("\nExample:", file=sys.stderr)
        print("  python quick_validate.py ~/.claude/skills/my-skill/", file=sys.stderr)
        print(
            "  python quick_validate.py /other/repo/skills/my-skill --root /other/repo",
            file=sys.stderr,
        )
        sys.exit(2)

    skill_path, root_arg = parsed

    # SECURITY: Validate path stays within the trusted root (CWE-22). The root is
    # the current working directory unless the caller opts in to another one with
    # --root, so a skill in a different repo validates without a cd or a copy.
    # normcase() makes the containment check case-insensitive on Windows (C:\ vs
    # c:\) while realpath() resolves symlinks so a descendant symlink cannot escape.
    if root_arg is not None and not Path(root_arg).is_dir():
        print(f"Error: --root is not a directory: {root_arg}", file=sys.stderr)
        sys.exit(2)
    cwd_root = _resolve_root(root_arg)
    resolved = os.path.normcase(os.path.realpath(skill_path))
    if not _is_within(resolved, cwd_root):
        print(f"Error: Path traversal detected: {skill_path}", file=sys.stderr)
        sys.exit(1)

    if not Path(skill_path).exists():
        print(f"Error: Path not found: {skill_path}", file=sys.stderr)
        sys.exit(1)

    valid, message = validate_skill(skill_path, root=cwd_root)

    if valid:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")

    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
