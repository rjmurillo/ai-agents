#!/usr/bin/env python3
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
    NAME_REGEX = r"^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$"


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
                frontmatter[current_key] = value
                current_value_lines = []

        elif (is_folded or is_literal) and (line.startswith("  ") or line.startswith("\t")):
            # Continuation of folded/literal scalar
            current_value_lines.append(line.strip())

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
    - Required fields present (name, description)
    - Name format (hyphen-case, ≤64 chars)
    - Description format (≤1024 chars, no angle brackets)

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
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"

    # Extract frontmatter (handles both LF and CRLF line endings)
    match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter_text = match.group(1)

    # Parse YAML frontmatter
    if HAS_YAML:
        try:
            frontmatter = yaml.safe_load(frontmatter_text)
            if frontmatter is None:
                frontmatter = {}
            elif not isinstance(frontmatter, dict):
                return False, "Frontmatter must be a YAML dictionary"
        except yaml.YAMLError as e:
            return False, f"Invalid YAML in frontmatter: {e}"
    else:
        # Basic parsing without yaml library (handles folded scalars)
        frontmatter = _parse_frontmatter_fallback(frontmatter_text)

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
    if name:
        # Check naming convention (hyphen-case: starts with letter, lowercase with hyphens)
        if not re.match(NAME_REGEX, name):
            return False, (
                f"Name '{name}' should be hyphen-case "
                "(start with letter, lowercase letters, digits, and hyphens only)"
            )
        if "--" in name:
            return False, f"Name '{name}' cannot contain consecutive hyphens"
        # Check name length
        if len(name) > NAME_MAX_LENGTH:
            return False, (
                f"Name is too long ({len(name)} characters). "
                f"Maximum is {NAME_MAX_LENGTH} characters."
            )

    # Validate description field
    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if description:
        # Check for angle brackets
        if "<" in description or ">" in description:
            return False, "Description cannot contain angle brackets (< or >)"
        # Check description length
        if len(description) > DESCRIPTION_MAX_LENGTH:
            return False, (
                f"Description is too long ({len(description)} characters). "
                f"Maximum is {DESCRIPTION_MAX_LENGTH} characters."
            )

    return True, "Skill is valid!"


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print("Usage: python quick_validate.py <skill_directory> [--root DIR]")
        print("\nValidate a skill's frontmatter. The skill directory must be under the")
        print("current directory, or under DIR when --root DIR is given.")
        print("\nExit codes: 0 valid, 1 invalid or bad path.")
        sys.exit(0)

    parsed = _parse_args(sys.argv[1:])
    if parsed is None:
        print("Usage: python quick_validate.py <skill_directory> [--root DIR]")
        print("\nExample:")
        print("  python quick_validate.py ~/.claude/skills/my-skill/")
        print("  python quick_validate.py /other/repo/skills/my-skill --root /other/repo")
        sys.exit(1)

    skill_path, root_arg = parsed

    # SECURITY: Validate path stays within the trusted root (CWE-22). The root is
    # the current working directory unless the caller opts in to another one with
    # --root, so a skill in a different repo validates without a cd or a copy.
    # normcase() makes the containment check case-insensitive on Windows (C:\ vs
    # c:\) while realpath() resolves symlinks so a descendant symlink cannot escape.
    if root_arg is not None and not Path(root_arg).is_dir():
        print(f"Error: --root is not a directory: {root_arg}")
        sys.exit(1)
    cwd_root = _resolve_root(root_arg)
    resolved = os.path.normcase(os.path.realpath(skill_path))
    if not _is_within(resolved, cwd_root):
        print(f"Error: Path traversal detected: {skill_path}")
        sys.exit(1)

    if not Path(skill_path).exists():
        print(f"Error: Path not found: {skill_path}")
        sys.exit(1)

    valid, message = validate_skill(skill_path, root=cwd_root)

    if valid:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")

    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
