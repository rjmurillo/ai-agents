#!/usr/bin/env python3
"""Truncation-aware full-catalog skill collision report (issue #5763).

`eval-skill-overlap.py` scores hand-picked skill pairs. `skill_description_budget.py`
sums description size. Neither answers: across the whole catalog, which skill names
or descriptions are exact, normalized, or near duplicates, and which pairs become
indistinguishable once a host abbreviates descriptions?

This script is deterministic and offline. It reads `<root>/*/SKILL.md` frontmatter,
compares every unordered skill pair, and reports:

  - exact:               identical text.
  - normalized:          identical after NFKC, casefold, and punctuation collapse.
  - truncated-identical: not exact or normalized in full, but the normalized
                         truncated text is equal under a controlled truncation
                         profile (`chars:N` keeps the first N characters). A
                         pair with a full-text exact or normalized hit skips
                         truncation scanning; a full-text near hit does not.
  - near:                token Jaccard similarity at or above `--near-threshold`.

exact, normalized, and truncated-identical are HIGH confidence. near is LOW
confidence: lexical similarity is a hint for owner review, never an automatic
failure.

The truncation profiles are controlled inputs chosen by the operator. They are not
measured limits of any model host, and this script does not observe any host's
description abbreviation. The report says so in its `assumptions` block. It makes
no semantic routing claim and measures no skill-selection accuracy.

Regression policy: with `--baseline FILE`, the run exits 1 when a HIGH confidence
finding is absent from the reviewed accepted list. LOW confidence findings never
fail the run. Each accepted entry needs a `reason` and an `owner`.

Evaluation inputs: findings group into clusters (connected components of colliding
skills). `--emit-pairs OUT --prompts-file FILE` writes a pairs file for
`eval-skill-overlap.py` covering every within-cluster pair whose two skills both
have prompts in FILE. `--only NAME` and `--changed-since REF` restrict the report to
findings that involve selected skills.

Usage:
    uv run python scripts/eval/skill_collision_report.py
    uv run python scripts/eval/skill_collision_report.py --format json --truncate 100
    uv run python scripts/eval/skill_collision_report.py \\
        --baseline scripts/eval/skill_collision_baseline.json

Exit codes (AGENTS.md): 0 ok, 1 new high-confidence collision, 2 config error,
3 external error (git failed).
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from _skill_collision import (
    DEFAULT_NEAR_THRESHOLD,
    DEFAULT_TRUNCATIONS,
    CollisionReport,
    Finding,
    GitError,
    ReportError,
    build_report,
    changed_skills,
)

EXIT_OK = 0
EXIT_NEW_COLLISION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

DEFAULT_ROOT = Path(".claude/skills")

# ---------------------------------------------------------------------------
# Regression policy
# ---------------------------------------------------------------------------


def load_accepted(path: Path) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    """Parse the reviewed accepted-collision list.

    Raises:
        ReportError: on any structural problem, or an entry without reason and owner.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReportError(f"Baseline not readable: {path}: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise ReportError(f"Baseline {path} is not valid JSON: {exc.msg}") from exc
    entries = data.get("accepted") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ReportError(f"Baseline {path}: top level needs an 'accepted' list.")
    accepted: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        accepted[_accepted_key(path, index, entry)] = entry
    return accepted


def _accepted_key(path: Path, index: int, entry: object) -> tuple[str, str, str, str, str]:
    where = f"Baseline {path}: accepted[{index}]"
    if not isinstance(entry, dict):
        raise ReportError(f"{where} must be an object.")
    for required in ("kind", "field", "profile", "reason", "owner"):
        value = entry.get(required)
        if not isinstance(value, str) or not value.strip():
            raise ReportError(f"{where} needs a non-empty '{required}'.")
    skills = entry.get("skills")
    if (
        not isinstance(skills, list)
        or len(skills) != 2
        or not all(isinstance(s, str) and s for s in skills)
    ):
        raise ReportError(f"{where} needs 'skills' as two non-empty names.")
    first, second = sorted(skills)
    return (entry["kind"], entry["field"], entry["profile"], first, second)


def new_high_findings(
    report: CollisionReport,
    accepted: dict[tuple[str, str, str, str, str], dict[str, Any]],
) -> list[Finding]:
    """High confidence findings absent from the accepted list."""
    return [f for f in report.high() if f.key not in accepted]


# ---------------------------------------------------------------------------
# Evaluation inputs
# ---------------------------------------------------------------------------


def load_prompts(path: Path) -> dict[str, Any]:
    """Read the `prompts` object of an eval-skill-overlap pairs file.

    Raises:
        ReportError: when the file is unreadable or has no prompts object.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ReportError(f"Prompts file not readable: {path}: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise ReportError(f"Prompts file {path} is not valid JSON: {exc.msg}") from exc
    prompts = data.get("prompts") if isinstance(data, dict) else None
    if not isinstance(prompts, dict) or not prompts:
        raise ReportError(f"Prompts file {path}: 'prompts' must be a non-empty object.")
    return prompts


def build_pairs_file(
    clusters: Iterable[Sequence[str]], prompts: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Build an eval-skill-overlap pairs payload from clusters.

    Returns the payload and the sorted skills skipped for lacking prompts.
    """
    pairs: list[list[str]] = []
    missing: set[str] = set()
    for cluster in clusters:
        for first, second in itertools.combinations(sorted(cluster), 2):
            absent = {s for s in (first, second) if s not in prompts}
            if absent:
                missing |= absent
            else:
                pairs.append([first, second])
    pairs.sort()
    used = sorted({s for pair in pairs for s in pair})
    payload = {"pairs": pairs, "prompts": {skill: prompts[skill] for skill in used}}
    return payload, sorted(missing)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_human(report: CollisionReport, new_high: Sequence[Finding] | None = None) -> str:
    """Human-readable report. `new_high` marks findings the policy rejects."""
    rejected = {f.key for f in new_high or ()}
    lines = [
        f"Skill collision report: {report.skills_scanned} skill(s) under {report.root}",
        f"Profiles (controlled, not measured host limits): {', '.join(report.profiles)}",
        f"Near threshold: {report.near_threshold} token Jaccard. Lexical only, no routing claim.",
        "Host abbreviation: not observed by this script.",
        f"Findings: {len(report.findings)} ({len(report.high())} high confidence)",
    ]
    for finding in report.findings:
        marker = " [NEW]" if finding.key in rejected else ""
        lines += [
            "",
            f"[{finding.confidence}] {finding.kind} {finding.field} "
            f"profile={finding.profile} sim={finding.similarity}{marker}",
            f"  {finding.skills[0]}: {finding.paths[0]}",
            f"    {finding.compared[0]}",
            f"  {finding.skills[1]}: {finding.paths[1]}",
            f"    {finding.compared[1]}",
            f"  Fix: {finding.remediation}",
        ]
    if report.clusters:
        lines += ["", "Clusters:"] + [f"  {', '.join(cluster)}" for cluster in report.clusters]
    return "\n".join(lines)


def render_json(report: CollisionReport, new_high: Sequence[Finding] | None = None) -> str:
    payload = report.to_dict()
    if new_high is not None:
        payload["policy"] = {"new_high_confidence": [f.to_dict() for f in new_high]}
    return json.dumps(payload, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report skill name and description collisions across the catalog (#5763)."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Skills root directory.")
    parser.add_argument(
        "--truncate",
        type=int,
        action="append",
        metavar="N",
        help=(
            "Controlled truncation profile: keep the first N characters of each description. "
            f"Repeatable. Default: {', '.join(map(str, DEFAULT_TRUNCATIONS))}."
        ),
    )
    parser.add_argument(
        "--near-threshold",
        type=float,
        default=DEFAULT_NEAR_THRESHOLD,
        help="Token Jaccard threshold for a near collision (0 to 1).",
    )
    parser.add_argument(
        "--only", action="append", default=[], help="Restrict to a skill. Repeatable."
    )
    parser.add_argument(
        "--changed-since", metavar="REF", help="Restrict to skills changed since this git ref."
    )
    parser.add_argument(
        "--baseline", type=Path, help="Reviewed accepted-collision list (gate mode)."
    )
    parser.add_argument("--emit-pairs", type=Path, help="Write an eval-skill-overlap pairs file.")
    parser.add_argument("--prompts-file", type=Path, help="Pairs file supplying prompts to emit.")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not 0.0 <= args.near_threshold <= 1.0:
        raise ReportError("--near-threshold must be between 0 and 1.")
    if any(n < 1 for n in args.truncate or ()):
        raise ReportError("--truncate values must be positive integers.")
    if bool(args.emit_pairs) != bool(args.prompts_file):
        raise ReportError("--emit-pairs and --prompts-file must be given together.")


def _selected_skills(args: argparse.Namespace) -> list[str]:
    selected = list(args.only)
    if args.changed_since:
        selected += changed_skills(args.root, args.changed_since)
    return selected


def _emit_pairs(args: argparse.Namespace, report: CollisionReport) -> None:
    payload, missing = build_pairs_file(report.clusters, load_prompts(args.prompts_file))
    if missing:
        print(f"No prompts for: {', '.join(missing)}. Pairs skipped.", file=sys.stderr)
    if not payload["pairs"]:
        raise ReportError("No cluster pair has prompts for both skills. Pairs file not written.")
    args.emit_pairs.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    _validate_args(args)
    selecting = bool(args.only or args.changed_since)
    selected = _selected_skills(args)
    if selecting and not selected:
        print("No selected skill changed. Nothing to report.")
        return EXIT_OK
    report = build_report(
        args.root,
        truncations=tuple(args.truncate) if args.truncate else DEFAULT_TRUNCATIONS,
        near_threshold=args.near_threshold,
        only=selected,
    )
    new_high = None
    if args.baseline:
        new_high = new_high_findings(report, load_accepted(args.baseline))
    print(
        render_json(report, new_high) if args.format == "json" else render_human(report, new_high)
    )
    if args.emit_pairs:
        _emit_pairs(args, report)
    return EXIT_NEW_COLLISION if new_high else EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return run(args)
    except ReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except GitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
