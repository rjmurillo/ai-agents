#!/usr/bin/env python3
"""Orchestrate the retrospective workflow and persist an artifact.

This is the thin Phase 0..5 orchestrator the SKILL.md contract describes. It
gathers evidence (Phase 0 via ``extract_evidence``), scores any supplied
learnings (Phase 4 via ``score_atomicity``), and writes a retrospective artifact
using the section order from
``.claude/skills/retrospective/references/learning-template.md``.

The interpretive phases (Five Whys, fishbone, diagnosis prose) are authored by
the agent or reviewer reading the rendered template; this script supplies the
deterministic scaffold and fills the data-bearing parts (session info, work
items, learning scores) so the human-or-agent does not start from a blank file.

Two write modes:
  * New artifact: writes ``.agents/retrospective/YYYY-MM-DD-[scope].md``.
  * Fill skeleton: when ``--fill`` targets an existing
    ``YYYY-MM-DD-auto-retro.md`` skeleton, the artifact overwrites that skeleton
    and removes the UNFILLED banner by replacement.

System of record: the session log is the SoR; this artifact is a derived record
of the retrospective. The script only reads evidence and writes one artifact.

Exit codes (ADR-035):
  0: artifact written
  1: a supplied learning scored below the persistence threshold (still written)
  2: usage or configuration error
  3: unexpected external failure
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Protocol

UTC = timezone.utc  # noqa: UP017 - Python 3.10 compatibility

_SCRIPT_DIR = Path(__file__).resolve().parent


def _resolve_paths_lib_dir() -> Path:
    """Resolve the plugin path-helper lib directory or fail with context."""
    plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        lib_dir = Path(plugin_root) / "lib"
    elif workspace := os.environ.get("GITHUB_WORKSPACE"):
        lib_dir = Path(workspace) / ".claude" / "lib"
    else:
        lib_dir = Path(__file__).resolve().parents[3] / "lib"

    if not lib_dir.is_dir():
        raise RuntimeError(
            "Expected portability helper lib directory not found: "
            f"{lib_dir}. Set COPILOT_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT to the "
            "plugin root, or run from an ai-agents checkout."
        )
    return lib_dir.resolve()


_LIB_DIR = _resolve_paths_lib_dir()
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

try:
    import paths  # noqa: E402
except ImportError as exc:  # pragma: no cover - guarded by explicit path check
    raise RuntimeError(f"Failed to import portability helper paths.py from {_LIB_DIR}") from exc


def _artifact_root_is_set() -> bool:
    """Return whether the artifact-root override has a non-blank value."""
    return bool(os.environ.get("AI_AGENTS_ARTIFACT_ROOT", "").strip())


def _artifact_dir(project_dir: Path, subdir: str) -> Path:
    """Resolve an artifact directory while preserving explicit project-dir tests."""
    if _artifact_root_is_set() or project_dir.resolve() == Path.cwd().resolve():
        return paths.resolve_artifact_root(subdir)
    return project_dir / ".agents" / subdir


class EvidenceLike(Protocol):
    """Fields from extract_evidence.Evidence used by this renderer."""

    work_items: list[str]
    outcomes: list[str]
    commits: list[str]
    notes: list[str]
    session_log_available: bool


def _load_sibling(module_name: str) -> ModuleType:
    """Import a sibling script module by path.

    Skill scripts are not packaged, so we load by file location rather than a
    package import. This keeps the three scripts independently runnable while
    letting the orchestrator reuse the evidence and scoring logic.
    """
    registered_name = f"{__name__}._retrospective_{module_name}"
    spec = importlib.util.spec_from_file_location(
        registered_name, _SCRIPT_DIR / f"{module_name}.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sibling module {module_name}")
    module = importlib.util.module_from_spec(spec)
    # Register under a namespaced key before exec so dataclass(slots=True) can
    # resolve the module namespace during class creation; an unregistered
    # module fails with AttributeError on Python 3.12+. The prefix avoids
    # shadowing a caller's own top-level import of the same script.
    sys.modules[registered_name] = module
    spec.loader.exec_module(module)
    return module


_evidence_mod = _load_sibling("extract_evidence")
_score_mod = _load_sibling("score_atomicity")

gather_evidence = _evidence_mod.gather_evidence
score_learning = _score_mod.score_learning
PERSISTENCE_THRESHOLD = _score_mod.PERSISTENCE_THRESHOLD


def _render_session_context(evidence: EvidenceLike) -> str:
    """Render the Phase 0 session-context block from gathered evidence."""
    lines: list[str] = []
    if evidence.work_items:
        lines.append("### Work Items")
        lines.extend(f"- {item}" for item in evidence.work_items)
    else:
        lines.append("_No session work items available._")
    if evidence.outcomes:
        lines.append("")
        lines.append("### Outcomes")
        lines.extend(f"- {outcome}" for outcome in evidence.outcomes)
    if evidence.commits:
        lines.append("")
        lines.append("### Commits")
        lines.extend(f"- {commit}" for commit in evidence.commits)
    if evidence.notes:
        lines.append("")
        lines.append("### Evidence Notes (degraded sources)")
        lines.extend(f"- {note}" for note in evidence.notes)
    return "\n".join(lines)


def _scope_date(scope: str) -> str | None:
    """Return the ISO date prefix from a retrospective scope when present."""
    candidate = scope.strip()[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def _artifact_date(scope: str) -> str:
    """Return the artifact date, preferring a dated retrospective scope."""
    return _scope_date(scope) or datetime.now(tz=UTC).strftime("%Y-%m-%d")


def _render_learnings(learnings: list[str]) -> tuple[str, bool]:
    """Render the Phase 4 learnings block, scoring each learning.

    Returns the rendered block and whether any learning fell below the
    persistence threshold.
    """
    if not learnings:
        return (
            "### Learning 1\n"
            "- **Statement**: [Atomic - max 15 words]\n"
            "- **Atomicity Score**: [%]\n"
            "- **Evidence**: [Execution detail]\n"
            "- **Skill Operation**: ADD | UPDATE | TAG | REMOVE\n"
            "- **Target Skill ID**: [If UPDATE/TAG/REMOVE]",
            False,
        )

    blocks: list[str] = []
    any_below = False
    for index, learning in enumerate(learnings, start=1):
        result = score_learning(learning)
        if result.score < PERSISTENCE_THRESHOLD:
            any_below = True
        blocks.append(
            f"### Learning {index}\n"
            f"- **Statement**: {learning.strip()}\n"
            f"- **Atomicity Score**: {result.score}% ({result.quality})\n"
            f"- **Evidence**: [Execution detail]\n"
            f"- **Skill Operation**: ADD | UPDATE | TAG | REMOVE\n"
            f"- **Target Skill ID**: [If UPDATE/TAG/REMOVE]"
        )
    return "\n\n".join(blocks), any_below


def render_artifact(
    scope: str, today: str, evidence: EvidenceLike, learnings: list[str]
) -> tuple[str, bool]:
    """Render a retrospective artifact with the template's section order.

    Interpretive sections (Phase 1 insights, Phase 2/3 prose) are left as
    placeholders for the agent or reviewer; the data-bearing sections are
    populated.

    Returns the rendered markdown and whether any learning scored below the
    persistence threshold.
    """
    session_context = _render_session_context(evidence)
    learnings_block, any_below = _render_learnings(learnings)
    outcome = "Success" if evidence.session_log_available else "Partial"

    artifact = f"""# Retrospective: {scope}

## Session Info
- **Date**: {today}
- **Agents**: [List]
- **Task Type**: [Feature | Bug | Research]
- **Outcome**: {outcome}

## Phase 0: Data Gathering
{session_context}

## Phase 1: Insights Generated
[Five Whys output if failure]
[Fishbone output if complex]
[Patterns and Shifts output]
[Learning Matrix output]

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| [Strategy] | [Outcome] | [1-10] | [%] |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| [Strategy] | [Type] | [Cause] | [Fix] | [%] |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| [Situation] | [Save] | [Takeaway] |

## Phase 3: Decisions

### Action Classification
[Keep/Drop/Add/Modify table]

### SMART Validation
[Validation for each new skill]

### Action Sequence
[Ordered actions with dependencies]

## Phase 4: Extracted Learnings

{learnings_block}

## Skillbook Updates

### ADD
```json
{{
  "skill_id": "{{domain}}-{{description}}",
  "statement": "[Atomic]",
  "context": "[When to apply]",
  "evidence": "[Source]",
  "atomicity": [%]
}}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
"""
    return artifact, any_below


def _resolve_output_path(
    retro_dir: Path,
    scope: str,
    today: str,
    fill: str | None,
    project_dir: Path | None = None,
) -> Path:
    """Resolve where the artifact is written.

    When ``fill`` names an existing skeleton, return that skeleton path so the
    caller overwrites it with filled content per the SKILL.md contract.
    Otherwise write ``YYYY-MM-DD-[scope].md``.
    """
    if fill:
        skeleton = Path(fill)
        if not skeleton.is_absolute():
            base_dir = retro_dir if _artifact_root_is_set() else (project_dir or retro_dir)
            if _artifact_root_is_set():
                parts = skeleton.parts
                if len(parts) >= 2 and parts[0] == ".agents" and parts[1] == "retrospective":
                    skeleton = Path(*parts[2:]) if len(parts) > 2 else Path()
            skeleton = base_dir / skeleton
        skeleton = _require_fill_path(skeleton, project_dir, retro_dir)
        if not skeleton.is_file():
            raise ValueError(f"fill skeleton not found: {fill}")
        return skeleton
    safe_scope = scope.strip().replace(" ", "-").replace("/", "-")
    return retro_dir / f"{today}-{safe_scope}.md"


def _require_project_output_path(path: Path, project_dir: Path) -> Path:
    """Return a resolved output path only when it stays inside project_dir."""
    resolved_project = project_dir.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_project):
        raise ValueError(f"output path escapes project dir: {path}")
    return resolved_path


def _require_fill_path(path: Path, project_dir: Path | None, retro_dir: Path) -> Path:
    """Return a fill path after validating its allowed root."""
    resolved_root = retro_dir.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"fill path escapes allowed root: {path}")
    return resolved_path


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Run the retrospective workflow and write an artifact.",
    )
    parser.add_argument(
        "--scope",
        default=datetime.now(tz=UTC).strftime("%Y-%m-%d"),
        help="Retrospective scope label (default: today's date).",
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Repository root (default: current directory).",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="git log --since value bounding the period (e.g. '1 day ago').",
    )
    parser.add_argument(
        "--learning",
        action="append",
        default=[],
        dest="learnings",
        help="A learning statement to score and include. Repeatable.",
    )
    parser.add_argument(
        "--fill",
        default=None,
        help="Path to an existing auto-retro skeleton to overwrite with filled content.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Explicit output path override.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Writes the artifact and returns an ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"ERROR: project dir not found: {args.project_dir}", file=sys.stderr)
        return 2

    today = _artifact_date(args.scope)
    retro_dir = _artifact_dir(project_dir, "retrospective")

    try:
        evidence = gather_evidence(project_dir, args.scope, args.since)
    except Exception as exc:  # noqa: BLE001 - boundary: report and exit cleanly
        print(f"ERROR: evidence gather failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    try:
        artifact, any_below = render_artifact(args.scope, today, evidence, args.learnings)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        if args.output:
            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = project_dir / output_path
            output_path = _require_project_output_path(output_path, project_dir)
        else:
            output_path = _resolve_output_path(retro_dir, args.scope, today, args.fill, project_dir)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(artifact, encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot write artifact: {exc}", file=sys.stderr)
        return 3

    print(str(output_path))
    return 1 if any_below else 0


if __name__ == "__main__":
    sys.exit(main())
