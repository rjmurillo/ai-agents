#!/usr/bin/env python3
"""Flag newly added Serena memories that read as normative or procedural (issue #5391).

The knowledge-persistence rule's placement contract says a memory holds
evidence and a rule, skill, or agent holds required behavior. This check flags
a NEWLY added memory that reads as policy and names the surface it belongs on.
It does not migrate the corpus, build a registry, or budget tokens.

SIGNALS, from :func:`classify` on raw text after fenced and indented code is
blanked: (a) normative-term count (MUST, MUST NOT, SHALL; must not, never,
always, required; bare lowercase "must" is prose); (b) a heading matching
Constraints|Guardrails|Workflow|Procedure|Protocol|Responsibilities|Entry
Criteria|Acceptance Criteria|Handoff; (c) an ordered list of 5+ items; (d)
two or more Role|Authority|Entry Criteria|Outputs|Handoff|Responsibilities
headings.

POLICY: ``normative`` when (b) or (d) fires, or (a) >= 5 with (c).
``suspect`` when (a) >= 3 or (c) fires, or both. Otherwise ``evidence``.
Two signals are required because single words are weak (figures: DESIGN-026).

A file present in the ``--base`` tree never fails; it warns. Only a file
absent from the base tree fails, and only when classified ``normative``.
``<!-- placement: evidence; reason: ... -->`` with a non-empty reason
downgrades to evidence (reported ``suppressed``); an empty reason is
reported ``invalid-suppression`` and does not downgrade. Route: (d) to an
agent, (c) without (a) >= 5 to a skill, else to a rule. README.md,
``*-index.md``, and non-``.md`` files are skipped.

EXIT CODES (ADR-035): 0 clean or warnings only; 1 a new normative file under
``--ci``; 2 usage error, not a git repository, bad ``--base``, or a path
outside the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))

from memory_placement_git import (  # noqa: E402
    ConfigError,
    base_tree_paths,
    index_paths,
    read_candidate,
    repo_root,
)

from scripts.utils.markdown_parser import (  # noqa: E402
    Section,
    blank_code_block_lines,
    parse_sections,
)

_NORMATIVE_TERM_THRESHOLD = 5
_SUSPECT_TERM_THRESHOLD = 3
_ORDERED_PROCEDURE_MIN_ITEMS = 5
_ROLE_CONTRACT_MIN_HEADINGS = 2

# One alternation, longest alternative first, so "MUST NOT" counts once:
# case-sensitive MUST NOT | MUST | SHALL, then case-insensitive phrases.
_NORMATIVE_TERM_RE = re.compile(r"\b(?:MUST NOT|MUST|SHALL|(?i:must not|never|always|required))\b")

_HEADING_NORMATIVE_WORDS = (
    "Constraints",
    "Guardrails",
    "Workflow",
    "Procedure",
    "Protocol",
    "Responsibilities",
    "Entry Criteria",
    "Acceptance Criteria",
    "Handoff",
)
_HEADING_NORMATIVE_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _HEADING_NORMATIVE_WORDS) + r")\b",
    re.IGNORECASE,
)

_ROLE_CONTRACT_WORDS = (
    "Role",
    "Authority",
    "Entry Criteria",
    "Outputs",
    "Handoff",
    "Responsibilities",
)
_ROLE_CONTRACT_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _ROLE_CONTRACT_WORDS) + r")\b",
    re.IGNORECASE,
)

_ORDERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+")

# The marker must stand alone on its line (not inside an inline code span or
# another HTML element) and the reason must start with a non-whitespace char.
_VALID_SUPPRESSION_RE = re.compile(
    r"^[ \t]*<!--\s*placement:\s*evidence;\s*reason:\s*(\S[^>]*?)\s*-->[ \t]*$", re.MULTILINE
)
# Looser sibling: detects a marker that is present but malformed.
_ANY_SUPPRESSION_RE = re.compile(r"<!--\s*placement:\s*evidence;\s*reason:\s*(.*?)-->", re.DOTALL)

_ROUTE_DESTINATIONS = {
    "rule": "templates/rules/",
    "skill": ".claude/skills/<name>/SKILL.md",
    "agent": "templates/agents/",
}


@dataclass(frozen=True, slots=True)
class Classification:
    """The result of classifying one memory file's text.

    ``label`` is the reportable classification after suppression is applied
    (``normative`` | ``suspect`` | ``evidence``). ``raw_label`` is the
    classification signals alone would produce, before suppression: it is
    what an invalid-suppression finding still reports and still fails on.
    """

    label: str
    raw_label: str
    signals: tuple[str, ...]
    route: str
    suppressed: bool
    invalid_suppression: bool


def _count_normative_terms(text: str) -> int:
    """Count signal-(a) normative-term hits, case rules per the module docstring."""
    return len(_NORMATIVE_TERM_RE.findall(text))


def _heading_signals(sections: list[Section]) -> tuple[list[str], list[str]]:
    """Return (signal-(b) heading matches, signal-(d) role-heading matches)."""
    normative_matches: list[str] = []
    role_matches: list[str] = []
    seen_roles: set[str] = set()
    for section in sections:
        normative_hit = _HEADING_NORMATIVE_RE.search(section.title)
        if normative_hit:
            normative_matches.append(normative_hit.group(1))
        role_hit = _ROLE_CONTRACT_RE.search(section.title)
        if role_hit:
            key = role_hit.group(1).lower()
            if key not in seen_roles:
                seen_roles.add(key)
                role_matches.append(role_hit.group(1))
    return normative_matches, role_matches


def _has_ordered_procedure(text: str) -> tuple[bool, int]:
    """Return (signal-(c) fired, longest run) of consecutive numbered items.

    A run tolerates a single blank line between items (loose Markdown
    lists); two or more blank lines, or any non-blank non-item line, ends it.
    """
    longest = 0
    streak = 0
    blank_run = 0
    for line in text.split("\n"):
        if _ORDERED_ITEM_RE.match(line):
            streak += 1
            blank_run = 0
            longest = max(longest, streak)
        elif line.strip() == "":
            blank_run += 1
            if blank_run > 1:
                streak = 0
        else:
            streak = 0
            blank_run = 0
    return longest >= _ORDERED_PROCEDURE_MIN_ITEMS, longest


def _suppression_status(text: str) -> tuple[bool, bool]:
    """Return (suppressed, invalid_suppression) for a placement marker in ``text``."""
    if _VALID_SUPPRESSION_RE.search(text):
        return True, False
    if _ANY_SUPPRESSION_RE.search(text):
        return False, True
    return False, False


def _derive_raw_label(a_count: int, b_fires: bool, ordered_fires: bool, d_fires: bool) -> str:
    """Apply the two-signal policy from the module docstring."""
    if b_fires or d_fires or (a_count >= _NORMATIVE_TERM_THRESHOLD and ordered_fires):
        return "normative"
    if a_count >= _SUSPECT_TERM_THRESHOLD or ordered_fires:
        return "suspect"
    return "evidence"


def _derive_route(a_count: int, b_fires: bool, ordered_fires: bool, d_fires: bool) -> str:
    """Apply the route heuristic from the module docstring."""
    if d_fires:
        return "agent"
    if b_fires:
        return "rule"
    if ordered_fires and a_count < _NORMATIVE_TERM_THRESHOLD:
        return "skill"
    return "rule"


def _collect_signals(
    a_count: int,
    heading_matches: list[str],
    ordered_fires: bool,
    ordered_count: int,
    role_matches: list[str],
) -> list[str]:
    """Render the fired signals as short strings for the finding report."""
    signals: list[str] = []
    if a_count:
        signals.append(f"normative-terms={a_count}")
    if heading_matches:
        signals.append("heading:" + ",".join(dict.fromkeys(heading_matches)))
    if ordered_fires:
        signals.append(f"ordered-procedure={ordered_count}")
    if role_matches:
        signals.append("role-contract:" + ",".join(role_matches))
    return signals


def classify(text: str) -> Classification:
    """Classify one memory file's raw text. Pure: no filesystem or git access."""
    sections = parse_sections(text)
    heading_matches, role_matches = _heading_signals(sections)
    # Signals (a) and (c) scan raw lines, so blank fenced and indented code
    # first: a memory that quotes a rule's shape inside a fence is evidence
    # about that rule, not a rule. parse_sections already skips fences.
    prose = blank_code_block_lines(text)
    a_count = _count_normative_terms(prose)
    ordered_fires, ordered_count = _has_ordered_procedure(prose)
    b_fires = bool(heading_matches)
    d_fires = len(role_matches) >= _ROLE_CONTRACT_MIN_HEADINGS

    signals = _collect_signals(a_count, heading_matches, ordered_fires, ordered_count, role_matches)
    raw_label = _derive_raw_label(a_count, b_fires, ordered_fires, d_fires)
    route = _derive_route(a_count, b_fires, ordered_fires, d_fires)

    suppressed, invalid_suppression = _suppression_status(prose)
    if invalid_suppression:
        signals.append("invalid-suppression")

    return Classification(
        label="evidence" if suppressed else raw_label,
        raw_label=raw_label,
        signals=tuple(signals),
        route=route,
        suppressed=suppressed,
        invalid_suppression=invalid_suppression,
    )


@dataclass(frozen=True, slots=True)
class Finding:
    """One reportable line: a file classified normative, suspect, or suppressed."""

    path: str
    reported_label: str
    raw_label: str
    signals: tuple[str, ...]
    route: str
    destination: str
    is_new: bool
    invalid_suppression: bool


def _reported_label(classification: Classification) -> str | None:
    """Label to report, or None for plain evidence."""
    if classification.suppressed:
        return "suppressed"
    if classification.label in ("normative", "suspect"):
        return classification.label
    return None


def evaluate_file(relpath: str, text: str, is_new: bool) -> Finding | None:
    """Classify one file's text and return a Finding, or None if it is clean."""
    classification = classify(text)
    reported = _reported_label(classification)
    if reported is None:
        return None
    return Finding(
        path=relpath,
        reported_label=reported,
        raw_label=classification.raw_label,
        signals=classification.signals,
        route=classification.route,
        destination=_ROUTE_DESTINATIONS[classification.route],
        is_new=is_new,
        invalid_suppression=classification.invalid_suppression,
    )


def format_finding_line(finding: Finding) -> str:
    """Render one finding as ``<path>: <label>: <signals> -> route to ...``."""
    signals_text = ",".join(finding.signals) if finding.signals else "none"
    return (
        f"{finding.path}: {finding.reported_label}: {signals_text} -> "
        f"route to {finding.route} ({finding.destination})"
    )


def _tally(findings: list[Finding]) -> tuple[Counter[str], int]:
    """Return (label counts, number of new-and-normative findings)."""
    counts = Counter(f.reported_label for f in findings)
    failing = sum(1 for f in findings if f.reported_label == "normative" and f.is_new)
    return counts, failing


def format_summary(examined: int, findings: list[Finding]) -> str:
    """Render the one summary line printed after every finding line."""
    counts, failing = _tally(findings)
    return (
        f"check-memory-placement: {examined} file(s) examined, "
        f"{counts.get('normative', 0)} normative, "
        f"{counts.get('suspect', 0)} suspect, "
        f"{counts.get('suppressed', 0)} suppressed, "
        f"{failing} failing (new and normative)."
    )


def _report_dict(examined: int, findings: list[Finding]) -> dict[str, object]:
    """Build the JSON-serializable report for ``--json``."""
    counts, failing = _tally(findings)
    return {
        "examined": examined,
        "counts": {k: counts.get(k, 0) for k in ("normative", "suspect", "suppressed")},
        "failing": failing,
        "findings": [asdict(f) for f in findings],
    }


def _is_skippable(path: Path) -> bool:
    """True for README.md, any *-index.md, and anything that is not .md."""
    if path.suffix.lower() != ".md":
        return True
    if path.name == "README.md":
        return True
    return path.name.endswith("-index.md")


def _candidate_paths(args: argparse.Namespace, repo_root: Path) -> list[Path]:
    """Return the raw paths a caller asked to check, before filtering."""
    if args.path is not None:
        base_dir = args.path if args.path.is_absolute() else repo_root / args.path
        base_dir = base_dir.resolve()
        if not base_dir.is_relative_to(repo_root):
            raise ConfigError(f"--path is outside the repository: {args.path}")
        if not base_dir.is_dir():
            raise ConfigError(f"--path is not a directory: {args.path}")
        return sorted(base_dir.rglob("*.md"))
    return [Path(p) for p in args.paths]


def _resolve_candidates(
    args: argparse.Namespace,
    repo_root: Path,
    index: dict[str, tuple[str, str] | None] | None,
) -> list[tuple[str, Path]]:
    """Resolve caller-supplied paths to (repo-relative posix path, absolute path).

    Applies the README/``*-index.md``/non-``.md`` skip and rejects (raises
    ``ConfigError``) any path that resolves outside the repository root.
    """
    candidates: list[tuple[str, Path]] = []
    for raw in _candidate_paths(args, repo_root):
        abspath = raw if raw.is_absolute() else repo_root / raw
        # Normalise without following symlinks: the staged path is the one
        # git tracks, and a link's target may sit in the base tree while the
        # link itself is new. resolve() would report the target instead.
        abspath = Path(os.path.normpath(abspath))
        if not abspath.is_relative_to(repo_root):
            raise ConfigError(f"path is outside the repository: {raw}")
        if abspath.is_dir():
            raise ConfigError(f"positional path is a directory, use --path: {raw}")
        if _is_skippable(abspath):
            continue
        relpath = abspath.relative_to(repo_root).as_posix()
        if index is not None:
            if relpath not in index:
                raise ConfigError(f"staged path is not in the index: {raw}")
            entry = index[relpath]
            if entry is None:
                raise ConfigError(f"staged path has unresolved index entries: {raw}")
            if entry[0] == "120000":
                raise ConfigError(f"staged symlink cannot be validated: {raw}")
            candidates.append((relpath, abspath))
            continue
        if not abspath.is_file():
            # Fail closed. lefthook's {staged_files} never lists deletions
            # (ACMR filter), so a staged memory deletion cannot land here.
            raise ConfigError(f"path is missing or a dangling symlink: {raw}")
        # Lexical path = git entry; resolved target = what read_text opens.
        if not abspath.resolve().is_relative_to(repo_root):
            raise ConfigError(f"symlink target is outside the repository: {raw}")
        candidates.append((relpath, abspath))
    return candidates


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Flag newly added Serena memories that read as normative or procedural."
    )
    parser.add_argument("paths", nargs="*", help="Memory files to check (lefthook {staged_files}).")
    parser.add_argument("--path", type=Path, default=None, help="Directory to walk for .md files.")
    parser.add_argument("--base", default="HEAD", help="Git ref that decides new vs existing.")
    parser.add_argument("--ci", action="store_true", help="Exit 1 when a NEW file is normative.")
    parser.add_argument("--json", action="store_true", help="Emit a JSON report instead of text.")
    parser.add_argument(
        "--staged", action="store_true", help="Read each file from the git index, not the tree."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)

    root = repo_root()
    if root is None:
        print("error: not a git repository (or git is unavailable)", file=sys.stderr)
        return 2

    try:
        index = index_paths(root) if args.staged else None
        candidates = _resolve_candidates(args, root, index)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    base_tree = base_tree_paths(root, args.base)
    if base_tree is None:
        print(f"error: could not read base ref {args.base!r} with git ls-tree", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    try:
        for relpath, abspath in candidates:
            text = read_candidate(root, relpath, abspath, index)
            finding = evaluate_file(relpath, text, relpath not in base_tree)
            if finding is not None:
                findings.append(finding)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(_report_dict(len(candidates), findings), indent=2))
    else:
        for finding in findings:
            print(format_finding_line(finding))
        print(format_summary(len(candidates), findings))

    return 1 if (args.ci and _tally(findings)[1]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
