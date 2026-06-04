#!/usr/bin/env python3
"""Orchestrate the retrospective workflow and persist an artifact.

This is the thin Phase 0..5 orchestrator the SKILL.md contract describes. It
gathers evidence (Phase 0 via ``extract_evidence``), scores any supplied
learnings (Phase 4 via ``score_atomicity``), and writes a retrospective artifact
whose section headings match the canonical Learning Extraction Template at
``.claude/skills/retrospective/references/learning-template.md``.

The interpretive phases (Five Whys, fishbone, diagnosis prose) are authored by
the agent or reviewer reading the rendered template; this script supplies the
deterministic scaffold and fills the data-bearing parts (session info, work
items, learning scores) so the human-or-agent does not start from a blank file.

Two write modes:
  * New artifact: writes ``.agents/retrospective/YYYY-MM-DD-[scope].md``.
  * Fill skeleton: when ``--fill`` targets an existing
    ``YYYY-MM-DD-auto-retro.md`` skeleton, the artifact is written next to it as
    a filled retrospective and the skeleton's UNFILLED banner is the signal it
    replaces. The script never deletes the skeleton; it writes the filled file
    and leaves removal to the caller.

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
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Protocol

UTC = timezone.utc  # noqa: UP017 - Python 3.10 compatibility

_SCRIPT_DIR = Path(__file__).resolve().parent


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


def _render_learnings(learnings: list[str]) -> tuple[str, bool]:
    """Render the Phase 4 learnings block, scoring each learning.

    Returns the rendered block and whether any learning fell below the
    persistence threshold.
    """
    if not learnings:
        return (
            "### Learning 1\n"
            "- **Statement**: _UNFILLED: extract an atomic learning (max 15 words)._\n"
            "- **Atomicity Score**: _pending_\n"
            "- **Evidence**: _UNFILLED._\n"
            "- **Skill Operation**: ADD | UPDATE | TAG | REMOVE\n"
            "- **Target Skill ID**: _If UPDATE/TAG/REMOVE_",
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
            f"- **Evidence**: _UNFILLED: cite the execution detail._\n"
            f"- **Skill Operation**: ADD | UPDATE | TAG | REMOVE\n"
            f"- **Target Skill ID**: _If UPDATE/TAG/REMOVE_"
        )
    return "\n\n".join(blocks), any_below


def render_artifact(
    scope: str, today: str, evidence: EvidenceLike, learnings: list[str]
) -> tuple[str, bool]:
    """Render a retrospective artifact matching the canonical template shape.

    The section headings and order mirror
    ``references/learning-template.md`` so downstream readers and the
    auto-retro fill path see a consistent structure. Interpretive sections
    (Phase 1 insights, Phase 2/3 prose) are left as explicit UNFILLED prompts
    for the agent or reviewer; the data-bearing sections are populated.

    Returns the rendered markdown and whether any learning scored below the
    persistence threshold.
    """
    session_context = _render_session_context(evidence)
    learnings_block, any_below = _render_learnings(learnings)
    outcome = "Success" if evidence.session_log_available else "Partial"

    artifact = f"""# Retrospective: {scope}

## Session Info
- **Date**: {today}
- **Agents**: _UNFILLED: list participating agents._
- **Task Type**: _UNFILLED: Feature | Bug | Research_
- **Outcome**: {outcome}

## Phase 0: Data Gathering
{session_context}

## Phase 1: Insights Generated
_UNFILLED: Five Whys (if failure), Fishbone (if complex), Patterns and Shifts, Learning Matrix._

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| _UNFILLED_ | _UNFILLED_ | _1-10_ | _%_ |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| _UNFILLED_ | _UNFILLED_ | _UNFILLED_ | _UNFILLED_ | _%_ |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| _UNFILLED_ | _UNFILLED_ | _UNFILLED_ |

## Phase 3: Decisions

### Action Classification
_UNFILLED: Keep/Drop/Add/Modify table._

### SMART Validation
_UNFILLED: Validation for each new skill._

### Action Sequence
_UNFILLED: Ordered actions with dependencies._

## Phase 4: Extracted Learnings

{learnings_block}

## Skillbook Updates

### ADD
_UNFILLED: one JSON block per skill to add._

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


def _resolve_output_path(retro_dir: Path, scope: str, today: str, fill: str | None) -> Path:
    """Resolve where the artifact is written.

    When ``fill`` names an existing skeleton, write a filled file next to it.
    The filled file replaces the ``-auto-retro`` suffix with ``-retro-filled``
    so the skeleton stays intact for the caller to remove deliberately.
    Otherwise write ``YYYY-MM-DD-[scope].md``.
    """
    if fill:
        skeleton = Path(fill)
        if not skeleton.is_absolute():
            skeleton = retro_dir / skeleton.name
        stem = skeleton.stem.replace("-auto-retro", "")
        if not stem:
            stem = today
        return skeleton.with_name(f"{stem}-retro-filled.md")
    safe_scope = scope.strip().replace(" ", "-").replace("/", "-")
    return retro_dir / f"{today}-{safe_scope}.md"


def _require_project_output_path(path: Path, project_dir: Path) -> Path:
    """Return a resolved output path only when it stays inside project_dir."""
    resolved_project = project_dir.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_project):
        raise ValueError(f"output path escapes project dir: {path}")
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
        help="Path to an existing auto-retro skeleton to fill (writes alongside it).",
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

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    retro_dir = project_dir / ".agents" / "retrospective"

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

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = project_dir / output_path
    else:
        output_path = _resolve_output_path(retro_dir, args.scope, today, args.fill)

    try:
        output_path = _require_project_output_path(output_path, project_dir)
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
