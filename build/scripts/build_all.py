#!/usr/bin/env python3
"""Orchestrate per-artifact generators (REQ-003-005, -008, -010, -011).

Runs every artifact generator wired in ``GENERATORS`` for one or more
platforms, emits an audit log under ``build/audit/`` (overwrite, not
append; not git-tracked), and offers staleness, clean, and audit-format
modes for CI integration.

CLI:
    uv run python build/scripts/build_all.py
    uv run python build/scripts/build_all.py --check
    uv run python build/scripts/build_all.py --clean
    uv run python build/scripts/build_all.py --audit-format json
    uv run python build/scripts/build_all.py --platform copilot-cli

EXIT CODES:
    0 - success
    1 - generator logic error
    2 - configuration error / staleness detected (--check)
    3 - audit blocklist violation (REQ-003-011)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

import generate_adr_index  # noqa: E402
import generate_commands  # noqa: E402
import generate_hooks  # noqa: E402
import generate_rules  # noqa: E402
import generate_skills  # noqa: E402
from yaml_loader import ConfigError, load_platform_config  # noqa: E402

# Path to the agent generator. Imported lazily because build/ is on a
# separate path; see build_agents().
_BUILD_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_BUILD_DIR))
import generate_agent_catalog  # noqa: E402


@dataclass
class GeneratorResult:
    """One generator's contribution to the audit log.

    ``hook_entries`` carries optional per-script audit detail emitted by
    the hooks generator (REQ-003-007). Each entry includes the source
    event, target event, matcher, script, target, action, and reason so
    security review can reconstruct every emitted or dropped mapping.
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
    artifacts = cfg.get("artifacts")
    stanza = (artifacts or {}).get("skills") if isinstance(artifacts, dict) else None
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


def _build_agent_catalog(repo_root: Path, _config_path: Path, _platform: str) -> GeneratorResult:
    """Regenerate docs/agent-catalog.md from templates/agents/*.shared.md."""
    templates_dir = repo_root / "templates" / "agents"
    output_path = repo_root / "docs" / "agent-catalog.md"
    if not templates_dir.is_dir():
        result = GeneratorResult(artifact="agent-catalog", platform="docs", exit_code=0)
        result.notices.append("agent catalog templates dir missing; skipped")
        return result
    rc = generate_agent_catalog.main(
        [
            "--templates-path",
            str(templates_dir),
            "--output",
            str(output_path),
        ]
    )
    result = GeneratorResult(artifact="agent-catalog", platform="docs", exit_code=rc)
    if templates_dir.is_dir():
        result.inputs = sum(1 for _ in templates_dir.glob("*.shared.md"))
    result.outputs = 1 if output_path.is_file() else 0
    return result


def _build_adr_index(repo_root: Path, _config_path: Path, _platform: str) -> GeneratorResult:
    """Regenerate .agents/architecture/README.md from the ADR corpus.

    Repo-level like ``_build_agent_catalog``, not per-platform: there is one ADR
    corpus and one index, and running it once per platform config would write the
    same bytes N times. ``_run_generators`` calls it in the run-once block for
    that reason.

    ``.agents/architecture/README.md`` is registered in :data:`OWNED_PREFIXES` so
    both ``--check`` consumers cover it: the staleness diff reports an ADR change
    that landed without a regeneration, and the snapshot/restore guard keeps
    ``--check`` read-only for this file the way it already does for
    ``docs/agent-catalog.md``.
    """
    adr_dir = repo_root / ".agents" / "architecture"
    output_path = adr_dir / "README.md"
    if not adr_dir.is_dir():
        result = GeneratorResult(artifact="adr-index", platform="docs", exit_code=0)
        result.notices.append("ADR directory missing; skipped")
        return result
    rc = generate_adr_index.main(
        [
            "--adr-dir",
            str(adr_dir),
            "--output",
            str(output_path),
        ]
    )
    result = GeneratorResult(artifact="adr-index", platform="docs", exit_code=rc)
    result.inputs = sum(
        1
        for path in adr_dir.glob("ADR-*.md")
        if generate_adr_index.is_adr_filename(path.name)
    )
    result.outputs = 1 if output_path.is_file() else 0
    return result


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


def _build_directory_copy(
    repo_root: Path,
    config_path: Path,
    platform: str,
    *,
    artifact_name: str,
    count_glob: str,
) -> GeneratorResult:
    """Generic directory-mirror builder for ``artifacts.<artifact_name>`` stanzas.

    Used by :func:`_build_lib` to copy a configured source dir to a
    configured output dir, with pycache exclusion and a containment
    guard. Retained as a shared helper so additional directory-mirror
    artifacts can reuse it without duplicating the logic.

    Parameters:
        artifact_name: stanza key under ``artifacts`` and the value used
            in the audit row's ``artifact`` field.
        count_glob: rglob pattern used for inputs/outputs counts (e.g.,
            ``"*.py"`` for lib). Matched files inside ``__pycache__`` are
            excluded from the count.

    Skips silently when the platform has no ``artifacts.<name>`` stanza.
    """
    try:
        cfg = load_platform_config(config_path)
    except ConfigError:
        cfg = {}
    artifacts = cfg.get("artifacts") if isinstance(cfg.get("artifacts"), dict) else {}
    stanza = artifacts.get(artifact_name) if isinstance(artifacts, dict) else None
    if not isinstance(stanza, dict):
        result = GeneratorResult(artifact=artifact_name, platform=platform, exit_code=0)
        result.notices.append(
            f"{platform}: no artifacts.{artifact_name} stanza; skipped"
        )
        return result

    src_rel = stanza.get("sourceDir")
    out_rel = stanza.get("outputDir")
    if not isinstance(src_rel, str) or not isinstance(out_rel, str):
        result = GeneratorResult(artifact=artifact_name, platform=platform, exit_code=2)
        result.notices.append(
            f"{platform}: artifacts.{artifact_name} missing sourceDir or outputDir"
        )
        return result

    src = (repo_root / src_rel).resolve()
    out = (repo_root / out_rel).resolve()
    repo_root_resolved = repo_root.resolve()
    # Containment guard (CWE-22): the output dir must resolve to a path
    # strictly under the repo root. is_relative_to handles OS path
    # separators correctly and avoids the prefix-confusion failure mode
    # of string startswith. Equality with the repo root is also rejected
    # because the rmtree-then-copytree below would otherwise wipe the
    # entire working tree when outputDir resolves to ".".
    if out == repo_root_resolved or not out.is_relative_to(repo_root_resolved):
        result = GeneratorResult(artifact=artifact_name, platform=platform, exit_code=2)
        result.notices.append(
            f"{platform}: artifacts.{artifact_name}.outputDir escapes repo root: {out_rel}"
        )
        return result

    result = GeneratorResult(artifact=artifact_name, platform=platform, exit_code=0)
    if not src.is_dir():
        result.notices.append(
            f"{platform}: {artifact_name} source dir missing: {src_rel}"
        )
        return result

    import shutil as _shutil

    if out.exists():
        _shutil.rmtree(out)
    _shutil.copytree(
        src,
        out,
        ignore=_shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    result.inputs = sum(
        1 for _ in src.rglob(count_glob) if "__pycache__" not in _.parts
    )
    result.outputs = sum(
        1 for _ in out.rglob(count_glob) if "__pycache__" not in _.parts
    )
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
    return _build_directory_copy(
        repo_root,
        config_path,
        platform,
        artifact_name="lib",
        count_glob="*.py",
    )


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
        drop_reasons = sorted(
            {
                entry.reason
                for entry in run_result.entries
                if entry.action == "dropped" and entry.reason
            }
        )
        reason_summary = "; ".join(drop_reasons) or "reason unavailable"
        result.notices.append(
            f"{platform}: dropped {run_result.dropped} hook entr"
            f"{'y' if run_result.dropped == 1 else 'ies'} ({reason_summary})"
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
                "reason": entry.reason,
            }
        )
    return result


# Order matters: agents → agent-catalog → adr-index → skills → commands → rules → lib → hooks.
# The skills generator copies .claude/skills/* first; the commands bridge
# layers user-invocable skills beside them; rules write to a separate dir
# (.github/instructions/); lib MUST land before hooks so the manifest-
# walk-up bootstrap in shimmed hooks finds .claude-plugin/plugin.json
# alongside lib/; hooks write src/copilot-cli/hooks/.
GENERATORS: list[tuple[str, Callable[[Path, Path, str], GeneratorResult]]] = [
    ("agents", _build_agents),
    ("agent-catalog", _build_agent_catalog),
    ("adr-index", _build_adr_index),
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


def _markdown_table_cell(value: object) -> str:
    """Escape one value for a single-line Markdown table cell."""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("|", r"\|").replace("\n", "<br>")


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
        lines.append(
            "| Claude Event | Source Script | Matcher | Target | Action | Reason |"
        )
        lines.append("|---|---|---|---|---|---|")
        for entry in r.hook_entries:
            source = _markdown_table_cell(entry.get("event_source", ""))
            script = _markdown_table_cell(entry.get("script", ""))
            matcher = _markdown_table_cell(entry.get("matcher") or "(none)")
            target = _markdown_table_cell(entry.get("target", ""))
            action = _markdown_table_cell(entry.get("action", ""))
            reason = _markdown_table_cell(entry.get("reason") or "(none)")
            lines.append(
                f"| {source} | {script} | {matcher} | {target} "
                f"| {action} | {reason} |"
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
    """Return changed paths via ``git diff --name-only`` UNION untracked.

    Unions tracked-file modifications (``git diff --name-only``) with
    untracked files honoring .gitignore (``git ls-files --others
    --exclude-standard``). The union is required so that #2222-class
    failures are detected: when a generator-owned file is removed from
    the index and then regenerated, ``git diff`` reports it as deleted
    but ``git status`` shows the regenerated copy as untracked. Without
    the untracked half, --check and the .claude/ guard both miss it.

    Used by --check (staleness) and the .claude/ guard. A failure to run
    git is treated as no-diff: this is a CI-side check, and CI always has
    git. We do not want to fail when a contributor runs the script in a
    non-git working tree.
    """
    paths: list[str] = []
    seen: set[str] = set()
    scrubbed_env = _git_scrubbed_env()
    for argv in (
        ["git", "-C", str(repo_root), "diff", "--name-only"],
        ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
                env=scrubbed_env,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            p = line.strip()
            if p and p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


# The .claude/ tree is off-limits to generators (REQ-003-010). It is
# snapshotted before the generators run, then compared after, so the guard
# attributes only writes the generators themselves made. Git-diff scoping
# (the prior approach) flagged any pre-build drift, including a legitimate
# `.claude/lib` sync from scripts/sync_plugin_lib.py (issue #2613).
CLAUDE_GUARD_PREFIX: tuple[str, ...] = (".claude/",)

# Git honors these env vars over ``-C``/discovery: an inherited GIT_DIR or
# GIT_WORK_TREE (for example when build_all.py runs inside a git hook) would
# redirect ``git ls-files`` away from ``repo_root`` and yield the wrong ignore
# set. Strip them so the subprocess resolves the repo purely from ``-C``.
_GIT_LOCATION_ENV_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
)


def _git_scrubbed_env() -> dict[str, str]:
    """Return a copy of the process env with git location overrides removed."""
    env = dict(os.environ)
    for key in _GIT_LOCATION_ENV_VARS:
        env.pop(key, None)
    return env


def assert_no_claude_writes(
    repo_root: Path, baseline: dict[Path, bytes]
) -> list[str]:
    """REQ-003-010: generators MUST NOT write under .claude/.

    ``baseline`` is a snapshot of the .claude/ tree captured BEFORE any
    generator ran (see :func:`_snapshot_owned_prefixes`). This function
    re-reads the tree and returns the repo-relative paths the generators
    created, modified, or deleted relative to that baseline.

    Scoping to generator-attributable writes (not raw git diff) lets a
    legitimate pre-build sync of .claude/lib pass while still tripping on
    a generator that writes under .claude/ during the run (issue #2613).

    Returns the sorted list of offending paths (empty when compliant).

    Candidates are re-checked against git before they are reported. The
    ignore set :func:`_snapshot_owned_prefixes` applies is computed before
    the tree walk, so a gitignored file created in between (CPython writing
    bytecode, a hook appending to ``audit.log``) is walked but not excluded
    and reads as a generator write. That window is reliably reachable: the
    pre-push ``build-all-check`` job shares a ``parallel: true`` lefthook
    group with a multi-minute ``python-tests`` job that byte-compiles under
    ``.claude/lib/`` throughout (issue #3773).
    """
    current = _snapshot_owned_prefixes(
        repo_root, CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )
    offending: set[Path] = set()
    for path, content in current.items():
        if baseline.get(path) != content:
            offending.add(path)  # created or modified by a generator
    for path in baseline.keys() - current.keys():
        offending.add(path)  # deleted by a generator
    offending -= _confirm_ignored(repo_root, offending)
    return sorted(str(p.relative_to(repo_root)) for p in offending)


def _confirm_ignored(repo_root: Path, candidates: set[Path]) -> set[Path]:
    """Return the subset of ``candidates`` git currently reports as ignored.

    Closes the report-time half of the race described in
    :func:`assert_no_claude_writes`. Generators never emit gitignored files,
    which is the same premise :func:`_ignored_paths` rests on, so a candidate
    git calls ignored is a runtime artifact and not a violation.

    ``git check-ignore`` exits 1 when nothing matches, which is the ordinary
    clean case, so the return code is not an error signal here. A failure to
    run git at all returns the empty set, leaving every candidate reported:
    the guard stays fail-closed when it cannot confirm.

    ``--stdin`` echoes back the matching input paths verbatim, so the result
    is a subset of ``candidates`` by construction and needs no re-filtering.
    """
    if not candidates:
        return set()
    payload = b"\0".join(os.fsencode(str(p)) for p in sorted(candidates))
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "--stdin", "-z"],
            input=payload,
            capture_output=True,
            check=False,
            env=_git_scrubbed_env(),
        )
    except OSError:
        return set()
    # git check-ignore exits 0 when at least one path matched, 1 when none
    # did, and 128 on error. Only 0 and 1 carry a trustworthy answer. Any
    # other code returns the empty set, which leaves every candidate
    # un-excluded and so keeps the guard fail-closed.
    if completed.returncode not in (0, 1):
        return set()
    # Decode with os.fsdecode (surrogateescape on POSIX) so a non-UTF-8
    # filename round-trips instead of raising UnicodeDecodeError and
    # crashing the pre-push guard. Splitting on bytes first keeps the
    # NUL delimiter unambiguous.
    return {
        Path(os.fsdecode(raw))
        for raw in completed.stdout.split(b"\0")
        if raw
    }


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


# --- Owned prefixes: scope shared by --check staleness and snapshot ------
#
# These are the directories generators are allowed to own. Two consumers
# need the exact same scope, kept identical here:
#   1. The --check staleness diff (filter on `git diff` output).
#   2. The --check snapshot/restore guard (#2440) that keeps --check
#      read-only by reverting any generator writes under these prefixes.
# Keep these in lock-step. If a new generator lands that writes to a
# different prefix, add it here so both behaviors keep covering it.
OWNED_PREFIXES: tuple[str, ...] = (
    "src/",
    ".github/instructions/",
    "docs/agent-catalog.md",
    ".agents/architecture/README.md",
)


def _is_bytecode_artifact(path: Path) -> bool:
    """Return True for paths CPython writes as import side effects.

    The rule is deliberately wider than "is a ``.pyc``": any file under a
    ``__pycache__`` directory matches, whatever its extension, plus any
    ``.pyc`` or ``.pyo`` anywhere. CPython is not the only writer into
    ``__pycache__`` (coverage and mypy drop their own caches there), and a
    filter narrowed to bytecode extensions would let those reopen the race
    this function exists to close. Do not narrow it to ``.pyc``/``.pyo``.

    :func:`_ignored_paths` already excludes gitignored files, but it queries
    git once per snapshot: a ``.pyc`` written after that query and before the
    ``rglob`` walk still lands in the snapshot. The pre-push hook runs the
    test suite concurrently with the REQ-003-010 guard (``lefthook.yml`` marks
    that job group ``parallel: true``), so pytest importing ``.claude/lib``
    writes bytecode inside the guard's snapshot window and the guard
    attributes it to a generator (issue #3856).

    Matching on path shape is race-immune because it does not depend on a
    point-in-time query. Excluding bytecode cannot mask a real violation:
    generators emit source and data files, never compiled bytecode.

    Only the comparison path may use this. The ``--check`` snapshot/restore
    path must not, or restore deletes pre-existing caches; see
    :func:`_snapshot_owned_prefixes`.
    """
    return "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo")


def _ignored_paths(repo_root: Path, prefixes: tuple[str, ...]) -> set[Path]:
    """Return absolute paths of gitignored files under ``prefixes``.

    Runtime artifacts such as ``.claude/hooks/audit.log`` and the
    ``__pycache__/*.pyc`` bytecode caches are gitignored. Generators never
    emit gitignored files, so the REQ-003-010 guard must exclude them: a
    session hook appending to ``audit.log`` or CPython writing bytecode
    during the build window would otherwise register as a spurious
    generator write and fail the build nondeterministically (issue #2992).

    Uses ``git ls-files --others --ignored --exclude-standard`` (one call
    per prefix, NUL-delimited). A git failure returns whatever was gathered
    so far: the guard then falls back to snapshotting those paths, which is
    safe but not race-immune. Paths are built as ``repo_root / rel`` without
    ``resolve()`` so they compare equal to the ``rglob`` output in
    :func:`_snapshot_owned_prefixes`.

    Git location env vars (``GIT_DIR`` and friends) are stripped from the
    subprocess env so an inherited value cannot redirect ``ls-files`` away
    from ``repo_root`` (issue #2992 hook-execution context).
    """
    ignored: set[Path] = set()
    scrubbed_env = _git_scrubbed_env()
    for prefix in prefixes:
        argv = [
            "git",
            "-C",
            str(repo_root),
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
            "--",
            prefix,
        ]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                check=False,
                timeout=30,
                env=scrubbed_env,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        for raw in proc.stdout.split(b"\x00"):
            if not raw:
                continue
            rel = os.fsdecode(raw)
            ignored.add(repo_root / rel)
    return ignored


def _snapshot_owned_prefixes(
    repo_root: Path,
    prefixes: tuple[str, ...],
    *,
    exclude_ignored: bool = False,
) -> dict[Path, bytes]:
    """Snapshot every file under ``prefixes`` into an in-memory dict.

    Returns a mapping of absolute Path → raw bytes for every regular file
    found under each prefix that exists. Directories that do not exist
    are silently skipped (they may be created by generators).

    Used by --check to make the build orchestrator read-only (#2440).
    The snapshot is held in process memory because the real owned-prefix
    tree is ~21MB and a temp-dir copytree adds I/O and cleanup hazards
    without buying meaningful safety. Symlinks under owned prefixes are
    not in scope today: generators only emit regular files, and treating
    them as such matches the existing copytree semantics in
    :func:`_build_directory_copy`.

    When ``exclude_ignored`` is set, gitignored runtime artifacts (see
    :func:`_ignored_paths`) and bytecode caches (see
    :func:`_is_bytecode_artifact`) are omitted. The REQ-003-010 guard passes
    this so a concurrent hook write to ``.claude/hooks/audit.log`` or a
    bytecode recompile does not read as a generator write (issue #2992).

    Both exclusions are tied to that flag on purpose. The guard only
    *compares* two snapshots, so dropping a path merely stops it being
    reported. ``--check`` *restores* from its snapshot, and
    :func:`_restore_owned_prefixes` deletes anything on disk that the
    snapshot does not name. Excluding bytecode there would delete every
    pre-existing ``__pycache__`` under an owned prefix, which is the same
    cache-eviction that makes the next run recompile inside the guard
    window: the exact race issue #3856 closes.
    """
    ignored = _ignored_paths(repo_root, prefixes) if exclude_ignored else set()
    snapshot: dict[Path, bytes] = {}
    for prefix in prefixes:
        root = repo_root / prefix
        if root.is_file() and not root.is_symlink():
            if root in ignored:
                continue
            try:
                snapshot[root] = root.read_bytes()
            except OSError:
                continue
            continue
        if root.exists() and not root.is_dir():
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if path in ignored or (exclude_ignored and _is_bytecode_artifact(path)):
                continue
            try:
                snapshot[path] = path.read_bytes()
            except OSError:
                # Unreadable file (permissions, race). Skip — restore will
                # treat it as not-present which keeps the working tree at
                # least as clean as it was before the run.
                continue
    return snapshot


def _restore_owned_prefixes(
    repo_root: Path,
    prefixes: tuple[str, ...],
    snapshot: dict[Path, bytes],
) -> None:
    """Restore the working tree to the snapshot state under ``prefixes``.

    Three cases per path:
      1. In snapshot AND on disk → if content differs, overwrite with
         snapshot bytes.
      2. In snapshot AND not on disk → write snapshot bytes back (the
         file existed before the run, the generator deleted it).
      3. On disk AND not in snapshot → delete it (the generator created
         a new path that did not exist pre-run).

    After this returns, every file under ``prefixes`` matches its
    pre-run state. Pre-existing dirty state (uncommitted edits, untracked
    files) is preserved exactly because the snapshot captured it.
    """
    current = _enumerate_files_under(repo_root, prefixes)

    # Cases 1 & 2: restore every file that was in the snapshot.
    for path, content in snapshot.items():
        try:
            if (
                path.is_file()
                and not path.is_symlink()
                and path.read_bytes() == content
            ):
                continue  # already matches snapshot
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            elif path.exists() or path.is_symlink():
                path.unlink()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except OSError as exc:
            # Best-effort restore; surface so CI logs show what was missed.
            print(
                f"WARN: failed to restore {path} after --check: {exc}",
                file=sys.stderr,
            )

    # Case 3: delete files that exist now but were not in the snapshot.
    for path in current - set(snapshot):
        try:
            path.unlink()
        except OSError as exc:
            print(
                f"WARN: failed to remove generator-created {path} after --check: {exc}",
                file=sys.stderr,
            )

    _prune_empty_dirs(repo_root, prefixes)


def _enumerate_files_under(
    repo_root: Path, prefixes: tuple[str, ...]
) -> set[Path]:
    """Return every regular non-symlink file under any of ``prefixes``."""
    found: set[Path] = set()
    for prefix in prefixes:
        root = repo_root / prefix
        if root.is_file() and not root.is_symlink():
            found.add(root)
            continue
        if root.exists() and not root.is_dir():
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                found.add(path)
    return found


def _prune_empty_dirs(repo_root: Path, prefixes: tuple[str, ...]) -> None:
    """Remove empty directories the generator created under ``prefixes``.

    Walks bottom-up so child dirs go before parents. Never touches the
    prefix root itself.
    """
    for prefix in prefixes:
        root = repo_root / prefix
        if root.is_file():
            continue
        if not root.is_dir():
            continue
        for dirpath in sorted(
            (p for p in root.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            try:
                if not any(dirpath.iterdir()):
                    dirpath.rmdir()
            except OSError:
                continue


def run(
    repo_root: Path,
    *,
    platform: str | None,
    check: bool,
    clean: bool,
    audit_format: str,
) -> int:
    repo_root = repo_root.resolve()
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

    # #2440: --check must be read-only. Snapshot the owned-prefix trees
    # BEFORE any generator runs so we can revert any writes after the
    # staleness diff is computed. This makes --check safe to call from
    # any worktree without dirtying it.
    snapshot: dict[Path, bytes] | None = None
    if check:
        snapshot = _snapshot_owned_prefixes(repo_root, OWNED_PREFIXES)

    # REQ-003-010 (issue #2613): snapshot the .claude/ tree before any
    # generator runs so the no-write guard attributes only writes the
    # generators made, not pre-build drift such as a .claude/lib sync.
    claude_baseline = _snapshot_owned_prefixes(
        repo_root, CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )

    try:
        return _run_generators(
            repo_root,
            configs,
            check=check,
            audit_format=audit_format,
            claude_baseline=claude_baseline,
        )
    finally:
        # #2440: ALWAYS restore on --check, including on exception paths.
        # Otherwise a generator crash mid-build leaves partial writes
        # in the caller's worktree.
        if snapshot is not None:
            _restore_owned_prefixes(repo_root, OWNED_PREFIXES, snapshot)


def _run_generators(
    repo_root: Path,
    configs: list[Path],
    *,
    check: bool,
    audit_format: str,
    claude_baseline: dict[Path, bytes],
) -> int:
    """Execute the generator pipeline and emit the audit log.

    Split out of :func:`run` so the snapshot/restore wrapping stays
    legible. Returns the orchestrator exit code.
    """
    audit = BuildAudit(started_at=time.time())
    started = time.monotonic()

    # Generators that iterate all platforms or write repo-level artifacts run once.
    # Call by name instead of through GENERATORS so tests can monkeypatch these
    # seams without updating the tuple's captured function objects.
    for result in (
        _build_agents(repo_root, configs[0], "*"),
        _build_agent_catalog(repo_root, configs[0], "*"),
        _build_adr_index(repo_root, configs[0], "*"),
    ):
        audit.results.append(result)
        if result.exit_code != 0:
            audit.overall_exit = max(audit.overall_exit, result.exit_code)

    # Per-platform per-artifact generators.
    for cfg in configs:
        platform_name = cfg.stem
        for artifact, fn in GENERATORS:
            if artifact in {"agents", "agent-catalog", "adr-index"}:
                continue  # ran once above
            result = fn(repo_root, cfg, platform_name)
            audit.results.append(result)
            if result.exit_code != 0:
                audit.overall_exit = max(audit.overall_exit, result.exit_code)

    audit.duration_s = time.monotonic() - started

    # REQ-003-010: enforce .claude/ no-write invariant.
    claude_writes = assert_no_claude_writes(repo_root, claude_baseline)
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
        diff = [
            p for p in _git_diff_paths(repo_root)
            if any(p.startswith(prefix) for prefix in OWNED_PREFIXES)
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
