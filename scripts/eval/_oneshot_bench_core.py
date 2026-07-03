"""Pure model and grading logic for the one-shot-vs-shipped benchmark (#2788).

The benchmark points an agent at a closed bug plus its full issue/PR discourse,
withholds the merged fix, has the agent reason a fix and set its own acceptance,
then grades the agent's fix against what shipped with an LLM judge. The closed
loop on a self-graded harness is broken because the ground truth here is a
human-merged, released fix.

This module is pure: fixture model, prompt construction, judge-response parsing,
and aggregation. All API I/O lives in `eval-oneshot-vs-shipped.py` behind a
single transport seam so the grading logic is unit-testable with no network.

Judge contract (FULL/PARTIAL/NONE) is modeled on the released-pair calibration
named in #2788: the judge scored 5/5 FULL on released pairs, and Sample 1
(Moq1208 #1091) graded PARTIAL: matched root cause, missed a valid-suppression
edge. The judge reports which discourse-named edges the agent's fix caught so a
PARTIAL is actionable for prompt tuning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Grades the judge may return, best to worst. NONE means the agent fix does not
# address the bug; PARTIAL means right direction with a named gap; FULL means
# same-or-better than shipped on every edge the discourse names.
GRADES = ("FULL", "PARTIAL", "NONE")

REQUIRED_FIXTURE_FIELDS = (
    "id",
    "source_repo",
    "issue_number",
    "title",
    "discourse",
    "shipped_fix",
)


class FixtureError(ValueError):
    """A fixture file is missing a required field or has a malformed value."""


@dataclass(frozen=True)
class Fixture:
    """One closed bug: the discourse the agent sees, the fix it must not see.

    `edges_named_in_discourse` are the specific edge cases the human discussion
    called out (e.g. "a valid suppression should not be flagged"). The judge
    checks each against the agent's proposed fix; missing one is the difference
    between FULL and PARTIAL.
    """

    id: str
    source_repo: str
    issue_number: int
    title: str
    discourse: str
    shipped_fix: str
    edges_named_in_discourse: tuple[str, ...] = ()
    difficulty: int = 3

    @staticmethod
    def from_dict(payload: dict[str, Any], *, source: str = "<dict>") -> Fixture:
        missing = [f for f in REQUIRED_FIXTURE_FIELDS if payload.get(f) in (None, "")]
        if missing:
            raise FixtureError(
                f"{source}: missing required field(s): {', '.join(missing)}"
            )
        try:
            issue_number = int(payload["issue_number"])
            raw_difficulty = payload.get("difficulty")
            difficulty = 3 if raw_difficulty is None else int(raw_difficulty)
        except (TypeError, ValueError) as exc:
            raise FixtureError(
                f"{source}: issue_number and difficulty must be integers"
            ) from exc
        if not 1 <= difficulty <= 5:
            raise FixtureError(
                f"{source}: difficulty must be in 1..5, got {difficulty}"
            )
        edges_raw = payload.get("edges_named_in_discourse")
        if edges_raw is None:
            edges_raw = []
        if not isinstance(edges_raw, list):
            raise FixtureError(
                f"{source}: edges_named_in_discourse must be a list"
            )
        return Fixture(
            id=str(payload["id"]),
            source_repo=str(payload["source_repo"]),
            issue_number=issue_number,
            title=str(payload["title"]),
            discourse=str(payload["discourse"]),
            shipped_fix=str(payload["shipped_fix"]),
            edges_named_in_discourse=tuple(str(e) for e in edges_raw),
            difficulty=difficulty,
        )


def load_fixture(path: Path) -> Fixture:
    """Read and validate one fixture JSON file. Raises FixtureError on any defect."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureError(f"{path}: not valid JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise FixtureError(f"{path}: top-level JSON must be an object")
    return Fixture.from_dict(payload, source=str(path))


def load_fixtures(fixtures_dir: Path) -> list[Fixture]:
    """Load every `*.json` fixture under a directory, sorted by id.

    Raises FixtureError on the first malformed file so a bad corpus fails fast
    rather than silently grading a subset.
    """
    fixtures = [load_fixture(p) for p in sorted(fixtures_dir.glob("*.json"))]
    return sorted(fixtures, key=lambda f: f.id)


def select_hardest(fixtures: list[Fixture], n: int | None) -> list[Fixture]:
    """Return the `n` hardest fixtures (highest difficulty, id as tiebreak).

    `n` of None or <= 0 returns all fixtures, still hardest-first, so the report
    order is stable regardless of whether a cap was passed.
    """
    ordered = sorted(fixtures, key=lambda f: (-f.difficulty, f.id))
    if n is None or n <= 0:
        return ordered
    return ordered[:n]


def build_agent_prompt(fixture: Fixture) -> str:
    """The prompt the agent sees: bug + discourse, fix withheld, self-acceptance."""
    return (
        "You are resolving a closed bug from "
        f"{fixture.source_repo} (issue #{fixture.issue_number}).\n"
        "The merged fix is withheld. Using only the issue and its discussion "
        "below, do three things:\n"
        "1. State the root cause.\n"
        "2. Propose a concrete fix (describe the code change; a diff is ideal).\n"
        "3. List the acceptance criteria you would require, including the edge "
        "cases your fix must handle.\n\n"
        f"## Title\n{fixture.title}\n\n"
        f"## Issue and discussion\n{fixture.discourse}\n"
    )


def build_judge_prompt(fixture: Fixture, agent_fix: str) -> str:
    """The judge prompt: compare the agent's fix to the shipped fix.

    The judge sees the discourse, the shipped fix (ground truth), the agent's
    proposal, and the discourse-named edges. It returns strict JSON so the
    parser never has to guess.
    """
    edges = (
        "\n".join(f"- {e}" for e in fixture.edges_named_in_discourse)
        or "- (none explicitly named)"
    )
    return (
        "You are grading whether a proposed bug fix is as good as the fix that "
        "actually shipped. Be strict and concrete.\n\n"
        f"## Issue and discussion\n{fixture.discourse}\n\n"
        f"## Shipped fix (ground truth)\n{fixture.shipped_fix}\n\n"
        f"## Edge cases the discussion named\n{edges}\n\n"
        f"## Proposed fix to grade\n{agent_fix}\n\n"
        "Grade the proposed fix against the shipped fix:\n"
        "- FULL: same root cause and handles every named edge as well as or "
        "better than shipped.\n"
        "- PARTIAL: right root cause but misses at least one named edge or "
        "detail.\n"
        "- NONE: wrong root cause or no usable fix.\n\n"
        'Respond with ONLY a JSON object: {"grade": "FULL|PARTIAL|NONE", '
        '"edges_caught": ["<edge text the fix handles>"], '
        '"edges_missed": ["<edge text the fix omits>"], '
        '"reasoning": "<two sentences>"}'
    )


@dataclass
class JudgeVerdict:
    """Parsed judge result for one fixture."""

    grade: str
    edges_caught: tuple[str, ...]
    edges_missed: tuple[str, ...]
    reasoning: str
    judge_failed: bool = False


def parse_judge_response(raw: str) -> JudgeVerdict:
    """Parse the judge's JSON. A malformed or off-grammar reply is a NONE failure.

    A judge that does not return a usable grade must not silently count as a
    pass: it is recorded as `judge_failed` with grade NONE so aggregation can
    surface the breakage rather than inflate the score.
    """
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return JudgeVerdict("NONE", (), (), f"judge returned no JSON: {text[:160]}", True)
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return JudgeVerdict("NONE", (), (), f"judge JSON parse error: {text[:160]}", True)
    if not isinstance(payload, dict):
        return JudgeVerdict("NONE", (), (), "judge JSON not an object", True)
    raw_grade = payload.get("grade")
    grade = str(raw_grade).strip().upper() if raw_grade is not None else ""
    if grade not in GRADES:
        return JudgeVerdict(
            "NONE", (), (), f"judge returned unknown grade {grade!r}", True
        )
    return JudgeVerdict(
        grade=grade,
        edges_caught=_as_str_tuple(payload.get("edges_caught")),
        edges_missed=_as_str_tuple(payload.get("edges_missed")),
        reasoning=str(payload.get("reasoning", "")),
        judge_failed=False,
    )


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


@dataclass
class FixtureResult:
    """One graded fixture: its verdict plus enough identity to log the delta."""

    fixture_id: str
    issue_number: int
    difficulty: int
    verdict: JudgeVerdict
    agent_fix: str = ""
    error: str | None = None


@dataclass
class BenchmarkSummary:
    """Aggregate over graded fixtures. The headline is the grade distribution."""

    total: int
    full: int
    partial: int
    none: int
    judge_failures: int
    api_errors: int
    edges_named: int
    edges_caught: int
    per_fixture: list[FixtureResult] = field(default_factory=list)

    @property
    def edge_catch_rate(self) -> float:
        return self.edges_caught / self.edges_named if self.edges_named else 0.0

    @property
    def same_or_better_rate(self) -> float:
        """Fraction graded FULL: agent fix at least as good as shipped."""
        return self.full / self.total if self.total else 0.0

    @property
    def verdict(self) -> str:
        if self.api_errors or self.judge_failures:
            return "INCONCLUSIVE_HARNESS_ERRORS"
        if self.total == 0:
            return "NO_FIXTURES"
        return "SCORED"


def aggregate(
    fixtures: list[Fixture], results: list[FixtureResult]
) -> BenchmarkSummary:
    """Roll graded fixtures into a summary.

    `edges_named` counts the edges the discourse named across the graded
    fixtures; `edges_caught` counts how many the judge confirmed the agent fix
    handled. The ratio is the actionable signal for prompt tuning.
    """
    by_id = {f.id: f for f in fixtures}
    counts = {grade: 0 for grade in GRADES}
    judge_failures = 0
    api_errors = 0
    edges_named = 0
    edges_caught = 0
    graded_total = 0
    for result in results:
        if result.error is not None:
            api_errors += 1
            continue
        if result.verdict.judge_failed:
            judge_failures += 1
            continue
        counts[result.verdict.grade] = counts.get(result.verdict.grade, 0) + 1
        graded_total += 1
        fixture = by_id.get(result.fixture_id)
        if fixture is not None:
            named_edges = set(fixture.edges_named_in_discourse)
            edges_named += len(named_edges)
            edges_caught += len(named_edges.intersection(result.verdict.edges_caught))
    return BenchmarkSummary(
        total=graded_total,
        full=counts["FULL"],
        partial=counts["PARTIAL"],
        none=counts["NONE"],
        judge_failures=judge_failures,
        api_errors=api_errors,
        edges_named=edges_named,
        edges_caught=edges_caught,
        per_fixture=list(results),
    )
