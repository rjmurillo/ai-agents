#!/usr/bin/env python3
"""Generate ``.github/instructions/`` rule files from ``.claude/rules/`` (REQ-003-006).

Reads ``artifacts.rules`` from a platform YAML and rewrites every
path-scoped Claude rule into a Copilot-compatible instruction file.
Universal rules (no path scope) are gated by an explicit severity
contract so customers do not silently get repository-wide instructions.

Per-rule logic:

1. Read source ``.claude/rules/<name>.md`` (frontmatter + body).
2. Detect path scope: any of ``paths:``, ``applyTo:``, ``globs:``.
3. If scoped → emit to ``.github/instructions/<name>.instructions.md``:
   - rename ``paths:`` to ``applyTo:`` (verbatim value)
   - drop ``alwaysApply:`` and ``priority:``
   - preserve ``description:`` and other unrelated keys
   - body unchanged
4. If unscoped → consult ``severity:``:
   - ``high`` → exit 1 (must declare scope or downgrade severity)
   - ``medium`` → skip with WARN
   - ``low`` → silent skip
   - unset + governance keyword in body (``secret``, ``credential``,
     ``license``, ``GP-001``..``GP-008``) → treat as ``high`` (exit 1)
   - unset + no keyword → treat as ``medium`` (skip + WARN)
5. NO-REGEN sentinel honored on the target file.

EXIT CODES:
  0 - success (with possible WARN/silent skips)
  1 - high-severity rule lacks path scope (operator must fix the rule)
  2 - configuration error (config/stanza missing, traversal, etc.)

Per ADR-035 Exit Code Standardization.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))

from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402
from generate_agents_common import (  # noqa: E402
    format_frontmatter_yaml,
    parse_simple_frontmatter,
    read_yaml_frontmatter,
)

_DEFAULT_SOURCE_SUFFIX = ".md"
_DEFAULT_OUTPUT_SUFFIX = ".instructions.md"
_SCOPE_KEYS = ("paths", "applyTo", "globs")
_GOVERNANCE_PATTERN = re.compile(
    r"\b(secret|credential|license|GP-00[1-8])\b",
    re.IGNORECASE,
)
_VALID_SEVERITIES = {"high", "medium", "low"}


class GenerateRulesError(Exception):
    """Domain error for rule generation."""


@dataclass
class RuleAuditEntry:
    """One rule's outcome — used by tests to assert audit messaging."""

    name: str
    action: str  # "emitted" | "warn-skipped" | "silent-skipped" | "high-error"
    reason: str = ""


@dataclass
class GenerateRulesResult:
    """Aggregate result for a generation run.

    The script returns only an exit code to its caller, but the structured
    result is exposed for tests and the build_all orchestrator.
    """

    written: int = 0
    skipped_warn: int = 0
    skipped_silent: int = 0
    high_severity_errors: list[str] = field(default_factory=list)
    sentinel_skipped: int = 0
    entries: list[RuleAuditEntry] = field(default_factory=list)


# --- Helpers --------------------------------------------------------------


def _resolve_paths(
    repo_root: Path, source_dir: str, output_dir: str
) -> tuple[Path, Path]:
    for field_name, value in (
        ("sourceDir", source_dir),
        ("outputDir", output_dir),
    ):
        errs = validate_relative_path(field_name, value)
        if errs:
            raise GenerateRulesError("; ".join(errs))
    return repo_root / source_dir, repo_root / output_dir


def _has_path_scope(frontmatter: dict[str, str | None]) -> bool:
    """True when frontmatter declares any path-scope key with a non-empty value."""
    for key in _SCOPE_KEYS:
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _classify_unscoped_severity(
    frontmatter: dict[str, str | None], body: str
) -> str:
    """Classify the effective severity for an unscoped rule.

    Returns one of {"high", "medium", "low"}. The ``severity:`` key wins
    when set; otherwise the body is scanned for governance keywords. The
    unset-and-no-keyword default is ``medium`` (skip + WARN), per spec.
    """
    raw = frontmatter.get("severity")
    if isinstance(raw, str):
        sev = raw.strip().lower()
        if sev in _VALID_SEVERITIES:
            return sev
    # Unset (or invalid). Inspect body.
    if _GOVERNANCE_PATTERN.search(body):
        return "high"
    return "medium"


def _remap_frontmatter(
    frontmatter: dict[str, str | None],
    remap: dict[str, str],
    drop: set[str],
) -> dict[str, str | None]:
    """Apply ``frontmatterRemap`` and ``frontmatterDrop`` rules.

    Iteration order is preserved so the output diff is stable. Drop wins
    over remap: a key listed in both is removed, not renamed.
    """
    result: dict[str, str | None] = {}
    for key, value in frontmatter.items():
        if key in drop:
            continue
        new_key = remap.get(key, key)
        result[new_key] = value
    return result


def _write_instruction(
    target: Path,
    frontmatter: dict[str, str | None],
    body: str,
    *,
    what_if: bool,
) -> bool:
    """Write the instruction file. Returns True on write, False on NO-REGEN skip."""
    reason = regen_detect_reason(target)
    if reason is not None:
        print(f"  NOTICE: skipped {target} (NO-REGEN: {reason})")
        return False

    fm_yaml = format_frontmatter_yaml(frontmatter) if frontmatter else ""
    if fm_yaml:
        content = f"---\n{fm_yaml}---\n{body}"
    else:
        content = body
    if not content.endswith("\n"):
        content += "\n"

    if what_if:
        print(f"  Would write: {target}")
        return True

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return True


# --- Per-rule processing --------------------------------------------------


def _process_rule(
    src_path: Path,
    output_dir: Path,
    *,
    source_suffix: str,
    output_suffix: str,
    remap: dict[str, str],
    drop: set[str],
    what_if: bool,
) -> tuple[str, str, str]:
    """Process one rule.

    Returns a tuple of ``(action, name, reason)`` where action is one of
    ``emitted``, ``warn-skipped``, ``silent-skipped``, ``high-error``,
    ``sentinel-skipped``. ``reason`` is empty unless skipping/erroring.
    """
    name = src_path.name[: -len(source_suffix)] if src_path.name.endswith(source_suffix) else src_path.stem
    text = src_path.read_text(encoding="utf-8")
    match = read_yaml_frontmatter(text)
    if match is None:
        source_fm: dict[str, str | None] = {}
        body = text
    else:
        source_fm = parse_simple_frontmatter(match["frontmatter_raw"])
        body = match["body"]

    if not _has_path_scope(source_fm):
        sev = _classify_unscoped_severity(source_fm, body)
        if sev == "high":
            reason = (
                f"rule '{name}' has no path scope and severity=high; "
                "either add paths/applyTo OR explicitly downgrade severity"
            )
            return ("high-error", name, reason)
        if sev == "medium":
            reason = (
                f"rule '{name}' has no path scope; severity=medium → skipped "
                "(declare paths/applyTo to emit)"
            )
            print(f"  WARN: {reason}", file=sys.stderr)
            return ("warn-skipped", name, reason)
        # low → silent skip
        return ("silent-skipped", name, "")

    # Scoped: emit.
    target_name = f"{name}{output_suffix}"
    target = output_dir / target_name
    transformed = _remap_frontmatter(source_fm, remap, drop)
    written = _write_instruction(target, transformed, body, what_if=what_if)
    if not written:
        return ("sentinel-skipped", name, "NO-REGEN")
    return ("emitted", name, "")


# --- Driver ---------------------------------------------------------------


def generate_rules(
    config_path: Path,
    repo_root: Path,
    *,
    what_if: bool = False,
) -> tuple[int, GenerateRulesResult]:
    """Generate instruction files per the artifacts.rules stanza.

    Returns ``(exit_code, result)`` so callers (tests, orchestrator) can
    inspect the audit without re-parsing logs.
    """
    print()
    print("=== Rules -> Instructions ===")
    print(f"Config: {config_path}")
    print(f"Repo root: {repo_root}")
    print(f"Mode: {'WhatIf' if what_if else 'Generate'}")
    print()

    result = GenerateRulesResult()

    try:
        cfg = load_platform_config(config_path)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result

    artifacts = cfg.get("artifacts")
    if not isinstance(artifacts, dict):
        print(f"Error: {config_path} has no `artifacts` mapping", file=sys.stderr)
        return 2, result
    stanza = artifacts.get("rules")
    if not isinstance(stanza, dict):
        print(
            f"Error: {config_path} has no `artifacts.rules` stanza",
            file=sys.stderr,
        )
        return 2, result

    source_dir_str = str(stanza.get("sourceDir", ""))
    output_dir_str = str(stanza.get("outputDir", ""))
    source_suffix = str(stanza.get("sourceSuffix", _DEFAULT_SOURCE_SUFFIX))
    output_suffix = str(stanza.get("outputSuffix", _DEFAULT_OUTPUT_SUFFIX))

    raw_remap = stanza.get("frontmatterRemap") or {}
    if not isinstance(raw_remap, dict):
        print(
            "Error: `artifacts.rules.frontmatterRemap` must be a mapping",
            file=sys.stderr,
        )
        return 2, result
    remap: dict[str, str] = {str(k): str(v) for k, v in raw_remap.items()}

    raw_drop = stanza.get("frontmatterDrop") or []
    if not isinstance(raw_drop, list):
        print(
            "Error: `artifacts.rules.frontmatterDrop` must be a list",
            file=sys.stderr,
        )
        return 2, result
    drop: set[str] = {str(item) for item in raw_drop}

    try:
        source_dir, output_dir = _resolve_paths(
            repo_root, source_dir_str, output_dir_str
        )
    except GenerateRulesError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result

    if not source_dir.is_dir():
        print(f"Error: sourceDir not found: {source_dir}", file=sys.stderr)
        return 1, result

    sources = sorted(source_dir.glob(f"*{source_suffix}"))
    if not sources:
        print(
            f"Error: no rule files found under {source_dir} (suffix={source_suffix})",
            file=sys.stderr,
        )
        return 1, result

    start = time.monotonic()
    print(f"Found {len(sources)} rule(s)")

    for src in sources:
        action, name, reason = _process_rule(
            src,
            output_dir,
            source_suffix=source_suffix,
            output_suffix=output_suffix,
            remap=remap,
            drop=drop,
            what_if=what_if,
        )
        result.entries.append(RuleAuditEntry(name=name, action=action, reason=reason))
        if action == "emitted":
            result.written += 1
        elif action == "warn-skipped":
            result.skipped_warn += 1
        elif action == "silent-skipped":
            result.skipped_silent += 1
        elif action == "sentinel-skipped":
            result.sentinel_skipped += 1
        elif action == "high-error":
            result.high_severity_errors.append(reason)

    duration = time.monotonic() - start

    print()
    print("=== Summary ===")
    print(f"Duration: {duration:.2f}s")
    print(f"Written: {result.written}")
    if result.skipped_warn:
        print(f"Skipped (WARN, severity=medium): {result.skipped_warn}")
    if result.skipped_silent:
        print(f"Skipped (silent, severity=low): {result.skipped_silent}")
    if result.sentinel_skipped:
        print(f"Skipped (NO-REGEN sentinel): {result.sentinel_skipped}")

    if result.high_severity_errors:
        print()
        print("=== High-severity rules without path scope ===", file=sys.stderr)
        for msg in result.high_severity_errors:
            print(f"  ERROR: {msg}", file=sys.stderr)
        return 1, result

    return 0, result


# --- CLI ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Platform YAML config (defaults to templates/platforms/copilot-cli.yaml).",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to script's grandparent).",
    )
    p.add_argument("--what-if", action="store_true", help="Dry-run mode.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root or _SCRIPT_DIR.parent.parent
    config_path = args.config or (
        repo_root / "templates" / "platforms" / "copilot-cli.yaml"
    )
    if not config_path.is_file():
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        return 2
    rc, _result = generate_rules(config_path, repo_root, what_if=args.what_if)
    return rc


if __name__ == "__main__":
    sys.exit(main())
