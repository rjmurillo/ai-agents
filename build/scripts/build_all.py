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

import generate_commands  # noqa: E402
import generate_hooks  # noqa: E402
import generate_rules  # noqa: E402
import generate_skills  # noqa: E402
from yaml_loader import ConfigError, load_platform_config  # noqa: E402

# Path to the agent generator. Imported lazily because build/ is on a
# separate path; see build_agents().
_BUILD_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_BUILD_DIR))


@dataclass
class GeneratorResult:
    """One generator's contribution to the audit log.

    ``hook_entries`` carries optional per-script audit detail emitted by
    the hooks generator (REQ-003-007). Each entry is a dict with the
    keys ``event_source``, ``event_target``, ``matcher``, ``script``,
    and ``action`` so security review can reconstruct the matcher ->
    file mapping without grepping source.
    """

    artifact: str
    platform: str
    inputs: int = 0
    outputs: int = 0
    skipped: int = 0
    notices: list[str] = field(default_factory=list)
    exit_code: int = 0
    hook_entries: list[dict[str, str]] = field(default_factory=list)


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


def _build_commands(repo_root: Path, config_path: Path, platform: str) -> GeneratorResult:
    """Bridge Claude commands to user-invocable skills (REQ-003-001, M4-T1).

    Skips silently when the platform has no ``artifacts.commands`` stanza
    (e.g. visual-studio, vscode platforms today). Tallies are read from
    the configured directories so the audit row reflects on-disk state,
    not generator internals.
    """
    try:
        cfg = load_platform_config(config_path)
    except ConfigError:
        cfg = {}
    artifacts = cfg.get("artifacts") if isinstance(cfg.get("artifacts"), dict) else {}
    stanza = artifacts.get("commands") if isinstance(artifacts, dict) else None
    if not isinstance(stanza, dict):
        result = GeneratorResult(artifact="commands", platform=platform, exit_code=0)
        result.notices.append(f"{platform}: no artifacts.commands stanza; skipped")
        return result

    rc = generate_commands.generate_commands(config_path, repo_root)
    result = GeneratorResult(artifact="commands", platform=platform, exit_code=rc)
    src = repo_root / str(stanza.get("sourceDir", ""))
    out = repo_root / str(stanza.get("outputDir", ""))
    if src.is_dir():
        # Top-level *.md files only (sub-directories are namespaced sub-
        # commands the generator skips). Mirrors generate_commands logic.
        result.inputs = sum(
            1 for p in src.glob("*.md") if p.is_file() and p.name != "CLAUDE.md"
        )
    if out.is_dir():
        # We can't distinguish command-bridged skills from skills generator
        # output by file alone, so report 0 and let the per-generator log
        # carry the truth. Inputs is the load-bearing number for staleness.
        result.outputs = 0
    return result


def _build_rules(repo_root: Path, config_path: Path, platform: str) -> GeneratorResult:
    """Generate path-scoped instruction files (REQ-003-006, M4-T2).

    Universal rules without path scope are gated by severity:
    high → exit 1, medium → WARN skip, low → silent skip,
    unset+keyword → high (exit 1), unset+no-keyword → medium (skip).
    Skipped silently when the platform has no ``artifacts.rules`` stanza.
    """
    try:
        cfg = load_platform_config(config_path)
    except ConfigError:
        cfg = {}
    artifacts = cfg.get("artifacts") if isinstance(cfg.get("artifacts"), dict) else {}
    stanza = artifacts.get("rules") if isinstance(artifacts, dict) else None
    if not isinstance(stanza, dict):
        result = GeneratorResult(artifact="rules", platform=platform, exit_code=0)
        result.notices.append(f"{platform}: no artifacts.rules stanza; skipped")
        return result

    rc, run_result = generate_rules.generate_rules(config_path, repo_root)
    result = GeneratorResult(artifact="rules", platform=platform, exit_code=rc)
    src = repo_root / str(stanza.get("sourceDir", ""))
    if src.is_dir():
        result.inputs = sum(1 for _ in src.glob("*.md"))
    result.outputs = run_result.written
    result.skipped = run_result.sentinel_skipped
    return result


def _build_lib(repo_root: Path, config_path: Path, platform: str) -> GeneratorResult:
    """Copy `.claude/lib/` to the platform's lib output directory (M7-T1).

    Hook scripts under `src/<provider>/hooks/<event>/` import
    ``hook_utilities`` from the sibling ``lib/`` of the plugin manifest.
    Without this step, every shimmed hook crashes on import in the
    install layout because the lib tree is never copied. M7-T1 closes
    that gap by mirroring `.claude/lib/` (the canonical source) to
    ``src/copilot-cli/lib/`` (the install destination), excluding
    ``__pycache__`` directories.

    Skips silently when the platform has no ``artifacts.lib`` stanza.
    """
    try:
        cfg = load_platform_config(config_path)
    except ConfigError:
        cfg = {}
    artifacts = cfg.get("artifacts") if isinstance(cfg.get("artifacts"), dict) else {}
    stanza = artifacts.get("lib") if isinstance(artifacts, dict) else None
    if not isinstance(stanza, dict):
        result = GeneratorResult(artifact="lib", platform=platform, exit_code=0)
        result.notices.append(f"{platform}: no artifacts.lib stanza; skipped")
        return result

    src_rel = stanza.get("sourceDir")
    out_rel = stanza.get("outputDir")
    if not isinstance(src_rel, str) or not isinstance(out_rel, str):
        result = GeneratorResult(artifact="lib", platform=platform, exit_code=2)
        result.notices.append(
            f"{platform}: artifacts.lib missing sourceDir or outputDir"
        )
        return result

    src = (repo_root / src_rel).resolve()
    out = (repo_root / out_rel).resolve()
    repo_root_resolved = repo_root.resolve()
    # Containment guard: refuse to write outside the repo root.
    if not str(out).startswith(str(repo_root_resolved) + "/") and out != repo_root_resolved:
        result = GeneratorResult(artifact="lib", platform=platform, exit_code=2)
        result.notices.append(
            f"{platform}: artifacts.lib.outputDir escapes repo root: {out_rel}"
        )
        return result

    result = GeneratorResult(artifact="lib", platform=platform, exit_code=0)
    if not src.is_dir():
        result.notices.append(f"{platform}: lib source dir missing: {src_rel}")
        return result

    import shutil as _shutil

    if out.exists():
        _shutil.rmtree(out)
    _shutil.copytree(
        src,
        out,
        ignore=_shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    result.inputs = sum(1 for _ in src.rglob("*.py") if "__pycache__" not in _.parts)
    result.outputs = sum(1 for _ in out.rglob("*.py") if "__pycache__" not in _.parts)
    return result


def _build_hooks(repo_root: Path, config_path: Path, platform: str) -> GeneratorResult:
    """Generate Copilot CLI hook config (REQ-003-007, M5-T6).

    Mirrors :func:`_build_rules`: skips silently when the platform has
    no ``artifacts.hooks`` stanza. Tallies inputs as the number of
    Claude hook entries in ``settings.json`` (across all events) and
    outputs as the number of entries written to the Copilot
    ``hooks.json`` (post event-drop). ``skipped`` counts NO-REGEN
    sentinel hits on copied scripts; ``dropped`` counts events landing
    in ``eventDrop``.
    """
    try:
        cfg = load_platform_config(config_path)
    except ConfigError:
        cfg = {}
    artifacts = cfg.get("artifacts") if isinstance(cfg.get("artifacts"), dict) else {}
    stanza = artifacts.get("hooks") if isinstance(artifacts, dict) else None
    if not isinstance(stanza, dict):
        result = GeneratorResult(artifact="hooks", platform=platform, exit_code=0)
        result.notices.append(f"{platform}: no artifacts.hooks stanza; skipped")
        return result

    rc, run_result = generate_hooks.generate_hooks(config_path, repo_root)
    result = GeneratorResult(artifact="hooks", platform=platform, exit_code=rc)
    settings_source = stanza.get("settingsSource")
    if isinstance(settings_source, str):
        settings_path = repo_root / settings_source
        if settings_path.is_file():
            try:
                import json as _json
                data = _json.loads(settings_path.read_text(encoding="utf-8"))
                hooks_obj = data.get("hooks", {}) if isinstance(data, dict) else {}
                count = 0
                for groups in hooks_obj.values() if isinstance(hooks_obj, dict) else []:
                    if not isinstance(groups, list):
                        continue
                    for group in groups:
                        if not isinstance(group, dict):
                            continue
                        count += len(group.get("hooks", []) or [])
                result.inputs = count
            except (OSError, ValueError):
                result.inputs = 0
    result.outputs = run_result.written
    result.skipped = run_result.sentinel_skipped
    if run_result.dropped:
        result.notices.append(
            f"{platform}: dropped {run_result.dropped} hook entr"
            f"{'y' if run_result.dropped == 1 else 'ies'} (eventDrop)"
        )
    # Surface the per-script audit detail to the rendered markdown so
    # security review sees matcher -> file mapping without grep. The
    # generator owns the suffix scheme; we re-derive the on-disk
    # filename here using the same helper.
    from generate_hooks import _matcher_suffix

    output_scripts = stanza.get("outputScripts")
    for entry in run_result.entries:
        if entry.action == "emitted" and isinstance(output_scripts, str) and entry.event_target:
            stem = Path(entry.script).stem
            suffix = _matcher_suffix(entry.matcher) if entry.matcher else ""
            file_name = f"{stem}__{suffix}.py" if suffix else f"{stem}.py"
            target = f"{output_scripts}/{entry.event_target}/{file_name}"
        elif entry.action == "dropped":
            target = "(dropped)"
        elif entry.action == "sentinel-skipped":
            target = "(NO-REGEN)"
        else:
            target = ""
        result.hook_entries.append(
            {
                "event_source": entry.event_source,
                "event_target": entry.event_target or "",
                "matcher": entry.matcher or "",
                "script": entry.script,
                "target": target,
                "action": entry.action,
            }
        )
    return result


# Order matters: agents → skills → commands → rules → lib → hooks.
# The skills generator copies .claude/skills/* first; the commands bridge
# layers user-invocable skills beside them; rules write to a separate dir
# (.github/instructions/); lib MUST land before hooks so the manifest-
# walk-up bootstrap in shimmed hooks finds .claude-plugin/plugin.json
# alongside lib/; hooks write src/copilot-cli/hooks/.
GENERATORS: list[tuple[str, Callable[[Path, Path, str], GeneratorResult]]] = [
    ("agents", _build_agents),
    ("skills", _build_skills),
    ("commands", _build_commands),
    ("rules", _build_rules),
    ("lib", _build_lib),
    ("hooks", _build_hooks),
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
    # Per-script hook detail (REQ-003-007): one subsection per platform
    # whose hooks generator produced entries. Lets security review map
    # each generated file back to its source matcher without grep.
    for r in audit.results:
        if r.artifact != "hooks" or not r.hook_entries:
            continue
        lines.append("")
        lines.append(f"### Hooks ({r.platform})")
        lines.append("")
        lines.append("| Claude Event | Matcher | Target | Action |")
        lines.append("|---|---|---|---|")
        for entry in r.hook_entries:
            matcher = entry.get("matcher") or "(none)"
            lines.append(
                f"| {entry.get('event_source', '')} "
                f"| {matcher} "
                f"| {entry.get('target', '')} "
                f"| {entry.get('action', '')} |"
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
                "hook_entries": r.hook_entries,
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
