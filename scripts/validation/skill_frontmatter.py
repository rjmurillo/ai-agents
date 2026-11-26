#!/usr/bin/env python3
# ruff: noqa: E402
"""Validate skill YAML frontmatter against the agentskills.io specification.

Spec: https://agentskills.io/specification. Each check reads the parsed YAML
value, not a flattened line view, so quoting and block scalars count as YAML
counts them.

- YAML syntax (delimiters, indentation, a mapping)
- name: required string, 1-64 characters, lowercase letters, digits, and
  hyphens, no leading, trailing, or consecutive hyphen, equal to the skill
  directory name
- description: required string, 1-1024 characters; no XML tags, which the
  Claude platform rejects in skill metadata
- compatibility: when present, a string of 1-500 characters
- license: when present, a string

The frontmatter is read with YAML 1.2 core-schema scalars, the schema the spec
assumes: unquoted `on`, `off`, `yes`, `no`, and dates stay strings, while
`true`, `false`, numbers, and null keep their types.
- allowed-tools: a space-separated string per the spec; comma-separated strings
  and YAML lists, the forms Claude Code and this repository's generators use,
  are accepted too. A tool containing `*` passes as a wildcard; any other tool
  is judged by its name before any `(...)` argument.
- model: valid model identifiers (aliases or dated snapshots)

Not checked here: top-level keys outside the spec and nested ``metadata``
values. This repository's skills carry harness fields and capability mappings
on purpose; skillforge's ``conformance.py --profile project`` reports those as
declared deviations.

Runs on staged .claude/skills/*/SKILL.md files during pre-commit.

Exit codes follow ADR-035:
    0 - Success: All skill frontmatter is valid
    1 - Error: Frontmatter validation failed (CI mode only)
    2 - Config error (path not found)

Related: ADR-040 (Skill Frontmatter Standardization), Issue #4
Reference: .project-toolkit/analysis/claude-code-skill-frontmatter-2026.md
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_PACKAGE_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _VALIDATION_PACKAGE_SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import yaml

from scripts.hook_utilities.frontmatter_block import (
    FrontmatterStatus,
    decode_frontmatter_yaml,
    split_frontmatter,
)
from scripts.validation import skill_corpus as _skill_corpus
from scripts.validation.models import ValidationResult

# Valid model identifiers.
# Source: .project-toolkit/analysis/claude-code-skill-frontmatter-2026.md
# Opus and Sonnet are pinned to the 4.6 family; the 4.5 aliases are no longer
# accepted. Haiku stays at 4.5 because no 4.6 Haiku has shipped. Older
# back-compat (4.0, 3.7) is retained until those skills are migrated.
VALID_MODEL_ALIASES: frozenset[str] = frozenset(
    {
        # Current (Claude 4.6 family for Opus and Sonnet, per environment as of 2026-04-13)
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",  # Haiku stayed at 4.5; current Haiku alias
        # Older back-compat (pre-4.5)
        "claude-sonnet-4-0",
        "claude-3-7-sonnet-latest",
        # CLI shortcuts
        "opus",
        "sonnet",
        "haiku",
    }
)

# Dated snapshot pattern: claude-{opus|sonnet}-4-6-YYYYMMDD or claude-haiku-4-5-YYYYMMDD.
# Haiku is pinned to 4.5; Opus and Sonnet are pinned to 4.6.
DATED_SNAPSHOT_PATTERN: re.Pattern[str] = re.compile(
    r"^claude-((opus|sonnet)-4-6|haiku-4-5)-\d{8}$"
)

# Known tool names accepted in `allowed-tools`.
# Skills under .claude/skills/ are Claude Code skills, which use canonical
# PascalCase names (Read, Write, Bash, ...). The lowercase entries are kept
# for Copilot CLI compatibility (gh copilot uses bash, view, edit, create).
# Source: .project-toolkit/analysis/claude-code-skill-frontmatter-2026.md (section 5.4).
# Parenthesized forms like "Bash(pwsh:*)" pass through `_tool_is_known`, which
# accepts any tool containing `*` and otherwise checks the name before `(`.
VALID_TOOLS: frozenset[str] = frozenset(
    {
        # Claude Code canonical tools (PascalCase)
        "Bash",
        "Edit",
        "Glob",
        "Grep",
        "Read",
        "Write",
        "Task",
        "WebFetch",
        "WebSearch",
        "NotebookEdit",
        "TodoWrite",
        "AskUserQuestion",
        "ExitPlanMode",
        "Skill",
        "SlashCommand",
        # Copilot CLI tools (lowercase)
        "bash",
        "view",
        "edit",
        "create",
        "grep",
        "glob",
        "task",
        "web_search",
        "web_fetch",
        # MCP server roots (skills typically use wildcards like mcp__serena__*)
        "mcp",
        "playwright-browser",
        "github-mcp-server",
        "deepwiki",
        "serena",
    }
)

# MCP tool names: `mcp__<server>__<tool>` (Claude Code) and `<server>/<tool>`
# (Copilot CLI). The server set varies by install, so any server passes except
# a retired one, which no harness can grant (issue #5574).
_MCP_TOOL_PATTERN: re.Pattern[str] = re.compile(r"^mcp__([A-Za-z0-9_-]+)__[A-Za-z0-9_-]+$")
_COPILOT_MCP_TOOL_PATTERN: re.Pattern[str] = re.compile(r"^([A-Za-z0-9_-]+)/[A-Za-z0-9_-]+$")
RETIRED_MCP_SERVERS: frozenset[str] = frozenset({"forgetful"})

NAME_MAX_LENGTH = 64
DESCRIPTION_MAX_LENGTH = 1024
COMPATIBILITY_MAX_LENGTH = 500


# A safe loader whose implicit scalars follow the YAML 1.2 core schema. PyYAML's
# default resolvers follow YAML 1.1, which reads unquoted `on`, `off`, `yes`, and
# `no` as booleans and ISO dates as dates. Under YAML 1.2 those are strings, so
# `name: on` is a valid skill name. Built with type() because PyYAML ships no
# type stubs, and mypy refuses a class statement that subclasses an Any base.
_Yaml12Loader: Any = type("_Yaml12Loader", (yaml.SafeLoader,), {})


_YAML11_ONLY_TAGS = {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp"}
_Yaml12Loader.yaml_implicit_resolvers = {
    first: [(tag, pattern) for tag, pattern in resolvers if tag not in _YAML11_ONLY_TAGS]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Yaml12Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


# XML tag detection pattern
_XML_TAG_PATTERN: re.Pattern[str] = re.compile(r"<[^>]+>")
_SKILL_FILE_PATTERN: re.Pattern[str] = re.compile(
    r"(?:^|/)(?:\.claude|src/claude|src/copilot-cli)/skills/[^/]+/SKILL\.md$",
    re.IGNORECASE,
)

# The two skill trees `_SKILL_FILE_PATTERN` matches. A default full scan covers
# both, so all three discovery paths (staged, changed-files, full scan) answer
# the same question. Before issue #4015 the full scan fell through to a single
# `--path` default of `.claude/skills` and measured 98 of 209 SKILL.md bodies,
# then printed "All skill frontmatter validated successfully!", a sentence about
# a corpus it never opened. This script has no lefthook or workflow caller, so
# the default full scan is its only invocation path.
# ADR-119: shipped skills are directory links under .claude/skills, which rglob
# does not follow, so they are read at src/claude/skills.
_SKILL_TREE_PREFIXES: tuple[str, ...] = (
    ".claude/skills",
    "src/claude/skills",
    "src/copilot-cli/skills",
)

# Copilot CLI rejects non-string values for this skill field at load time.
STRING_ONLY_FIELDS: frozenset[str] = frozenset({"argument-hint"})


@dataclass
class FrontmatterResult(ValidationResult):
    """Result of parsing YAML frontmatter.

    Extends ValidationResult with parsed frontmatter data.
    is_valid is derived from the errors list (no errors = valid).

    ``frontmatter`` is the flat string view every existing caller uses. It is
    line-based, so a nested mapping collapses to an empty string and the keys
    under it are dropped. ``typed`` is the full YAML structure, which this
    parser already computes for validation; callers that must see nested keys
    read it instead of re-parsing the block (issue #2840).

    ``typed`` is keyed by ``object`` because YAML allows non-string scalars as
    keys, so ``true:`` or ``1:`` parses to a bool or int key. Narrowing the
    annotation to ``str`` would be a lie, and normalising those keys to strings
    would let one contrived file collide two distinct keys and drop a pin the
    gate exists to find.
    """

    frontmatter: dict[str, str] = field(default_factory=dict)
    typed: dict[object, object] = field(default_factory=dict)


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

    The fence comes from ``scripts/hook_utilities/frontmatter_block.py`` and the
    typed view loads through ``_Yaml12Loader`` (YAML 1.2 core schema, last
    duplicate key wins). The flat ``frontmatter`` view is a line-based reader
    for simple key-value pairs and basic arrays. It does NOT support quoted
    strings with embedded colons, complex nested structures, YAML anchors or
    aliases, or advanced features.
    """
    result = FrontmatterResult()

    split = split_frontmatter(content)
    if split.status is FrontmatterStatus.ABSENT:
        result.errors.append("Frontmatter must start with '---' on line 1")
        return result
    if split.status is FrontmatterStatus.UNTERMINATED:
        result.errors.append("Frontmatter must end with '---'")
        return result

    # The payload runs from the line after the opening fence to the closing
    # fence. The fence rule lets the opening fence absorb whitespace-only lines,
    # so slice from the first newline instead of using ``split.raw``: a
    # tab-only line there must still reach the tab check and the YAML load.
    frontmatter_content = content[split.open_end : split.raw_end].removesuffix("\n")

    # Check for tab characters
    if "\t" in frontmatter_content:
        result.errors.append("Frontmatter must use spaces for indentation (tabs not allowed)")

    try:
        loaded = (
            decode_frontmatter_yaml(
                frontmatter_content, yaml, allow_duplicate_keys=True, loader=_Yaml12Loader
            )
            or {}
        )
    except yaml.YAMLError as exc:
        result.errors.append(f"Frontmatter YAML parse error: {exc}")
        loaded = {}
    if not isinstance(loaded, dict):
        result.errors.append("Frontmatter must be a YAML mapping")
        loaded = {}
    typed_frontmatter: dict[object, object] = dict(loaded)

    for field_name in STRING_ONLY_FIELDS:
        if field_name in typed_frontmatter and not isinstance(typed_frontmatter[field_name], str):
            result.errors.append(f"{field_name} must be a string")

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
    result.typed = typed_frontmatter
    return result


# ---------------------------------------------------------------------------
# Field validators
# ---------------------------------------------------------------------------

# agentskills.io name rule: lowercase letters and digits in hyphen-separated
# runs, so no leading, trailing, or consecutive hyphen.
_NAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _type_name(value: object) -> str:
    return "null" if value is None else type(value).__name__


def validate_name(name: object, directory: str | None = None) -> list[str]:
    """Validate the 'name' field against the agentskills.io name rules."""
    if name is None or (isinstance(name, str) and not name.strip()):
        return ["Missing required field: 'name'"]
    if not isinstance(name, str):
        return [f"name must be a string, got {_type_name(name)}"]
    errors: list[str] = []
    if len(name) > NAME_MAX_LENGTH:
        errors.append(f"name exceeds {NAME_MAX_LENGTH} characters (found {len(name)})")
    if not _NAME_PATTERN.match(name):
        reasons = []
        if re.search(r"[A-Z]", name):
            reasons.append("contains uppercase letters")
        if re.search(r"[^a-zA-Z0-9-]", name):
            reasons.append("contains characters other than a-z, 0-9, and hyphen")
        if name.startswith("-") or name.endswith("-"):
            reasons.append("starts or ends with a hyphen")
        if "--" in name:
            reasons.append("contains consecutive hyphens")
        detail = f" ({', '.join(reasons)})" if reasons else ""
        errors.append(f"Invalid name format: '{name}'{detail}")
    if directory is not None and name != directory:
        errors.append(f"name '{name}' must match its directory name '{directory}'")
    return errors


def validate_description(description: object) -> list[str]:
    """Validate the 'description' field: a 1-1024 character string, no XML tags."""
    if description is None or (isinstance(description, str) and not description.strip()):
        return ["Missing required field: 'description'"]
    if not isinstance(description, str):
        return [f"description must be a string, got {_type_name(description)}"]
    errors: list[str] = []
    if len(description) > DESCRIPTION_MAX_LENGTH:
        errors.append(
            f"Description exceeds {DESCRIPTION_MAX_LENGTH} characters (found {len(description)})"
        )
    if _XML_TAG_PATTERN.search(description):
        errors.append("Description contains XML tags (not allowed)")
    return errors


def validate_compatibility(compatibility: object) -> list[str]:
    """Validate the optional 'compatibility' field: a 1-500 character string."""
    if not isinstance(compatibility, str):
        return [f"compatibility must be a string, got {_type_name(compatibility)}"]
    if not compatibility.strip():
        return ["compatibility is empty; omit the field instead"]
    if len(compatibility) > COMPATIBILITY_MAX_LENGTH:
        return [
            f"compatibility exceeds {COMPATIBILITY_MAX_LENGTH} characters "
            f"(found {len(compatibility)})"
        ]
    return []


def validate_license(license_value: object) -> list[str]:
    """Validate the optional 'license' field: a string, as the spec defines it."""
    if isinstance(license_value, str):
        return []
    return [f"license must be a string, got {_type_name(license_value)}"]


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
        "(use aliases like 'claude-sonnet-4-6' or "
        "dated snapshots like 'claude-sonnet-4-6-20251015')"
    )
    return errors


def split_allowed_tools(value: str) -> list[str]:
    """Split an allowed-tools string on whitespace and commas outside parentheses.

    The spec form is space-separated (`Bash(git:*) Read`); Claude Code also
    accepts commas (`Read, Grep`). A space inside `Bash(git status:*)` belongs
    to the argument, so it does not split.
    """
    tools: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        if depth == 0 and (char.isspace() or char == ","):
            if current:
                tools.append("".join(current))
                current = []
            continue
        current.append(char)
    if current:
        tools.append("".join(current))
    return tools


def _tool_is_known(tool: str) -> bool:
    if "*" in tool:
        return True
    base = tool.split("(", 1)[0]
    if base in VALID_TOOLS:
        return True
    match = _MCP_TOOL_PATTERN.match(base) or _COPILOT_MCP_TOOL_PATTERN.match(base)
    if match is None:
        return False
    return match.group(1) not in RETIRED_MCP_SERVERS


def validate_allowed_tools(allowed_tools: object) -> list[str]:
    """Validate the optional 'allowed-tools' field: a string or a list of tool names."""
    if allowed_tools is None:
        return []
    if isinstance(allowed_tools, str):
        tools = split_allowed_tools(allowed_tools)
    elif isinstance(allowed_tools, list) and all(isinstance(t, str) for t in allowed_tools):
        tools = [t.strip() for t in allowed_tools if t.strip()]
    else:
        return ["allowed-tools must be a space-separated string or a list of tool names"]
    unknown = [tool for tool in tools if not _tool_is_known(tool)]
    if unknown:
        return [f"Unknown tools in allowed-tools: {', '.join(unknown)}"]
    return []


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _normalize_skill_path(path: str, root: Path | None = None) -> str:
    """Return a repo-relative, slash-normalized path when possible."""
    candidate = Path(path)
    if root is not None:
        try:
            candidate = candidate.resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            pass
    return str(candidate).replace("\\", "/")


def _is_skill_file_path(path: str, root: Path | None = None) -> bool:
    """Return true for Claude skill files and Copilot CLI skill mirrors."""
    return _SKILL_FILE_PATTERN.fullmatch(_normalize_skill_path(path, root)) is not None


def get_staged_skill_files() -> list[Path]:
    """Get staged SKILL.md files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0:
        return []

    files: list[Path] = []
    for line in result.stdout.strip().split("\n"):
        if _is_skill_file_path(line):
            path = Path(line)
            if path.exists():
                files.append(path)
    return files


def default_corpus_files() -> list[Path]:
    """Return every SKILL.md under the trees named in ``_SKILL_TREE_PREFIXES``.

    Discovery lives in ``skill_corpus.corpus_files``. Module globals are read
    at call time so tests can repoint ``_PROJECT_ROOT``.
    """
    return _skill_corpus.corpus_files(_PROJECT_ROOT, _SKILL_TREE_PREFIXES)


def default_corpus_summary() -> str:
    """One line naming the trees a default full scan measures, and any absent."""
    return _skill_corpus.corpus_summary(_PROJECT_ROOT, _SKILL_TREE_PREFIXES)


def get_skill_files(
    path: str | None,
    staged_only: bool = False,
    changed_files: list[str] | None = None,
) -> list[Path]:
    """Get list of SKILL.md files to validate based on parameters.

    ``path`` is the explicit narrowing override. When it is None (the default),
    the scan covers every tree in ``_SKILL_TREE_PREFIXES``.
    """
    if changed_files:
        root = Path(path) if path else None
        skill_files = [f for f in changed_files if _is_skill_file_path(f, root)]
        if not skill_files:
            print("No SKILL.md files in changed files list. Skipping frontmatter validation.")
            return []

        return [Path(f) for f in skill_files if Path(f).exists()]

    if staged_only:
        files = get_staged_skill_files()
        if not files:
            print("No SKILL.md files staged. Skipping frontmatter validation.")
        return files

    if path is None:
        return default_corpus_files()

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


def _relative_display(file_path: Path) -> Path:
    """Repo-relative path for display; cwd-relative, then absolute, as fallbacks.

    ``_PROJECT_ROOT`` comes first because the default corpus is anchored there,
    so a run from a subdirectory would otherwise print absolute paths, and a run
    from ``/`` would print a slash-stripped path that resolves to nothing.
    """
    for base in (_PROJECT_ROOT, Path.cwd()):
        try:
            return file_path.relative_to(base)
        except ValueError:
            continue
    return file_path


def validate_typed_fields(typed: dict[object, object], directory: str) -> list[str]:
    """Run the field checks on parsed YAML values."""
    errors = validate_name(typed.get("name"), directory)
    errors.extend(validate_description(typed.get("description")))
    if "compatibility" in typed:
        errors.extend(validate_compatibility(typed["compatibility"]))
    if "license" in typed:
        errors.extend(validate_license(typed["license"]))
    if "allowed-tools" in typed:
        errors.extend(validate_allowed_tools(typed["allowed-tools"]))
    model = typed.get("model")
    if model is not None:
        errors.extend(
            validate_model(model) if isinstance(model, str) else ["model must be a string"]
        )
    return errors


def validate_skill_file(file_path: Path) -> FileValidationResult:
    """Validate a single SKILL.md file's frontmatter."""
    relative = _relative_display(file_path)

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

    if yaml_result.is_valid and yaml_result.typed:
        all_errors.extend(validate_typed_fields(yaml_result.typed, file_path.parent.name))

    if not all_errors:
        print("    [PASS] Frontmatter is valid")
        return FileValidationResult(file_path=str(relative), passed=True)

    print("    [FAIL] Frontmatter validation failed:")
    for error in all_errors:
        print(f"      - {error}")

    return FileValidationResult(file_path=str(relative), passed=False, errors=all_errors)


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
        default=os.environ.get("SKILL_PATH"),
        help=(
            "Narrow the scan to one SKILL.md file or directory "
            "(env: SKILL_PATH, default: every tree in _SKILL_TREE_PREFIXES)"
        ),
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
    if args.path is None and not args.staged_only and not args.changed_files:
        print(default_corpus_summary())

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
        print("See: .project-toolkit/analysis/claude-code-skill-frontmatter-2026.md")

        if args.ci:
            return 1

        print()
        print("Validation failed, but not running in CI mode. Continuing...")

    else:
        print("All skill frontmatter validated successfully!")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
