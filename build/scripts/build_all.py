#!/usr/bin/env python3
"""Orchestrate per-artifact generators (REQ-003-005, -008, -010, -011).

Runs every artifact generator wired in ``GENERATORS`` for one or more
platforms, emits an audit log under ``build/audit/`` (overwrite, not
append; not git-tracked), and offers staleness, clean, and audit-format
modes for CI integration.

CLI:
    python3 build/scripts/build_all.py
    python3 build/scripts/build_all.py --check
    python3 build/scripts/build_all.py --clean
    python3 build/scripts/build_all.py --audit-format json
    python3 build/scripts/build_all.py --platform copilot-cli

EXIT CODES:
    0 - success
    1 - generator logic error
    2 - configuration error / staleness detected (--check)
    3 - audit blocklist violation (REQ-003-011)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

import generate_skills  # noqa: E402
from yaml_loader import ConfigError, load_platform_config  # noqa: E402

# Path to the agent generator. Imported lazily because build/ is on a
# separate path; see build_agents().
_BUILD_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_BUILD_DIR))


@dataclass
class GeneratorResult:
    """One generator's contribution to the audit log."""

    artifact: str
    platform: str
    inputs: int = 0
    outputs: int = 0
    skipped: int = 0
    notices: list[str] = field(default_factory=list)
    exit_code: int = 0


@dataclass
class BuildAudit:
    """Aggregate audit emitted at end of run.

    Persisted to ``build/audit/GENERATION-AUDIT.md`` (overwrite-only) and
    optionally serialized to stdout as JSON for CI parsing.
    """

    started_at: float
    duration_s: float = 0.0
    results: list[GeneratorResult] = field(default_factory=list)
    blocklist_violations: list[str] = field(default_factory=list)
    overall_exit: int = 0


# --- Artifact registry ----------------------------------------------------


def _build_skills(repo_root: Path, config_path: Path, platform: str) -> GeneratorResult:
    # If the platform has no skills stanza, treat as not-applicable rather
    # than a config error. visual-studio and vscode platforms ship without
    # one today; they should not break the orchestrator.
    try:
        cfg = load_platform_config(config_path)
    except ConfigError:
        cfg = {}
    stanza = (cfg.get("artifacts") or {}).get("skills") if isinstance(cfg.get("artifacts"), dict) else None
    if not isinstance(stanza, dict):
        result = GeneratorResult(artifact="skills", platform=platform, exit_code=0)
        result.notices.append(f"{platform}: no artifacts.skills stanza; skipped")
        return result

    rc = generate_skills.generate_skills(config_path, repo_root)
    result = GeneratorResult(artifact="skills", platform=platform, exit_code=rc)
    # Tally inputs and outputs from the actual configured directories.
    src = repo_root / str(stanza.get("sourceDir", ""))
    out = repo_root / str(stanza.get("outputDir", ""))
    if src.is_dir():
        result.inputs = sum(1 for _ in src.glob("*/SKILL.md"))
    if out.is_dir():
        # Count skill targets, not every nested file. One SKILL.md per output.
        result.outputs = sum(1 for _ in out.glob("*/SKILL.md"))
    return result


def _build_agents(repo_root: Path, _config_path: Path, _platform: str) -> GeneratorResult:
    """Run the agents generator across all platform configs.

    The current generator iterates platforms internally; we do not pass a
    single config_path. We surface its output in a single combined
    ``agents`` row to keep the audit reader simple.
    """
    import generate_agents

    rc = generate_agents.main([
        "--templates-path", str(repo_root / "templates"),
        "--output-root", str(repo_root / "src"),
    ])
    return GeneratorResult(artifact="agents", platform="*", exit_code=rc)


# Order matters: agents → skills. Hooks/commands/rules land in M4-M5.
GENERATORS: list[tuple[str, Callable[[Path, Path, str], GeneratorResult]]] = [
    ("agents", _build_agents),
    ("skills", _build_skills),
]


# --- Audit blocklist ------------------------------------------------------


def _load_blocklist(config_path: Path) -> list[re.Pattern[str]]:
    """Read auditPolicy.pathBlocklist patterns and compile them.

    Patterns that fail to compile are skipped with a warning rather than
    aborting the build; the blocklist is meant to harden, not to block.
    """
    try:
        cfg = load_platform_config(config_path)
    except ConfigError:
        return []
    audit = cfg.get("auditPolicy")
    if not isinstance(audit, dict):
        return []
    raw = audit.get("pathBlocklist") or []
    patterns: list[re.Pattern[str]] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        try:
            patterns.append(re.compile(item))
        except re.error as exc:
            print(
                f"Warning: blocklist pattern '{item}' failed to compile: {exc}",
                file=sys.stderr,
            )
    return patterns


def _check_blocklist(text: str, patterns: Iterable[re.Pattern[str]]) -> list[str]:
    """Return human-readable strings for every blocklist hit."""
    hits: list[str] = []
    for ln, line in enumerate(text.splitlines(), start=1):
        for pat in patterns:
            if pat.search(line):
                hits.append(f"line {ln}: matches '{pat.pattern}': {line.strip()}")
    return hits


# --- Audit emission -------------------------------------------------------


def _format_audit_md(audit: BuildAudit) -> str:
    """Render the audit log as markdown.

    Overwrite, never append; CI reads the latest run.
    """
    lines: list[str] = []
    lines.append("# Generation Audit")
    lines.append("")
    lines.append(f"- duration: {audit.duration_s:.2f}s")
    lines.append(f"- overall exit: {audit.overall_exit}")
    lines.append("")
    lines.append("| artifact | platform | inputs | outputs | skipped | exit |")
    lines.append("|----------|----------|--------|---------|---------|------|")
    for r in audit.results:
        lines.append(
            f"| {r.artifact} | {r.platform} | {r.inputs} | {r.outputs} "
            f"| {r.skipped} | {r.exit_code} |"
        )
    if audit.blocklist_violations:
        lines.append("")
        lines.append("## Blocklist violations")
        for v in audit.blocklist_violations:
            lines.append(f"- {v}")
    notices = [n for r in audit.results for n in r.notices]
    if notices:
        lines.append("")
        lines.append("## Notices")
        for n in notices:
            lines.append(f"- {n}")
    return "\n".join(lines) + "\n"


def _format_audit_json(audit: BuildAudit) -> str:
    payload = {
        "duration_s": audit.duration_s,
        "overall_exit": audit.overall_exit,
        "blocklist_violations": audit.blocklist_violations,
        "results": [
            {
                "artifact": r.artifact,
                "platform": r.platform,
                "inputs": r.inputs,
                "outputs": r.outputs,
                "skipped": r.skipped,
                "notices": r.notices,
                "exit_code": r.exit_code,
            }
            for r in audit.results
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_audit(
    audit: BuildAudit,
    audit_path: Path,
    blocklist: list[re.Pattern[str]],
) -> list[str]:
    """Write audit markdown and return any blocklist violations.

    The blocklist is enforced on the OUTPUT TEXT just before write so
    accidental absolute paths or secret tokens cannot land on disk.
    """
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    text = _format_audit_md(audit)
    violations = _check_blocklist(text, blocklist)
    if violations:
        # Emit a violation summary so operators see why the build halted.
        for v in violations:
            print(f"AUDIT-BLOCKLIST: {v}", file=sys.stderr)
        return violations
    audit_path.write_text(text, encoding="utf-8")
    return []


# --- .claude/ guard (REQ-003-010) ----------------------------------------


def _git_diff_paths(repo_root: Path) -> list[str]:
    """Return changed paths via ``git diff --name-only`` (untracked excluded).

    Used by --check (staleness) and the .claude/ guard. A failure to run
    git is treated as no-diff: this is a CI-side check, and CI always has
    git. We do not want to fail when a contributor runs the script in a
    non-git working tree.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--name-only"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def assert_no_claude_writes(repo_root: Path) -> list[str]:
    """REQ-003-010: generators MUST NOT write under .claude/.

    Returns the list of offending paths (empty when compliant).
    """
    return [p for p in _git_diff_paths(repo_root) if p.startswith(".claude/")]


# --- Clean ----------------------------------------------------------------


def clean_outputs(repo_root: Path, config_path: Path) -> int:
    """Remove orphan output files (sources deleted, outputs lingering).

    The clean strategy mirrors the simplest contract: rm -rf the
    configured output dirs. Generators rebuild deterministically, so a
    full purge is safe between builds and avoids carrying stale files
    when a source skill is renamed or removed.
    """
    try:
        cfg = load_platform_config(config_path)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    artifacts = cfg.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        return 0
    # Only clean output dirs whose contents are exclusively generator
    # output. Skills outputs to src/<provider>/skills/ — safe to nuke.
    # Agents legacy outputDir is src/copilot-cli (not a subdir), so
    # cleaning would destroy unrelated content. Hooks/commands/rules
    # share dirs with hand-authored files. Restrict to skills for now.
    cleanable = {"skills"}
    removed = 0
    for name, stanza in artifacts.items():
        if name not in cleanable:
            continue
        if not isinstance(stanza, dict):
            continue
        out = stanza.get("outputDir")
        if not isinstance(out, str) or not out:
            continue
        target = repo_root / out
        if target.is_dir():
            shutil.rmtree(target)
            print(f"Cleaned: {target}")
            removed += 1
    print(f"Removed {removed} output dir(s)")
    return 0


# --- Driver ---------------------------------------------------------------


def _select_platform_configs(
    platforms_dir: Path, requested: str | None
) -> list[Path]:
    if not platforms_dir.is_dir():
        return []
    files = sorted(platforms_dir.glob("*.yaml"))
    if requested:
        return [p for p in files if p.stem == requested]
    return files


def run(
    repo_root: Path,
    *,
    platform: str | None,
    check: bool,
    clean: bool,
    audit_format: str,
) -> int:
    platforms_dir = repo_root / "templates" / "platforms"
    configs = _select_platform_configs(platforms_dir, platform)
    if not configs:
        print(
            f"Error: no platform configs in {platforms_dir} "
            f"(filter: {platform!r})",
            file=sys.stderr,
        )
        return 2

    if clean:
        rc = 0
        for cfg in configs:
            rc = max(rc, clean_outputs(repo_root, cfg))
        return rc

    audit = BuildAudit(started_at=time.time())
    started = time.monotonic()

    # Agents generator iterates platforms internally; run once per build.
    agents_result = _build_agents(repo_root, configs[0], "*")
    audit.results.append(agents_result)
    if agents_result.exit_code != 0:
        audit.overall_exit = max(audit.overall_exit, agents_result.exit_code)

    # Per-platform per-artifact generators.
    for cfg in configs:
        platform_name = cfg.stem
        for artifact, fn in GENERATORS:
            if artifact == "agents":
                continue  # ran once above
            result = fn(repo_root, cfg, platform_name)
            audit.results.append(result)
            if result.exit_code != 0:
                audit.overall_exit = max(audit.overall_exit, result.exit_code)

    audit.duration_s = time.monotonic() - started

    # REQ-003-010: enforce .claude/ no-write invariant.
    claude_writes = assert_no_claude_writes(repo_root)
    if claude_writes:
        for p in claude_writes:
            print(f"REQ-003-010 VIOLATION: generator wrote to {p}", file=sys.stderr)
        audit.overall_exit = 2
        audit.blocklist_violations.extend(
            f".claude/ write detected: {p}" for p in claude_writes
        )

    # Build the blocklist from the first config that has one.
    blocklist: list[re.Pattern[str]] = []
    for cfg in configs:
        blocklist = _load_blocklist(cfg)
        if blocklist:
            break

    audit_path = repo_root / "build" / "audit" / "GENERATION-AUDIT.md"
    violations = write_audit(audit, audit_path, blocklist)
    if violations:
        audit.blocklist_violations.extend(violations)
        audit.overall_exit = max(audit.overall_exit, 3)

    if check:
        # Limit staleness check to paths the generators actually own. Other
        # working-tree drift (e.g. uv.lock) is the user's responsibility,
        # not the build orchestrator's.
        owned_prefixes = ("src/", ".github/instructions/")
        diff = [
            p for p in _git_diff_paths(repo_root)
            if any(p.startswith(prefix) for prefix in owned_prefixes)
        ]
        if diff:
            print("STALENESS DETECTED — uncommitted regen drift:", file=sys.stderr)
            for p in diff:
                print(f"  {p}", file=sys.stderr)
            audit.overall_exit = 2

    if audit_format == "json":
        sys.stdout.write(_format_audit_json(audit))

    return audit.overall_exit


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=None)
    p.add_argument("--platform", type=str, default=None)
    p.add_argument("--check", action="store_true", help="CI staleness gate.")
    p.add_argument("--clean", action="store_true", help="Remove output dirs.")
    p.add_argument(
        "--audit-format",
        choices=("md", "json"),
        default="md",
        help="Audit output format. md writes file only; json also emits to stdout.",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root or _SCRIPT_DIR.parent.parent
    if not repo_root.is_dir():
        print(f"Error: repo root not found: {repo_root}", file=sys.stderr)
        return 2
    return run(
        repo_root,
        platform=args.platform,
        check=args.check,
        clean=args.clean,
        audit_format=args.audit_format,
    )


if __name__ == "__main__":
    sys.exit(main())
