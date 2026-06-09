#!/usr/bin/env python3
"""Generate Copilot instruction files from ``.claude/rules/`` (REQ-003-006).

Reads ``artifacts.rules`` from a platform YAML and rewrites every Claude
rule into a Copilot-compatible instruction file. Rules are universal
across providers; unscoped rules emit with ``applyTo: "**"`` (the
universal-scope default).

Output targets:
  - ``outputDir`` (string): single destination. Backward-compatible.
  - ``outputDirs`` (list of strings): multiple destinations, one copy
    each. Set when a rule must ship to both the repo-internal Copilot
    path (``.github/instructions/``) and the project-toolkit plugin
    path (``src/copilot-cli/instructions/``) so vendor installs via
    marketplace pick them up alongside agents, skills, and hooks.

``outputDir`` and ``outputDirs`` are mutually exclusive. At least one
must be set.

Per-rule logic (Round 3 amendment, 2026-04-29):

1. Read source ``.claude/rules/<name>.md`` (frontmatter + body).
2. Emit to ``.github/instructions/<name>.instructions.md``:
   - rename ``paths:`` to ``applyTo:`` (verbatim value)
   - drop ``alwaysApply:`` and ``priority:``
   - preserve ``description:`` and other unrelated keys
   - if neither ``paths:`` nor ``applyTo:`` is declared, synthesize
     ``applyTo: "**"`` (universal scope, the default for unscoped rules)
   - body unchanged
3. NO-REGEN sentinel honored on the target file.

The Round 2 severity-gate (high/medium/low + governance-keyword scan +
conditional skip) was removed. Rationale: rules are universal across
Claude and Copilot; there is no use case for Claude-only or Copilot-only
rules. A rule exists in ``.claude/rules/`` → it ships.

EXIT CODES:
  0 - success
  1 - sourceDir missing OR no rule files found
  2 - configuration error (config/stanza missing, traversal, etc.)

Per ADR-035 Exit Code Standardization.
"""

from __future__ import annotations

import argparse
import ast
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

from generate_agents_common import (  # noqa: E402
    format_frontmatter_yaml,
    parse_simple_frontmatter,
    read_yaml_frontmatter,
)
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402

_DEFAULT_SOURCE_SUFFIX = ".md"
_DEFAULT_OUTPUT_SUFFIX = ".instructions.md"
_SCOPE_KEYS = ("paths", "applyTo", "globs")
_UNIVERSAL_SCOPE = "**"

# M7-T4: vendor-install path filter. Globs that begin with these prefixes
# reference internal repository directories that do not ship in any
# downstream install (the rules generator emits files for the Copilot CLI
# plugin and the GitHub Copilot instructions tree, neither of which carry
# `.agents/`, `.claude/`, or `.serena/`). Filtering them out at emit time
# prevents dead `applyTo` entries that would never match a vendor-side
# file path.
_INTERNAL_PATH_PREFIXES = (".agents/", ".claude/", ".serena/")


class GenerateRulesError(Exception):
    """Domain error for rule generation."""


@dataclass
class RuleAuditEntry:
    """One rule's outcome at one output target.

    Used by tests to assert audit messaging. With multi-output (`outputDirs`)
    one rule produces one entry per destination, so callers can distinguish
    which write succeeded, was skipped, or hit a sentinel; the ``destination``
    field carries the repo-relative output dir (e.g. ``.github/instructions``
    or ``src/copilot-cli/instructions``) for that entry.
    """

    name: str
    action: str  # "emitted" | "sentinel-skipped"
    reason: str = ""
    destination: str = ""


@dataclass
class GenerateRulesResult:
    """Aggregate result for a generation run.

    The script returns only an exit code to its caller, but the structured
    result is exposed for tests and the build_all orchestrator.
    """

    written: int = 0
    sentinel_skipped: int = 0
    entries: list[RuleAuditEntry] = field(default_factory=list)


# --- Helpers --------------------------------------------------------------


def _resolve_paths(
    repo_root: Path, source_dir: str, output_dirs: list[str]
) -> tuple[Path, list[Path]]:
    """Validate and resolve sourceDir + one or more outputDirs.

    ``output_dirs`` is always a list of one or more entries. Multi-output
    support exists so a single rule can ship to both the GitHub Copilot
    instructions tree (`.github/instructions/`) and the project-toolkit
    plugin's instructions tree (`src/copilot-cli/instructions/`) without
    a second generator run. Each entry is validated and resolved
    independently; validation failure on any one fails the whole run.
    """
    errs = validate_relative_path("sourceDir", source_dir)
    if errs:
        raise GenerateRulesError("; ".join(errs))
    if not output_dirs:
        raise GenerateRulesError("at least one outputDir is required")
    resolved_outputs: list[Path] = []
    for idx, out in enumerate(output_dirs):
        field_label = f"outputDirs[{idx}]" if len(output_dirs) > 1 else "outputDir"
        errs = validate_relative_path(field_label, out)
        if errs:
            raise GenerateRulesError("; ".join(errs))
        resolved_outputs.append(repo_root / out)
    return repo_root / source_dir, resolved_outputs


def _read_output_dirs(stanza: dict) -> list[str]:
    """Parse `outputDir` (string) or `outputDirs` (list) from the rules stanza.

    Backward-compatible: existing configs and tests use `outputDir`. New
    multi-target configs use `outputDirs`. Setting both is a config error
    so the intent stays unambiguous.

    Type-strict: a non-string `outputDir` or a non-string element inside
    `outputDirs` is a config error. Without this check, ``str(item)`` would
    coerce an int or `null` to a string and the downstream
    ``validate_relative_path`` would happily accept ``"None"`` or ``"42"``
    as a directory name. The YAML loader returns native Python types here,
    so we require strings explicitly.
    """
    single = stanza.get("outputDir")
    multi = stanza.get("outputDirs")
    if single is not None and multi is not None:
        raise GenerateRulesError(
            "set either `outputDir` or `outputDirs`, not both"
        )
    if multi is not None:
        if not isinstance(multi, list) or not multi:
            raise GenerateRulesError(
                "`outputDirs` must be a non-empty list"
            )
        for idx, item in enumerate(multi):
            if not isinstance(item, str):
                raise GenerateRulesError(
                    f"`outputDirs[{idx}]` must be a string (got "
                    f"{type(item).__name__})"
                )
        return list(multi)
    if single is not None:
        if not isinstance(single, str):
            raise GenerateRulesError(
                f"`outputDir` must be a string (got {type(single).__name__})"
            )
        return [single]
    raise GenerateRulesError(
        "rules stanza requires `outputDir` or `outputDirs`"
    )


def _has_path_scope(frontmatter: dict[str, str | None]) -> bool:
    """True when frontmatter declares any path-scope key with a non-empty value."""
    for key in _SCOPE_KEYS:
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _filter_internal_globs(value: str) -> tuple[str, list[str]]:
    """Drop comma-separated glob entries pointing at internal-only paths.

    Source rules under `.claude/rules/` declare ``applyTo``/``paths`` with
    repo-local globs like ``.agents/security/**,**/Auth/**,*.env*,.claude/rules/security.md``.
    Some of those entries (`.agents/`, `.claude/`, `.serena/` prefixes) only
    exist in the source repository; for any downstream consumer they are
    dead references that match nothing and add noise. Drop them and keep
    everything else verbatim.

    Returns ``(filtered, dropped)`` where ``filtered`` is the comma-joined
    survivors and ``dropped`` is the list of removed entries (so the
    caller can log or audit them). When every entry was internal,
    ``filtered`` is the empty string and the caller should synthesize a
    universal scope.
    """
    if not value or not value.strip():
        return value, []
    parts = [p.strip() for p in value.split(",")]
    kept: list[str] = []
    dropped: list[str] = []
    for p in parts:
        if not p:
            continue
        if p.startswith(_INTERNAL_PATH_PREFIXES):
            dropped.append(p)
        else:
            kept.append(p)
    return ",".join(kept), dropped


def _flatten_serialized_scope_list(value: str) -> str:
    """Flatten a serialized frontmatter list into a comma-separated scope string."""
    stripped = value.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return value
    try:
        parsed = ast.literal_eval(stripped)
    except (ValueError, SyntaxError):
        return ",".join(
            item.strip().strip("'\"")
            for item in stripped[1:-1].split(",")
            if item.strip()
        )
    if not isinstance(parsed, list):
        return value
    return ",".join(str(item) for item in parsed)


def _remap_frontmatter(
    frontmatter: dict[str, str | None],
    remap: dict[str, str],
    drop: set[str],
) -> dict[str, str | None]:
    """Apply ``frontmatterRemap`` and ``frontmatterDrop`` rules; ensure
    the output declares ``applyTo`` (synthesizing universal scope when
    the source rule has no path scope).

    Iteration order is preserved so the output diff is stable. Drop wins
    over remap: a key listed in both is removed, not renamed.

    M7-T4: scope values mapped to ``applyTo`` are filtered through
    :func:`_filter_internal_globs` to drop dead-on-arrival references to
    internal-only paths (``.agents/``, ``.claude/``, ``.serena/``). When
    every glob in the source is internal, the universal scope is
    synthesized so the rule still applies somewhere in the vendor tree
    rather than being dropped entirely.
    """
    had_scope = _has_path_scope(frontmatter)
    result: dict[str, str | None] = {}
    for key, value in frontmatter.items():
        if key in drop:
            continue
        new_key = remap.get(key, key)
        # Sanitize the destination scope key (post-remap) so the filter
        # runs once on `applyTo` regardless of whether the source used
        # `paths`, `applyTo`, or `globs`.
        if new_key == "applyTo" and isinstance(value, str):
            # A source `paths:` block list is parsed by the simple
            # frontmatter parser into an inline-array string
            # ("['a', 'b']"). Copilot's `applyTo` is a comma-separated
            # string, so flatten the array to that shape before the
            # internal-glob filter (which splits on ",") and before emit.
            value = _flatten_serialized_scope_list(value)
            value, dropped = _filter_internal_globs(value)
            for entry in dropped:
                # Visible warning per dropped entry so plugin authors
                # see what was filtered (and why) without grepping the
                # generator source.
                print(
                    f"  WARNING: dropped internal-only glob from applyTo: {entry!r}",
                    file=sys.stderr,
                )
        result[new_key] = value
    # If the post-filter applyTo is empty but the source had a scope,
    # the source was entirely internal-only globs. Synthesize universal
    # scope so the rule still ships rather than landing with applyTo: "".
    if (
        had_scope
        and isinstance(result.get("applyTo"), str)
        and not result["applyTo"].strip()
    ):
        result["applyTo"] = _UNIVERSAL_SCOPE
    if not had_scope and "applyTo" not in result:
        # Universal-scope default for unscoped rules. Insert at the top
        # of the output frontmatter for consistent placement.
        result = {"applyTo": _UNIVERSAL_SCOPE, **result}
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
    # format_frontmatter_yaml joins with "\n" without a trailing newline; add
    # one so the closing fence does not run into the last key line.
    if fm_yaml and not fm_yaml.endswith("\n"):
        fm_yaml += "\n"
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
    """Process one rule. Round 3: every rule emits.

    Returns a tuple of ``(action, name, reason)`` where action is one of
    ``emitted`` or ``sentinel-skipped``. Unscoped rules receive a
    synthesized ``applyTo: "**"`` (universal scope) via ``_remap_frontmatter``.
    """
    name = (
        src_path.name[: -len(source_suffix)]
        if src_path.name.endswith(source_suffix)
        else src_path.stem
    )
    text = src_path.read_text(encoding="utf-8")
    match = read_yaml_frontmatter(text)
    if match is None:
        source_fm: dict[str, str | None] = {}
        body = text
    else:
        source_fm = parse_simple_frontmatter(match["frontmatter_raw"])
        body = match["body"]

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
    try:
        output_dir_strs = _read_output_dirs(stanza)
    except GenerateRulesError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2, result
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
        source_dir, output_dirs = _resolve_paths(
            repo_root, source_dir_str, output_dir_strs
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
    if len(output_dirs) > 1:
        print(f"Output targets: {len(output_dirs)}")
        for out in output_dirs:
            print(f"  - {out.relative_to(repo_root)}")

    expected_outputs: set[str] = set()
    for src in sources:
        name = (
            src.name[: -len(source_suffix)]
            if src.name.endswith(source_suffix)
            else src.stem
        )
        expected_outputs.add(f"{name}{output_suffix}")
        # Process once per output target. The audit records each
        # write separately so callers can see all destinations.
        for output_dir in output_dirs:
            action, name_out, reason = _process_rule(
                src,
                output_dir,
                source_suffix=source_suffix,
                output_suffix=output_suffix,
                remap=remap,
                drop=drop,
                what_if=what_if,
            )
            try:
                destination = str(output_dir.relative_to(repo_root))
            except ValueError:
                destination = str(output_dir)
            result.entries.append(
                RuleAuditEntry(
                    name=name_out,
                    action=action,
                    reason=reason,
                    destination=destination,
                )
            )
            if action == "emitted":
                result.written += 1
            elif action == "sentinel-skipped":
                result.sentinel_skipped += 1

    # M7-T4: prune orphan instruction files in every output target.
    # Without this, deleted-source files leave stale *.instructions.md
    # entries that re-introduce internal-path leakage and rotted applyTo
    # globs. Skips files carrying the NO-REGEN sentinel and skips entirely
    # in --what-if mode so dry-runs never delete.
    if not what_if:
        for output_dir in output_dirs:
            if not output_dir.is_dir():
                continue
            for existing in output_dir.glob(f"*{output_suffix}"):
                if existing.name in expected_outputs:
                    continue
                reason = regen_detect_reason(existing)
                if reason is not None:
                    print(f"  NOTICE: kept orphan {existing} (NO-REGEN: {reason})")
                    continue
                existing.unlink()
                print(f"  PRUNED orphan: {existing.relative_to(repo_root)}")

    duration = time.monotonic() - start

    print()
    print("=== Summary ===")
    print(f"Duration: {duration:.2f}s")
    print(f"Written: {result.written}")
    if result.sentinel_skipped:
        print(f"Skipped (NO-REGEN sentinel): {result.sentinel_skipped}")

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
