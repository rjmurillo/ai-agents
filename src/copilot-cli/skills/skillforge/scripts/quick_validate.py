#!/usr/bin/env python3
"""
quick_validate.py - Fast validation for Claude Code skills

Validates that a skill meets the packaging requirements for distribution.
This is the minimal validation required before packaging with package_skill.py.

Usage:
    python quick_validate.py <skill_directory>
    python quick_validate.py ~/.claude/skills/my-skill/
"""

import os
import re
import sys
from pathlib import Path
from typing import Any, Protocol

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

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


class _PathModule(Protocol):
    """Structural type for the ``os.path`` surface ``_is_within`` needs.

    Lets tests substitute ``posixpath`` or ``ntpath`` for the host ``os.path``
    while keeping a precise return type (``commonpath`` yields ``str``, so the
    containment comparison stays ``bool`` instead of decaying to ``Any``).
    """

    sep: str
    altsep: str | None

    def commonpath(self, paths: list[str], /) -> str: ...

    def splitdrive(self, p: str, /) -> tuple[str, str]: ...


def _is_within(child: str, root: str, pathmod: _PathModule = os.path) -> bool:
    """Return True when case-normalized realpath ``child`` is ``root`` or nested inside it.

    Both arguments must already be ``os.path.normcase(os.path.realpath(...))``
    results. Containment is decided by ``os.path.commonpath`` rather than a
    separator-appended prefix match, because ``os.path.join(root, "")`` does NOT
    append a separator to a bare drive root (``C:\\``) or a bare UNC share root
    (``\\\\server\\share``) on Windows. With the old prefix match a sibling that
    merely shares a string prefix (``C:\\evil`` under ``C:\\``,
    ``\\\\server\\shareevil`` under ``\\\\server\\share``) passed the guard and
    escaped the CWD sandbox (CWE-22). ``commonpath`` compares whole path
    components, so only true descendants match.

    ``commonpath`` raises ``ValueError`` when the two paths cannot form a common
    base. Different drives or drive-vs-UNC genuinely mean "not contained". But a
    bare UNC share root (``\\\\server\\share``) has an empty root-relative part,
    so ``ntpath`` treats it as rootless and refuses to mix it with a rooted
    child, even though real descendants of that share ARE contained. On that
    ``ValueError`` the guard decides by drive identity: contained only when child
    and root share the same drive/share and root is that drive/share root itself.
    This keeps the CWE-22 sibling-share rejection while no longer false-rejecting
    a legitimate SKILL.md that lives directly under a bare share root.

    ``pathmod`` is injected only so tests can pin ``posixpath`` or ``ntpath`` and
    exercise both platforms' root semantics deterministically on any host;
    production always uses the default ``os.path``.
    """
    if child == root:
        return True
    try:
        return pathmod.commonpath([child, root]) == root
    except ValueError:
        # See the docstring: distinguish a genuine different-drive mismatch from
        # a bare UNC share root that ``ntpath`` cannot mix with a rooted child.
        child_drive, _ = pathmod.splitdrive(child)
        root_drive, root_rel = pathmod.splitdrive(root)
        if child_drive != root_drive:
            return False
        separators = {pathmod.sep, pathmod.altsep or pathmod.sep}
        return root_rel == "" or root_rel in separators


def _contained_realpath(target: Path, root: str) -> str | None:
    """Resolve ``target`` and return its real path only if it stays within ``root``.

    ``root`` must already be an ``os.path.normcase(os.path.realpath(...))``
    result. Returns ``None`` when the resolved target escapes ``root`` (via a
    symlink or ``..``), letting the caller reject an out-of-root read (CWE-22).

    The containment check compares case-normalized paths so a Windows path that
    differs only by drive-letter or component casing (``C:\\`` vs ``c:\\``) is not
    misclassified as an escape. The original real path is returned unchanged so
    the caller reads the exact resolved target.
    """
    real = os.path.realpath(target)
    real_cmp = os.path.normcase(real)
    if _is_within(real_cmp, root):
        return real
    return None


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
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        print("\nExample:")
        print("  python quick_validate.py ~/.claude/skills/my-skill/")
        sys.exit(1)

    skill_path = sys.argv[1]

    # SECURITY: Validate path stays within the current working directory (CWE-22).
    # normcase() makes the containment check case-insensitive on Windows (C:\ vs
    # c:\) while realpath() resolves symlinks so a descendant symlink cannot escape.
    cwd_root = os.path.normcase(os.path.realpath(os.getcwd()))
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
