#!/usr/bin/env python3
"""Measure whether documented trigger phrases are things a user has ever said.

A skill's description is the only thing the router sees before deciding to load
it, so the phrases in that description are load-bearing. They are also written
by the same person who wrote the skill, scored by a predicate written by the
same person, against examples chosen by the same person. That is a closed loop.

The wiki concept ``Skill Triggering Failure Modes`` records what happens when
the loop is opened: a practitioner's skill-activation classifier scored 93
percent precision and recall on 40 prompts he wrote, and 27 percent precision
on 86 prompts mined from his own transcripts. Same classifier, same author. The
only thing that changed was who wrote the prompts.

This tool opens the loop locally. It reads real prompts out of the Claude Code
transcript store and reports what fraction of documented trigger phrases have
ever appeared in one.

It never writes prompt text anywhere. Transcripts contain whatever the user
typed, including paths, tokens, and third-party content, so the corpus stays in
memory and only aggregate counts and the phrases themselves reach stdout or the
report file.

Examples:
    uv run python scripts/eval/eval-trigger-phrase-realism.py
    uv run python scripts/eval/eval-trigger-phrase-realism.py --project-filter ai-agents
    uv run python scripts/eval/eval-trigger-phrase-realism.py --output realism.json

Exit codes (ADR-035):
    0 success
    2 configuration error (skills directory missing, bad arguments)
    3 external error (no transcript store, or it yielded no prompts)
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import TypedDict

import yaml

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from _trigger_realism import (  # noqa: E402
    MINIMUM_CORPUS,
    RealismReport,
    is_operator_entry,
    is_operator_text,
    score,
)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_TRIGGER_SECTION = re.compile(r"^## Triggers\s*$(.*?)(?=^## |\Z)", re.M | re.S)
# The standard permits a trigger "table or list", so both shapes must be read.
# A table-only reader silently halves the denominator.
_TABLE_CELL = re.compile(r'^\|\s*(?:`([^`]+)`|"([^"]+)")', re.M)
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+`([^`]+)`", re.M)
# Descriptions carry phrases in double quotes or backticks; both are promoted.
_QUOTED = re.compile(r'"([^"]+)"')
_BACKTICKED = re.compile(r"`([^`]+)`")


class SetReport(TypedDict):
    """Scored result for one phrase set, as it appears in the JSON report."""

    skills: int
    measurable_phrases: int
    excluded_phrases: int
    observed_phrases: int
    realism: float


class ObservedRow(TypedDict):
    """One phrase a real user typed, with how many prompts contained it."""

    skill: str
    phrase: str
    occurrences: int


class Report(TypedDict):
    """The whole report. Serialised verbatim when --output is given."""

    corpus_prompts: int
    control_prompts: int
    documented: SetReport
    promoted: SetReport
    control_documented: SetReport
    observed_phrases: list[ObservedRow]



def load_transcript_prompts(store: Path, project_filter: str) -> tuple[list[str], list[str]]:
    """Return the operator-typed and machine-authored prompts from the store.

    Both halves are returned because the machine-authored half is this eval's
    negative control, not waste. See ``build_report``.
    """
    operator: set[str] = set()
    machine: set[str] = set()
    for project in sorted(store.glob(f"*{project_filter}*")):
        for transcript in project.rglob("*.jsonl"):
            try:
                lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                split = _split_user_text(line)
                if split is None:
                    continue
                text, is_operator = split
                (operator if is_operator else machine).add(text)
    return sorted(operator), sorted(machine)


def _split_user_text(line: str) -> tuple[str, bool] | None:
    """Return one line's user text and whether a human typed it, or None.

    The ``user`` role in this format is not a claim that a user wrote the text.
    Sidechain entries are prompts an agent wrote for a subagent, meta entries
    are harness-injected, and compaction and tool-originated turns are
    bookkeeping. On this store those shapes are the overwhelming majority of
    the role, so treating the role as provenance benchmarks the phrases against
    machine-authored text. That is the exact closed loop this eval detects, so
    the two halves are separated rather than merged.

    Provenance rules live in ``_trigger_realism`` so they are testable without
    a store.
    """
    try:
        entry = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(entry, dict) or entry.get("type") != "user":
        return None
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = " ".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not is_operator_text(text):
        return None
    return text, is_operator_entry(entry)


def load_session_store_prompts(database: Path, project_filter: str) -> list[str]:
    """Return operator prompts from the Copilot CLI session store.

    This store is where the operator turns actually live. Its ``turns`` table
    records the human turn as a distinct column, so provenance is structural
    rather than inferred, and only the synthetic-text rule has to be applied.
    Opened read-only so a live store is never mutated by a measurement.
    """
    uri = f"file:{database}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        rows = connection.execute(
            "SELECT DISTINCT t.user_message FROM turns t "
            "JOIN sessions s ON s.id = t.session_id "
            "WHERE t.user_message IS NOT NULL AND s.repository LIKE ?",
            (f"%{project_filter}%",),
        ).fetchall()
    return sorted(
        {
            text.strip()
            for (text,) in rows
            if isinstance(text, str) and is_operator_text(text)
        }
    )


def collect_phrases(skills_dir: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return each skill's documented table phrases and its promoted phrases.

    Documented phrases come from the ``## Triggers`` section, which the
    standard permits to be a table or a list, so both shapes are read.
    Promoted phrases are the quoted and backticked spans in the description,
    which is the only one of the two the router ever sees.
    """
    documented: dict[str, list[str]] = {}
    promoted: dict[str, list[str]] = {}
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        body = skill_md.read_text(encoding="utf-8", errors="replace")
        parts = body.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            front = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(front, Mapping):
            continue
        description = front.get("description")
        if not isinstance(description, str):
            continue
        name = skill_md.parent.name
        section = _TRIGGER_SECTION.search(body)
        if section:
            # _TABLE_CELL alternates backticked and quoted, so findall yields a
            # pair per row with one side empty. Flatten before stripping.
            cells = [
                group
                for pair in _TABLE_CELL.findall(section.group(1))
                for group in pair
                if group
            ]
            raw = cells + _LIST_ITEM.findall(section.group(1))
            phrases = sorted({p.strip() for p in raw})
            if phrases:
                documented[name] = phrases
        quoted = sorted(
            {p.strip() for p in _QUOTED.findall(description) + _BACKTICKED.findall(description)}
        )
        if quoted:
            promoted[name] = quoted
    return documented, promoted


def build_report(skills_dir: Path, corpus: list[str], control: list[str]) -> Report:
    """Score both phrase sets against the operator corpus and its control.

    ``control`` is the machine-authored half of the transcript store: sidechain,
    meta, and agent-authored turns. It is the negative control for this eval.
    A low operator score on its own is ambiguous, since a broken matcher also
    produces one. Scoring the same phrases against text written by agents that
    read the documentation disambiguates it: if the phrases match the machine
    corpus and not the human one, the matcher works and the phrases circulate
    only inside the loop that defined them.
    """
    documented, promoted = collect_phrases(skills_dir)
    documented_report = score(documented, corpus)
    promoted_report = score(promoted, corpus)
    control_report = score(documented, control)
    return {
        "corpus_prompts": len(corpus),
        "control_prompts": len(control),
        "documented": _as_dict(documented_report, len(documented)),
        "promoted": _as_dict(promoted_report, len(promoted)),
        "control_documented": _as_dict(control_report, len(documented)),
        "observed_phrases": sorted(
            (
                {"skill": skill, "phrase": phrase, "occurrences": count}
                for (skill, phrase), count in documented_report.hits.items()
            ),
            key=lambda row: (-row["occurrences"], row["skill"]),
        ),
    }


def _as_dict(report: RealismReport, skill_count: int) -> SetReport:
    return {
        "skills": skill_count,
        "measurable_phrases": report.measurable,
        "excluded_phrases": report.excluded,
        "observed_phrases": report.observed,
        "realism": round(report.realism, 4),
    }


def render(report: Report) -> str:
    """Return the human-readable summary."""
    lines = [
        f"Corpus: {report['corpus_prompts']} unique operator-typed prompts "
        "(word-boundary matched; slash commands and single words excluded)",
        f"Control: {report['control_prompts']} machine-authored prompts "
        "(sidechain, meta, and agent-authored turns)",
        "",
    ]
    for block, label in (
        (report["documented"], "documented in a ## Triggers table"),
        (report["promoted"], "promoted into a description"),
    ):
        lines.append(f"{label}:")
        lines.append(
            f"  {block['observed_phrases']} of {block['measurable_phrases']} phrases "
            f"have ever been said  ({block['realism']:.1%})"
        )
    control = report["control_documented"]
    lines.append("")
    lines.append("negative control, same phrases against machine-authored text:")
    lines.append(
        f"  {control['observed_phrases']} of {control['measurable_phrases']} phrases "
        f"appear  ({control['realism']:.1%})"
    )
    observed = report["observed_phrases"]
    if observed:
        lines.append("")
        lines.append("phrases a real user actually said:")
        for row in observed[:15]:
            lines.append(
                f"  {row['occurrences']:4}x  {row['skill']:26} {row['phrase']!r}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--transcript-store",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="Claude Code transcript store (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--session-store",
        type=Path,
        default=Path.home() / ".copilot" / "session-store.db",
        help="Copilot CLI session store (default: ~/.copilot/session-store.db)",
    )
    parser.add_argument(
        "--project-filter",
        default="ai-agents",
        help="Substring selecting which project directories to read",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / ".claude" / "skills",
        help="Canonical skills directory",
    )
    parser.add_argument(
        "--output", type=Path, help="Write the JSON report to this path"
    )
    args = parser.parse_args(argv)

    if not args.skills_dir.is_dir():
        print(f"Skills directory not found: {args.skills_dir}", file=sys.stderr)
        return EXIT_CONFIG

    corpus: set[str] = set()
    control: set[str] = set()
    sources: list[str] = []
    if args.transcript_store.is_dir():
        operator, machine = load_transcript_prompts(
            args.transcript_store, args.project_filter
        )
        corpus.update(operator)
        control.update(machine)
        sources.append(f"{args.transcript_store} (Claude Code transcripts)")
    if args.session_store.is_file():
        try:
            corpus.update(
                load_session_store_prompts(args.session_store, args.project_filter)
            )
        except sqlite3.Error as error:
            print(f"Cannot read {args.session_store}: {error}", file=sys.stderr)
            return EXIT_EXTERNAL
        sources.append(f"{args.session_store} (Copilot CLI sessions)")
    if not sources:
        print(
            "No prompt store found. This eval needs real prompts; it cannot "
            "fall back to authored ones without defeating its own purpose.",
            file=sys.stderr,
        )
        return EXIT_EXTERNAL

    if len(corpus) < MINIMUM_CORPUS:
        print(
            f"Operator corpus is {len(corpus)} prompts, below the {MINIMUM_CORPUS} "
            "needed to report a share. At this size a zero reading and a small "
            "non-zero reading are indistinguishable, so no percentage is "
            "reported. Sources read:\n  " + "\n  ".join(sources),
            file=sys.stderr,
        )
        return EXIT_EXTERNAL

    report = build_report(args.skills_dir, sorted(corpus), sorted(control))
    print(render(report))
    if args.output:
        try:
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        except OSError as error:
            print(f"Cannot write {args.output}: {error}", file=sys.stderr)
            return EXIT_EXTERNAL
        print(f"\nWrote {args.output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
