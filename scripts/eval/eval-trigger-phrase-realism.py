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
    python3 scripts/eval/eval-trigger-phrase-realism.py
    python3 scripts/eval/eval-trigger-phrase-realism.py --project-filter ai-agents
    python3 scripts/eval/eval-trigger-phrase-realism.py --output realism.json

Exit codes (ADR-035):
    0 success
    2 configuration error (skills directory missing, bad arguments)
    3 external error (no transcript store, or it yielded no prompts)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from importlib import import_module
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
_realism = import_module("_trigger_realism")
score = _realism.score

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_TRIGGER_SECTION = re.compile(r"^## Triggers\s*$(.*?)(?=^## |\Z)", re.M | re.S)
_FIRST_COLUMN = re.compile(r"^\|\s*`([^`]+)`", re.M)
_QUOTED = re.compile(r'"([^"]+)"')


def load_transcript_prompts(store: Path, project_filter: str) -> list[str]:
    """Return unique user-authored prompts from the Claude transcript store.

    Only entries the user actually typed are returned. Tool results share the
    ``user`` role in this format and are excluded, as are the harness-injected
    entries that begin with an XML tag or a known preamble.
    """
    prompts: set[str] = set()
    for project in sorted(store.glob(f"*{project_filter}*")):
        for transcript in project.rglob("*.jsonl"):
            try:
                lines = transcript.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                text = _user_text(line)
                if text:
                    prompts.add(text)
    return sorted(prompts)


def _user_text(line: str) -> str | None:
    """Return the user-typed text of one transcript line, or None."""
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
    if not text or text.startswith(("<", "[Request interrupted", "Caveat:")):
        return None
    if "<local-command" in text:
        return None
    return text


def collect_phrases(skills_dir: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return each skill's documented table phrases and its promoted phrases.

    Table phrases come from the first column of the ``## Triggers`` table.
    Promoted phrases are the double-quoted spans in the description, which is
    the only one of the two the router ever sees.
    """
    documented: dict[str, list[str]] = {}
    promoted: dict[str, list[str]] = {}
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        body = skill_md.read_text(errors="replace")
        parts = body.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            front = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            continue
        description = front.get("description")
        if not isinstance(description, str):
            continue
        name = skill_md.parent.name
        section = _TRIGGER_SECTION.search(body)
        if section:
            phrases = [p.strip() for p in _FIRST_COLUMN.findall(section.group(1))]
            if phrases:
                documented[name] = phrases
        quoted = _QUOTED.findall(description)
        if quoted:
            promoted[name] = quoted
    return documented, promoted


def build_report(skills_dir: Path, corpus: list[str]) -> dict[str, object]:
    """Score both phrase sets and return a JSON-serialisable report."""
    documented, promoted = collect_phrases(skills_dir)
    documented_report = score(documented, corpus)
    promoted_report = score(promoted, corpus)
    return {
        "corpus_prompts": len(corpus),
        "documented": _as_dict(documented_report, len(documented)),
        "promoted": _as_dict(promoted_report, len(promoted)),
        "observed_phrases": sorted(
            (
                {"skill": skill, "phrase": phrase, "occurrences": count}
                for (skill, phrase), count in documented_report.hits.items()
            ),
            key=lambda row: (-row["occurrences"], row["skill"]),
        ),
    }


def _as_dict(report: object, skill_count: int) -> dict[str, object]:
    return {
        "skills": skill_count,
        "measurable_phrases": report.measurable,
        "excluded_phrases": report.excluded,
        "observed_phrases": report.observed,
        "realism": round(report.realism, 4),
    }


def render(report: dict[str, object]) -> str:
    """Return the human-readable summary."""
    lines = [
        f"Corpus: {report['corpus_prompts']} unique real prompts "
        "(word-boundary matched; slash commands and single words excluded)",
        "",
    ]
    for key, label in (
        ("documented", "documented in a ## Triggers table"),
        ("promoted", "promoted into a description"),
    ):
        block = report[key]
        lines.append(f"{label}:")
        lines.append(
            f"  {block['observed_phrases']} of {block['measurable_phrases']} phrases "
            f"have ever been said  ({block['realism']:.1%})"
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
    if not args.transcript_store.is_dir():
        print(
            f"No transcript store at {args.transcript_store}. This eval needs real "
            "prompts; it cannot fall back to authored ones without defeating its "
            "own purpose.",
            file=sys.stderr,
        )
        return EXIT_EXTERNAL

    corpus = load_transcript_prompts(args.transcript_store, args.project_filter)
    if not corpus:
        print(
            f"No user prompts matched --project-filter {args.project_filter!r} "
            f"under {args.transcript_store}.",
            file=sys.stderr,
        )
        return EXIT_EXTERNAL

    report = build_report(args.skills_dir, corpus)
    print(render(report))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nWrote {args.output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
