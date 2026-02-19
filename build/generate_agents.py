#!/usr/bin/env python3
"""Generate platform-specific agent files from shared sources.

Reads shared agent source files from templates/agents/*.shared.md and generates
platform-specific outputs for VS Code and Copilot CLI. This enables maintaining
a single source of truth for agents that differ only in frontmatter.

The script transforms:
- YAML frontmatter (model field, name field, tools array)
- Handoff syntax (#runSubagent vs /agent)
- Memory prefix placeholders

EXIT CODES:
  0  - Success (or validation passed)
  1  - Logic error (drift detected, validation failed, generation errors)
  2  - Configuration error (missing paths, no platform configs)

See: ADR-035 Exit Code Standardization

This is a Python port of Generate-Agents.ps1 following ADR-042 migration.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Add build directory to path for imports
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from generate_agents_common import (  # noqa: E402
    convert_frontmatter_for_platform,
    convert_handoff_syntax,
    convert_memory_prefix,
    expand_toolset_references,
    format_frontmatter_yaml,
    is_path_within_root,
    parse_simple_frontmatter,
    read_toolset_definitions,
    read_yaml_frontmatter,
)


def read_platform_config(config_path: Path) -> dict[str, object] | None:
    """Read platform configuration from a YAML file.

    Parses simple YAML with top-level keys and nested sections.
    """
    if not config_path.exists():
        print(f"Error: Platform config not found: {config_path}", file=sys.stderr)
        return None

    content = config_path.read_text(encoding="utf-8")
    config: dict[str, object] = {}
    current_section: str | None = None

    for line in re.split(r"\r?\n", content):
        if re.match(r"^\s*#", line) or not line.strip():
            continue

        # Section header (key with no value)
        section_match = re.match(r"^(\w+):\s*$", line)
        if section_match:
            current_section = section_match.group(1)
            config[current_section] = {}
            continue

        # Nested key-value (indented)
        nested_match = re.match(r"^\s+(\w+):\s*(.*)$", line)
        if nested_match:
            key = nested_match.group(1)
            value = _parse_yaml_value(nested_match.group(2).strip())
            if current_section:
                section_value = config.get(current_section)
                if isinstance(section_value, dict):
                    section_value[key] = value
            continue

        # Top-level key-value
        top_match = re.match(r"^(\w+):\s*(.+)$", line)
        if top_match:
            key = top_match.group(1)
            value = _parse_yaml_value(top_match.group(2).strip())
            config[key] = value
            current_section = None

    return config


def _parse_yaml_value(raw: str) -> object:
    """Parse a simple YAML scalar value."""
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw in ("null", ""):
        return None
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    return raw


def generate_agents(
    templates_path: Path,
    output_root: Path,
    repo_root: Path,
    validate: bool = False,
    what_if: bool = False,
) -> int:
    """Main generation logic. Returns exit code."""
    mode = "Validate" if validate else ("WhatIf" if what_if else "Generate")
    print()
    print("=== Agent Generation ===")
    print(f"Templates Path: {templates_path}")
    print(f"Output Root: {output_root}")
    print(f"Mode: {mode}")
    print()

    start_time = time.monotonic()

    # Load platform configurations
    platforms_path = templates_path / "platforms"
    platforms: list[dict[str, object]] = []

    if platforms_path.is_dir():
        for config_file in sorted(platforms_path.glob("*.yaml")):
            config = read_platform_config(config_file)
            if config:
                platforms.append(config)

    if not platforms:
        print(f"Error: No platform configurations found in {platforms_path}", file=sys.stderr)
        return 2

    print(f"Loaded {len(platforms)} platform configuration(s)")

    # Load toolset definitions
    toolsets_file = templates_path / "toolsets.yaml"
    toolsets: dict[str, dict[str, object]] = {}
    if toolsets_file.exists():
        toolsets = read_toolset_definitions(toolsets_file)
        print(f"Loaded {len(toolsets)} toolset definition(s)")

    # Find shared source files
    agents_path = templates_path / "agents"
    shared_files = sorted(agents_path.glob("*.shared.md"))

    if not shared_files:
        print(f"Error: No shared source files found in {agents_path}", file=sys.stderr)
        return 1

    print(f"Found {len(shared_files)} shared source file(s)")
    print()

    generated = 0
    errors = 0
    differences: list[str] = []

    for shared_file in shared_files:
        agent_name = shared_file.stem.replace(".shared", "")
        print(f"Processing: {agent_name}")

        content = shared_file.read_text(encoding="utf-8")
        parsed = read_yaml_frontmatter(content)
        if not parsed:
            print(f"  Error: Failed to parse frontmatter for {agent_name}", file=sys.stderr)
            errors += 1
            continue

        frontmatter = parse_simple_frontmatter(parsed["frontmatter_raw"])
        body = parsed["body"]

        for platform in platforms:
            platform_name = str(platform.get("platform", ""))
            output_dir_relative = str(platform.get("outputDir", ""))

            # Remove src/ prefix if present since output_root is already src/
            prefix_match = re.match(r"^src/(.*)$", output_dir_relative)
            if prefix_match:
                output_dir_relative = prefix_match.group(1)

            output_dir = output_root / output_dir_relative
            file_ext = str(platform.get("fileExtension", ".md"))
            output_file = output_dir / f"{agent_name}{file_ext}"

            # Security check
            if not is_path_within_root(str(output_file), str(repo_root)):
                print(
                    f"  Error: Output path escapes repository root: {output_file}",
                    file=sys.stderr,
                )
                errors += 1
                continue

            transformed_fm = convert_frontmatter_for_platform(
                frontmatter, platform, agent_name
            )

            # Expand toolset references
            tools_value = transformed_fm.get("tools")
            if (
                toolsets
                and isinstance(tools_value, str)
                and "$toolset:" in tools_value
            ):
                transformed_fm["tools"] = expand_toolset_references(
                    tools_value, toolsets, platform_name
                )

            # Transform body
            handoff_syntax = str(platform.get("handoffSyntax", ""))
            memory_prefix = str(platform.get("memoryPrefix", "cloudmcp-manager/"))

            transformed_body = convert_handoff_syntax(body, handoff_syntax)
            transformed_body = convert_memory_prefix(transformed_body, memory_prefix)

            # Build output content with CRLF line endings
            fm_yaml = format_frontmatter_yaml(transformed_fm)
            output_content = f"---\n{fm_yaml}\n---\n{transformed_body}"
            output_content = output_content.replace("\r\n", "\n").replace("\n", "\r\n")

            if validate:
                _handle_validate(output_file, output_content, platform_name, differences)
            elif what_if:
                print(f"  Would generate: {output_file}")
            else:
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file.write_bytes(output_content.encode("utf-8"))
                print(f"  Generated: {platform_name}")
                generated += 1

    duration = time.monotonic() - start_time
    print()
    print("=== Summary ===")
    print(f"Duration: {duration:.2f}s")

    if validate:
        return _report_validation(differences)

    if what_if:
        print("Dry run complete. No files were written.")
        return 0

    print(f"Generated: {generated} file(s)")
    if errors > 0:
        print(f"Errors: {errors}")
        return 1

    print()
    return 0


def _handle_validate(
    output_file: Path,
    output_content: str,
    platform_name: str,
    differences: list[str],
) -> None:
    """Compare generated content with existing committed file."""
    if output_file.exists():
        existing = output_file.read_text(encoding="utf-8")
        normalized_existing = existing.replace("\r\n", "\n")
        normalized_generated = output_content.replace("\r\n", "\n")

        if normalized_existing != normalized_generated:
            print(f"  DIFF: {platform_name} output differs from committed file")
            differences.append(str(output_file))
        else:
            print(f"  OK: {platform_name}")
    else:
        print(f"  MISSING: {output_file}")
        differences.append(str(output_file))


def _report_validation(differences: list[str]) -> int:
    """Report validation results and return exit code."""
    if differences:
        print()
        print(f"VALIDATION FAILED: {len(differences)} file(s) differ from generated output")
        print()
        print("Files with differences:")
        for diff in differences:
            print(f"  - {diff}")
        print()
        print("To fix: Run 'python3 build/generate_agents.py' and commit the changes")
        return 1

    print("VALIDATION PASSED: All generated files match committed files")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate platform-specific agent files from shared sources.",
    )
    parser.add_argument(
        "--templates-path",
        type=Path,
        default=None,
        help="Path to templates directory. Defaults to templates/ in repo root.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Root directory for generated output. Defaults to src/ in repo root.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="CI mode: regenerate and compare to committed files.",
    )
    parser.add_argument(
        "--what-if",
        action="store_true",
        help="Dry-run mode: show what would be generated without writing.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for agent generation."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve repo root: script is in build/, go up one level
    # When paths are explicitly provided, derive repo root from templates path
    if args.templates_path:
        repo_root = args.templates_path.resolve().parent
    else:
        repo_root = _SCRIPT_DIR.parent

    templates_path = args.templates_path or (repo_root / "templates")
    output_root = args.output_root or (repo_root / "src")

    if not templates_path.is_dir():
        print(f"Error: Templates path not found: {templates_path}", file=sys.stderr)
        return 2

    return generate_agents(
        templates_path=templates_path,
        output_root=output_root,
        repo_root=repo_root,
        validate=args.validate,
        what_if=args.what_if,
    )


if __name__ == "__main__":
    sys.exit(main())
