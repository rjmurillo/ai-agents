#!/usr/bin/env python3
"""Validate Claude Code skill YAML frontmatter against schema requirements.

Enforces frontmatter constraints for SKILL.md files:
- YAML syntax (delimiters, indentation)
- Required fields: name, description
- Name format: lowercase alphanumeric + hyphens, max 64 chars (regex: ^[a-z0-9-]{1,64}$)
- Description: non-empty, max 1024 chars, no XML tags
- Model: valid model identifiers (aliases or dated snapshots)
- Allowed-tools: valid Claude Code tool names (if present)

Runs on staged .claude/skills/*/SKILL.md files during pre-commit.

Exit codes follow ADR-035:
    0 - Success: All skill frontmatter is valid
    1 - Error: Frontmatter validation failed (CI mode only)
    2 - Config error (path not found)

Related: ADR-040 (Skill Frontmatter Standardization), Issue #4
Reference: .agents/analysis/claude-code-skill-frontmatter-2026.md
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Valid model identifiers (from .agents/analysis/claude-code-skill-frontmatter-2026.md)
VALID_MODEL_ALIASES: frozenset[str] = frozenset(
    {
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-sonnet-4-0",
        "claude-3-7-sonnet-latest",
        # CLI shortcuts
        "opus",
        "sonnet",
        "haiku",
    }
)

# Dated snapshot pattern: claude-{tier}-4-5-YYYYMMDD
DATED_SNAPSHOT_PATTERN: re.Pattern[str] = re.compile(
    r"^claude-(opus|sonnet|haiku)-4-5-\d{8}$"
)

# Known Claude Code tools (partial list)
VALID_TOOLS: frozenset[str] = frozenset(
    {
        "bash",
        "view",
        "edit",
        "create",
        "grep",
        "glob",
        "task",
        "web_search",
        "web_fetch",
        "mcp",
        "playwright-browser",
        "github-mcp-server",
        "deepwiki",
        "serena",
        "forgetful",
    }
)

# XML tag detection pattern
_XML_TAG_PATTERN: re.Pattern[str] = re.compile(r"<[^>]+>")


@dataclass
class FrontmatterResult:
    """Result of parsing YAML frontmatter."""

    is_valid: bool = True
    frontmatter: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class FileValidationResult:
    """Result of validating a single SKILL.md file."""

    file_path: str
    passed: bool
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


def parse_frontmatter(content: str) -> FrontmatterResult:
    """Parse and validate YAML frontmatter structure.

    This parser handles simple key-value pairs and basic arrays.
    It does NOT support quoted strings with embedded colons, complex nested
    structures, YAML anchors/aliases, or advanced features.
    """
    result = FrontmatterResult()

    if not content.startswith("---"):
        result.is_valid = False
        result.errors.append("Frontmatter must start with '---' on line 1")
        return result

    lines = content.split("\n")
    frontmatter_end = -1

    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            frontmatter_end = i
            break

    if frontmatter_end == -1:
        result.is_valid = False
        result.errors.append("Frontmatter must end with '---'")
        return result

    frontmatter_content = "\n".join(lines[1:frontmatter_end])

    # Check for tab characters
    if "\t" in frontmatter_content:
        result.is_valid = False
        result.errors.append(
            "Frontmatter must use spaces for indentation (tabs not allowed)"
        )

    # Parse YAML using simple key-value parsing
    frontmatter: dict[str, str] = {}
    current_key: str | None = None
    current_value = ""
    in_multiline = False
    key_pattern = re.compile(r"^([a-zA-Z0-9_-]+):\s*(.*)$")

    for line in frontmatter_content.split("\n"):
        if not line.strip():
            continue

        key_match = key_pattern.match(line)
        if key_match:
            if current_key is not None:
                frontmatter[current_key] = current_value.strip()

            current_key = key_match.group(1)
            current_value = key_match.group(2)

            if current_value in (">", "|"):
                in_multiline = True
                current_value = ""
            else:
                in_multiline = False
        elif in_multiline:
            trimmed = line.lstrip()
            if current_value:
                current_value += " " + trimmed
            else:
                current_value = trimmed
        elif line.lstrip().startswith("-"):
            array_value = line.lstrip()[1:].strip()
            if current_value:
                current_value += "," + array_value
            else:
                current_value = array_value

    if current_key is not None:
        frontmatter[current_key] = current_value.strip()

    result.frontmatter = frontmatter
    return result


# ---------------------------------------------------------------------------
# Field validators
# ---------------------------------------------------------------------------

_NAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9-]{1,64}$")


def validate_name(name: str | None) -> list[str]:
    """Validate the 'name' field in frontmatter."""
    errors: list[str] = []

    if not name or not name.strip():
        errors.append("Missing required field: 'name'")
        return errors

    if not _NAME_PATTERN.match(name):
        reason_parts: list[str] = []

        if re.search(r"[A-Z]", name):
            reason_parts.append("contains uppercase letters")
        if re.search(r"[^a-z0-9-]", name):
            reason_parts.append(
                "contains invalid characters (only a-z, 0-9, hyphen allowed)"
            )
        if len(name) > 64:
            reason_parts.append(f"exceeds 64 characters (found {len(name)})")
        if len(name) == 0:
            reason_parts.append("is empty")

        reason = f" ({', '.join(reason_parts)})" if reason_parts else ""
        errors.append(
            f"Invalid name format: '{name}'{reason} (must match ^[a-z0-9-]{{1,64}}$)"
        )

    return errors


def validate_description(description: str | None) -> list[str]:
    """Validate the 'description' field in frontmatter."""
    errors: list[str] = []

    if not description or not description.strip():
        errors.append("Missing required field: 'description'")
        return errors

    if len(description) > 1024:
        errors.append(
            f"Description exceeds 1024 characters (found {len(description)})"
        )

    if _XML_TAG_PATTERN.search(description):
        errors.append("Description contains XML tags (not allowed)")

    return errors


def validate_model(model: str | None) -> list[str]:
    """Validate the 'model' field in frontmatter (optional)."""
    errors: list[str] = []

    if not model or not model.strip():
        return errors

    if model in VALID_MODEL_ALIASES:
        return errors

    if DATED_SNAPSHOT_PATTERN.match(model):
        return errors

    errors.append(
        f"Invalid model identifier: '{model}' "
        "(use aliases like 'claude-sonnet-4-5' or "
        "dated snapshots like 'claude-sonnet-4-5-20250929')"
    )
    return errors


def validate_allowed_tools(allowed_tools: str | None) -> list[str]:
    """Validate the 'allowed-tools' field in frontmatter (optional)."""
    errors: list[str] = []

    if not allowed_tools or not allowed_tools.strip():
        return errors

    tools = [t.strip() for t in allowed_tools.split(",") if t.strip()]

    invalid_tools: list[str] = []
    for tool in tools:
        clean_tool = re.sub(r"^\s*-\s*", "", tool)

        # Allow wildcards
        if "*" in clean_tool:
            continue

        if clean_tool not in VALID_TOOLS:
            invalid_tools.append(clean_tool)

    if invalid_tools:
        errors.append(f"Unknown tools in allowed-tools: {', '.join(invalid_tools)}")

    return errors


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def get_staged_skill_files() -> list[Path]:
    """Get staged SKILL.md files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0:
        return []

    files: list[Path] = []
    for line in result.stdout.strip().split("\n"):
        if re.search(r"\.claude/skills/.*/SKILL\.md$", line):
            path = Path(line)
            if path.exists():
                files.append(path)
    return files


def get_skill_files(
    path: str,
    staged_only: bool = False,
    changed_files: list[str] | None = None,
) -> list[Path]:
    """Get list of SKILL.md files to validate based on parameters."""
    if changed_files:
        skill_files = [
            f for f in changed_files
            if re.search(r"\.claude/skills/.*/SKILL\.md$", f)
        ]
        if not skill_files:
            print("No SKILL.md files in changed files list. "
                  "Skipping frontmatter validation.")
            return []

        return [Path(f) for f in skill_files if Path(f).exists()]

    if staged_only:
        files = get_staged_skill_files()
        if not files:
            print("No SKILL.md files staged. Skipping frontmatter validation.")
        return files

    target = Path(path)
    if not target.exists():
        print(f"Path not found: {path}. Skipping frontmatter validation.")
        return []

    if target.is_file():
        if target.name == "SKILL.md":
            return [target]
        print(f"Path is not a SKILL.md file: {path}")
        return []

    return sorted(target.rglob("SKILL.md"))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_skill_file(file_path: Path) -> FileValidationResult:
    """Validate a single SKILL.md file's frontmatter."""
    try:
        relative = file_path.relative_to(Path.cwd())
    except ValueError:
        relative = file_path

    print(f"  Checking: {relative}")

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        content = ""

    if not content:
        print("    [FAIL] File is empty or unreadable")
        return FileValidationResult(
            file_path=str(relative),
            passed=False,
            errors=["File is empty or unreadable"],
        )

    yaml_result = parse_frontmatter(content)
    all_errors: list[str] = list(yaml_result.errors)

    if yaml_result.is_valid and yaml_result.frontmatter:
        all_errors.extend(validate_name(yaml_result.frontmatter.get("name")))
        all_errors.extend(
            validate_description(yaml_result.frontmatter.get("description"))
        )

        if "model" in yaml_result.frontmatter:
            all_errors.extend(validate_model(yaml_result.frontmatter["model"]))

        if "allowed-tools" in yaml_result.frontmatter:
            all_errors.extend(
                validate_allowed_tools(yaml_result.frontmatter["allowed-tools"])
            )

    if not all_errors:
        print("    [PASS] Frontmatter is valid")
        return FileValidationResult(file_path=str(relative), passed=True)

    print("    [FAIL] Frontmatter validation failed:")
    for error in all_errors:
        print(f"      - {error}")

    return FileValidationResult(
        file_path=str(relative), passed=False, errors=all_errors
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Validate Claude Code skill YAML frontmatter against schema.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("SKILL_PATH", ".claude/skills"),
        help="Path to SKILL.md file or directory (env: SKILL_PATH, default: .claude/skills)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit non-zero on validation failure (env: CI)",
    )
    parser.add_argument(
        "--staged-only",
        action="store_true",
        default=os.environ.get("STAGED_ONLY", "").lower() in ("true", "1"),
        help="Only check staged files (env: STAGED_ONLY)",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Explicit list of file paths to check (for CI workflow)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    print("Validating skill frontmatter...")

    files_to_check = get_skill_files(
        path=args.path,
        staged_only=args.staged_only,
        changed_files=args.changed_files,
    )

    if not files_to_check:
        print("No SKILL.md files found to validate.")
        return 0

    print(f"Found {len(files_to_check)} SKILL.md file(s) to validate.")
    print()

    pass_count = 0
    fail_count = 0
    results: list[FileValidationResult] = []

    for file_path in files_to_check:
        result = validate_skill_file(file_path)
        results.append(result)
        if result.passed:
            pass_count += 1
        else:
            fail_count += 1

    print()
    print("=" * 40)
    print("Validation Summary")
    print("=" * 40)
    print(f"  Total:  {len(files_to_check)}")
    print(f"  Passed: {pass_count}")
    print(f"  Failed: {fail_count}")
    print()

    if fail_count > 0:
        print("Fix SKILL.md frontmatter and retry commit.")
        print("See: .agents/analysis/claude-code-skill-frontmatter-2026.md")

        if args.ci:
            return 1

        print()
        print("Validation failed, but not running in CI mode. Continuing...")

    else:
        print("All skill frontmatter validated successfully!")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
