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
    2 - configuration error; staleness detected (--check); a path under
        OWNED_PREFIXES that cannot be read, redirects (symlink or
        junction), or holds a nested git repository (--check, aborts
        before generation); a generator wrote under .claude/
        (REQ-003-010)
    3 - audit blocklist violation (REQ-003-011); git state unreadable
        (--check)

Exit 2 has four producers and only the staleness one is fixed by
regenerating and committing. The unreachable-owned-path producer arrived with
issue #4632 and covers three shapes: a path that cannot be read, one that
redirects (a symlink or a Windows junction, which is a directory carrying a
reparse tag and passes every symlink test), and a directory holding its own
``.git`` entry. All three are cases where ``--check`` could write somewhere it
cannot restore, so it refuses before any generator runs.

The fourth producer is the REQ-003-010 no-write violation,
set in :func:`_run_generators` when :func:`assert_no_claude_writes` reports a
write under ``.claude/``: that is a generator policy failure, and regenerating
reproduces it, because the offending generator runs again.

Exit 3 covers the two failures that are not a stale tree: an audit blocklist
violation, and a git that could not answer. Git is an external tool and
``AGENTS.md`` reads "0=ok|1=logic|2=config|3=external", so every git-read
failure lands here: a git that will not launch, one that times out, and one
that exits nonzero. Neither exit-3 producer is cleared by regenerating.

Do not split "not a git repository" back out to 2. It is a git fatal like any
other, git localizes its fatal messages so no stderr match is reliable, and
routing it to 2 would put "your environment is broken" back in the same code
as "regenerate and commit", which is the conflation this split exists to
remove.

Issue #4632 reversed a promise the old :func:`_git_diff_paths` docstring
made: "We do not want to fail when a contributor runs the script in a non-git
working tree." ``--check`` in a non-git tree now exits 3. A plain
(non-``--check``) build there still succeeds, because :func:`_git_diff_paths`
is reached only under ``--check``.

That last sentence is a claim about one function, not about the script.
Every run, ``--check`` or not, snapshots ``.claude/`` for the REQ-003-010
guard with ``exclude_ignored=True``, and that path calls
:func:`_ignored_paths`, which shells out to ``git ls-files``. A plain build
in a broken-git tree therefore does read git; it survives because
:func:`_ignored_paths` tolerates its own failures and returns what it
gathered, not because nothing asked git. Do not read the fail-closed change
here as "the script only touches git under ``--check``".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

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

    A missing ``adr_dir`` is not pre-checked and turned into a silent skip
    here: unlike the per-platform artifacts elsewhere in this module, there is
    exactly one ADR corpus, required for the whole repo, and
    ``generate_adr_index.main`` already fails loud on its absence (ADR-035
    exit 2, "ADR directory not found"). A wrapper-level skip converted that
    into an exit-0 "skipped" notice, so ``build_all.py --check`` could report
    green after examining zero ADRs if the corpus directory were absent (PR
    #5209 review, discussion_r3831902216). Calling ``main`` unconditionally
    preserves its own contract instead of shadowing it with a second,
    looser one.
    """
    adr_dir = repo_root / ".agents" / "architecture"
    output_path = adr_dir / "README.md"
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


class GitStateUnreadableError(RuntimeError):
    """Raised when git cannot report the working-tree state (issue #4632).

    A caller that swallows this and substitutes an empty path list cannot
    tell "git says nothing changed" from "nobody asked git". Both render as
    ``[]``. See :func:`_git_diff_paths`.
    """


# git's stderr is unbounded, and the most common failure here is the worst
# case: `git diff --no-index` prints 128 lines of flag documentation when it
# refuses to run outside a repository. The pre-PR gate
# (scripts/validation/check_generated_staleness.py) echoes only the last
# _MAX_OUTPUT_LINES = 40 lines specifically so the diagnosis is last, so an
# unbounded detail pushes the diagnosis into the "earlier line(s) omitted"
# bucket and shows the operator nothing but flag help.
_GIT_STDERR_DETAIL_CHARS = 200


def _first_stderr_line(stderr: str | bytes | None) -> str:
    """Return git's first stderr line, capped, for a one-line error message."""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    raw = (stderr or "").strip()
    first = raw.splitlines()[0] if raw else ""
    return first[:_GIT_STDERR_DETAIL_CHARS] or "(no stderr)"


def _git_diff_paths(repo_root: Path) -> list[str]:
    """Return changed paths via ``git diff --name-only`` UNION untracked.

    Unions tracked-file modifications (``git diff --name-only``) with
    untracked files honoring .gitignore (``git ls-files --others
    --exclude-standard``). The union is required so that #2222-class
    failures are detected: when a generator-owned file is removed from
    the index and then regenerated, ``git diff`` reports it as deleted
    but ``git status`` shows the regenerated copy as untracked. Without
    the untracked half, --check misses it.

    Raises :class:`GitStateUnreadableError` when either git invocation fails to
    start, times out, or exits nonzero. All three are external failures, and
    the ``--check`` handler maps them to exit 3 per ``AGENTS.md``; see the
    module docstring. The prior behavior returned the
    paths gathered so far, which for a broken git is the empty list: the
    exact value a clean tree produces, so ``--check`` reported exit 0 over a
    tree it never examined (issue #4632, reproduction 1: ``PATH=/nonexistent
    build_all.py --check`` returned rc=0 with a stale generated file on
    disk). Fail-closed here costs nothing in CI, which always has git, and
    the only caller is the ``--check`` staleness gate, so a plain
    (non-``--check``) build in a non-git working tree still succeeds. That is
    this function's caller set, not the script's git use: :func:`_ignored_paths`
    runs git on every build and fails open (see the module docstring).

    The raised message stays one line: see :func:`_first_stderr_line`.

    The ``.claude/`` guard does NOT use this function. It compares two
    :func:`_snapshot_owned_prefixes` results; see
    :func:`assert_no_claude_writes`.
    """
    paths: list[str] = []
    seen: set[str] = set()
    scrubbed_env = _git_scrubbed_env()
    for argv in (
        ["git", "-C", str(repo_root), "diff", "--name-only", "-z"],
        [
            "git",
            "-C",
            str(repo_root),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
    ):
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                check=False,
                timeout=30,
                env=scrubbed_env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GitStateUnreadableError(
                f"could not run {' '.join(argv)}: {exc}"
            ) from exc
        if proc.returncode != 0:
            raise GitStateUnreadableError(
                f"{' '.join(argv)} exited {proc.returncode}: "
                f"{_first_stderr_line(proc.stderr)}"
            )
        for raw in proc.stdout.split(b"\x00"):
            p = os.fsdecode(raw)
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
    repo_root: Path,
    baseline: dict[Path, bytes],
    *,
    preexisting_boundaries: set[Path] | None = None,
) -> list[str]:
    """REQ-003-010: generators MUST NOT write under .claude/.

    ``baseline`` is a snapshot of the .claude/ tree captured BEFORE any
    generator ran (see :func:`_snapshot_owned_prefixes`). This function
    re-reads the tree and returns the repo-relative paths the generators
    created, modified, or deleted relative to that baseline.

    ``preexisting_boundaries`` is the set :func:`_git_boundaries_under`
    recorded before the generators ran, and it MUST be the same set the
    baseline snapshot used. Both walks stop at git repository boundaries.
    Detecting those by shape at each end independently means a generator
    can write a ``.git`` entry of its own and take the whole tree it
    created out of the second walk, while the first walk never saw it
    either, so the diff is empty and REQ-003-010 reports nothing.
    Measured before this argument existed: a generator creating
    ``.claude/out/.git`` plus ``.claude/out/leaked.md`` produced
    ``violations reported: []`` with the file still on disk. Passing one
    recorded set makes the two walks skip exactly the same trees, so a
    boundary that appeared during the build is walked and reported like
    any other generator write.

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
        repo_root,
        CLAUDE_GUARD_PREFIX,
        exclude_ignored=True,
        opaque_boundaries=preexisting_boundaries,
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

    An entry here can be a directory rather than a file: ``ls-files``
    reports an embedded git repository (a nested worktree checkout, for
    example under ``.claude/worktrees/<name>/``) as one ignored directory,
    not one entry per file inside it. Callers must treat each returned
    path as a prefix, not just an exact key: see
    :func:`_is_ignored_path`.
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
        except (OSError, subprocess.SubprocessError) as exc:
            print(
                f"WARN: git ls-files failed for {prefix!r}, ignore set may be "
                f"incomplete: {exc}",
                file=sys.stderr,
            )
            continue
        if proc.returncode != 0:
            print(
                f"WARN: git ls-files exited {proc.returncode} for {prefix!r}, "
                "ignore set may be incomplete",
                file=sys.stderr,
            )
            continue
        for raw in proc.stdout.split(b"\x00"):
            if not raw:
                continue
            rel = os.fsdecode(raw)
            ignored.add(repo_root / rel)
    return ignored


def _is_ignored_path(path: Path, ignored: set[Path]) -> bool:
    """Return True if ``path`` is ignored, or nested under an ignored dir.

    ``ignored`` (see :func:`_ignored_paths`) can hold directory entries: a
    nested worktree checkout is reported as one ignored directory, not one
    entry per file inside it. Matching ``ignored`` with plain set
    membership therefore misses every file nested under such a directory,
    which is what let a full worktree checkout get read into the
    :func:`_snapshot_owned_prefixes` snapshot instead of skipped (issue
    #5370, OOM reading 24+ nested worktrees under ``.claude/worktrees/``).
    Treating each ignored entry as a path prefix closes that gap.
    """
    return path in ignored or any(parent in ignored for parent in path.parents)


class SnapshotIncompleteError(RuntimeError):
    """Raised when a file under an owned prefix could not be snapshotted.

    Only :func:`_snapshot_owned_prefixes` in ``strict`` mode raises this. See
    that function for why an unreadable file is fatal to ``--check`` and
    harmless to the ``.claude/`` guard.
    """


def _missing_owned_root(path: Path) -> bool:
    """Return whether the parent directory also reports no entry for ``path``."""
    try:
        with os.scandir(path.parent) as entries:
            return all(entry.name != path.name for entry in entries)
    except FileNotFoundError:
        return True
    except OSError as exc:
        raise SnapshotIncompleteError(
            f"cannot verify missing owned path {path}: {exc}"
        ) from exc


# stat.IO_REPARSE_TAG_MOUNT_POINT exists only on Windows builds, so reading it
# through getattr with a sentinel default made the junction arm inert wherever
# the attribute is missing: a check that cannot fire is not a check. The value
# is a fixed Windows constant, and CPython's own os.path.isjunction compares
# against exactly it, so pinning the literal makes the predicate answer the
# same question on every platform. Non-Windows stat results carry no
# st_reparse_tag at all, so the arm is unreachable there by data, not by a
# missing name.
_MOUNT_POINT_REPARSE_TAG = 0xA0000003


def _is_redirecting(metadata: os.stat_result) -> bool:
    """Return whether a no-follow stat names a link or a Windows junction.

    ``S_ISLNK`` alone is not enough. A Windows directory junction is reported
    as a directory carrying a reparse tag, so it passes every symlink test and
    is then traversed, which is the same escape a symlink gives. The
    repository already draws the line at both shapes: see `_is_redirecting_link`
    in ``scripts/validation/portability_baseline.py``, which asks
    ``path.is_symlink() or path.is_junction()``.

    This reads the tag off an lstat result the caller already has, rather than
    calling ``Path.is_junction()``. That helper delegates to
    ``os.path.isjunction``, which swallows ``OSError`` and answers False, and a
    strict probe that answers False on a metadata failure is the fail-open this
    whole path exists to remove.
    """
    if stat.S_ISLNK(metadata.st_mode):
        return True
    return getattr(metadata, "st_reparse_tag", 0) == _MOUNT_POINT_REPARSE_TAG


def _reject_redirecting_ancestors(repo_root: Path, path: Path) -> None:
    """Fail the strict snapshot when a component above ``path`` redirects.

    ``stat(follow_symlinks=False)`` only declines to follow the FINAL
    component. Every directory above it is resolved by the kernel on the way
    there, so a redirecting parent is followed before any per-path check runs.
    Concretely: ``docs/agent-catalog.md`` is a single-file owned prefix, and a
    ``docs`` symlink or junction pointing outside the repository sends the
    generated catalog to the link target, where restore cannot reach it.

    A missing ancestor ends the walk without complaint. Nothing exists below
    it to protect, and generators may create the tree.
    """
    try:
        relative = path.relative_to(repo_root)
    except ValueError:
        return
    current = repo_root
    for part in relative.parts[:-1]:
        current = current / part
        try:
            metadata = current.stat(follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise SnapshotIncompleteError(
                f"cannot inspect owned path ancestor {current}: {exc}"
            ) from exc
        if _is_redirecting(metadata):
            raise SnapshotIncompleteError(
                f"owned path ancestor redirects, so --check cannot restore a "
                f"write through it: {current}"
            )


def _strict_owned_stat(
    path: Path, *, missing_root_ok: bool
) -> os.stat_result | None:
    """Return metadata for ``path``, rejecting symlinks, without following them.

    A symlink under an owned prefix raises here instead of being skipped by
    the caller. Skipping was fail-open in the one direction ``--check``
    promises to be safe. The snapshot omits the link, but generation writes
    THROUGH it: :func:`generate_skills._copy_skill_tree` builds each
    destination as ``dst_path = target / rel`` and then calls
    ``dst_path.parent.mkdir(parents=True, exist_ok=True)``, so a
    ``src/copilot-cli/skills/<name>`` symlink pointing outside the repository
    takes the generated bytes to the link target.

    :func:`_restore_owned_prefixes` cannot undo that write.
    :func:`_enumerate_files_under` skips symlinks too, and ``Path.rglob`` does
    not descend into a symlinked directory, so the written file lands in
    neither the snapshot nor the post-run enumeration. A ``--check`` run
    documented as read-only would leave files changed outside the repository,
    which is issue #4632's contract failing in a second place.

    Raising is cheap: the repository has no symlink under
    :data:`OWNED_PREFIXES` today, so the cost is one error message to whoever
    introduces the first one. Snapshotting and restoring link metadata is the
    alternative, and it would still not undo a write that landed outside the
    repository.

    Only strict callers reach this. The ``.claude/`` guard keeps skipping
    symlinks: it compares snapshots and never deletes, so a link there costs
    a missed report, not data.
    """
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        if missing_root_ok and _missing_owned_root(path):
            return None
        raise SnapshotIncompleteError(
            f"owned path disappeared during snapshot {path}: {exc}"
        ) from exc
    except OSError as exc:
        raise SnapshotIncompleteError(
            f"cannot inspect owned path {path}: {exc}"
        ) from exc
    if _is_redirecting(metadata):
        raise SnapshotIncompleteError(
            f"owned path redirects (symlink or junction), and --check cannot "
            f"restore a write through it: {path}"
        )
    if not stat.S_ISDIR(metadata.st_mode) and not stat.S_ISREG(metadata.st_mode):
        raise SnapshotIncompleteError(
            f"owned path is neither a regular file nor a directory, and "
            f"--check can neither snapshot nor restore it: {path}"
        )
    return metadata


def _strict_owned_children(path: Path) -> list[Path]:
    """Return direct children of ``path`` or fail the strict snapshot."""
    try:
        with os.scandir(path) as entries:
            return [Path(entry.path) for entry in entries]
    except OSError as exc:
        raise SnapshotIncompleteError(
            f"cannot enumerate owned directory {path}: {exc}"
        ) from exc


def _strict_is_git_boundary(directory: Path) -> bool:
    """Return whether ``directory`` holds its own ``.git`` entry, failing closed.

    :func:`_is_opaque_boundary`'s shape branch asks ``(entry / ".git").exists()``,
    and that is fail-open in strict mode for the reason this file spends a
    docstring on elsewhere: ``Path.exists()`` answers "absent" and "could not
    be stat'ed" with the same ``False``. A permission error or a stale handle
    on ``<directory>/.git`` would read as "not a boundary", the strict walk
    would descend into the checkout, and the nested-worktree read that issue
    #5370 closed would be back, this time reached through the very metadata
    failure this branch was added to reject.

    So the marker gets the same treatment every other strict probe gets. Only
    :class:`FileNotFoundError` means absent. A symlinked marker is rejected
    rather than followed, matching :func:`_strict_owned_stat`. Every other
    :class:`OSError` aborts the snapshot.

    Both marker shapes count: ``git worktree add`` writes ``.git`` as a file
    holding a ``gitdir:`` pointer, a normal clone writes it as a directory.
    """
    marker = directory / ".git"
    try:
        metadata = marker.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SnapshotIncompleteError(
            f"cannot inspect git boundary marker {marker}: {exc}"
        ) from exc
    if _is_redirecting(metadata):
        raise SnapshotIncompleteError(
            f"git boundary marker redirects, so it cannot be trusted to say "
            f"whether {directory} is a nested repository: {marker}"
        )
    return True


def _reject_nested_repository(directory: Path) -> None:
    """Refuse a directory that holds its own ``.git`` entry.

    Called on every directory the strict walk is about to enter, the prefix
    root included. Checking only children left the root itself unguarded: a
    prefix such as ``src/`` holding its own ``.git`` was queued directly and
    traversed, and generators then wrote into that repository.
    """
    if _strict_is_git_boundary(directory):
        raise SnapshotIncompleteError(
            f"owned prefix contains a nested git repository, and --check "
            f"cannot keep its promise over one: {directory}"
        )


def _queue_strict_owned_path(pending: list[Path], path: Path) -> Path | None:
    """Queue child directories and return child files for strict snapshots."""
    metadata = _strict_owned_stat(path, missing_root_ok=False)
    assert metadata is not None, (
        "missing_root_ok=False guarantees a non-None result or a raise"
    )
    if stat.S_ISDIR(metadata.st_mode):
        _reject_nested_repository(path)
        pending.append(path)
        return None
    return path


def _iter_strict_owned_files(root: Path) -> Iterable[Path]:
    """Yield owned files while surfacing strict metadata and scan failures.

    Rejects a nested git repository under an owned prefix rather than
    skipping it. Skipping protected restore and nothing else: the checkout
    stays out of the snapshot, generation still writes into it (a checkout at
    ``src/copilot-cli/skills/alpha`` gets its ``SKILL.md`` overwritten by
    :func:`generate_skills.generate_skills` like any other target), and
    restore then skips the same directory, so ``--check`` returns having
    modified a tree it promised not to touch. The snapshot cannot hold the
    checkout (issue #5370: 24 nested worktrees under ``.claude/worktrees/``
    read into memory until the process died) and restore cannot repair it, so
    the only honest answer is to refuse the run.

    That refusal is cheap here. :data:`OWNED_PREFIXES` is generated output,
    and the repository has no nested checkout under any of it. The
    ``.claude/`` guard keeps skipping boundaries, which is where #5370
    actually bit: it compares snapshots, never deletes, and never generates
    into them.

    Shape detection is correct at this call site because this runs before any
    generator, so nothing can have manufactured a ``.git`` entry yet. The
    probe is :func:`_strict_is_git_boundary`, not :func:`_is_opaque_boundary`,
    because the latter's shape branch uses ``Path.exists()`` and would swallow
    a metadata failure on the marker.

    Neither this function nor :func:`_queue_strict_owned_path` re-tests
    ``Path.is_symlink()``, and neither tests for a special file.
    :func:`_strict_owned_stat` stats with ``follow_symlinks=False`` and raises
    on a redirect or on anything that is not a regular file or a directory
    before returning, so every ``st_mode`` reaching a caller is already one of
    those two.
    """
    root_metadata = _strict_owned_stat(root, missing_root_ok=True)
    if root_metadata is None:
        return
    if stat.S_ISREG(root_metadata.st_mode):
        yield root
        return

    _reject_nested_repository(root)
    pending = [root]
    while pending:
        current = pending.pop()
        for child in _strict_owned_children(current):
            child_file = _queue_strict_owned_path(pending, child)
            if child_file is not None:
                yield child_file


def _snapshot_owned_prefixes(
    repo_root: Path,
    prefixes: tuple[str, ...],
    *,
    exclude_ignored: bool = False,
    opaque_boundaries: set[Path] | None = None,
    strict: bool = False,
) -> dict[Path, bytes]:
    """Snapshot every file under ``prefixes`` into an in-memory dict.

    Returns a mapping of absolute Path → raw bytes for every regular file
    found under each prefix that exists. Directories that do not exist
    are silently skipped (they may be created by generators).

    Used by --check to make the build orchestrator read-only (#2440).
    The snapshot is held in process memory because the real owned-prefix
    tree is ~21MB and a temp-dir copytree adds I/O and cleanup hazards
    without buying meaningful safety. The two modes answer the symlink
    question differently: the comparison-only caller skips links, and
    ``strict`` rejects them (see :func:`_strict_owned_stat`).

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

    ``opaque_boundaries`` forwards to :func:`_iter_tree_skip_git_boundaries`;
    see :func:`_is_opaque_boundary` for why a caller comparing two
    snapshots must pass one recorded set to both rather than letting each
    walk detect boundaries by shape.

    The walk always skips nested git repository boundaries (see
    :func:`_iter_tree_skip_git_boundaries`), regardless of
    ``exclude_ignored``. ``--check`` calls this with ``exclude_ignored=False``,
    so relying on ``_is_ignored_path`` alone would leave this snapshot pass
    asymmetric with :func:`_enumerate_files_under`'s boundary skip: a nested
    worktree would still be read here and then clobbered by
    :func:`_restore_owned_prefixes` (issue #5370).

    ``strict`` decides what an unreadable file means, and the two consumers
    need opposite answers (issue #4632).

    The ``.claude/`` guard takes ``strict=False``, and the cost of that is a
    missed violation, not nothing. :func:`assert_no_claude_writes` builds
    ``offending`` from ``current.items()`` and from
    ``baseline.keys() - current.keys()``, so a ``.claude/`` path unreadable at
    both snapshot times lands in neither set: on that one path the guard
    cannot see a generator write, which is REQ-003-010 failing open. The trade
    is deliberate. The guard can only report (it never deletes), and the
    alternative is failing a pre-push gate on a transient permission error in
    the same concurrent-write window issue #3773 describes. Do not read
    ``strict=False`` here as the file's general convention: the neighbouring
    :func:`_confirm_ignored` is fail-closed for this same guard, because there
    the failure direction is reversed and a git that will not run leaves every
    candidate reported rather than dropped.

    ``--check`` takes ``strict=True``, because it *restores* from its
    snapshot: :func:`_restore_owned_prefixes` deletes anything on disk the
    snapshot does not name, so the same skip turns a file the run could not
    read into a file the run deletes. Issue #4632 reproduction 2
    made one generated instruction file unreadable and observed
    ``rc=1 state=deleted``: a ``--check`` run, documented as read-only,
    destroyed a pre-existing file. ``strict=True`` raises
    :class:`SnapshotIncompleteError` there so the caller aborts before any
    generator runs and no partial snapshot ever reaches restore.

    Strict discovery does not use ``Path.is_file()``, ``Path.is_dir()``,
    ``Path.exists()``, or ``Path.rglob()``. In Python 3.14 those helpers can
    suppress stat and traversal errors, which turns a transient metadata or
    scan failure into an omitted path. If the error clears before restore,
    ``--check`` can then delete that pre-existing file as generator-created.
    A missing prefix root is skipped because generators may create it. Once a
    path has been discovered, every metadata, traversal, or read error raises
    before generation starts, including :class:`FileNotFoundError`, so a
    transient disappear-and-recreate race cannot leave restore with a partial
    snapshot. A symlink raises for the same reason one class further out: the
    snapshot cannot hold it, generation writes through it, and restore cannot
    reach what the write touched (:func:`_strict_owned_stat`).
    """
    ignored = _ignored_paths(repo_root, prefixes) if exclude_ignored else set()
    snapshot: dict[Path, bytes] = {}
    for prefix in prefixes:
        root = repo_root / prefix
        # Every branch below this one runs only when ``strict`` is false: the
        # strict branch handles single-file and directory prefixes alike and
        # ``continue``s. So they pass ``strict=False`` literally rather than
        # forwarding the parameter. Forwarding read as live wiring while being
        # dead, which is an argument no mutation can distinguish (measured:
        # rewriting the forward to ``strict=False`` left all 137 tests green).
        if strict:
            _reject_redirecting_ancestors(repo_root, root)
            for path in _iter_strict_owned_files(root):
                if _is_ignored_path(path, ignored) or (
                    exclude_ignored and _is_bytecode_artifact(path)
                ):
                    continue
                _read_into_snapshot(snapshot, path, strict=True)
            continue
        if root.is_file() and not root.is_symlink():
            if root in ignored:
                continue
            _read_into_snapshot(snapshot, root, strict=False)
            continue
        if root.exists() and not root.is_dir():
            continue
        if not root.is_dir():
            continue
        for path, is_dir in _iter_tree_skip_git_boundaries(
            root, opaque_boundaries=opaque_boundaries
        ):
            if is_dir or not path.is_file():
                continue
            if _is_ignored_path(path, ignored) or (
                exclude_ignored and _is_bytecode_artifact(path)
            ):
                continue
            _read_into_snapshot(snapshot, path, strict=False)
    return snapshot


def _read_into_snapshot(
    snapshot: dict[Path, bytes], path: Path, *, strict: bool
) -> None:
    """Read ``path`` into ``snapshot``, or decide what its failure means.

    Extracted so the single-file prefix branch and the directory walk in
    :func:`_snapshot_owned_prefixes` cannot drift apart. ``docs/agent-catalog.md``
    and ``.agents/architecture/README.md`` are single-file owned prefixes, so
    the branch that handles them is exactly as exposed to the delete-on-
    unreadable bug as the walk is.

    Under ``strict`` every :class:`OSError` raises, :class:`FileNotFoundError`
    included, because restore CAN delete a file that is still on disk. An
    earlier version of this sentence carved out `FileNotFoundError` as
    "vanished" and skipped it. That contradicted the code below and the
    post-discovery contract: a path that disappears and returns before restore
    would be absent from the snapshot and deleted as generator-created. Only
    the non-strict caller skips, and it skips every :class:`OSError` alike.

    The narrower ``strict and path.exists()`` guard this replaces was
    fail-open. ``Path.exists()`` reports a boolean over two different
    questions, "is it absent" and "could I stat it", and it answers both with
    ``False``. On CPython 3.14.7 it delegates to ``os.path.exists``, whose
    body is::

        def exists(path):
            try:
                os.stat(path)
            except (OSError, ValueError):
                return False
            return True

    So a permission error, a stale handle, or a transient I/O failure on the
    ``stat`` made ``exists()`` ``False`` for a file that was still there, the
    strict branch was skipped, the path stayed out of the snapshot, and
    :func:`_restore_owned_prefixes` deleted it as generator-created: the exact
    data loss issue #4632 reproduction 2 reported. Measured with a symlink
    loop, which needs no mock and no permission bits: ``exists()`` is
    ``False`` while ``read_bytes()`` raises ``OSError(ELOOP)``, not
    ``FileNotFoundError``.

    Under ``strict`` every :class:`OSError` raises because the path was already
    discovered and statted. A path that disappears and returns before restore
    would otherwise be absent from the snapshot and deleted as generator-created.
    """
    try:
        snapshot[path] = path.read_bytes()
    except OSError as exc:
        if strict:
            raise SnapshotIncompleteError(
                f"cannot read owned file {path}: {exc}"
            ) from exc


def _restore_owned_prefixes(
    repo_root: Path,
    prefixes: tuple[str, ...],
    snapshot: dict[Path, bytes],
    *,
    preexisting_boundaries: set[Path] | None = None,
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

    ``preexisting_boundaries`` is the set of git repository boundaries recorded
    before the generators ran. ``--check`` passes an EMPTY set, not ``None``,
    because strict discovery aborts on any nested repository under an owned
    prefix, so by the time this runs there provably are none. ``None`` would
    switch :func:`_is_opaque_boundary` back to shape detection and let a
    generator hide its own output behind a ``.git`` entry it wrote during the
    build. The ``.claude/`` guard passes a real set from
    :func:`_git_boundaries_under`, because that walk tolerates boundaries
    rather than refusing them. Detecting boundaries by shape here instead would read the
    post-generation tree, so a tree the generator created with a ``.git``
    entry inside it would look like a nested checkout and case 3 would
    skip its files. Measured before this argument existed: a generator
    creating ``owned/out/.git`` plus ``owned/out/generated.txt`` left both
    on disk after a ``--check`` restore, breaking the read-only contract
    of issue #2440. ``None`` keeps the shape test, which is correct for a
    caller with no recorded baseline.
    """
    current = _enumerate_files_under(
        repo_root, prefixes, opaque_boundaries=preexisting_boundaries
    )

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

    _prune_empty_dirs(
        repo_root, prefixes, opaque_boundaries=preexisting_boundaries
    )


def _is_opaque_boundary(entry: Path, opaque: set[Path] | None) -> bool:
    """Return True if ``entry`` is a boundary the walk must not enter.

    ``opaque`` of ``None`` means "detect boundaries by shape": any
    directory holding its own ``.git`` file or directory. That is the
    right question before a build, when nothing has been recorded yet.

    A caller that passes a set is asking a different question: which
    boundaries existed at a recorded moment. Shape is the wrong test
    there, because a generator can create a ``.git`` entry during the
    build, and treating that new tree as opaque would leave the
    generator's own output on disk (see :func:`_restore_owned_prefixes`).
    """
    if opaque is None:
        return (entry / ".git").exists()
    return entry in opaque


def _iter_tree_skip_git_boundaries(
    root: Path,
    *,
    opaque_boundaries: set[Path] | None = None,
    boundaries_seen: set[Path] | None = None,
) -> Iterator[tuple[Path, bool]]:
    """Yield ``(path, is_dir)`` for every entry under ``root``.

    Never descends into a directory that is itself a git repository
    boundary (holds its own ``.git`` file or directory), the same shape
    ``git worktree`` uses for a nested checkout under, for example,
    ``.claude/worktrees/<name>/``. A boundary directory is not yielded
    either, so callers never enumerate, prune, or (via
    :func:`_restore_owned_prefixes`) delete anything inside one.

    This is what keeps a future addition of ``.claude/`` to
    :data:`OWNED_PREFIXES` from making :func:`_restore_owned_prefixes` walk
    into, and delete, a nested worktree's own working tree (issue #5370).

    ``opaque_boundaries`` narrows that skip to a recorded set of paths;
    see :func:`_is_opaque_boundary` for why the post-build walk cannot use
    shape detection. ``boundaries_seen`` collects every boundary the walk
    refused to enter, which is how :func:`_git_boundaries_under` records
    the pre-build set without a second traversal shape.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            is_dir = entry.is_dir()
            if is_dir and _is_opaque_boundary(entry, opaque_boundaries):
                # git repository boundary; opaque, do not descend
                if boundaries_seen is not None:
                    boundaries_seen.add(entry)
                continue
            yield entry, is_dir
            if is_dir:
                stack.append(entry)


def _git_boundaries_under(
    repo_root: Path, prefixes: tuple[str, ...]
) -> set[Path]:
    """Return the git repository boundaries under ``prefixes`` right now.

    ``--check`` records this before any generator runs so
    :func:`_restore_owned_prefixes` can tell a pre-existing nested
    checkout, which it must leave alone, from a boundary-shaped tree a
    generator created during the build, which is output and must be
    removed like any other generator write (issue #2440).

    The walk stops at each boundary, so this costs a directory traversal
    and reads no file contents, which is the property issue #5370 needed.
    """
    boundaries: set[Path] = set()
    for prefix in prefixes:
        root = repo_root / prefix
        if not root.is_dir():
            continue
        for _ in _iter_tree_skip_git_boundaries(root, boundaries_seen=boundaries):
            pass
    return boundaries


def _enumerate_files_under(
    repo_root: Path,
    prefixes: tuple[str, ...],
    *,
    opaque_boundaries: set[Path] | None = None,
) -> set[Path]:
    """Return every regular non-symlink file under any of ``prefixes``.

    Skips nested git repository boundaries; see
    :func:`_iter_tree_skip_git_boundaries` and, for what
    ``opaque_boundaries`` changes, :func:`_is_opaque_boundary`.

    ``path.is_file()`` is load-bearing, not a redundant re-check of
    ``not is_dir``. A FIFO, a unix socket, or a device node is neither a
    directory nor a regular file. :func:`_snapshot_owned_prefixes` drops
    those with the same predicate (``if is_dir or not path.is_file():
    continue``), so counting every non-directory entry here would put a
    pre-existing special file in ``current - snapshot`` and case 3 of
    :func:`_restore_owned_prefixes` would unlink it. That turns a
    read-only ``--check`` into a delete. Symlinks are already dropped
    upstream by :func:`_iter_tree_skip_git_boundaries`.
    """
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
        for path, is_dir in _iter_tree_skip_git_boundaries(
            root, opaque_boundaries=opaque_boundaries
        ):
            if not is_dir and path.is_file():
                found.add(path)
    return found


def _prune_empty_dirs(
    repo_root: Path,
    prefixes: tuple[str, ...],
    *,
    opaque_boundaries: set[Path] | None = None,
) -> None:
    """Remove empty directories the generator created under ``prefixes``.

    Walks bottom-up so child dirs go before parents. Never touches the
    prefix root itself, and never descends into or removes a nested git
    repository boundary; see :func:`_iter_tree_skip_git_boundaries`.

    ``opaque_boundaries`` protects the same set
    :func:`_enumerate_files_under` protects. Without it here, a
    boundary-shaped tree a generator created would keep its now-empty
    directories after case 3 deleted their files, which is still a
    ``--check`` write.
    """
    for prefix in prefixes:
        root = repo_root / prefix
        if root.is_file():
            continue
        if not root.is_dir():
            continue
        dirs = [
            p
            for p, is_dir in _iter_tree_skip_git_boundaries(
                root, opaque_boundaries=opaque_boundaries
            )
            if is_dir
        ]
        for dirpath in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
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
    #
    # A file that cannot be read is fatal HERE, before any generator runs and
    # before the try/finally below arms the restore. Continuing with a partial
    # snapshot would let _restore_owned_prefixes classify the unreadable file
    # as generator-created and delete it (issue #4632).
    snapshot: dict[Path, bytes] | None = None
    boundaries: set[Path] | None = None
    if check:
        # Restore's boundary set comes from this same traversal, not from a
        # separate _git_boundaries_under pass. Two passes could disagree: that
        # helper's walker swallows every directory-scan OSError, so one
        # transient failure returns an incomplete set while a separate strict
        # pass, run again later, hits no transient failure and correctly
        # rejects the nested repository outright (SnapshotIncompleteError),
        # never merely skipping it by shape the way the non-strict
        # _is_opaque_boundary fallback would. Restore would then receive
        # the short set, descend into a repository the snapshot never read,
        # and delete its files as generator-created: issue #4632's data loss
        # reopened one level out. Collecting here makes the two agree by
        # construction, and a scan failure aborts the run instead.
        # Empty on purpose, not None. Strict discovery aborts on any nested
        # repository under an owned prefix, so by the time restore runs there
        # provably are none, and membership against an empty set is the right
        # answer. None would switch _is_opaque_boundary back to shape
        # detection, which would let a generator hide its own output behind a
        # .git entry it wrote during the build (#5464).
        boundaries = set()
        try:
            snapshot = _snapshot_owned_prefixes(
                repo_root, OWNED_PREFIXES, strict=True
            )
        except SnapshotIncompleteError as exc:
            print(
                f"Error: --check aborted before generation: {exc}",
                file=sys.stderr,
            )
            return 2

    # REQ-003-010 (issue #2613): snapshot the .claude/ tree before any
    # generator runs so the no-write guard attributes only writes the
    # generators made, not pre-build drift such as a .claude/lib sync.
    # Record the boundaries the baseline walk is about to skip, so the
    # post-generation re-read in assert_no_claude_writes skips that same
    # set instead of re-deriving it from the post-generation tree. Without
    # it, a generator can hide a .claude/ write behind a .git entry it
    # wrote itself: the second walk skips a tree the first one never saw,
    # so the diff is empty.
    #
    # The baseline below is deliberately NOT given the set. It runs on the
    # same filesystem state _git_boundaries_under just read, so shape
    # detection and set membership return the same answer here by
    # construction. Passing it would be an argument no mutation can
    # distinguish, which is an argument with no test holding it.
    claude_boundaries = _git_boundaries_under(repo_root, CLAUDE_GUARD_PREFIX)
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
            claude_boundaries=claude_boundaries,
        )
    finally:
        # #2440: ALWAYS restore on --check, including on exception paths.
        # Otherwise a generator crash mid-build leaves partial writes
        # in the caller's worktree.
        if snapshot is not None:
            _restore_owned_prefixes(
                repo_root,
                OWNED_PREFIXES,
                snapshot,
                preexisting_boundaries=boundaries,
            )


def _run_generators(
    repo_root: Path,
    configs: list[Path],
    *,
    check: bool,
    audit_format: str,
    claude_baseline: dict[Path, bytes],
    claude_boundaries: set[Path] | None = None,
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
    claude_writes = assert_no_claude_writes(
        repo_root, claude_baseline, preexisting_boundaries=claude_boundaries
    )
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
        try:
            changed = _git_diff_paths(repo_root)
        except GitStateUnreadableError as exc:
            # An empty diff and an unreadable git both yield zero paths. Only
            # the first one means the tree is clean (issue #4632).
            #
            # Exit 3, not 2. Git is an external tool, and AGENTS.md's exit-code
            # contract reads "0=ok|1=logic|2=config|3=external". Exit 2 here
            # told a caller the same thing staleness tells it, so "you are
            # missing git" and "your generated tree is stale" arrived as one
            # code and the caller could recommend a regeneration that cannot
            # fix the problem. See the module docstring for why a non-repository
            # root is not split back out to 2.
            print(
                f"STALENESS UNKNOWN: cannot read git state: {exc}",
                file=sys.stderr,
            )
            audit.overall_exit = max(audit.overall_exit, 3)
            changed = []
        diff = [
            p for p in changed
            if any(p.startswith(prefix) for prefix in OWNED_PREFIXES)
        ]
        if diff:
            print("STALENESS DETECTED: uncommitted regen drift:", file=sys.stderr)
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
