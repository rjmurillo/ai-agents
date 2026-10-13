"""Core of the skill collision report (issue #5763).

Loads a skill catalog, compares every unordered pair of names and descriptions under
the full text and controlled truncation profiles, and groups collisions into
clusters. `skill_collision_report.py` owns the policy, the pairs emitter, the
rendering, and the CLI.
"""

from __future__ import annotations

import itertools
import re
import subprocess
import sys
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:  # pragma: no cover
    # Script bootstrap. tests/eval/test_skill_collision_report.py runs it in a subprocess.
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.frontmatter_split import split_leading_frontmatter  # noqa: E402

PROFILE_FULL = "full"
DEFAULT_TRUNCATIONS: tuple[int, ...] = (80, 160, 320)
DEFAULT_NEAR_THRESHOLD = 0.8

HIGH = "high"
LOW = "low"

FIELD_NAME = "name"
FIELD_DESCRIPTION = "description"

KIND_EXACT = "exact"
KIND_NORMALIZED = "normalized"
KIND_TRUNCATED = "truncated-identical"
KIND_NEAR = "near"

_HIGH_KINDS = frozenset({KIND_EXACT, KIND_NORMALIZED, KIND_TRUNCATED})
_EXCERPT_CHARS = 160
_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)

_REMEDIATION = {
    KIND_EXACT: (
        "Merge the skills or rewrite one {field} so the trigger conditions differ in "
        "the first words."
    ),
    KIND_NORMALIZED: (
        "The {field} values differ only in case or punctuation. Rewrite one so the "
        "trigger conditions differ in the first words."
    ),
    KIND_TRUNCATED: (
        "A host that abbreviates descriptions to this profile cannot tell these skills "
        "apart. Move the distinguishing trigger words to the start of the {field}."
    ),
    KIND_NEAR: (
        "Owner review: compare the two {field} values and keep the trigger conditions "
        "distinct. Run eval-skill-overlap.py on this pair for a semantic verdict."
    ),
}


class ReportError(ValueError):
    """Raised for unusable input: bad root, bad baseline, bad prompts file (exit 2)."""


class GitError(RuntimeError):
    """Raised when `git diff` fails while resolving `--changed-since` (exit 3)."""


@dataclass(frozen=True, slots=True)
class SkillEntry:
    """One skill's routing text. `skill` is the directory name, the pairs-file key."""

    skill: str
    name: str
    description: str
    path: str


@dataclass(frozen=True, slots=True)
class Finding:
    """One collision between two skills for one field under one profile."""

    kind: str
    confidence: str
    field: str
    profile: str
    skills: tuple[str, str]
    paths: tuple[str, str]
    compared: tuple[str, str]
    similarity: float
    remediation: str

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (self.kind, self.field, self.profile, self.skills[0], self.skills[1])

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "field": self.field,
            "profile": self.profile,
            "skills": list(self.skills),
            "paths": list(self.paths),
            "compared": list(self.compared),
            "similarity": self.similarity,
            "remediation": self.remediation,
        }


@dataclass(frozen=True, slots=True)
class CollisionReport:
    """Result of one catalog scan."""

    root: str
    skills_scanned: int
    profiles: tuple[str, ...]
    near_threshold: float
    findings: tuple[Finding, ...]
    clusters: tuple[tuple[str, ...], ...]

    def high(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.confidence == HIGH)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "skills_scanned": self.skills_scanned,
            "profiles": list(self.profiles),
            "near_threshold": self.near_threshold,
            "findings": [f.to_dict() for f in self.findings],
            "clusters": [list(c) for c in self.clusters],
            "assumptions": assumptions(self.profiles),
        }


def assumptions(profiles: Sequence[str]) -> dict[str, Any]:
    """Name what the report does and does not claim."""
    return {
        "truncation_profiles": {
            "profiles": [p for p in profiles if p != PROFILE_FULL],
            "controlled": True,
            "basis": ("Operator-chosen character cutoffs. Not measured limits of any model host."),
        },
        "host_observed_abbreviation": {
            "status": "not_observed",
            "note": (
                "This script reads SKILL.md files only. It captures no harness behavior, "
                "so it cannot say how any host abbreviates descriptions."
            ),
        },
        "semantic_routing": {
            "measured": False,
            "model": None,
            "harness": None,
            "note": "Lexical comparison only. No skill-selection accuracy is claimed.",
        },
    }


def normalize(text: str) -> str:
    """NFKC, casefold, collapse every non-word run to one space."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return _NON_WORD.sub(" ", folded).strip()


def jaccard(left: str, right: str) -> float:
    """Token-set Jaccard similarity of two normalized strings. Empty vs empty is 0.0."""
    a, b = set(left.split()), set(right.split())
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def truncation_profile(chars: int) -> str:
    return f"chars:{chars}"


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    block, _ = split_leading_frontmatter(text)
    if not block:
        return None
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _string_field(frontmatter: dict[str, Any], key: str) -> str:
    value = frontmatter.get(key)
    return value if isinstance(value, str) else ""


def load_entry(skill_md: Path) -> SkillEntry | None:
    """Read one SKILL.md. None when unreadable or without a usable description."""
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    frontmatter = _parse_frontmatter(text)
    if frontmatter is None:
        return None
    description = _string_field(frontmatter, "description")
    if not description:
        return None
    directory = skill_md.parent.name
    name = _string_field(frontmatter, "name") or directory
    return SkillEntry(
        skill=directory,
        name=name,
        description=description,
        path=skill_md.as_posix(),
    )


def load_catalog(root: Path) -> list[SkillEntry]:
    """Load every `<root>/*/SKILL.md`, sorted by directory name.

    Raises:
        ReportError: when root is not a directory or holds no usable skill.
    """
    if not root.is_dir():
        raise ReportError(f"Skills root not found: {root}")
    entries = [e for e in map(load_entry, sorted(root.glob("*/SKILL.md"))) if e is not None]
    if not entries:
        raise ReportError(f"No skill with a description found under {root}")
    return entries


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= _EXCERPT_CHARS:
        return flat
    return flat[:_EXCERPT_CHARS] + "..."


def _make_finding(
    kind: str,
    field: str,
    profile: str,
    pair: tuple[SkillEntry, SkillEntry],
    texts: tuple[str, str],
    similarity: float,
) -> Finding:
    first, second = pair
    return Finding(
        kind=kind,
        confidence=HIGH if kind in _HIGH_KINDS else LOW,
        field=field,
        profile=profile,
        skills=(first.skill, second.skill),
        paths=(first.path, second.path),
        compared=(_excerpt(texts[0]), _excerpt(texts[1])),
        similarity=round(similarity, 4),
        remediation=_REMEDIATION[kind].format(field=field),
    )


def _classify_full(
    raw: tuple[str, str], norm: tuple[str, str], threshold: float
) -> tuple[str, float] | None:
    if raw[0] == raw[1]:
        return KIND_EXACT, 1.0
    if norm[0] == norm[1]:
        return KIND_NORMALIZED, 1.0
    similarity = jaccard(norm[0], norm[1])
    if similarity >= threshold:
        return KIND_NEAR, similarity
    return None


def _classify_truncated(
    raw: tuple[str, str], norm: tuple[str, str], threshold: float
) -> tuple[str, float] | None:
    if norm[0] and norm[0] == norm[1]:
        return KIND_TRUNCATED, 1.0
    similarity = jaccard(norm[0], norm[1])
    if similarity >= threshold:
        return KIND_NEAR, similarity
    return None


def _field_text(entry: SkillEntry, field: str) -> str:
    return entry.name if field == FIELD_NAME else entry.description


def _scan_field(
    pairs: Iterable[tuple[SkillEntry, SkillEntry]],
    field: str,
    chars: int | None,
    threshold: float,
    full_hits: set[tuple[str, str, str]],
) -> list[Finding]:
    """Scan every pair for one field and profile. `chars` None means the full text."""
    profile = PROFILE_FULL if chars is None else truncation_profile(chars)
    findings: list[Finding] = []
    for first, second in pairs:
        pair_id = (field, first.skill, second.skill)
        if chars is not None and pair_id in full_hits:
            continue
        raw = (_field_text(first, field), _field_text(second, field))
        if chars is not None:
            raw = (raw[0][:chars], raw[1][:chars])
        norm = (normalize(raw[0]), normalize(raw[1]))
        classify = _classify_full if chars is None else _classify_truncated
        verdict = classify(raw, norm, threshold)
        if verdict is None:
            continue
        findings.append(_make_finding(verdict[0], field, profile, (first, second), raw, verdict[1]))
        if chars is None:
            full_hits.add(pair_id)
    return findings


def _sort_key(finding: Finding) -> tuple[Any, ...]:
    return (
        0 if finding.confidence == HIGH else 1,
        finding.field,
        finding.profile,
        finding.kind,
        finding.skills,
    )


def find_collisions(
    entries: Sequence[SkillEntry],
    *,
    truncations: Sequence[int] = DEFAULT_TRUNCATIONS,
    near_threshold: float = DEFAULT_NEAR_THRESHOLD,
) -> list[Finding]:
    """Compare every unordered pair. Stable order: high first, then field, profile, kind, names."""
    ordered = sorted(entries, key=lambda e: e.skill)
    pairs = list(itertools.combinations(ordered, 2))
    full_hits: set[tuple[str, str, str]] = set()
    findings: list[Finding] = []
    for field in (FIELD_NAME, FIELD_DESCRIPTION):
        findings += _scan_field(pairs, field, None, near_threshold, full_hits)
    for chars in sorted(set(truncations)):
        findings += _scan_field(pairs, FIELD_DESCRIPTION, chars, near_threshold, full_hits)
    return sorted(findings, key=_sort_key)


def build_clusters(findings: Iterable[Finding]) -> tuple[tuple[str, ...], ...]:
    """Connected components of colliding skills. Each cluster is sorted, size >= 2."""
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for finding in findings:
        left, right = find(finding.skills[0]), find(finding.skills[1])
        if left != right:
            parent[max(left, right)] = min(left, right)
    groups: dict[str, list[str]] = {}
    for item in list(parent):
        groups.setdefault(find(item), []).append(item)
    return tuple(sorted(tuple(sorted(members)) for members in groups.values()))


def filter_findings(findings: Iterable[Finding], only: Iterable[str]) -> list[Finding]:
    """Keep findings that involve at least one selected skill. Empty selection keeps all."""
    selected = set(only)
    if not selected:
        return list(findings)
    return [f for f in findings if selected.intersection(f.skills)]


def changed_skills(root: Path, ref: str) -> list[str]:
    """Skill directories under root with a file changed since `ref`.

    Raises:
        ReportError: when ref starts with "-", which git would read as an option.
        GitError: when git cannot diff against ref.
    """
    if ref.startswith("-"):
        raise ReportError(f"--changed-since ref must not start with '-': {ref!r}")
    command = ["git", "diff", "--name-only", ref, "--", root.as_posix()]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise GitError(f"git unavailable: {exc}") from exc
    if result.returncode != 0:
        raise GitError(f"git diff against {ref!r} failed: {result.stderr.strip()}")
    skills: set[str] = set()
    for line in result.stdout.splitlines():
        relative = Path(line).relative_to(root) if Path(line).is_relative_to(root) else None
        if relative is not None and len(relative.parts) > 1:
            skills.add(relative.parts[0])
    return sorted(skills)


def build_report(
    root: Path,
    *,
    truncations: Sequence[int] = DEFAULT_TRUNCATIONS,
    near_threshold: float = DEFAULT_NEAR_THRESHOLD,
    only: Iterable[str] = (),
) -> CollisionReport:
    """Scan root and assemble a report, optionally restricted to selected skills."""
    entries = load_catalog(root)
    findings = filter_findings(
        find_collisions(entries, truncations=truncations, near_threshold=near_threshold),
        only,
    )
    profiles = (PROFILE_FULL, *(truncation_profile(n) for n in sorted(set(truncations))))
    return CollisionReport(
        root=root.as_posix(),
        skills_scanned=len(entries),
        profiles=profiles,
        near_threshold=near_threshold,
        findings=tuple(findings),
        clusters=build_clusters(findings),
    )
