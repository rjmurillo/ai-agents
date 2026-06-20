#!/usr/bin/env python3
"""Pairwise Skill Overlap Analysis: detect redundancy between two skills.

`eval-knowledge-integration.py` answers "does skill A earn its tokens versus
the baseline LLM". It cannot answer "are skills A and B redundant with each
other". This script fills that gap for the `.claude/skills/` catalog prune.

For each pair (A, B) and each prompt, three conditions run:
  - baseline:  prompt only.
  - skill_A:   prompt + skill A context (SKILL.md + references/).
  - skill_B:   prompt + skill B context.

Each response is scored against the prompt's expected answer on a 1-5 scale by
an LLM judge. A pair verdict is computed from the per-direction deltas:
  - DISTINCT: each skill helps mainly on its own native prompts.
  - OVERLAP:  both skills help symmetrically on both prompt sets.
  - SUBSUMED: one skill helps on both prompt sets while the other does not.

Phase 1 (Issue #1932): explicit pair list only via `--pairs cluster.json`.
No cluster shortcuts, no full catalog sweep. The O(N^2) cost is
N*(N-1)/2 unordered pairs * prompts per pair * 6 calls per prompt. At 70
skills and 5 prompts per skill, that is about 145k API calls, so unbounded
mode is deliberately out of scope and gated.

Usage:
    python3 scripts/eval/eval-skill-overlap.py --pairs cluster.json --dry-run
    python3 scripts/eval/eval-skill-overlap.py --pairs cluster.json

cluster.json shape:
    {
      "pairs": [["memory-enhancement", "curating-memories"]],
      "prompts": {
        "memory-enhancement": [
          {"prompt": "...", "expected": "...", "owner": "memory-enhancement"}
        ],
        "curating-memories": [
          {"prompt": "...", "expected": "...", "owner": "curating-memories"}
        ]
      }
    }

Exit codes (ADR-035):
    0  success (analysis completed; verdicts written)
    1  logic error (pair references a non-existent skill directory)
    2  config error (malformed pairs file, missing prompts, bad CLI usage)
    3  external error (Anthropic API failure during a live run)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TextIO

# ---------------------------------------------------------------------------
# API utilities (shared module). Imported lazily-friendly at module top per the
# sibling eval scripts; the call boundary is the only network surface and is
# the sole thing tests mock.
# ---------------------------------------------------------------------------
from _anthropic_api import call_api as _call_api
from _anthropic_api import load_api_key as _load_api_key
from _eval_common import (
    EST_TOKENS_PER_CALL,
    MODEL_PRICING_RATES_USD_PER_1K_TOKENS,
    PRICING_RATE_AS_OF,
)

# ---------------------------------------------------------------------------
# Exit codes (ADR-035-exit-code-standardization.md). Named so call sites read
# as intent, not magic numbers.
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

# ---------------------------------------------------------------------------
# Repo layout. This script lives at scripts/eval/, so the repo root is two
# parents up. Skills live under .claude/skills/.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"

# Aligned with scripts/eval/eval-agent-vs-baseline.py DEFAULT_MODEL and the
# canonical pricing table in scripts/eval/_eval_common.py
# (MODEL_PRICING_RATES_USD_PER_1K_TOKENS).
DEFAULT_MODEL = "claude-sonnet-4-6"
RATE_LIMIT_SLEEP_SEC = 1.0  # fixed inter-call delay; matches eval-knowledge-integration.py
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# Verdict thresholds. A delta is "meaningful help" when a skill's enhanced score
# beats baseline by at least DELTA_HELP_THRESHOLD on the relevant prompt set.
DELTA_HELP_THRESHOLD = 0.5

OverlapVerdict = Literal["DISTINCT", "OVERLAP", "SUBSUMED"]


# ---------------------------------------------------------------------------
# Cost telemetry (pure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """Projected API cost for a run. Computed before any call is made."""

    api_calls: int
    est_tokens: int
    usd_estimate: float

    def render(self) -> str:
        return (
            f"Cost estimate: {self.api_calls} API calls, "
            f"~{self.est_tokens:,} tokens, ~${self.usd_estimate:.2f} USD "
            f"(pricing as of {PRICING_RATE_AS_OF})"
        )


class PricingError(ValueError):
    """Raised when a model has no central eval pricing entry."""


def estimate_cost(
    pairs: list[tuple[str, str]],
    prompts: dict[str, list[dict[str, Any]]],
    *,
    model: str = DEFAULT_MODEL,
    calls_per_prompt: int = 6,
) -> CostEstimate:
    """Estimate API cost for the run.

    Per pair, each prompt set (A's prompts and B's prompts) runs 3 conditions
    (baseline, skill_A, skill_B), and each condition response is scored by the
    judge. That is 3 generation + 3 judge = 6 calls per prompt across both
    prompt sets combined per prompt, defaulting calls_per_prompt=6.
    """
    total_prompts = 0
    for skill_a, skill_b in pairs:
        total_prompts += len(prompts.get(skill_a, []))
        total_prompts += len(prompts.get(skill_b, []))
    api_calls = total_prompts * calls_per_prompt
    est_tokens = api_calls * EST_TOKENS_PER_CALL
    usd = est_tokens / 1000.0 * _blended_rate_for_model(model)
    return CostEstimate(api_calls=api_calls, est_tokens=est_tokens, usd_estimate=round(usd, 4))


def _blended_rate_for_model(model: str) -> float:
    rates = MODEL_PRICING_RATES_USD_PER_1K_TOKENS.get(model)
    if rates is None:
        raise PricingError(
            f"No pricing rate for model_id={model!r}. "
            "Add it to MODEL_PRICING_RATES_USD_PER_1K_TOKENS in _eval_common.py."
        )
    return (rates["input"] + rates["output"]) / 2.0


# ---------------------------------------------------------------------------
# Verdict classification (pure; the unit under test)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DirectionScores:
    """Averaged scores for one prompt set (one skill's native prompts).

    For prompt set owned by skill X:
      - baseline: average score with no skill context.
      - own:      average score with the OWNING skill's context (X helping X).
      - other:    average score with the OTHER skill's context (Y helping X).
    """

    baseline: float
    own: float
    other: float

    @property
    def own_delta(self) -> float:
        return round(self.own - self.baseline, 4)

    @property
    def other_delta(self) -> float:
        return round(self.other - self.baseline, 4)


def classify_overlap(
    a_on_a: DirectionScores,
    b_on_b: DirectionScores,
    *,
    threshold: float = DELTA_HELP_THRESHOLD,
) -> OverlapVerdict:
    """Classify the overlap between skills A and B from cross-prompt deltas.

    Args:
        a_on_a: scores on A's native prompts (own = A's context, other = B's).
        b_on_b: scores on B's native prompts (own = B's context, other = A's).
        threshold: minimum delta over baseline to count as "meaningful help".

    Rules (asymmetry-based, per Issue #1932):
        - B helps on A's prompts within `threshold` of A's own help, AND
          A helps on B's prompts within `threshold` of B's own help
              => OVERLAP (symmetric mutual coverage).
        - exactly one direction shows the other skill covering the owner's
          prompts as well as the owner does
              => SUBSUMED (the covering skill subsumes the covered one).
        - otherwise (each skill wins on its own prompts)
              => DISTINCT.

    "Covers as well as the owner" means the other skill's delta is within
    `threshold` of the owning skill's delta on that prompt set, and the other
    skill itself provides meaningful help (other_delta >= threshold).
    """
    b_covers_a = _covers(a_on_a, threshold)
    a_covers_b = _covers(b_on_b, threshold)

    if b_covers_a and a_covers_b:
        return "OVERLAP"
    if b_covers_a or a_covers_b:
        return "SUBSUMED"
    return "DISTINCT"


def _covers(scores: DirectionScores, threshold: float) -> bool:
    """True when the OTHER skill covers this prompt set about as well as the owner.

    The other skill must (1) provide meaningful help over baseline and (2) land
    within `threshold` of the owning skill's help. Condition (2) holds whenever
    the other skill is not more than `threshold` below the owner, including when
    the other skill is BETTER than the owner.
    """
    if scores.other_delta < threshold:
        return False
    return scores.own_delta - scores.other_delta <= threshold


def recommend_action(verdict: OverlapVerdict, skill_a: str, skill_b: str) -> str:
    """Map a verdict to a human-facing recommendation. Table-driven."""
    actions: dict[OverlapVerdict, str] = {
        "DISTINCT": f"Keep both. {skill_a} and {skill_b} cover different prompts.",
        "OVERLAP": (
            f"Fold candidate. {skill_a} and {skill_b} cover each other's prompts; "
            "consider merging into one skill."
        ),
        "SUBSUMED": (
            f"Prune candidate. One of {skill_a}/{skill_b} covers the other's prompts "
            "without reciprocity; the covered skill is a deletion candidate."
        ),
    }
    return actions[verdict]


# ---------------------------------------------------------------------------
# Retirement-claim guard (Issue #2676)
#
# The pair verdict is the only signal that authorizes a skill-RETIREMENT
# (prune/fold) claim in a generated follow-up issue. DISTINCT means "keep
# both" and MUST NOT produce a retire/fold claim. A prior generator emitted a
# SUBSUMED retirement claim for a pair the cited report scored DISTINCT
# (bogus #2663 / PR #2671). Before any generator emits a retirement claim for a
# pair, it MUST validate the claimed verdict word against the machine-readable
# report (matrix.json) it cites. On mismatch the claim is dropped.
# ---------------------------------------------------------------------------

# A cited machine-readable report, as the parsed matrix.json payload or a
# path to the matrix.json file or its report directory.
ReportRef = dict[str, Any] | str | Path


class ReportVerdictError(ValueError):
    """Raised when the cited machine-readable report cannot back a verdict claim.

    Covers a malformed report, an unreadable report file, and a pair the report
    never scored. Each case makes a retirement claim untrustworthy.
    """


def _coerce_report_payload(report: ReportRef) -> dict[str, Any]:
    """Return the matrix.json payload as a dict from a dict, path, or directory.

    The cited report may be passed as the already-parsed payload (a dict shaped
    like build_matrix's output), a path to a matrix.json file, or a path to the
    report directory that contains matrix.json. File access is the integration
    point: an unreadable or non-JSON report raises ReportVerdictError rather
    than letting a transport-shaped error leak into the verdict guard.
    """
    if isinstance(report, dict):
        return report
    if isinstance(report, (str, Path)):
        path = Path(report).expanduser().resolve()
        repo_root = REPO_ROOT.resolve()
        if not path.is_relative_to(repo_root):
            raise ReportVerdictError(f"Cited report path is outside repo root: {path}")
        if path.is_dir():
            path = path / "matrix.json"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ReportVerdictError(f"Cannot read cited report at {path}: {exc}") from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReportVerdictError(f"Cited report at {path} is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ReportVerdictError(f"Cited report at {path} is not a JSON object.")
        return payload
    raise ReportVerdictError(
        f"Unsupported report reference type {type(report).__name__!r}; "
        "pass a matrix.json payload dict or a path to it."
    )


# Verdicts that authorize a skill-retirement (prune/fold) recommendation.
# DISTINCT is deliberately absent: it means "keep both".
RETIREMENT_VERDICTS: frozenset[str] = frozenset({"SUBSUMED", "OVERLAP"})


def is_retirement_verdict(verdict: str) -> bool:
    """True when the verdict authorizes a prune/fold retirement claim."""
    return verdict in RETIREMENT_VERDICTS


def load_report_verdicts(report: ReportRef) -> dict[frozenset[str], str]:
    """Map each pair in a machine-readable report to its verdict word.

    `report` is the matrix.json payload (a dict shaped like build_matrix's
    output) or a path to that file. The key is an order-independent
    frozenset({skill_a, skill_b}) so callers cite a pair in either order.
    """
    payload = _coerce_report_payload(report)
    verdicts: dict[frozenset[str], str] = {}
    pairs = payload.get("pairs")
    if pairs is None:
        pairs = []
    if not isinstance(pairs, list):
        raise ReportVerdictError("Cited report field 'pairs' is not a list.")
    for pair in pairs:
        try:
            key = frozenset({pair["skill_a"], pair["skill_b"]})
            verdicts[key] = pair["verdict"]
        except (KeyError, TypeError) as exc:
            raise ReportVerdictError(f"Malformed pair entry in report: {pair!r}") from exc
    return verdicts


def report_verdict_for_pair(report: ReportRef, skill_a: str, skill_b: str) -> str:
    """Return the report's verdict word for a pair, order-independent.

    Raises ReportVerdictError when the pair is absent from the report; a
    retirement claim for a pair the report never scored is never trustworthy.
    """
    verdicts = load_report_verdicts(report)
    key = frozenset({skill_a, skill_b})
    if key not in verdicts:
        raise ReportVerdictError(
            f"Pair ({skill_a}, {skill_b}) is absent from the cited report."
        )
    return verdicts[key]


def validate_retirement_claim(
    skill_a: str,
    skill_b: str,
    claimed_verdict: str,
    report: ReportRef,
) -> bool:
    """True only when a retirement claim for this pair is backed by the report.

    A claim is honored only when the claimed verdict word (1) is a retirement
    verdict and (2) matches the verdict the cited report records for the pair.
    A DISTINCT report verdict, or any mismatch, returns False so the caller
    drops the claim instead of emitting a bogus retirement issue.
    """
    if not is_retirement_verdict(claimed_verdict):
        return False
    try:
        report_verdict = report_verdict_for_pair(report, skill_a, skill_b)
    except ReportVerdictError:
        return False
    return report_verdict == claimed_verdict


def emit_retirement_claim(
    skill_a: str,
    skill_b: str,
    claimed_verdict: str,
    recommendation: str,
    report: ReportRef,
    *,
    stream: TextIO = sys.stderr,
) -> str | None:
    """Return the retirement claim text only if the report backs the verdict.

    This is the choke point a follow-up-issue generator MUST call before it
    emits a SUBSUMED/OVERLAP (retire/fold) claim. On mismatch (for example the
    body says SUBSUMED but the report says DISTINCT) it logs and returns None so
    the generator skips the pair rather than creating a bogus retirement issue.
    """
    if validate_retirement_claim(skill_a, skill_b, claimed_verdict, report):
        return recommendation
    try:
        actual = report_verdict_for_pair(report, skill_a, skill_b)
    except ReportVerdictError:
        actual = "MISSING"
    print(
        f"SKIP retirement claim for ({skill_a}, {skill_b}): claimed "
        f"{claimed_verdict!r} but cited report verdict is {actual!r}.",
        file=stream,
    )
    return None


# ---------------------------------------------------------------------------
# Pair-list and prompts loading (config boundary; untrusted input)
# ---------------------------------------------------------------------------


class PairsFileError(ValueError):
    """Raised when the --pairs file is structurally invalid (exit 2)."""


@dataclass(frozen=True, slots=True)
class PairsConfig:
    pairs: list[tuple[str, str]]
    prompts: dict[str, list[dict[str, Any]]]


def load_pairs_file(path: str) -> PairsConfig:
    """Parse and validate a cluster.json pair-list file.

    Raises:
        PairsFileError: on any structural problem. Callers map this to exit 2.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise PairsFileError(f"Pairs file not found: {path}")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PairsFileError(f"Pairs file {path} is not valid JSON: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise PairsFileError(f"Pairs file {path}: top level must be an object.")

    raw_pairs = data.get("pairs")
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise PairsFileError(f"Pairs file {path}: 'pairs' must be a non-empty list.")

    pairs: list[tuple[str, str]] = []
    for index, entry in enumerate(raw_pairs):
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or not all(isinstance(name, str) and name for name in entry)
        ):
            raise PairsFileError(
                f"Pairs file {path}: pair {index} must be a [skillA, skillB] list of two "
                "non-empty strings."
            )
        if entry[0] == entry[1]:
            raise PairsFileError(
                f"Pairs file {path}: pair {index} is a self-pair for '{entry[0]}'. "
                "Use two different skills."
            )
        pairs.append((entry[0], entry[1]))

    raw_prompts = data.get("prompts")
    if not isinstance(raw_prompts, dict) or not raw_prompts:
        raise PairsFileError(f"Pairs file {path}: 'prompts' must be a non-empty object.")

    prompts = _validate_prompts(path, raw_prompts)
    _require_prompts_for_pairs(path, pairs, prompts)
    return PairsConfig(pairs=pairs, prompts=prompts)


def _validate_prompts(
    path: str, raw_prompts: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    prompts: dict[str, list[dict[str, Any]]] = {}
    for skill_name, items in raw_prompts.items():
        if not isinstance(items, list) or not items:
            raise PairsFileError(
                f"Pairs file {path}: prompts for '{skill_name}' must be a non-empty list."
            )
        for item_index, entry in enumerate(items):
            if not isinstance(entry, dict):
                raise PairsFileError(
                    f"Pairs file {path}: prompts['{skill_name}'][{item_index}] must be an object."
                )
            if not isinstance(entry.get("prompt"), str) or not entry["prompt"]:
                raise PairsFileError(
                    f"Pairs file {path}: prompts['{skill_name}'][{item_index}] needs a "
                    "non-empty 'prompt'."
                )
            if not isinstance(entry.get("expected"), str) or not entry["expected"]:
                raise PairsFileError(
                    f"Pairs file {path}: prompts['{skill_name}'][{item_index}] needs a "
                    "non-empty 'expected'."
                )
        prompts[skill_name] = items
    return prompts


def _require_prompts_for_pairs(
    path: str,
    pairs: list[tuple[str, str]],
    prompts: dict[str, list[dict[str, Any]]],
) -> None:
    for skill_a, skill_b in pairs:
        for skill in (skill_a, skill_b):
            if skill not in prompts:
                raise PairsFileError(
                    f"Pairs file {path}: no prompts provided for skill '{skill}' in pair "
                    f"[{skill_a}, {skill_b}]."
                )


# ---------------------------------------------------------------------------
# Skill context loading (filesystem boundary; logic error if a skill is gone)
# ---------------------------------------------------------------------------


class MissingSkillError(ValueError):
    """Raised when a pair references a skill directory that does not exist (exit 1)."""


def require_skill_dir(skill_name: str, skills_dir: Path = SKILLS_DIR) -> Path:
    """Resolve a skill directory or raise MissingSkillError.

    CWE-22 mitigation: reject names that escape the skills root. A pair list is
    config a human wrote, but the file is still untrusted input.
    """
    if "/" in skill_name or "\\" in skill_name or skill_name in (".", ".."):
        raise MissingSkillError(
            f"Skill name '{skill_name}' is not a bare directory name under {skills_dir}."
        )
    skill_dir = (skills_dir / skill_name).resolve()
    if skills_dir.resolve() not in skill_dir.parents:
        raise MissingSkillError(
            f"Skill name '{skill_name}' resolves outside {skills_dir} (path traversal rejected)."
        )
    if not skill_dir.is_dir():
        raise MissingSkillError(
            f"Skill directory not found: '{skill_name}' under {skills_dir}. "
            "It may have been deleted in a catalog prune; update your pairs file."
        )
    return skill_dir


def _validate_pair_skill_dirs(
    pairs: list[tuple[str, str]], skills_dir: Path = SKILLS_DIR
) -> None:
    for skill_a, skill_b in pairs:
        require_skill_dir(skill_a, skills_dir)
        require_skill_dir(skill_b, skills_dir)


def load_skill_context(skill_dir: Path) -> str:
    """Load SKILL.md and all references/ files for a skill directory."""
    parts: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        parts.append(f"# SKILL.md\n\n{skill_md.read_text(encoding='utf-8')}")
    refs_dir = skill_dir / "references"
    if refs_dir.is_dir():
        for ref_file in sorted(refs_dir.iterdir()):
            if ref_file.is_file():
                parts.append(
                    f"# Reference: {ref_file.name}\n\n{ref_file.read_text(encoding='utf-8')}"
                )
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# API-driven scoring (network boundary; the only thing tests mock)
# ---------------------------------------------------------------------------

# A response generator: (prompt, system_context) -> response text.
ResponseFn = Callable[[str, str], str]
# A judge: (prompt, response, expected) -> 1-5 score.
JudgeFn = Callable[[str, str, str], float]


def make_response_fn(api_key: str, model: str) -> ResponseFn:
    """Build a response generator bound to the Anthropic API."""

    def _respond(prompt: str, system_context: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        return _call_api(api_key, messages, system=system_context, model=model)

    return _respond


def make_judge_fn(api_key: str, model: str) -> JudgeFn:
    """Build an LLM-judge scorer bound to the Anthropic API."""

    def _judge(prompt: str, response: str, expected: str) -> float:
        scoring_prompt = (
            "Score how well the response matches the expected answer on a 1-5 scale "
            "(5 = fully correct concepts present, 1 = unrelated).\n\n"
            f"**Prompt**: {prompt}\n\n"
            f"**Expected**: {expected}\n\n"
            f"**Response**: {response}\n\n"
            'Respond in JSON only: {"score": <int 1-5>}'
        )
        raw = _call_api(api_key, [{"role": "user", "content": scoring_prompt}], model=model)
        return _parse_judge_score(raw)

    return _judge


class JudgeScoreError(ValueError):
    """Raised when the LLM judge returns a malformed score payload."""


def _parse_judge_score(raw: str) -> float:
    """Extract the score from a judge response or raise on malformed payload."""
    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    parsed = _first_json_object(text)
    if parsed is None:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise JudgeScoreError(
                f"Judge score payload is not valid JSON: {text[:100]}"
            ) from exc
    if not isinstance(parsed, dict):
        raise JudgeScoreError(f"Judge score payload is not an object: {text[:100]}")
    score = parsed.get("score")
    if score is None:
        raise JudgeScoreError(f"Judge score missing or null: {text[:100]}")
    try:
        return min(max(float(score), 1.0), 5.0)
    except (TypeError, ValueError) as exc:
        raise JudgeScoreError(f"Judge score is not numeric: {text[:100]}") from exc


def _first_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
        return None
    return None


# ---------------------------------------------------------------------------
# Pair evaluation (orchestration over pure scoring; injectable boundaries)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PairResult:
    skill_a: str
    skill_b: str
    a_on_a: DirectionScores
    b_on_b: DirectionScores
    verdict: OverlapVerdict
    recommendation: str
    api_calls: int = 0
    flags: list[str] = field(default_factory=list)


def _score_prompt_set(
    prompt_items: list[dict[str, Any]],
    owner_context: str,
    other_context: str,
    respond: ResponseFn,
    judge: JudgeFn,
) -> tuple[DirectionScores, int]:
    """Run all three conditions over one prompt set and average each.

    Returns the averaged DirectionScores plus the API call count consumed.
    """
    baselines: list[float] = []
    owns: list[float] = []
    others: list[float] = []
    calls = 0
    for item in prompt_items:
        prompt = item["prompt"]
        expected = item["expected"]

        baseline_resp = respond(prompt, "")
        baselines.append(judge(prompt, baseline_resp, expected))
        calls += 2
        time.sleep(RATE_LIMIT_SLEEP_SEC)

        own_resp = respond(prompt, _system_for(owner_context))
        owns.append(judge(prompt, own_resp, expected))
        calls += 2
        time.sleep(RATE_LIMIT_SLEEP_SEC)

        other_resp = respond(prompt, _system_for(other_context))
        others.append(judge(prompt, other_resp, expected))
        calls += 2
        time.sleep(RATE_LIMIT_SLEEP_SEC)

    return (
        DirectionScores(
            baseline=_avg(baselines),
            own=_avg(owns),
            other=_avg(others),
        ),
        calls,
    )


def _system_for(context: str) -> str:
    return (
        "You are a software engineering expert. Use the following skill knowledge "
        f"to answer:\n\n{context}"
    )


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def evaluate_pair(
    skill_a: str,
    skill_b: str,
    prompts: dict[str, list[dict[str, Any]]],
    *,
    respond: ResponseFn,
    judge: JudgeFn,
    skills_dir: Path = SKILLS_DIR,
) -> PairResult:
    """Evaluate one skill pair end to end.

    Raises MissingSkillError if either skill directory is gone (exit 1 at CLI).
    """
    dir_a = require_skill_dir(skill_a, skills_dir)
    dir_b = require_skill_dir(skill_b, skills_dir)
    context_a = load_skill_context(dir_a)
    context_b = load_skill_context(dir_b)

    a_on_a, calls_a = _score_prompt_set(
        prompts[skill_a], context_a, context_b, respond, judge
    )
    b_on_b, calls_b = _score_prompt_set(
        prompts[skill_b], context_b, context_a, respond, judge
    )

    verdict = classify_overlap(a_on_a, b_on_b)
    return PairResult(
        skill_a=skill_a,
        skill_b=skill_b,
        a_on_a=a_on_a,
        b_on_b=b_on_b,
        verdict=verdict,
        recommendation=recommend_action(verdict, skill_a, skill_b),
        api_calls=calls_a + calls_b,
    )


# ---------------------------------------------------------------------------
# Report writers (pure)
# ---------------------------------------------------------------------------


def build_matrix(results: list[PairResult], *, model: str, run_id: str) -> dict[str, Any]:
    """Build the machine-readable matrix.json payload."""
    return {
        "run_id": run_id,
        "model": model,
        "generated_at": datetime.now(UTC).isoformat(),
        "pairs": [
            {
                "skill_a": r.skill_a,
                "skill_b": r.skill_b,
                "verdict": r.verdict,
                "recommendation": r.recommendation,
                "a_on_a": {
                    "baseline": r.a_on_a.baseline,
                    "own": r.a_on_a.own,
                    "other": r.a_on_a.other,
                    "own_delta": r.a_on_a.own_delta,
                    "other_delta": r.a_on_a.other_delta,
                },
                "b_on_b": {
                    "baseline": r.b_on_b.baseline,
                    "own": r.b_on_b.own,
                    "other": r.b_on_b.other,
                    "own_delta": r.b_on_b.own_delta,
                    "other_delta": r.b_on_b.other_delta,
                },
                "api_calls": r.api_calls,
                "flags": r.flags,
            }
            for r in results
        ],
    }


def build_report_md(results: list[PairResult], *, model: str, run_id: str) -> str:
    """Render the human-facing REPORT.md with a prune/fold table."""
    lines = [
        f"# Skill Overlap Report: {run_id}",
        "",
        f"Model: `{model}`",
        "",
        "Pairwise skill overlap analysis (Issue #1932). Verdicts: DISTINCT (keep both), "
        "OVERLAP (fold candidate), SUBSUMED (prune candidate).",
        "",
        "## Prune / Fold Table",
        "",
        "| Skill A | Skill B | Verdict | A_delta | B_delta | Recommendation |",
        "|---------|---------|---------|---------|---------|----------------|",
    ]
    for r in results:
        lines.append(
            f"| {r.skill_a} | {r.skill_b} | {r.verdict} | "
            f"{r.a_on_a.own_delta:+.2f} | {r.b_on_b.own_delta:+.2f} | {r.recommendation} |"
        )
    lines.extend(["", "## Per-Pair Detail", ""])
    for r in results:
        lines.extend(_render_pair_detail(r))
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def _render_pair_detail(r: PairResult) -> list[str]:
    return [
        f"### {r.skill_a} vs {r.skill_b}: {r.verdict}",
        "",
        f"- {r.skill_a} on its own prompts: baseline {r.a_on_a.baseline:.2f}, "
        f"own {r.a_on_a.own:.2f} (delta {r.a_on_a.own_delta:+.2f}), "
        f"cross {r.a_on_a.other:.2f} (delta {r.a_on_a.other_delta:+.2f}).",
        f"- {r.skill_b} on its own prompts: baseline {r.b_on_b.baseline:.2f}, "
        f"own {r.b_on_b.own:.2f} (delta {r.b_on_b.own_delta:+.2f}), "
        f"cross {r.b_on_b.other:.2f} (delta {r.b_on_b.other_delta:+.2f}).",
        f"- Recommendation: {r.recommendation}",
        "",
    ]


def write_reports(
    results: list[PairResult],
    *,
    model: str,
    run_id: str,
    reports_dir: Path = REPORTS_DIR,
) -> Path:
    """Write matrix.json and REPORT.md under evals/reports/overlap-<run_id>/.

    Returns the report directory. Idempotent: re-running with the same run_id
    overwrites the prior files.
    """
    safe_run_id = _validate_run_id(run_id)
    reports_root = reports_dir.resolve()
    out_dir = (reports_root / f"overlap-{safe_run_id}").resolve()
    if reports_root not in out_dir.parents:
        raise ValueError(f"Invalid run id '{run_id}': report path escapes {reports_root}.")
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix = build_matrix(results, model=model, run_id=safe_run_id)
    (out_dir / "matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    (out_dir / "REPORT.md").write_text(
        build_report_md(results, model=model, run_id=safe_run_id), encoding="utf-8"
    )
    return out_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _make_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id) or ".." in run_id:
        raise ValueError(
            "run id must be 1-128 characters of letters, digits, '.', '_', or '-', "
            "start with a letter or digit, and not contain '..'."
        )
    return run_id


def run(args: argparse.Namespace) -> int:
    """Execute the analysis. Returns a process exit code (ADR-035)."""
    try:
        config = load_pairs_file(args.pairs)
    except PairsFileError as exc:
        print(f"ERROR (config): {exc}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        run_id = _validate_run_id(args.run_id or _make_run_id())
    except ValueError as exc:
        print(f"ERROR (config): {exc}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        _validate_pair_skill_dirs(config.pairs, SKILLS_DIR)
    except MissingSkillError as exc:
        print(f"ERROR (logic): {exc}", file=sys.stderr)
        return EXIT_LOGIC

    try:
        cost = estimate_cost(config.pairs, config.prompts, model=args.model)
    except PricingError as exc:
        print(f"ERROR (config): {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(cost.render(), file=sys.stderr)

    if args.dry_run:
        print(
            f"Dry run: {len(config.pairs)} pair(s) validated, no API calls made.",
            file=sys.stderr,
        )
        return EXIT_OK

    try:
        api_key = _load_api_key()
    except RuntimeError as exc:
        print(f"ERROR (external): {exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    respond = make_response_fn(api_key, args.model)
    judge = make_judge_fn(api_key, args.model)

    results: list[PairResult] = []
    try:
        for skill_a, skill_b in config.pairs:
            print(f"Evaluating pair: {skill_a} vs {skill_b}", file=sys.stderr)
            result = evaluate_pair(
                skill_a,
                skill_b,
                config.prompts,
                respond=respond,
                judge=judge,
                skills_dir=SKILLS_DIR,
            )
            print(f"  Verdict: {result.verdict}", file=sys.stderr)
            results.append(result)
    except MissingSkillError as exc:
        print(f"ERROR (logic): {exc}", file=sys.stderr)
        return EXIT_LOGIC
    except JudgeScoreError as exc:
        print(f"ERROR (external): LLM judge returned invalid score payload: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    except RuntimeError as exc:
        print(f"ERROR (external): Anthropic API failure: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    out_dir = write_reports(results, model=args.model, run_id=run_id, reports_dir=REPORTS_DIR)
    print(f"Report written to {out_dir}", file=sys.stderr)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pairwise skill overlap analysis (Issue #1932, Phase 1: explicit pairs only)."
    )
    parser.add_argument(
        "--pairs",
        required=True,
        help="Path to cluster.json with 'pairs' and 'prompts' (explicit pair list).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model id for generation and judge.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print the cost estimate without calling the API.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override the generated run id (used for the report directory name).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
