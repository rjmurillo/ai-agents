"""Pure model for the adr-review catch-rate falsification harness (issue #5248).

ADR-101 names a measured per-role catch rate for the six-role adr-review panel
as the only thing that can reopen its Phase 2. This module holds everything
that needs no model call and no network: corpus loading, text materialization
from git, prompt assembly from the repository's own Phase 1 prompts, review
parsing, deterministic scoring, and the report shapes. The CLI
(`eval_adr_review_catch_rate.py`) owns the model seam.

Detection is deterministic. A corpus entry carries a `match` rule: a list of
groups, each group a list of lowercase substrings. A review finding catches the
defect when every group has at least one substring present in that one finding.
No model judges another model's output, so a rate cannot be inflated by a judge
that agrees with the reviewer.

Two strengths are reported. `flagged` means a finding in any review section
matches. `blocked` means the matching finding is a P0 or P1 Blocking Concern or
a REFUTED claim, the strength that stops a real review.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROLES = (
    "architect",
    "critic",
    "independent-thinker",
    "security",
    "analyst",
    "high-level-advisor",
)
ARM_UNASSISTED = "unassisted"
ARM_ASSISTED = "assisted"
ARM_CONTROL = "control"
ARMS = (ARM_UNASSISTED, ARM_ASSISTED, ARM_CONTROL)

ENTRY_FIELDS = (
    "id",
    "fix_commit",
    "base_commit",
    "doc_path",
    "anchor",
    "kind",
    "defect",
    "match",
    "topic",
)
BLOCKING_PRIORITIES = ("P0", "P1")
_SECTION_FLAGGED = ("weaknesses/gaps", "scope concerns", "questions")

GitShow = Callable[[str, str], "str | None"]


class CorpusError(ValueError):
    """The corpus is malformed, or an entry cannot be materialized."""


@dataclass(frozen=True)
class Evidence:
    """A bounded repository excerpt a verifying reviewer would read."""

    path: str
    find: str
    lines: int


@dataclass(frozen=True)
class MatchRule:
    """Every group needs one of its substrings inside a single finding."""

    all_of: tuple[tuple[str, ...], ...]

    def matches(self, finding: str) -> bool:
        text = finding.lower()
        return all(any(alt in text for alt in group) for group in self.all_of)


@dataclass(frozen=True)
class Entry:
    """One seeded defect: the text as it stood before the fix, and how to detect it."""

    id: str
    fix_commit: str
    base_commit: str
    doc_path: str
    anchor: str
    kind: str
    defect: str
    match: MatchRule
    topic: tuple[str, ...]
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class Corpus:
    selection: dict[str, Any]
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class Materialized:
    """The reviewable text for one entry, per arm."""

    entry: Entry
    base_text: str
    fixed_text: str
    evidence_text: str


@dataclass
class Review:
    """Findings pulled from one role's markdown review."""

    flagged: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


def _parse_match(raw: dict[str, Any] | None, entry_id: str) -> MatchRule:
    groups = raw.get("all_of") if isinstance(raw, dict) else None
    if not isinstance(groups, list) or not groups:
        raise CorpusError(f"{entry_id}: match.all_of must be a non-empty list of groups")
    parsed: list[tuple[str, ...]] = []
    for group in groups:
        if not isinstance(group, list) or not group:
            raise CorpusError(f"{entry_id}: every match group needs at least one substring")
        alts = tuple(str(alt).lower() for alt in group)
        if any(not alt for alt in alts):
            raise CorpusError(f"{entry_id}: an empty substring matches every finding")
        parsed.append(alts)
    return MatchRule(tuple(parsed))


def _parse_evidence(raw: list[dict[str, Any]] | None, entry_id: str) -> tuple[Evidence, ...]:
    items: list[Evidence] = []
    for item in raw or []:
        try:
            items.append(Evidence(str(item["path"]), str(item["find"]), int(item["lines"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise CorpusError(f"{entry_id}: evidence needs path, find, lines") from exc
        if items[-1].lines < 1:
            raise CorpusError(f"{entry_id}: evidence lines must be at least 1")
    return tuple(items)


def _parse_topic(raw: list[str] | None, entry_id: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw or any(not str(t) for t in raw):
        raise CorpusError(f"{entry_id}: topic needs a non-empty list of non-empty substrings")
    return tuple(str(t).lower() for t in raw)


def parse_entry(raw: dict[str, Any]) -> Entry:
    entry_id = str(raw.get("id", "<missing id>"))
    for name in ENTRY_FIELDS:
        if name not in raw:
            raise CorpusError(f"{entry_id}: missing field {name!r}")
    return Entry(
        id=entry_id,
        fix_commit=str(raw["fix_commit"]),
        base_commit=str(raw["base_commit"]),
        doc_path=str(raw["doc_path"]),
        anchor=str(raw["anchor"]),
        kind=str(raw["kind"]),
        defect=str(raw["defect"]),
        match=_parse_match(raw["match"], entry_id),
        topic=_parse_topic(raw["topic"], entry_id),
        evidence=_parse_evidence(raw.get("evidence"), entry_id),
    )


def parse_corpus(payload: dict[str, Any]) -> Corpus:
    if payload.get("schema_version") != 1:
        raise CorpusError("corpus schema_version must be 1")
    selection = payload.get("selection")
    if not isinstance(selection, dict) or not selection.get("rule"):
        raise CorpusError("corpus needs a selection block with a stated rule")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise CorpusError("corpus needs at least one entry")
    entries = tuple(parse_entry(raw) for raw in raw_entries)
    ids = [e.id for e in entries]
    if len(set(ids)) != len(ids):
        raise CorpusError("corpus entry ids must be unique")
    return Corpus(selection=selection, entries=entries)


def load_corpus(path: Path) -> Corpus:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusError(f"cannot read corpus {path}: {exc}") from exc
    return parse_corpus(payload)


# ---------------------------------------------------------------------------
# Materialization: pre-fix text, post-fix text, evidence excerpts
# ---------------------------------------------------------------------------


def extract_evidence(text: str, find: str, lines: int) -> str | None:
    """Return `lines` lines starting at the first line containing `find`."""
    rows = text.splitlines()
    for index, row in enumerate(rows):
        if find in row:
            return "\n".join(rows[index : index + lines])
    return None


def _require_text(show: GitShow, commit: str, path: str, entry_id: str) -> str:
    text = show(commit, path)
    if text is None:
        raise CorpusError(
            f"{entry_id}: {path} not readable at {commit[:12]}; "
            "fetch the pull request ref named in corpus.selection.fetch_hint"
        )
    return text


def _evidence_block(entry: Entry, show: GitShow) -> str:
    parts: list[str] = []
    for item in entry.evidence:
        text = _require_text(show, entry.base_commit, item.path, entry.id)
        excerpt = extract_evidence(text, item.find, item.lines)
        if excerpt is None:
            raise CorpusError(f"{entry.id}: evidence {item.find!r} not found in {item.path}")
        parts.append(f"### {item.path} (excerpt)\n\n```\n{excerpt}\n```")
    return "\n\n".join(parts)


def materialize(entry: Entry, show: GitShow) -> Materialized:
    base = _require_text(show, entry.base_commit, entry.doc_path, entry.id)
    if entry.anchor not in base:
        raise CorpusError(f"{entry.id}: anchor not found in the pre-fix text")
    fixed = _require_text(show, entry.fix_commit, entry.doc_path, entry.id)
    return Materialized(entry, base, fixed, _evidence_block(entry, show))


# ---------------------------------------------------------------------------
# Prompt assembly from the repository's own Phase 1 prompts
# ---------------------------------------------------------------------------

_ROLE_HEADINGS = {
    "architect": "Architect",
    "critic": "Critic",
    "independent-thinker": "Independent-Thinker",
    "security": "Security",
    "analyst": "Analyst",
    "high-level-advisor": "High-Level-Advisor",
}
_PASTE_MARKER = "Paste the Factual Claim Verification Block here."
_HARNESS_NOTE = (
    "Harness constraint: you have no shell, repository, or network access in this "
    "review. Where a claim needs one, record it as UNVERIFIED and ask the question. "
)


def parse_claim_block(prompts_md: str) -> str:
    heading = prompts_md.index("## Factual Claim Verification Block")
    start = prompts_md.index("```markdown\n", heading) + len("```markdown\n")
    return prompts_md[start : prompts_md.index("\n```\n", start)].strip()


def parse_phase1_prompts(prompts_md: str) -> dict[str, str]:
    """Return the Phase 1 prompt body per role, with `{adr_content}` left in place."""
    phase1 = prompts_md.index("## Phase 1: Independent Review Prompts")
    out: dict[str, str] = {}
    for role, heading in _ROLE_HEADINGS.items():
        at = prompts_md.index(f"\n### {heading}\n", phase1)
        opener = prompts_md.index('prompt="""\n', at) + len('prompt="""\n')
        out[role] = prompts_md[opener : prompts_md.index('\n""")', opener)]
    return out


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    return text if end < 0 else text[end + 5 :].lstrip("\n")


def build_user_prompt(template: str, claim_block: str, adr_text: str, evidence: str) -> str:
    """Fill one role's Phase 1 prompt. `evidence` is empty for the unassisted arm."""
    if "{adr_content}" not in template or _PASTE_MARKER not in template:
        raise CorpusError("Phase 1 prompt lost its {adr_content} or claim-block marker")
    note = _HARNESS_NOTE
    if evidence:
        note = (
            "Harness note: read-only extracts from the repository at the reviewed "
            "revision follow the ADR. You have no other repository access. "
        )
    body = template.replace(_PASTE_MARKER, note + "\n\n" + claim_block, 1)
    body = body.replace("{adr_content}", adr_text, 1)
    if evidence:
        body += "\n\n## Repository evidence (reviewed revision)\n\n" + evidence
    return body


# ---------------------------------------------------------------------------
# Review parsing and scoring
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^#{2,4}\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")


def _split_sections(raw: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in raw.splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = heading.group(1).strip().lower()
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return sections


def _table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or set(stripped) <= set("|-: "):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _bullets(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        match = _BULLET.match(line)
        if match:
            out.append(match.group(1))
        elif line.strip() and out and line.startswith((" ", "\t")):
            out[-1] += " " + line.strip()
    return out


def _blocking_rows(lines: list[str]) -> tuple[list[str], list[str]]:
    """Return (all rows, rows at P0 or P1)."""
    every: list[str] = []
    severe: list[str] = []
    for line in lines:
        cells = _table_cells(line)
        if not cells or cells[0].lower() == "issue":
            continue
        row = " ".join(cells)
        every.append(row)
        if any(cell.upper() in BLOCKING_PRIORITIES for cell in cells[1:2]):
            severe.append(row)
    return every, severe


def _refuted_rows(lines: list[str]) -> list[str]:
    """Claims Checked rows marked REFUTED.

    UNVERIFIED rows are not findings: a review with no repository access marks
    nearly every claim UNVERIFIED, and such a row only repeats the ADR's own
    wording beside a verdict cell.
    """
    rows: list[str] = []
    for line in lines:
        cells = _table_cells(line)
        if cells and cells[0].lower() != "claim" and "REFUTED" in cells[-1].upper():
            rows.append(" ".join(cells))
    return rows


def parse_review(raw: str) -> Review:
    sections = _split_sections(raw)
    review = Review()
    for name in _SECTION_FLAGGED:
        review.flagged.extend(_bullets(sections.get(name, [])))
    every, severe = _blocking_rows(sections.get("blocking concerns", []))
    review.flagged.extend(every)
    review.blocking.extend(severe)
    refuted = _refuted_rows(sections.get("claims checked", []))
    review.flagged.extend(refuted)
    review.blocking.extend(refuted)
    return review


@dataclass(frozen=True)
class Outcome:
    flagged: bool
    blocked: bool
    matched: str = ""
    mentioned: bool = False


def _first_match(findings: list[str], rule: MatchRule) -> str | None:
    return next((f for f in findings if rule.matches(f)), None)


def mentions_topic(raw: str, topic: tuple[str, ...]) -> bool:
    """True when the full response names the defect's subject anywhere, even without a finding."""
    text = raw.lower()
    return any(term in text for term in topic)


def score_review(review: Review, rule: MatchRule) -> Outcome:
    """Score one review. `matched` keeps the finding text so a human can audit the hit."""
    severe = _first_match(review.blocking, rule)
    if severe is not None:
        return Outcome(flagged=True, blocked=True, matched=severe[:400])
    loose = _first_match(review.flagged, rule)
    if loose is not None:
        return Outcome(flagged=True, blocked=False, matched=loose[:400])
    return Outcome(flagged=False, blocked=False)


def score_response(raw: str, rule: MatchRule, topic: tuple[str, ...]) -> Outcome:
    """Parse one response and score it for match strength and topic mention."""
    outcome = score_review(parse_review(raw), rule)
    return Outcome(outcome.flagged, outcome.blocked, outcome.matched, mentions_topic(raw, topic))
