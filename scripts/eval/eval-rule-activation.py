#!/usr/bin/env python3
"""Rule Activation Eval: measure whether rules and skill references actually fire.

Tests how a rule or skill reference activates across loading mechanisms:
  - baseline       : no rule context (control)
  - description    : only the rule description, or the skill catalog front door
                     plus skill router, must select the reference before use
  - full           : entire rule body, or skill router plus selected reference body,
                     in system prompt as a diagnostic ceiling

Each scenario is graded by an LLM judge on three dimensions (1-5):
  - activation_score : did the response apply rule-specific guidance vs generic advice?
  - citation_score   : did the response use the rule's specific vocabulary?
  - behavior_score   : did the response gate behavior on the rule's preconditions?

Compares mechanisms per scenario, aggregates to per-rule verdict.

Usage:
    # Eval one rule
    python3 scripts/eval/eval-rule-activation.py \
        --scenarios tests/evals/rule-scenarios/working-with-legacy-code.json

    # Dry run (skip API calls)
    python3 scripts/eval/eval-rule-activation.py \
        --scenarios tests/evals/rule-scenarios/working-with-legacy-code.json --dry-run

    # Multiple rules at once
    python3 scripts/eval/eval-rule-activation.py \
        --scenarios tests/evals/rule-scenarios/*.json

    # Save results
    python3 scripts/eval/eval-rule-activation.py \
        --scenarios tests/evals/rule-scenarios/working-with-legacy-code.json \
        --output rule-activation-results.json

Exit codes:
    0 ok
    1 logic (one or more rules failed activation gate)
    2 config (missing rule, scenarios file invalid)
    3 external (API failure)
    4 auth   (missing ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import statistics
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from _anthropic_api import DEFAULT_MODEL, verify_model_available
from _anthropic_api import call_api as _call_api
from _anthropic_api import (
    load_api_key_for_selected_provider as _load_api_key,
)
from _eval_common import EST_TOKENS_PER_CALL

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RATE_LIMIT_SLEEP_SEC = 1.0
MECHANISMS = ("baseline", "description", "full")

# Rule passes activation gate when the single best non-baseline mechanism
# averages >= MIN_ACTIVATION_SCORE across all non-negative-case scenarios,
# AND that mechanism beats baseline by >= MIN_DELTA_VS_BASELINE.
MIN_ACTIVATION_SCORE = 3.5
MIN_DELTA_VS_BASELINE = 0.5
# Negative scenarios grade restraint on an inverted rubric: 5 means the
# response correctly did NOT activate the rule, 1 means it fired where it must
# not. So this is a floor and a LOW score is the failure. Set symmetric with
# MIN_ACTIVATION_SCORE: the same 3.5 that counts as "activated well enough" on
# the positive side counts as "held back well enough" here.
MIN_RESTRAINT_SCORE = 3.5
# The judge rubric is a 1 to 5 scale. A stored score outside it, or one that is
# not a finite real number, is not a measurement the rubric can express. NaN is
# the dangerous case: every comparison against it is False, so an unguarded
# `worst < MIN_RESTRAINT_SCORE` would wave a NaN straight through the gate.
MIN_RUBRIC_SCORE = 1.0
MAX_RUBRIC_SCORE = 5.0
DEFAULT_SEED = 0
DEFAULT_JUDGE_REPEATS = 3
DEFAULT_JUDGE_REDUCER = "median"
RESULTS_SCHEMA_VERSION = 1
_SCORE_KEYS = ("activation_score", "citation_score", "behavior_score")
_SCORE_REDUCERS: dict[str, Callable[[list[float]], float]] = {
    "mean": statistics.fmean,
    "min": min,
    "max": max,
    "median": statistics.median,
}


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------


def parse_rule(rule_path: Path) -> dict[str, str]:
    """Split a rule file into frontmatter description and body."""
    return _parse_markdown_artifact(rule_path)


def _parse_markdown_artifact(path: Path) -> dict[str, str]:
    """Split a Markdown artifact into frontmatter description and body."""
    text = path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not fm_match:
        return {"description": "", "body": text, "frontmatter": ""}

    frontmatter = fm_match.group(1)
    body = fm_match.group(2)

    desc_match = re.search(r"^description:\s*(.+?)$", frontmatter, re.MULTILINE)
    description = desc_match.group(1).strip() if desc_match else ""

    return {
        "description": description,
        "body": body,
        "frontmatter": frontmatter,
    }


def parse_skill_reference(skill_path: Path, reference_path: Path) -> dict[str, str]:
    """Build the progressive-disclosure prompt surface for one skill reference."""
    skill = _parse_markdown_artifact(skill_path)
    reference = _parse_markdown_artifact(reference_path)
    skill_name_match = re.search(r"^name:\s*(.+?)$", skill["frontmatter"], re.MULTILINE)
    skill_name = skill_name_match.group(1).strip() if skill_name_match else skill_path.parent.name
    reference_rel = str(reference_path.relative_to(skill_path.parent))
    body = (
        "Skill router:\n\n"
        f"{skill['body']}\n\n"
        "Selected reference:\n\n"
        f"{reference['body']}"
    )
    return {
        "description": skill["description"],
        "body": body,
        "frontmatter": skill["frontmatter"],
        "skill_name": skill_name,
        "skill_body": skill["body"],
        "skill_path": str(skill_path.relative_to(REPO_ROOT)),
        "reference_path": reference_rel,
        "reference_body": reference["body"],
    }


def _baseline_system_prompt(_rule: dict[str, str], _rule_id: str) -> str:
    """Construct the baseline prompt shared by collapsed mechanisms."""
    return ""


def build_system_prompt(mechanism: str, rule: dict[str, str], rule_id: str) -> str:
    """Construct the system prompt for a given activation mechanism."""
    if mechanism == "baseline":
        return _baseline_system_prompt(rule, rule_id)
    if mechanism == "description":
        if not rule["description"]:
            return ""
        if rule.get("skill_name"):
            return (
                "Project skills are available on demand. Available skill:\n\n"
                f"  - {rule['skill_name']}: {rule['description']}\n\n"
                "Decide whether to select this skill based on the user's request. "
                "If selected, open the skill router and then the smallest matching "
                "reference before advising the user."
            )
        return (
            "Project rules apply to your work. Available rule:\n\n"
            f"  - {rule_id}: {rule['description']}\n\n"
            "Decide whether to apply rules based on the user's request "
            "and apply them when relevant."
        )
    if mechanism == "full":
        if not rule["body"].strip() and not rule.get("skill_name"):
            return _baseline_system_prompt(rule, rule_id)
        return (
            "The following project rule applies to your work. "
            "Apply it when relevant.\n\n"
            f"{rule['body']}"
        )
    raise ValueError(f"Unknown mechanism: {mechanism}")


NEGATIVE_GATE = "skip-rule-not-applicable"


def _normalize_gate(value: object) -> str:
    """Normalize an ``expected_gate`` label for comparison.

    Case and separator style are authoring noise, not meaning. Folding them
    here means a scenario written `SKIP_RULE_NOT_APPLICABLE` lands in the pool
    its author intended instead of silently becoming a positive case.
    """
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("_", "-")


def _is_negative_gate(value: object) -> bool:
    """True when this scenario's gate marks it as a negative case.

    Every consumer that splits the pools calls this. The gate string also
    selects the judge rubric, so a scenario misclassified here is graded
    against the wrong rubric and then filed in the wrong pool: the score is
    wrong and the population it joins is wrong.
    """
    return _normalize_gate(value) == NEGATIVE_GATE


def _validate_results_artifact_schema(data: dict[str, Any]) -> None:
    """Refuse stored result artifacts written by an unknown schema."""
    schema_version = data.get("schema_version")
    if schema_version is None:
        return
    if schema_version != RESULTS_SCHEMA_VERSION:
        raise ValueError(
            "unsupported eval results schema_version "
            f"{schema_version!r}; expected {RESULTS_SCHEMA_VERSION}"
        )


def _results_artifact_rules(data: dict[str, Any]) -> dict[str, Any]:
    """Return stored result rules after checking the artifact schema."""
    _validate_results_artifact_schema(data)
    rules = data.get("rules")
    if isinstance(rules, dict):
        return rules
    raise ValueError("eval results artifact must contain a rules object")


def _graded_count(cell: dict[str, Any]) -> int:
    """Read coverage from current and pre-coverage stored result cells."""
    graded_count = cell.get("graded_count")
    if graded_count is not None:
        return int(graded_count)
    return int(cell["scenario_count"])


# Calibrated against the shipped corpus: the 32 distinct real positive gate
# names score at most 0.400 similarity to the sentinel, while single-character
# corruptions of the sentinel score at least 0.958. Any threshold inside that
# gap separates them; 0.80 sits clear of both edges. A prefix test cannot do
# this job, because `skiprule-not-applicable` and `skip-rul-not-applicable`
# never carry the literal prefix yet both mean the negative case.
_GATE_NEAR_MISS_RATIO = 0.80


def _is_gate_near_miss(normalized: str) -> bool:
    """True when a gate is close enough to the sentinel to be a typo of it.

    Refusing a near miss is the visible failure. Accepting one is invisible:
    the scenario is graded against the positive rubric and then averaged into
    the positive pool, so both the score and the population are wrong.
    """
    if normalized.startswith("skip-rule"):
        return True
    ratio = difflib.SequenceMatcher(None, normalized, NEGATIVE_GATE).ratio()
    return ratio >= _GATE_NEAR_MISS_RATIO


def build_skill_route_prompt(rule: dict[str, str], scenario: dict[str, Any]) -> str:
    """Build the progressive-disclosure routing prompt for a skill reference."""
    return f"""Route the user request through the available skill catalog.

Available skill:
- {rule["skill_name"]}: {rule["description"]}

If the skill is relevant, open this skill router and choose the smallest matching reference:

{rule["skill_body"]}

User request:
{scenario.get("input", "")}

Return JSON only with these fields:
- selected_skill: skill name or null
- selected_reference: reference path or null
- reasoning: one sentence"""


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Extract one JSON object from a model response."""
    stripped = text.strip()
    if "```" in stripped:
        match = re.search(r"```(?:json)?\s*\n(.*?)```", stripped, re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_selected_reference(value: object) -> str | None:
    """Normalize a route response reference path."""
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    cleaned = value.strip().strip("`")
    if not cleaned or cleaned.lower() == "null":
        return None
    if cleaned.startswith("references/"):
        return cleaned
    if "/references/" in cleaned:
        return "references/" + cleaned.rsplit("/references/", maxsplit=1)[1]
    if cleaned.endswith(".md"):
        return f"references/{Path(cleaned).name}"
    return cleaned


def _resolve_reference_body(rule: dict[str, str], selected_reference: str | None) -> str:
    """Return the selected reference body if it resolves under the skill reference dir."""
    if not selected_reference:
        return ""
    skill_path_str = rule.get("skill_path")
    if not skill_path_str:
        return ""
    skill_path = (REPO_ROOT / skill_path_str).resolve()
    candidate = (skill_path.parent / selected_reference).resolve()
    try:
        candidate.relative_to((skill_path.parent / "references").resolve())
    except ValueError:
        return ""
    if candidate.suffix != ".md" or not candidate.is_file():
        return ""
    return _parse_markdown_artifact(candidate)["body"]


def _build_routed_reference_prompt(
    rule: dict[str, str],
    selected_reference: str | None,
) -> str:
    """Build the system prompt after the progressive route selected a reference."""
    reference_body = _resolve_reference_body(rule, selected_reference)
    if not reference_body:
        return ""
    return (
        "The on-demand skill route selected this reference. Apply it when relevant.\n\n"
        f"Skill: {rule['skill_name']}\n"
        f"Reference: {selected_reference}\n\n"
        f"{reference_body}"
    )


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------


def _skip_string_literal(text: str, index: int) -> int:
    """Return the index just past the string starting at ``index``.

    Returns ``len(text)`` for a string that never closes, which is the shape
    salvage exists for: the caller then sees no further structure, and a
    payload whose tail is one open string cannot donate a brace to anything.
    """
    index += 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index + 1
        index += 1
    return len(text)


def _scan_balanced_object(text: str, start: int) -> int | None:
    """Return the index just past the object opening at ``start``, or ``None``.

    String contents are skipped so that braces or escaped quotes inside a value
    cannot terminate the scan early.
    """
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build the object, refusing a repeated key instead of taking the last.

    ``json.loads`` silently keeps the last value for a duplicated key, and it
    compares keys *after* unescaping, so ``\\u0061ctivation_score`` collides
    with ``activation_score``. A judge payload carrying both therefore parsed
    cleanly and reported the second value, which is fabrication reached
    through the strict path rather than the salvage path.
    """
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key: {key}")
        seen[key] = value
    return seen


def _reject_json_constant(name: str) -> object:
    """Refuse ``NaN``, ``Infinity``, and ``-Infinity``, which JSON excludes."""
    raise ValueError(f"non-finite JSON constant: {name}")


def _strict_json_loads(text: str) -> object:
    """``json.loads`` restricted to what the JSON grammar actually allows.

    Raises ``ValueError`` (which ``json.JSONDecodeError`` subclasses, so a
    single ``except ValueError`` covers both) when the text is not JSON, uses
    a non-finite constant, or repeats an object key.

    Deeply nested input is folded into that same ``ValueError`` on purpose. The
    C scanner raises ``RecursionError`` past roughly a hundred thousand levels,
    and ``RecursionError`` subclasses ``RuntimeError``, which the scoring call
    site already catches as a transport error. Left alone, a malformed payload
    would therefore be filed as a judge API failure and retried against an API
    that was never at fault. Converting it here keeps the classification honest:
    unparseable text is a parse failure wherever it is unparseable.

    This does not close issue #3999. The recovery helpers still disagree with
    each other about what a partially valid payload means; this only fixes
    which *kind* of failure an over-nested payload is reported as.
    """
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except RecursionError as exc:
        raise ValueError(f"JSON nesting exceeds the decoder's limit: {exc}") from exc


def _extract_json_object(text: str) -> str | None:
    """Return the object the payload begins with, when the payload is not one.

    The judge is told to answer in JSON only. When a whole-payload parse fails,
    the one recoverable shape is a valid object followed by content that is not
    part of it. The object is therefore read from offset 0, never searched for.

    Searching here was the twelfth defect of a single class. ``_salvage_anchor``
    had already stopped the *failure* path from searching, but this is the
    *success* path: it returns through the normal result branch, so a searched
    verdict was indistinguishable from a clean parse and no post-hoc audit
    could surface it. An unauditable search is worse than an auditable one, so
    both paths now obey one rule: the verdict is the object the payload starts
    with, or there is no verdict. Callers mark what this recovers.

    The version this replaces justified its search by saying agentic CLI
    providers interleave tool-call traces into the answer. That is stale.
    ``_copilot_cli._read_session_transcript`` reads ``assistant.message``
    events from the session log, where tool calls sit in a sibling
    ``toolRequests`` field and never reach this function.

    ``_names_a_score_field_twice`` applies here for the same reason it applies
    to salvage: a second copy of a score field anywhere in the payload makes
    the leading object one of two candidate answers, and two candidates is an
    ambiguity rather than a choice. It applies only when text follows the
    object, because that trailing text is what a second candidate would hide
    in and it is exactly what cannot be parsed and checked exactly.

    Returns ``None`` when the payload does not begin with a balanced,
    strictly-parseable object, or when it names two verdicts.
    """
    start = _salvage_anchor(text)
    if start is None:
        return None
    end = _scan_balanced_object(text, start)
    if end is None:
        return None
    candidate = text[start:end]
    try:
        parsed = _strict_json_loads(candidate)
    except ValueError:
        return None
    if text[end:].strip():
        # Something follows the object, so a second verdict could be sitting in
        # a tail this function never parses. Only the raw count can see it.
        return None if _names_a_score_field_twice(text) else candidate
    # The object is the whole payload. There is no unparsed tail to protect
    # against, and the parse has already decoded every escape, so the exact
    # structural check applies. Using the raw count here instead would refuse
    # any payload containing ``\u``, which discards a healthy fenced verdict
    # whose reasoning carries an em-dash or a curly quote.
    return None if _parsed_names_two_verdicts(parsed) else candidate


def score_response(
    api_key: str,
    scenario: dict[str, Any],
    response: str,
    model: str = DEFAULT_MODEL,
    seed: int | None = None,
) -> dict[str, Any]:
    """Use the API to score a response on rule activation."""
    expected_signals = scenario.get("expected_signals", [])
    expected_gate = scenario.get("expected_gate", "")
    rationale = scenario.get("rationale", "")

    is_negative = _is_negative_gate(expected_gate)
    signals_str = ", ".join(expected_signals) if expected_signals else "none"
    negative_flag = "YES" if is_negative else "no"

    activation_doc = (
        "did the response apply guidance specific to the scenario's rule, "
        "or only generic advice? "
        "(negative case: 5 means the response correctly did NOT activate "
        "the rule and gave generic advice instead)"
    )
    citation_doc = (
        "did the response use the expected vocabulary or cite specific "
        "concepts? (negative case: 5 means absence of these concepts)"
    )
    behavior_doc = (
        "did the response gate the behavior on the rule's preconditions "
        "(e.g., write tests first, separate commits, refuse deletion)? "
        "(negative case: 5 means the response correctly proceeded without "
        "the unnecessary gate)"
    )
    json_schema = (
        '{"activation_score": <int>, "citation_score": <int>, '
        '"behavior_score": <int>, "reasoning": "<one sentence>"}'
    )

    judge_prompt = f"""Score this response on three dimensions (1-5 each).

**Scenario**: {scenario.get("desc", "")}
**Rationale**: {rationale}
**Expected signals (vocabulary the rule prescribes)**: {signals_str}
**Expected behavior gate**: {expected_gate or "none"}
**Negative case (rule should NOT activate)**: {negative_flag}

**User prompt**: {scenario.get("input", "")}

**Actual response**:
{response}

Score on these dimensions (1=absent, 5=clearly present):

- **activation_score**: {activation_doc}
- **citation_score**: {citation_doc}
- **behavior_score**: {behavior_doc}

Respond in JSON only, no other text:
{json_schema}"""

    metadata: dict[str, object] = {}
    raw = _call_api(
        api_key,
        [{"role": "user", "content": judge_prompt}],
        model=model,
        seed=seed,
        metadata=metadata,
    )

    text = raw.strip()

    try:
        parsed = _strict_json_loads(text)
        recovered_from_prefix = False
    except ValueError:
        embedded = _recover_verdict(text)
        if embedded is None:
            return _judge_parse_failure(text, f"judge parse error: {text[:200]}")
        # _recover_verdict only returns text it already parsed with
        # _strict_json_loads, so this cannot raise.
        parsed = _strict_json_loads(embedded)
        recovered_from_prefix = True
    else:
        # A second copy of a score field makes the payload carry two candidate
        # verdicts, and picking one of two is a guess. Both recovery paths
        # already refused on this. The strict parse did not, because a
        # whole-payload parse succeeding was read as proof the payload named
        # one answer. It is not: valid JSON nests, so a second verdict can sit
        # inside the first as a member, a list element, or a quoted string,
        # and the parse still succeeds.
        #
        # That gap was worse than the recovery defects it mirrors. Those at
        # least set ``judge_salvaged``, so a guess stayed auditable. This one
        # returned through the clean-parse branch, which sets no marker at
        # all, so a fabricated triple was indistinguishable from a judge that
        # simply answered.
        #
        # Checked against the parsed object rather than the raw text. The two
        # answer the same question, but only one of them can answer it here
        # without also refusing healthy output: see _parsed_names_two_verdicts.
        # The recovery branch above keeps the raw-text guard, which each of its
        # entry points already applies, because a payload that did not parse
        # offers nothing exact to check.
        if _parsed_names_two_verdicts(parsed):
            return _failed_judge(
                f"ambiguous judge output names two verdicts: {text[:200]}"
            )
    if not isinstance(parsed, dict):
        return _failed_judge(f"judge returned non-object JSON: {text[:200]}")
    score_error = _judge_score_shape_error(parsed)
    if score_error is not None:
        return _judge_parse_failure(text, score_error)
    result = {
        "activation_score": _clamp_score(parsed["activation_score"]),
        "citation_score": _clamp_score(parsed["citation_score"]),
        "behavior_score": _clamp_score(parsed["behavior_score"]),
        "reasoning": str(parsed.get("reasoning", ""))[:300],
        "judge_failed": False,
    }
    if recovered_from_prefix:
        # The whole payload did not parse; the verdict came from its leading
        # object. Marking it is what makes the recovery auditable after the
        # run, which the searching version it replaced never was.
        result["judge_salvaged"] = True
    fingerprint = metadata.get("system_fingerprint")
    if isinstance(fingerprint, str):
        result["judge_system_fingerprint"] = fingerprint
    return result


def _clamp_score(value: object) -> int:
    """Return an exact judge score, or 0 after shape validation fails."""
    if isinstance(value, int) and not isinstance(value, bool) and value in _SCORE_RANGE:
        return value
    return 0


def _reduce_score_samples(
    samples: list[dict[str, Any]],
    reducer_name: str,
) -> dict[str, Any]:
    """Reduce judge samples, ignoring the ones that failed to parse.

    A failed sample carries no score, so folding it in as a zero would drag
    the cell toward zero and invert rankings between mechanisms that happened
    to fail at different rates. Reduce over the graded samples only and report
    how many were graded. `judge_failed` still flips when any sample failed,
    so the caller keeps failing loudly; it just no longer reads a fabricated
    zero as if the judge had scored it.
    """
    reducer = _SCORE_REDUCERS[reducer_name]
    graded = [s for s in samples if not s.get("judge_failed")]
    failed_count = len(samples) - len(graded)
    if not graded:
        return {
            "activation_score": None,
            "citation_score": None,
            "behavior_score": None,
            "judge_failed": True,
            "graded": False,
            "score_reducer": reducer_name,
            "sample_count": len(samples),
            "graded_sample_count": 0,
            "failed_sample_count": failed_count,
        }
    reduced: dict[str, Any] = {
        key: reducer([float(sample[key]) for sample in graded]) for key in _SCORE_KEYS
    }
    # Reducing each field on its own is a coordinate-wise reduction: the triple
    # it produces need not be one any judge gave, and can be strictly better
    # than every one of them. Three samples of 5/5/1, 5/1/5 and 1/5/5 each
    # average 3.67, and per-field medians publish 5/5/5. Reduce each sample to
    # its own scalar first so the cell is a real observation, or the midpoint
    # of two. The per-field values stay as the per-axis diagnostic.
    reduced["cell_score"] = reducer(
        [_sample_scalar(sample) for sample in graded]
    )
    reduced["judge_failed"] = failed_count > 0
    reduced["graded"] = True
    reduced["score_reducer"] = reducer_name
    reduced["sample_count"] = len(samples)
    reduced["graded_sample_count"] = len(graded)
    reduced["failed_sample_count"] = failed_count
    return reduced


def _sample_scalar(sample: dict[str, Any]) -> float:
    """Collapse one judge sample's three fields to the score it stands for."""
    return sum(float(sample[key]) for key in _SCORE_KEYS) / len(_SCORE_KEYS)

_SCORE_FIELDS = ("activation_score", "citation_score", "behavior_score")

# The judge rubric is 1-5. Kept as one authoritative range because three code
# paths police it: the shape gate, the clamp, and salvage. They disagreed once
# already, and that disagreement is what let an out-of-range score through.
_SCORE_RANGE = range(1, 6)

_JSON_INT_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")

# A score field spelled as a JSON key: quoted, quoted with the quotes escaped
# because the object was itself serialized into a string, or single-quoted
# because the judge emitted the JSON5/Python dialect that lenient decoders
# accept. Counting this shape rather than the bare identifier is what lets
# ordinary prose name a field without being mistaken for a second verdict.
# Each spelling pairs its own quotes, so a mismatched pair is not a key.
_KEY_SHAPED_SCORE_FIELDS = tuple(
    re.compile(
        "(?:"
        + '"' + re.escape(field) + '"'
        + "|" + r"\\\"" + re.escape(field) + r"\\\""
        + "|" + "'" + re.escape(field) + "'"
        + r")\s*:"
    )
    for field in _SCORE_FIELDS
)

# The same field names, used only to detect that a decoded layer names a score
# field at all. Neither the quoting nor the separator is required, and the value
# is deliberately not captured.
#
# Three rounds of trying to compare a restated value to the filed one were each
# broken by the next round, so round 21 refused on the name instead. Round 22
# then showed that refusing on a *quoted* name still missed the unquoted JSON5
# and Python spellings (``{activation_score:1}``, ``dict(activation_score=1)``),
# and that requiring a colon still missed ``=``. Quoting styles and separators
# are both unbounded enumerations, which is the trap the previous three rounds
# fell into, so this matches the bare name and stops there.
#
# The cost is measured, not assumed: across the 264 reasoning strings nested in
# the 288 archived judge payloads, zero name a score field, so this refuses no
# sample any real judge in the archive has produced. A trailing capture group
# here also consumed the rest of the layer once, so ``finditer`` returned one
# match per layer and every field after the first went unexamined.
_NAMED_SCORE_FIELD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(f) for f in _SCORE_FIELDS) + r")\b"
)

# The escapes a JSON string body can carry. ``\\`` matters most: a value
# serialized twice spells its escapes with a doubled backslash, and decoding
# only ``\uXXXX`` consumes the second backslash of ``\\u0061`` and destroys the
# escape instead of revealing it.
_JSON_STRING_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

_HEX4_RE = re.compile(r"[0-9a-fA-F]{4}\Z")

# How many further decode layers to peel before giving up. A parse decodes one
# layer, so anything surviving here was serialized more than once. The bound
# exists so a crafted payload cannot turn the check into unbounded work; when
# it is reached with decoding still possible, the payload is refused rather
# than accepted, since an undecoded remainder is exactly the case this cannot
# clear.
#
# Each peel strictly shortens the string, so a walk terminates on its own and
# the bound is about cost, not termination. It is set high enough that ordinary
# prose reaches a fixpoint well inside it: a run of N consecutive backslashes
# halves each layer, so eight layers absorb 256 of them, and a judge writing
# about regex escaping does not produce that. A smaller bound refused such a
# judge over a remainder that held no score field at all.
_MAX_ESCAPE_LAYERS = 8

# The opening line of a Markdown code fence, capturing its delimiter run so
# the close can be paired to the same width. Applied only when the payload
# holds exactly one block, so no candidate is ever selected from several.
_FENCE_OPEN_RE = re.compile(r"(`{3,})(?:json)?[ \t]*")

_ASCII_SPACE = " \t\r\n"

# Stands in for an object or array value that was skipped rather than read.
# It only has to be something `_JSON_INT_RE` can never match, so a score field
# holding a structure is rejected instead of parsed. Recording the key at all
# is the point: it lets the no-duplicate check see structure-valued members,
# which otherwise slip past and let a later repeat of the same key win.
_STRUCTURE_VALUE = "<structure>"


def _span_parses_as_json(text: str, start: int, end: int) -> bool:
    """Return whether ``text[start:end]`` is one complete, strict JSON value.

    Strict matters: ``NaN``, ``Infinity``, and duplicate keys are all things
    ``json.loads`` accepts by default and the JSON grammar does not. Accepting
    them here would let this report "verified" on a span it had not really
    verified, which is the claim the whole boundary decision rests on.
    """
    try:
        _strict_json_loads(text[start:end])
    except (ValueError, RecursionError):
        return False
    return True


def _advance_string_state(
    char: str, in_string: bool, escaped: bool
) -> tuple[bool, bool]:
    """Return the ``(in_string, escaped)`` pair after consuming ``char``."""
    if not in_string:
        return char == '"', False
    if escaped:
        return True, False
    if char == "\\":
        return True, True
    return char != '"', False


def _skip_balanced(text: str, index: int) -> int | None:
    """Return the index just past the structure opening at ``index``.

    Tracks string state so a brace inside a string value does not change
    depth, then confirms the span it landed on parses as a complete JSON
    value. That second step is what makes the boundary trustworthy.

    Depth tracking alone is not enough. Salvage runs precisely because
    ``json.loads`` already failed, and the usual cause is an unescaped quote
    in judge prose. One stray quote desynchronizes ``in_string``, so a brace
    sitting inside prose reads as a structural close and this function
    returns an index *inside* the nested object rather than past it. The
    caller then harvests the nested object's members as if they were
    top-level, which is how an exemplar's zeros can outrank the real verdict.

    Re-parsing the span closes that hole using the JSON grammar itself rather
    than a heuristic. Counting quotes does not work: the payload that
    motivated this check has an even quote count, which is exactly why the
    desynchronization happens. A span that parses cleanly is a complete
    value, so its end is the real end; a span that does not parse means the
    boundary cannot be trusted and the whole payload is rejected.
    """
    opener = text[index]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for position in range(index, len(text)):
        char = text[position]
        was_in_string = in_string
        in_string, escaped = _advance_string_state(char, in_string, escaped)
        if was_in_string or in_string:
            continue
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                end = position + 1
                if char != closer or not _span_parses_as_json(text, index, end):
                    return None
                return end
    return None


def _read_key(text: str, index: int) -> tuple[str, int] | None:
    """Read a quoted member key starting at ``index``, or return ``None``."""
    if index >= len(text) or text[index] != '"':
        return None
    escaped = False
    for position in range(index + 1, len(text)):
        char = text[position]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return text[index + 1 : position], position + 1
    return None


def _skip_while(text: str, index: int, chars: str) -> int:
    """Return the first index at or after ``index`` not in ``chars``."""
    while index < len(text) and text[index] in chars:
        index += 1
    return index


def _read_member_key(text: str, index: int) -> tuple[str, int] | None:
    """Read a ``"key":`` pair, returning the key and the index past the colon."""
    key_read = _read_key(text, index)
    if key_read is None:
        return None
    key, index = key_read
    index = _skip_while(text, index, _ASCII_SPACE)
    if index >= len(text) or text[index] != ":":
        return None
    return key, index + 1


def _read_scalar_value(text: str, index: int) -> tuple[str, int] | None:
    """Read an unquoted value up to the next comma or closing brace.

    Returns ``None`` when the text read is not a single JSON primitive.
    Without that check a malformed member swallows the punctuation that
    separates it from a nested object, and the nested object's members are
    then read as members of the root. ``{"noise":true {"x":1,"citation_score":
    0}, ...}`` promoted a depth-2 score to depth 1 exactly that way.
    """
    end = index
    while end < len(text) and text[end] not in ",}":
        end += 1
    token = text[index:end].strip(_ASCII_SPACE)
    try:
        _strict_json_loads(token)
    except (ValueError, RecursionError):
        return None
    return token, end


def _value_start(text: str, index: int) -> int | None:
    """Return where a member's value begins, or ``None`` to stop scanning.

    Two stops, both meaning "trust nothing further": the payload ended, or the
    value is a string. Salvage runs on output that broke inside a string, so
    the first string value is the last point at which offsets are reliable.
    """
    index = _skip_while(text, index, _ASCII_SPACE)
    if index >= len(text) or text[index] == '"':
        return None
    return index


def _members_read_so_far(members: dict[str, str]) -> dict[str, str] | None:
    """Return what was read, or ``None`` when the scan stopped before any key.

    An empty result is not a partial verdict, it is a failure to read the
    object at all, and callers distinguish the two.
    """
    return members or None


def _member_key_is_usable(key: str, members: dict[str, str]) -> bool:
    """Return whether ``key`` may be recorded alongside the keys already read.

    A repeat is a duplicate the strict loader would have refused. A backslash
    means the raw undecoded text is not a reliable identity: ``\\u0061ctivation_score``
    and ``activation_score`` compare as different keys, so the duplicate check
    above would miss the collision. The judge is asked for fixed ASCII field
    names, so refusing escapes costs nothing.
    """
    return "\\" not in key and key not in members


def _scan_root_members(text: str, start: int | None = None) -> dict[str, str] | None:
    """Return the depth-1 scalar members of the object at ``start`` in ``text``.

    Salvage exists because the judge's ``reasoning`` string is malformed, so
    this cannot use ``json.loads`` and cannot trust anything after the first
    string value: an unescaped quote there desynchronizes every subsequent
    read. It scans members in order and stops at the first string value,
    which is exactly as far as the payload is trustworthy.

    Only depth-1 members of the object starting at ``start`` are returned. A
    nested rubric's scores sit at depth 2 and are skipped wholesale, and a
    sibling object is never reached, so neither can contribute a number to a
    verdict it does not belong to.

    Returns ``None`` on a duplicate key or a malformed structure. See
    ``_member_key_is_usable`` for why an escaped key rejects too.
    """
    start = text.find("{") if start is None else start
    if start == -1 or start >= len(text) or text[start] != "{":
        return None
    members: dict[str, str] = {}
    index = start + 1
    while index < len(text):
        index = _skip_while(text, index, _ASCII_SPACE + ",")
        if index >= len(text) or text[index] == "}":
            return members
        key_read = _read_member_key(text, index)
        if key_read is None:
            return _members_read_so_far(members)
        key, index = key_read
        if not _member_key_is_usable(key, members):
            return None
        value_index = _value_start(text, index)
        if value_index is None:
            return members
        index = value_index
        char = text[index]
        if char not in "{[":
            scalar = _read_scalar_value(text, index)
            if scalar is None:
                return None
            members[key], index = scalar
            continue
        skipped = _skip_balanced(text, index)
        if skipped is None:
            return _members_read_so_far(members)
        members[key] = _STRUCTURE_VALUE
        index = skipped
    return members


def _salvage_anchor(text: str) -> int | None:
    """Return the offset of the only object salvage may read, or ``None``.

    Salvage exists for one shape: the judge emitted a well-formed verdict
    prefix and then broke inside ``reasoning``. In that shape the verdict is
    the very first thing in the payload, so the anchor is fixed at offset 0
    rather than searched for.

    Searching is what produced eleven fabrication defects across seven review
    rounds. Every one was a disagreement about which candidate object was the
    judge's answer: a rubric exemplar, a tool trace, an array element, the
    second of a duplicate pair. A search cannot be made safe by adding another
    disqualifier, because each new one only narrows the set of wrong answers it
    may still return. Refusing to search removes the question.

    The cost is real and bounded: a payload that leads with prose or a tool
    trace is no longer salvaged. That discards one of three judge samples. The
    alternative is a fabricated score in a published number, and the archived
    recoveries all lead with the verdict, so the shape this gives up is not one
    the judges actually produce.
    """
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return None
    return len(text) - len(stripped)


def _count_score_bearing_objects(value: object) -> int:
    """Count objects carrying a score field, at any depth, in a parsed payload.

    Iterative on purpose. A recursive walk overflows Python's own call stack on
    payloads the JSON decoder accepts happily, and ``RecursionError`` subclasses
    ``RuntimeError``, which the scoring call site catches as a transport error.
    A healthy verdict carrying a deeply nested member would therefore have been
    filed as a judge API failure and dropped from the sample, which moves a
    published number by removing a valid observation. The decoder's C scanner
    has its own much deeper limit, so the walkers, not the parse, were the
    binding constraint.
    """
    total = 0
    stack: list[object] = [value]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if isinstance(current, (dict, list)):
            if id(current) in seen:
                continue
            seen.add(id(current))
        if isinstance(current, dict):
            if any(field in current for field in _SCORE_FIELDS):
                total += 1
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return total


def _string_values(value: object) -> Iterator[str]:
    """Yield every string in a parsed payload, at any depth, keys included.

    Walking only ``dict.values()`` leaves a hole, because a JSON object key is
    a string too. A payload can carry a second verdict as a key:

        {"activation_score": 1, ...,
         "corrected verdict: {\\"activation_score\\": 5}": true}

    The raw-text guard this check replaced caught that shape. Dropping to
    values-only would have made the replacement a regression on the one case it
    exists to stop, so the walk covers both halves of every pair.

    One kind of key is skipped: a key that is *exactly* a score field name.
    That key is the schema slot the parser already read, so yielding it would
    make every healthy payload refuse once the field pattern stopped requiring
    quotes. The skip is deliberately narrow. It is equality against
    ``_SCORE_FIELDS``, so a key that merely *contains* a field name is still
    yielded, and it applies to keys only. An exact field name appearing as a
    *value* is not a schema slot; it is a reference to a field, and round 23
    showed why that distinction is load-bearing:

        {"activation_score": 5, ...,
         "corrected_verdict": [{"field": "activation_score", "value": 1}, ...]}

    names a competing 1/1/1 verdict with the field names in value position and
    the numbers in siblings. An earlier fix exempted exact field names wherever
    they appeared, on the reasoning that a string holding only a name holds no
    number. That is true of the string and false of the payload, which is where
    the number actually lives. A nested object that keys real scores is still
    covered by ``_count_score_bearing_objects``.

    Iterative for the same reason as ``_count_score_bearing_objects``: a
    recursive walk turns a healthy but deeply nested payload into a mislabelled
    API failure.
    """
    stack: list[object] = [value]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if isinstance(current, (dict, list)):
            if id(current) in seen:
                continue
            seen.add(id(current))
        if isinstance(current, str):
            yield current
        elif isinstance(current, dict):
            for key, member in current.items():
                if isinstance(key, str) and key not in _SCORE_FIELDS:
                    yield key
                stack.append(member)
        elif isinstance(current, list):
            stack.extend(current)


def _parsed_names_two_verdicts(parsed: object) -> bool:
    """Return whether a payload that parsed whole carries two candidate verdicts.

    The textual guard below answers the same question for payloads that do not
    parse, where the verdict has to be searched for. Once a payload parses, the
    search is over and the question can be answered exactly instead of by
    spelling, which matters in both directions.

    It stops a false accept: ``_names_a_score_field_twice`` counts key shapes in
    raw text, so a second verdict nested as a member, a list element, or a value
    three levels down is caught only if it happens to be spelled the way the
    patterns expect. Counting score-bearing objects in the parsed structure
    catches all three by construction.

    It also stops a false refuse, which is why this is not simply the textual
    guard run twice. That guard refuses any payload containing ``\\u``, because
    a name spelled with a unicode escape would slip a raw count. On a malformed
    payload that costs nothing. On a healthy one it is a live hazard: JSON
    encoders default to ASCII output, so a judge whose reasoning contains an
    em-dash, a curly quote, or an accented name emits ``\\uXXXX`` and would be
    refused for prose. Here the parse has already decoded those escapes, so the
    blanket is not needed and the string check sees what the judge meant.

    A verdict serialized inside a string value is still a second candidate and
    is still refused, on the same reasoning that governs the recovery paths: the
    judge named two answers and choosing one of them is a guess.

    Known limit, measured rather than assumed: this cannot detect a second
    verdict whose field name is not spelled as the literal codepoint sequence.
    Three shapes share that one cause. The name can be split
    (``'activation' '_score'`` as Python adjacent literals), substituted
    (``activation_scоre`` with a Cyrillic о), or interleaved (a zero-width
    space inside it). Each survives any pattern written over the real name, and
    no textual check closes the class, because the encoding space is open.
    Zero of the
    264 recovered judge payloads contain any of those shapes, and the one
    payload with adjacent quoted tokens is ordinary prose. The exposure is
    bounded by the top
    level being the schema-defined answer slot, so an undetected second verdict
    in prose loses to the verdict the judge actually filed.
    """
    if _count_score_bearing_objects(parsed) > 1:
        return True
    filed = parsed if isinstance(parsed, dict) else {}
    return any(
        _string_contradicts_filed_scores(text, filed)
        for text in _string_values(parsed)
    )


def _peel_one_escape_layer(text: str) -> tuple[str, bool]:
    """Decode one layer of JSON string escaping, reporting whether any applied.

    Decoding only ``\\uXXXX`` is not enough. A value serialized twice spells its
    escapes with a doubled backslash, so ``\\\\u0061`` arrives here with two
    backslashes; a substitution that matches a single one consumes the second
    and leaves ``\\activation_score``, which no further peel can decode and no
    field pattern can match. Handling ``\\\\`` first turns the same input into
    ``\\u0061``, which the next layer decodes to ``a``.

    Handing the string to ``codecs.decode(s, "unicode_escape")`` instead would
    be shorter and wrong: it decodes through latin-1, mangling characters the
    parse already decoded correctly, and raises on invalid escapes that this
    must merely classify.
    """
    out: list[str] = []
    changed = False
    index = 0
    end = len(text)
    while index < end:
        char = text[index]
        if char != "\\" or index + 1 >= end:
            out.append(char)
            index += 1
            continue
        marker = text[index + 1]
        hex_digits = text[index + 2 : index + 6]
        if marker == "u" and _HEX4_RE.match(hex_digits):
            out.append(chr(int(hex_digits, 16)))
            index += 6
            changed = True
        elif marker in _JSON_STRING_ESCAPES:
            out.append(_JSON_STRING_ESCAPES[marker])
            index += 2
            changed = True
        else:
            out.append(char)
            index += 1
    return "".join(out), changed


def _escape_layers(text: str) -> Iterator[tuple[str, bool]]:
    """Yield each decode layer of ``text``, flagging only a truncated walk.

    A parse decodes exactly one layer of escaping. A verdict serialized into a
    string can therefore spell its own field names in escapes and survive the
    parse as literal backslash text, which no pattern for ``"activation_score"``
    will match. Peeling further layers asks the question the parse could not:
    what does this string say once it is fully decoded?

    The second element is True only on the last layer of a walk that ran out of
    budget while more decoding remained. It is not "this layer still decodes",
    which every layer but the last does by construction: a caller refusing on
    that would refuse a judge who merely wrote a Windows path, since ``\\b`` is
    a JSON escape and ``C:\\Users\\bob`` survives a parse carrying one. The flag
    marks the case where the remainder was never read, so a caller can refuse
    what it failed to inspect instead of accepting it by default.
    """
    seen = text
    for _ in range(_MAX_ESCAPE_LAYERS):
        yield seen, False
        peeled, changed = _peel_one_escape_layer(seen)
        if not changed:
            return
        seen = peeled
    yield seen, _peel_one_escape_layer(seen)[1]


def _string_contradicts_filed_scores(text: str, filed: dict[str, Any]) -> bool:
    """Return whether ``text`` names a score field, making the payload unreadable.

    A judge that writes ``I assigned "activation_score": 5 because ...`` while
    filing 5 has restated its answer rather than offering another one, and for
    three rounds this function tried to prove that by comparing the restated
    value to the filed one. Every version of that proof was broken by the next
    adversarial round, because lexical equality over arbitrary prose is not
    equality. Comparing a token accepted ``5 - 1``. Naming the operators that
    could follow a token accepted ``5 ^ 1``, ``5 and 0``, and ``5 if False
    else 1``. Requiring a second digit accepted ``5 - True``, ``5 - len([None])``,
    and ``5 minus one``, since an operand need not be written as a digit; and it
    refused ``5 because all 3 concepts were present``, which is ordinary prose.
    Stripping sentence punctuation read ``5!`` as ``5``. Bounding the run at a
    delimiter let ``5, but corrected it to 1`` end before its own correction.

    So this proves nothing and refuses everything. A decoded layer that names a
    score field is uncomparable, and the payload is treated as ambiguous.

    Refusing is not free, and it is not symmetric with accepting a fabrication
    either: a refusal increments ``judge_failed`` and shrinks a sample count a
    reader can inspect, while a fabrication is an unmarked false observation
    that no reader can distinguish from a real one. The cost here is also
    measured rather than assumed. The archive stores a raw payload for all 288
    samples, successes included, so the measurement is not confined to the
    failures (which is the population limit issue #3998 raises elsewhere).
    Parsing all 288 and walking the strings nested inside them yields 264
    reasoning values, and zero of them name a score field, so this refuses no
    sample any real judge in the archive has produced. It closes an attack
    surface that grew a new hole in each of rounds 19, 20, 21, and 22.

    A truncated decode is likewise a refusal, since the unread remainder could
    name a field by definition.

    There is no exemption here, and an earlier version of this function had one
    that was wrong. ``_string_values`` yields object keys as well as values, so
    once the field pattern stopped requiring quotes, a healthy payload's own
    root key ``activation_score`` reached this check and every healthy payload
    refused. The first repair exempted any string equal to a field name,
    arguing that a string holding only a name holds no number. Round 23 broke
    it in one move: the number does not have to be in the same string. A
    ``{"field": "activation_score", "value": 1}`` record names a competing
    verdict with the name in one slot and the number in its sibling. The skip
    now lives in ``_string_values``, applies to keys only, and leaves every
    value under the refusal, because a key is a schema slot and a value is not.
    """
    for layer, truncated in _escape_layers(text):
        if _NAMED_SCORE_FIELD_RE.search(layer):
            return True
        if truncated:
            return True
    return False


def _names_a_score_field_twice(text: str) -> bool:
    """Return whether any score field name appears more than once in ``text``.

    ``_scan_root_members`` stops at ``reasoning`` because nothing after a
    malformed string can be trusted. That makes it blind to a second copy of a
    score field placed *after* ``reasoning``, so a judge answer of

        {"activation_score": 1, ..., "reasoning": "...",
         "activation_score": 5, ...}

    was salvaged as ``1`` while a lenient parse would have said ``5``. The two
    disagree, which makes the payload ambiguous, and ambiguous payloads are
    refused rather than guessed at.

    Counting raw names is cheap and needs no parse of the untrusted tail. The
    count is of the field spelled as a JSON *key*, quoted, escaped-quoted, or
    single-quoted, not of the bare identifier. A quoted-only count is evaded by
    an escaped one: a payload carrying a second verdict serialized inside a
    string spells its keys with escaped quotes, which
    ``count('"activation_score"')`` does not see. It is evaded again by the
    JSON5/Python dialect, where a second verdict spells its keys
    ``'activation_score':``; salvage exists precisely because the payload is
    malformed, so treating that dialect as absent is unsafe. A bare-identifier
    count closes both but refuses any payload whose prose names a field, and a
    judge that emits its verdict and then explains it in prose ("the
    activation_score reflects...") is plausible output, so the bare count buys
    the same protection at the price of discarding real samples. Matching the
    key shape covers all three spellings and leaves prose alone. A name spelled
    with a unicode escape would still slip the count, so any ``\\u`` in the
    payload refuses outright.

    That ``\\u`` blanket is why this function is no longer the general answer.
    ``json.dumps`` defaults to ``ensure_ascii=True``, so an em-dash or a curly
    quote anywhere in a judge's reasoning is serialized as ``\\uXXXX``. Applying
    the blanket to every payload therefore refuses healthy, strictly-parseable
    verdicts for the crime of containing punctuation. Call this only where the
    exact check cannot run: where a tail follows the object and is never
    parsed, so escapes stay undecoded and structure is unknown. When the parse
    succeeded, ask ``_parsed_names_two_verdicts`` instead, which counts
    score-bearing objects and scans *decoded* strings and needs no blanket.

    A refusal costs a sample while a fabrication costs a published number, so
    the blanket stays where the payload is already malformed.
    """
    if "\\u" in text:
        return True
    return any(len(pattern.findall(text)) > 1 for pattern in _KEY_SHAPED_SCORE_FIELDS)


def _fenced_blocks(text: str) -> tuple[list[str], bool] | None:
    """Return *text*'s fenced blocks and whether they were all of it.

    The second element is ``True`` when nothing but whitespace sat outside the
    fences. The caller needs it because "exactly one fence" is not the same
    claim as "exactly one candidate": a payload can hold one fenced block and
    still carry a competing verdict in the prose around it.

    Refuses (``None``) on an unterminated fence rather than treating the rest
    of the payload as a body: a truncated judge response would otherwise hand
    back whatever prose followed the opening run.

    A closing run must be at least as wide as the one that opened the block
    and may hold nothing else, which is the CommonMark rule. That is what lets
    a four-backtick fence carry a three-backtick run in its body.
    """
    lines = text.splitlines()
    blocks: list[str] = []
    outside_is_blank = True
    index = 0
    while index < len(lines):
        opening = _FENCE_OPEN_RE.fullmatch(lines[index])
        if opening is None:
            if lines[index].strip():
                outside_is_blank = False
            index += 1
            continue
        closing = re.compile(r"`{" + str(len(opening.group(1))) + r",}[ \t]*")
        index += 1
        body: list[str] = []
        while index < len(lines) and closing.fullmatch(lines[index]) is None:
            body.append(lines[index])
            index += 1
        if index == len(lines):
            return None
        blocks.append("\n".join(body))
        index += 1
    return blocks, outside_is_blank


def _unwrap_lone_fence(text: str) -> str | None:
    """Return the body of the payload's only Markdown fence, or ``None``.

    A judge told to answer in JSON sometimes wraps the object in a fence. The
    unwrap is safe only when there is nothing to choose between. The defect
    class this file keeps hitting is *selection*: a search returning a
    candidate that was not the judge's answer. ``re.search`` for a fence
    selected the first one and replaced the whole payload with it, so a
    verdict followed by a fenced rubric exemplar was answered with the
    exemplar, and the substitution happened before both the offset-zero anchor
    and the duplicate-name guard could see the real payload. That was the
    thirteenth defect of the class.

    Requiring exactly one fence removes the choice *among fences*. It does not
    remove the choice between the fence and the prose around it, which was the
    sixteenth defect: a payload whose unfenced text held the real verdict and
    whose single fenced block held a rubric exemplar the judge had explicitly
    labelled as one was answered with the exemplar. Unwrapping is only ever
    justified when the fence is the whole payload, so anything but whitespace
    outside it refuses too. Found by adversarial review round 13.

    The close is paired to the width of the run that opened it, per CommonMark.
    Matching a bare three-backtick run instead closed a four-backtick fence at
    the first inner run, and a judge reaches for four backticks precisely
    because its own reasoning quotes a three-backtick block, so the body came
    back truncated and unparseable. That failed in the safe direction, but it
    is still a lost sample. Pairing by width does not restore any selection:
    every block in the payload is still collected, and anything other than
    exactly one still refuses. Found by adversarial review round 12.
    """
    scan = _fenced_blocks(text)
    if scan is None:
        return None
    bodies, outside_is_blank = scan
    if not outside_is_blank or len(bodies) != 1:
        return None
    return bodies[0].strip()


def _recover_verdict(text: str) -> str | None:
    """Return JSON text holding the judge's verdict, or ``None`` to refuse.

    Runs only after the whole payload failed to parse.

    Each branch checks for a second verdict with the sharpest instrument it
    can. ``_unwrap_lone_fence`` already refuses unless nothing but whitespace
    sits outside the fence, so a successful unwrap means the fence body is the
    whole payload: it parses, its escapes are decoded, and the exact structural
    check applies. Running the raw count on the original payload there would
    add nothing except its ``\\u`` blanket, which refuses a healthy fenced
    verdict whose reasoning contains an em-dash. ``_extract_json_object``
    applies its own guard, and keeps the raw count when text follows the
    object, because that tail is never parsed.
    """
    fenced = _unwrap_lone_fence(text)
    if fenced is not None:
        try:
            parsed = _strict_json_loads(fenced)
        except ValueError:
            return None
        return None if _parsed_names_two_verdicts(parsed) else fenced
    return _extract_json_object(text)


def _complete_verdict(members: dict[str, str] | None) -> dict[str, int] | None:
    """Return the three scores when ``members`` carries a whole valid verdict.

    Returns ``None`` when any field is absent, is not a JSON integer, or falls
    outside 1-5, so a partial object (a tool trace naming one field) is not a
    candidate and cannot compete with the real answer.
    """
    if members is None:
        return None
    verdict: dict[str, int] = {}
    for field in _SCORE_FIELDS:
        raw = members.get(field)
        if raw is None or not _JSON_INT_RE.match(raw):
            return None
        value = int(raw)
        if value not in _SCORE_RANGE:
            return None
        verdict[field] = value
    return verdict


def _salvage_scores(text: str) -> dict[str, int] | None:
    """Recover the three numeric scores from judge output that will not parse.

    The eval scores on three numbers. ``reasoning`` is diagnostic only, yet it
    is the field that breaks the parse: judges routinely quote the response
    they are grading, and an unescaped quote inside that prose invalidates the
    whole object. Discarding the cell then throws away scores the judge stated
    plainly, and it does so more often for verbose models, which biases the
    comparison the eval exists to make.

    Five conditions, all required, so a salvage cannot invent a score:

    1. The payload *begins* with the object, ignoring leading whitespace. This
       is the load-bearing one, and it replaces every prior attempt to search
       out the right candidate. See ``_salvage_anchor``.
    2. No score field name appears twice anywhere in the payload, which is the
       only way to see a duplicate placed after the unreadable tail. See
       ``_names_a_score_field_twice``.
    3. All three fields are depth-1 members of that one object, with no
       repeated key inside the readable prefix.
    4. Each value matches the JSON integer grammar in full. ``4.5``, ``5e-1``,
       ``05``, and ``5junk`` all fail rather than being read as ``4`` or
       ``5``, which would be fabrication.
    5. Each value is in 1-5. Salvage runs *after* ``_judge_score_shape_error``
       has already rejected the payload, so deferring range to that checker
       re-admits exactly what it just refused: a judge answer of ``6`` came
       back as a clean ``5`` once ``_clamp_score`` was through with it.

    Conditions 1 and 2 replaced a walk over root-level objects that accepted
    whichever one carried a complete verdict. That walk, and the two rewrites
    before it, each defined "root" by counting braces, so an object inside a
    top-level array qualified and ``[{...exemplar...}]`` was returned as the
    judge's answer. Bracket-blindness was the eighth defect of this class in
    seven review rounds; the pattern is the search itself, not any one of its
    disqualifiers.

    **Known limitations, both deliberate.** Scores must precede ``reasoning``,
    and the verdict must lead the payload. JSON requires neither. Both refuse
    rather than guess, because a refusal discards one of three judge samples
    while a wrong guess silently corrupts a published number.
    """
    if _names_a_score_field_twice(text):
        return None
    start = _salvage_anchor(text)
    if start is None:
        return None
    return _complete_verdict(_scan_root_members(text, start))


def _judge_parse_failure(text: str, reason: str) -> dict[str, Any]:
    """Build a failed-judge record, salvaging scores when they are recoverable."""
    salvaged = _salvage_scores(text)
    if salvaged is not None:
        return {
            "activation_score": _clamp_score(salvaged["activation_score"]),
            "citation_score": _clamp_score(salvaged["citation_score"]),
            "behavior_score": _clamp_score(salvaged["behavior_score"]),
            "reasoning": f"scores salvaged from unparseable judge output: {reason}",
            "judge_failed": False,
            "judge_salvaged": True,
        }
    return _failed_judge(reason)


def _failed_judge(reason: str) -> dict[str, Any]:
    return {
        "activation_score": 0,
        "citation_score": 0,
        "behavior_score": 0,
        "reasoning": reason,
        "judge_failed": True,
    }


def _judge_score_shape_error(parsed: dict[str, Any]) -> str | None:
    required_fields = ("activation_score", "citation_score", "behavior_score")
    missing = [field for field in required_fields if field not in parsed]
    if missing:
        return f"judge returned missing score field(s): {', '.join(missing)}"
    for field in required_fields:
        value = parsed[field]
        if not isinstance(value, int) or isinstance(value, bool):
            return (
                f"judge returned non-integral {field}: "
                f"{type(value).__name__}"
            )
        if value not in _SCORE_RANGE:
            return f"judge returned out-of-range {field}: {value!r}"
    return None



# ---------------------------------------------------------------------------
# Eval driver
# ---------------------------------------------------------------------------


def _prompt_collapses_to_baseline(
    mechanism: str, system: str, rule: dict[str, str], rule_id: str
) -> bool:
    """True when this mechanism hands the model the baseline prompt.

    A target with no description produces an empty description prompt, which
    is the baseline prompt, so the two mechanisms put identical text in front
    of the model. Scoring that cell publishes a description average, a gap
    against baseline and a candidate for best mechanism, all describing a
    treatment the target never received. The gap is then whatever the two
    identical runs happened to differ by, and a large enough coin flip
    certifies a rule the model never saw. Nineteen of this repository's
    twenty five rule targets carry no description, so this is the common case
    rather than an edge.

    Written as a comparison against the baseline prompt rather than a test for
    emptiness so it keeps holding if baseline ever carries text.

    This sees only what `build_system_prompt` produced. A non-routed rule with
    an empty body produces an empty `full` prompt, so it declines here. A routed
    target has `skill_name` and can still resolve real reference content, so the
    prompt builder preserves that path.
    """
    if mechanism == "baseline":
        return False
    return system == build_system_prompt("baseline", rule, rule_id)


def _declined_cell(system: str) -> dict[str, Any]:
    """A cell the run declined to measure, and the reason.

    `graded` False is the existing spelling for a cell carrying no usable
    measurement, and it deliberately does not set `judge_failed`: the judge
    did not fail, it was never asked. Marking it as a judge error would report
    a broken instrument for what is a property of the target.

    Named `declined` rather than `unreachable` because the summary already
    publishes `unreachable_mechanisms`, and that field means something else:
    it lists the mechanisms the routing gate excluded, which today is `full`
    on a routed target. A cell declined here is not in that list, it drops out
    of its mechanism's average and surfaces through
    `best_mechanism_unmeasured`. One word covering both exclusions would send
    a reader to the wrong field to find this one.
    """
    return {
        "response_preview": "(not called: prompt identical to baseline)",
        "scores": {"graded": False},
        "declined": "prompt identical to baseline",
        "system_prompt_chars": len(system),
    }


def eval_one_scenario(
    api_key: str,
    rule: dict[str, str],
    rule_id: str,
    scenario: dict[str, Any],
    model: str,
    dry_run: bool,
    seed: int | None = None,
    judge_repeats: int = DEFAULT_JUDGE_REPEATS,
    judge_reducer: str = DEFAULT_JUDGE_REDUCER,
) -> dict[str, Any]:
    """Run all mechanisms on one scenario."""
    result: dict[str, Any] = {
        "id": scenario["id"],
        "desc": scenario.get("desc", ""),
        "negative_case": _is_negative_gate(scenario.get("expected_gate")),
        "mechanisms": {},
    }

    for mechanism in MECHANISMS:
        system = build_system_prompt(mechanism, rule, rule_id)
        if _prompt_collapses_to_baseline(mechanism, system, rule, rule_id):
            result["mechanisms"][mechanism] = _declined_cell(system)
            continue
        routing: dict[str, Any] | None = None
        if dry_run:
            result["mechanisms"][mechanism] = {
                "response_preview": "(dry-run, no API call)",
                "scores": {"activation_score": 0, "citation_score": 0, "behavior_score": 0},
                "score_samples": [],
                "judge_repeats": judge_repeats,
                "score_reducer": judge_reducer,
                "system_prompt_chars": len(system),
            }
            continue

        try:
            metadata: dict[str, object] = {}
            if mechanism == "description" and rule.get("skill_name"):
                route_response = _call_api(
                    api_key,
                    [{"role": "user", "content": build_skill_route_prompt(rule, scenario)}],
                    system=system,
                    model=model,
                    max_tokens=300,
                    seed=seed,
                    metadata=metadata,
                )
                parsed_route = _parse_json_object(route_response)
                if parsed_route is None:
                    result["mechanisms"][mechanism] = {
                        "error": "route parse failure",
                        "response_preview": route_response[:400]
                        + ("..." if len(route_response) > 400 else ""),
                        "scores": {"activation_score": 0, "citation_score": 0, "behavior_score": 0},
                        "routing": {
                            "selected_skill": None,
                            "selected_reference": None,
                            "route_failed": True,
                            "reference_matched": False,
                        },
                    }
                    continue
                selected_skill = parsed_route.get("selected_skill")
                selected_reference = _normalize_selected_reference(
                    parsed_route.get("selected_reference")
                )
                routing = {
                    "selected_skill": selected_skill if isinstance(selected_skill, str) else None,
                    "selected_reference": selected_reference,
                    "route_failed": False,
                    # One skill router fronts many sibling references, and a
                    # sibling resolves for this target as readily as the target
                    # does. Without this the score a sibling earned is published
                    # under a reference the run never opened.
                    "reference_matched": (
                        selected_reference is not None
                        # A route that declined the skill still resolves a
                        # reference, because resolution reads `skill_path` off
                        # the target and never consults `selected_skill`.
                        # Counting a decline as a match credits the description
                        # mechanism with a route it refused to make. The name
                        # itself is not compared: no archived run records
                        # `selected_skill`, so there is no evidence about how
                        # models spell it, and a miscalibrated name check would
                        # flag every routed cell.
                        and isinstance(selected_skill, str)
                        and bool(selected_skill.strip())
                        and selected_reference
                        == _normalize_selected_reference(rule.get("reference_path"))
                    ),
                    "reasoning": str(parsed_route.get("reasoning", ""))[:300],
                }
                system = _build_routed_reference_prompt(rule, selected_reference)
                metadata = {}
            response = _call_api(
                api_key,
                [{"role": "user", "content": scenario["input"]}],
                system=system,
                model=model,
                max_tokens=600,
                seed=seed,
                metadata=metadata,
            )
        except RuntimeError as e:
            result["mechanisms"][mechanism] = {
                "error": str(e),
                "scores": {"activation_score": 0, "citation_score": 0, "behavior_score": 0},
            }
            continue

        time.sleep(RATE_LIMIT_SLEEP_SEC)
        score_samples: list[dict[str, Any]] = []
        for sample_index in range(judge_repeats):
            judge_seed = None if seed is None else seed + sample_index + 1
            try:
                sample = score_response(
                    api_key, scenario, response, model=model, seed=judge_seed
                )
            except RuntimeError as e:
                sample = {
                    "judge_failed": True,
                    "reasoning": f"judge API failure: {e}",
                    "sample_index": sample_index,
                }
            else:
                sample["sample_index"] = sample_index
            score_samples.append(sample)
            time.sleep(RATE_LIMIT_SLEEP_SEC)
        scores = _reduce_score_samples(score_samples, judge_reducer)
        mechanism_result = {
            "response_preview": response[:400] + ("..." if len(response) > 400 else ""),
            "scores": scores,
            "score_samples": score_samples,
            "judge_repeats": judge_repeats,
            "score_reducer": judge_reducer,
            "system_prompt_chars": len(system),
        }
        if routing is not None:
            mechanism_result["routing"] = routing
        fingerprint = metadata.get("system_fingerprint")
        if isinstance(fingerprint, str):
            mechanism_result["system_fingerprint"] = fingerprint
        result["mechanisms"][mechanism] = mechanism_result
    return result


def _is_valid_score(value: object) -> bool:
    """True when `value` is a real number the 1 to 5 judge rubric can express.

    Rejects `bool` explicitly: `True` is an `int` in Python and would otherwise
    read as a score of 1. Rejects NaN and the infinities, which survive an
    `isinstance` check but make every threshold comparison meaningless.

    The finiteness question is asked of floats only. An `int` is finite by
    construction, and `math.isfinite` reaches it by converting to `float`,
    which raises `OverflowError` on a value too large to convert. JSON admits
    arbitrary-precision integer literals, so a damaged artifact can carry one.
    Asking would turn an off-rubric cell into a crash, which is the opposite
    of what this predicate exists to do: report the cell as unmeasured. The
    bounds comparison below needs no such guard, because Python compares an
    `int` to a `float` exactly rather than converting either side.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return MIN_RUBRIC_SCORE <= value <= MAX_RUBRIC_SCORE


def _scenario_score_triple(
    scenario: dict[str, Any], mech: str
) -> tuple[float | None, bool, bool]:
    """Return (cell_score, judge_failed, legacy_reduced) for one cell.

    Returns `None` for the score when the cell carries no usable measurement:
    the judge never graded it, or the stored number is not on the rubric.
    `None` means "no measurement", which is different from a measured zero;
    callers must exclude it from the average instead of averaging in a number
    the judge never produced.

    Prefers `cell_score`, which reduces each judge sample to a scalar before
    reducing across samples. Artifacts written before that field existed carry
    only the per-field reduction, so those fall back to averaging the triple and
    report `legacy_reduced=True`. That reproduces the number the run published
    rather than silently restating an archived result under a rule it was not
    computed with, and the flag keeps the substitution visible to the caller.

    A `cell_score` that is present but off-rubric is a damaged artifact, not a
    legacy one. Falling back there would restate a corrupt cell under a second
    reduction rule and hide the damage, so the cell is reported as unmeasured.
    """
    mech_data = scenario["mechanisms"].get(mech, {})
    sc = mech_data.get("scores", {})
    failed = bool(sc.get("judge_failed")) or "error" in mech_data
    ungraded = "error" in mech_data or sc.get("graded") is False
    if ungraded:
        return None, failed, False
    if "cell_score" in sc:
        # Presence is the signal, not the value. `_reduce_score_samples` writes
        # this key only on a graded cell and always from a reducer over a
        # non-empty list, so it never emits null. A present null therefore came
        # from something other than the writer, which makes it damage in the
        # same way an off-rubric number is. Falling back to the triple there
        # would restate a corrupt cell under a second reduction rule and label
        # it legacy, which is a claim about the artifact's age that is false.
        cell = sc["cell_score"]
        if _is_valid_score(cell):
            return float(cell), failed, False
        return None, failed, False
    triple = [sc.get(key) for key in _SCORE_KEYS]
    if not all(_is_valid_score(value) for value in triple):
        return None, failed, False
    return sum(triple) / len(_SCORE_KEYS), failed, True


def _route_missed_target(scenario: dict[str, Any], mech: str) -> bool:
    """True when this cell's router did not open the target reference.

    Absence and a recorded unknown are different facts. A cell written before
    the flag existed carries no evidence either way, so it counts zero and an
    archived run reproduces unchanged. A cell that carries the key with
    something other than a boolean recorded a route result the run could not
    read, and reading that for truth turns it into a clean route: `None is
    False` is False, and so is `"false" is False`, so a damaged record and a
    recorded miss both certify the route they failed to make. Refuse instead,
    because a refusal is visible where a fabricated match is not.

    The same split applies one level up, to the routing block itself. A cell
    with no `routing` key is the archived shape and counts zero. A cell whose
    `routing` is present but is not a mapping recorded a route the run cannot
    read, and treating that as absence hands it the same silence a legacy
    record earns, so the score is published under the target reference with
    no evidence the reference was opened. All 96 cells in the archived record
    carry no `routing` key at all, so refusing here moves no stored number.
    """
    mech_data = scenario["mechanisms"].get(mech, {})
    if "routing" not in mech_data:
        return False
    routing = mech_data["routing"]
    if not isinstance(routing, dict):
        raise ValueError(
            f"mechanisms[{mech}].routing must be a mapping, "
            f"got {type(routing).__name__} {routing!r}"
        )
    if "reference_matched" not in routing:
        return False
    matched = routing["reference_matched"]
    if not isinstance(matched, bool):
        raise ValueError(
            f"mechanisms[{mech}].routing.reference_matched must be a boolean, "
            f"got {type(matched).__name__} {matched!r}"
        )
    return not matched


def _incomplete_mechanisms(
    per_mech: dict[str, dict[str, Any]], mechs: list[str], pool_size: int
) -> list[str]:
    """Mechanisms whose average rests on fewer cells than the pool holds.

    An average over a subset of a pool, published beside a verdict that names
    the whole pool, is a number attached to a population it was never computed
    over. That is the defect this instrument keeps re-growing, so the check
    lives in one place and both pools call it.
    """
    return sorted(m for m in mechs if _graded_count(per_mech[m]) < pool_size)


def _mechanism_summary(
    pool: list[dict[str, Any]], mech: str
) -> dict[str, Any]:
    """Compute avg_score over the graded scenarios for one mechanism."""
    scores: list[float] = []
    failures = 0
    legacy = 0
    route_missed = 0
    for s in pool:
        score, failed, legacy_reduced = _scenario_score_triple(s, mech)
        if _route_missed_target(s, mech):
            route_missed += 1
        if score is not None:
            scores.append(score)
        if failed:
            failures += 1
        if legacy_reduced:
            legacy += 1
    # None rather than 0.0 when nothing graded. A 0.0 reads as a real score
    # in every consumer: it becomes a published average, a delta against
    # baseline, and a candidate for best_mechanism, none of which any
    # observation supports. An absent number has to be handled; a zero does
    # not, so it travels silently into the table.
    avg = round(sum(scores) / len(scores), 2) if scores else None
    return {
        "avg_score": avg,
        # The published average is rounded, and archived runs recorded it that
        # way, so it cannot gain precision without breaking replay. A gate that
        # reads it inherits the rounding: a restraint average of 3.4991 is
        # published as 3.5, and `3.5 < 3.5` is false, so a measurement below the
        # floor is certified as clearing it. Keep the measured value beside the
        # published one and let the gates read this.
        "avg_score_exact": (sum(scores) / len(scores)) if scores else None,
        "scenario_count": len(pool),
        "graded_count": len(scores),
        "judge_failures": failures,
        "legacy_reduced_count": legacy,
        "route_mismatch_count": route_missed,
    }


def _dropped_candidates(
    per_mech: dict[str, Any], candidates: list[str]
) -> tuple[list[str], list[str]]:
    """Split the candidates a ranking passed over by why each fell out.

    Partial coverage and no coverage are different things to go fix, so they
    are returned separately rather than as one "not eligible" bucket.
    """
    partial = [
        m
        for m in candidates
        if per_mech[m]["avg_score"] is not None and not _fully_graded(per_mech[m])
    ]
    unmeasured = [m for m in candidates if per_mech[m]["avg_score"] is None]
    return partial, unmeasured


def _require_boolean_pool_markers(scenarios: list[dict[str, Any]]) -> None:
    """Refuse a scenario whose pool marker is not a boolean.

    The marker is read for truth, so a non-boolean silently decides a
    scenario's population: the string "false" is truthy and files a restraint
    case among the positives. Every number the run then publishes is attached
    to a pool the scenario does not belong to, and nothing in the output says
    so. The grader in this module always writes a boolean, but `aggregate` is
    also handed scenario records parsed from a stored file, and a refusal here
    is visible where a mis-split is not.
    """
    for idx, scenario in enumerate(scenarios):
        marker = scenario["negative_case"]
        if not isinstance(marker, bool):
            raise ValueError(
                f"scenarios[{idx}].negative_case must be a boolean, got "
                f"{type(marker).__name__} {marker!r}"
            )


def aggregate(scenarios: list[dict[str, Any]], routed: bool = False) -> dict[str, Any]:
    """Aggregate per-mechanism averages across scenarios.

    `routed` marks a progressive-disclosure target (a skill reference), where
    the `full` mechanism force-injects the reference that routing exists to
    keep out of context. That treatment is a diagnostic, not a reachable
    deployment, so the restraint gate below reads only the routed surface for
    those targets. An always-on rule ships its whole body, so every
    rule-enhanced mechanism is reachable and all of them gate.

    Averages only the scenarios the judge actually graded. Ungraded cells are
    excluded rather than counted as zero: a zero is a measurement, and folding
    a non-measurement in as one biases the mean toward whichever mechanism
    happened to fail more often, which can invert the ranking outright.

    This does not soften the failure signal. `judge_failures` still counts
    every failure and any non-zero count still forces the FAIL_JUDGE_ERRORS
    verdict below, so a broken judge can never yield a PASS. `graded_count`
    exposes how many scenarios each average actually rests on.
    """
    summary: dict[str, Any] = {"per_mechanism": {}, "negative_case_per_mechanism": {}}
    _require_boolean_pool_markers(scenarios)
    pos_scenarios = [s for s in scenarios if not s["negative_case"]]
    neg_scenarios = [s for s in scenarios if s["negative_case"]]

    for mech in MECHANISMS:
        summary["per_mechanism"][mech] = _mechanism_summary(pos_scenarios, mech)
        summary["negative_case_per_mechanism"][mech] = _mechanism_summary(
            neg_scenarios, mech
        )

    baseline_avg = _gate_avg(summary["per_mechanism"]["baseline"])
    desc_avg = _gate_avg(summary["per_mechanism"]["description"])

    # A routed target performs no `full` treatment, so it is a candidate for
    # nothing: not the ranking, not the record of what the ranking dropped.
    # Reachability is derived once here so both read the same population. Rank
    # it and the table names a best the operator cannot adopt, on the same
    # screen as the caveat calling it unreachable.
    measured_mechs = [m for m in MECHANISMS if not (routed and m == "full")]
    # `description` is the progressive-disclosure gate. The `full` mechanism is
    # retained only as a diagnostic ceiling and cannot rescue a failed front door.
    rule_enhanced = [m for m in measured_mechs if m != "baseline"]
    # Ranking two mechanisms is the same comparison a delta makes, so it needs
    # the same footing: both averages must cover the whole pool. A mechanism
    # graded on one lucky scenario would otherwise take the headline from a
    # mechanism graded on all of them, and the table would refuse that same
    # comparison one line later as a delta.
    best_mech = max(
        (m for m in rule_enhanced if _fully_graded(summary["per_mechanism"][m])),
        key=lambda m: _graded_avg(summary["per_mechanism"][m]),
        default=None,
    )
    best_avg = summary["per_mechanism"][best_mech]["avg_score"] if best_mech else None
    # Distinguish "no rule-enhanced mechanism was graded" from "none was graded
    # completely". Both leave the headline empty and they are not the same
    # problem to go fix. Both states are read off `rule_enhanced` alone, so
    # neither says anything about `baseline`: a run can grade `baseline` fully
    # and still reach either one.
    summary["best_mechanism_partial"] = best_mech is None and any(
        summary["per_mechanism"][m]["avg_score"] is not None for m in rule_enhanced
    )

    total_judge_failures = sum(
        summary["per_mechanism"][m]["judge_failures"] for m in MECHANISMS
    ) + sum(
        summary["negative_case_per_mechanism"][m]["judge_failures"]
        for m in MECHANISMS
    )
    # `total_judge_failures` stays the whole-run count, because it is the
    # published record of how the judge behaved. The verdict reads a narrower
    # count: for a routed target `full` is a treatment no deployment performs,
    # so a judge error there says nothing about a surface a user can reach.
    # Failing on it would fail a rule for a broken measurement of something
    # that is not shipped. The two counts are equal whenever nothing is
    # excluded, which is every always-on rule.
    # The negative pool is counted over the mechanisms that actually gate it,
    # not over every measured one. `baseline` carries no rule, so a broken
    # judgement of what the baseline did on a negative case says nothing about
    # the rule and must not fail it. That exclusion is already stated for the
    # restraint floor below; counting failures over a wider set than the floor
    # reads them off contradicted it.
    neg_gate_mechs = ["description"] if routed else [m for m in MECHANISMS if m != "baseline"]
    gating_judge_failures = sum(
        summary["per_mechanism"][m]["judge_failures"] for m in measured_mechs
    ) + sum(
        summary["negative_case_per_mechanism"][m]["judge_failures"]
        for m in neg_gate_mechs
    )

    summary["best_mechanism"] = best_mech
    summary["best_avg_score"] = best_avg
    summary["baseline_avg"] = _round_or_none(baseline_avg)
    pos_cells = summary["per_mechanism"]
    summary["delta_full_vs_baseline"] = _delta(pos_cells["full"], pos_cells["baseline"])
    summary["delta_description_vs_baseline"] = _delta(
        pos_cells["description"], pos_cells["baseline"]
    )
    for mech_name in ("full", "description"):
        summary[f"delta_{mech_name}_vs_baseline_measured"] = _delta_measured(
            pos_cells[mech_name], pos_cells["baseline"]
        )
    summary["delta_rounding_disagrees"] = any(
        summary[f"delta_{mech_name}_vs_baseline"]
        != summary[f"delta_{mech_name}_vs_baseline_measured"]
        for mech_name in ("full", "description")
    )

    summary["total_judge_failures"] = total_judge_failures
    # Name the cells whose failures no gate reads. Deriving this in the
    # renderer instead would let the disclosure drift from the exclusion, which
    # is how the negative-baseline exclusion shipped silent in the first place.
    excluded_cells: list[str] = []
    for pool_label, pool_key, gating in (
        ("positive", "per_mechanism", measured_mechs),
        ("negative", "negative_case_per_mechanism", neg_gate_mechs),
    ):
        for mech in MECHANISMS:
            ungated = mech not in gating
            if ungated and summary[pool_key][mech]["judge_failures"]:
                excluded_cells.append(f"{pool_label} {mech}")
    summary["excluded_judge_failure_cells"] = excluded_cells
    summary["gating_judge_failures"] = gating_judge_failures
    summary["unreachable_mechanisms"] = [
        m for m in MECHANISMS if m not in measured_mechs
    ]
    # "Best" is a superlative over a population even though it prints one
    # name. Any candidate the ranking dropped has to be named, or a table row
    # scoring above the winner reads as a broken ordering. Partial coverage
    # and no coverage are different things to go fix, so they are published
    # separately. `rule_enhanced` is already narrowed to what the target can
    # reach, which is what keeps this list and the ranking on one population.
    (
        summary["best_mechanism_excluded"],
        summary["best_mechanism_unmeasured"],
    ) = _dropped_candidates(summary["per_mechanism"], rule_enhanced)

    # Negative scenarios were measured but never gated: a rule that fired on
    # every case it was written to stay out of still returned PASS. Their
    # rubric is inverted (5 = correctly did not activate), so the gate is a
    # FLOOR and a low score is the failure.
    #
    # The positive gate reads `description` alone so `full` cannot rescue a
    # broken front door. The negative gate reads the WORST mechanism the target
    # can actually reach in deployment: a benefit has to be earned at the front
    # door, a harm counts wherever a real user could meet it. `baseline` is
    # excluded because it carries no rule, so what it does is not the rule's
    # doing. For a routed target `full` is excluded too, because force-injecting
    # a reference is a measurement treatment no deployment performs.
    #
    # Only mechanisms whose negative cell covers the whole pool contribute. The
    # floor is a threshold on the average restraint across the negative
    # scenarios, so an average over a subset is not the quantity the floor
    # names. Gating on a subset made the verdict turn on which scenarios
    # happened to grade: one cell scoring 1.0 with the rest ungraded averaged
    # 1.0 and failed, while that same 1.0 beside two 5.0s averaged 3.67 and
    # passed. Requiring the whole pool does not hide that harm, it renames it:
    # `negative_gate_incomplete` is non-empty in exactly that case, so the run
    # reports FAIL_NEGATIVE_INCOMPLETE instead of claiming a measurement it
    # does not have. `_fully_graded` implies a non-empty pool, so a suite with
    # no negative scenarios still reports that it measured none rather than
    # failing every rule in it.
    gate_mechs = neg_gate_mechs
    gate_cells = {m: summary["negative_case_per_mechanism"][m] for m in gate_mechs}
    # `_fully_graded` already implies a measured average, so the None filter is
    # a type guard rather than a behavior change.
    gate_avgs = (_gate_avg(c) for c in gate_cells.values() if _fully_graded(c))
    graded_neg = [avg for avg in gate_avgs if avg is not None]
    worst_neg_avg = min(graded_neg) if graded_neg else None
    # `round` is monotone, so the minimum of the rounded values and the rounded
    # minimum are the same number. The published field is unchanged; only the
    # value the floor is compared against gained its measured precision.
    summary["worst_negative_avg"] = (
        None if worst_neg_avg is None else round(worst_neg_avg, 2)
    )
    # Name the population the number was read off. An average over a subset of
    # the negative scenarios, reported as if it covered them all, is the defect
    # this whole change exists to remove.
    summary["negative_gate_mechanisms"] = gate_mechs
    summary["negative_gate_incomplete"] = _incomplete_mechanisms(
        summary["negative_case_per_mechanism"], gate_mechs, len(neg_scenarios)
    )
    # Name which mechanism produced the worst average and how many cells it
    # rests on. `worst_negative_avg` is a min across mechanisms that need not
    # have graded the same scenarios, so the number alone does not say what it
    # covers, and a reader cannot recover it from the verdict.
    # Keyed on the measured average because `worst_negative_avg` is the
    # measured minimum. Ranking on the published 2dp value lets two mechanisms
    # tie there while differing in measurement, and the label then names a
    # mechanism the published number did not come from.
    worst_neg_mech = min(
        (m for m in gate_mechs if _fully_graded(gate_cells[m])),
        key=lambda m: _graded_avg(gate_cells[m]),
        default=None,
    )
    # The floor is read over the fully graded gate cells only, so the gate
    # mechanism list no longer names the population behind the number. Publish
    # the eligible set beside it, and whether any gate cell was graded but not
    # completely, so an absent floor distinguishes "nothing graded" from
    # "nothing graded on every negative scenario". This mirrors
    # `best_mechanism_partial` on the positive side.
    summary["negative_floor_mechanisms"] = [
        m for m in gate_mechs if _fully_graded(gate_cells[m])
    ]
    summary["negative_floor_partial"] = not summary[
        "negative_floor_mechanisms"
    ] and any(_graded_count(gate_cells[m]) > 0 for m in gate_mechs)
    summary["worst_negative_mechanism"] = worst_neg_mech
    summary["worst_negative_graded"] = (
        _graded_count(gate_cells[worst_neg_mech]) if worst_neg_mech else 0
    )

    # The positive verdict is read off `description` and `baseline`, so those
    # are the two that must be fully measured. The same partial-pool hole the
    # negative gate just closed was open here: an off-rubric positive cell is
    # dropped from the average without setting `judge_failed`, so a PASS could
    # be published over a subset of the scenarios the verdict names.
    pos_gate_mechs = ["baseline", "description"]
    summary["positive_gate_mechanisms"] = pos_gate_mechs
    summary["positive_gate_incomplete"] = _incomplete_mechanisms(
        summary["per_mechanism"], pos_gate_mechs, len(pos_scenarios)
    )

    # Derived once here and read by both the verdict and the caveat, so the
    # number a reader sees and the number that decides the run cannot drift.
    # Positive pool only: on a negative case the router is supposed to decline,
    # so a miss there is correct restraint rather than a defect. Measured
    # mechanisms only: a routed target cannot reach `full`, and its scores are
    # already excluded from every average and every gate, so counting a miss
    # there would let a mechanism the target cannot reach decide the run and
    # would put the caveat on a different population than the scores it
    # explains.
    summary["positive_route_mismatches"] = sum(
        summary["per_mechanism"][m].get("route_mismatch_count", 0)
        for m in measured_mechs
    )

    common = {
        "gating_judge_failures": gating_judge_failures,
        "has_positive_cases": bool(pos_scenarios),
        "has_negative_cases": bool(neg_scenarios),
    }
    summary["verdict"] = _decide_verdict(
        summary,
        worst_neg_avg=worst_neg_avg,
        desc_avg=desc_avg,
        baseline_avg=baseline_avg,
        **common,
    )
    # The table prints the rounded averages, so a reader who checks the verdict
    # against them can reach a different answer than the run did whenever a
    # threshold sits inside the rounding window. Decide again on the printed
    # numbers and record the disagreement rather than leaving the reader to
    # conclude the instrument is broken.
    summary["rounding_would_change_verdict"] = summary["verdict"] != _decide_verdict(
        summary,
        worst_neg_avg=_round_or_none(worst_neg_avg),
        desc_avg=_round_or_none(desc_avg),
        baseline_avg=_round_or_none(baseline_avg),
        **common,
    )

    return summary


def _round_or_none(value: float | None) -> float | None:
    """Round to the precision the table prints, preserving an absent value."""
    return None if value is None else round(value, 2)


def _gate_avg(cell: dict[str, Any]) -> float | None:
    """The average a gate compares, at the precision it was measured.

    Falls back to the published 2dp value for any cell that lacks the measured
    one. Every cell this module builds carries both, and replay rebuilds each
    summary from the stored cells rather than reading the archived summary, so
    the fallback covers a cell handed in from elsewhere rather than the
    archived-replay path.
    """
    exact = cell.get("avg_score_exact")
    return cell.get("avg_score") if exact is None else exact


def _graded_avg(cell: dict[str, Any]) -> float:
    """The measured average of a cell the caller has already found graded.

    `_fully_graded` requires a non-null published average, and `_gate_avg`
    returns that value when the measured one is absent, so a graded cell
    always has an average. Raising rather than substituting a default keeps a
    broken invariant visible instead of ranking a mechanism at zero.
    """
    avg = _gate_avg(cell)
    if avg is None:
        raise AssertionError("a fully graded cell must carry an average")
    return avg


def _fully_graded(cell: dict[str, Any]) -> bool:
    """Whether a cell's average covers every scenario in its pool."""
    return (
        cell.get("avg_score") is not None
        and _graded_count(cell) == cell.get("scenario_count")
    )


def _delta(treatment: dict[str, Any], control: dict[str, Any]) -> float | None:
    """A difference is only measured where both sides cover the same pool.

    Subtracting a mean over 2 scenarios from a mean over 1 produces a number
    that describes neither. With `baseline` graded 1/2 at 1.0 and
    `description` graded 2/2 at 3.0, the published delta was 2.0 while the
    only scenario both actually measured differed by 4.0. Both sides must
    cover their whole pool, not merely be non-null.
    """
    if not _fully_graded(treatment) or not _fully_graded(control):
        return None
    treatment_avg: float = treatment["avg_score"]
    control_avg: float = control["avg_score"]
    return round(treatment_avg - control_avg, 2)


def _delta_measured(treatment: dict[str, Any], control: dict[str, Any]) -> float | None:
    """The same gap taken between the measured averages.

    `_delta` subtracts two values that were each rounded to 2 decimals, so it
    reports the difference of rounded numbers rather than the rounded
    difference. The two disagree by up to 0.01, and one shipped artifact
    already does: its published gap is -0.16 where the measurement gives
    -0.17. The archived field cannot be corrected without rewriting the
    record, so the corrected value is published beside it and the table prints
    this one.
    """
    if not _fully_graded(treatment) or not _fully_graded(control):
        return None
    return round(_graded_avg(treatment) - _graded_avg(control), 2)


def _positive_verdict(desc_avg: float | None, baseline_avg: float | None) -> str:
    """Name which of the two positive requirements a reachable run missed.

    Written as negated `>=` rather than `<` so that a non-comparable average
    fails closed. Both comparisons are False against NaN, so negating them
    reports FAIL_THRESHOLD instead of falling through to PASS.
    """
    if desc_avg is None or baseline_avg is None:
        # Reachable only if the coverage gate above let an unmeasured mechanism
        # through. Report the miss rather than comparing against nothing.
        return "FAIL_THRESHOLD"
    passes_threshold = desc_avg >= MIN_ACTIVATION_SCORE
    beats_baseline = (desc_avg - baseline_avg) >= MIN_DELTA_VS_BASELINE
    if not passes_threshold:
        return "FAIL_THRESHOLD"
    if not beats_baseline:
        return "FAIL_NO_DELTA"
    return "PASS"


def _decide_verdict(
    summary: dict[str, Any],
    *,
    gating_judge_failures: int,
    worst_neg_avg: float | None,
    has_positive_cases: bool,
    has_negative_cases: bool,
    desc_avg: float | None,
    baseline_avg: float | None,
) -> str:
    """Rank the gates and return the one that decides the run.

    Order is load-bearing, so it lives in one function rather than threaded
    through the collection above it. An observed harm outranks an unobserved
    benefit, and an unproven harm outranks an unproven benefit.
    """
    if gating_judge_failures > 0:
        return "FAIL_JUDGE_ERRORS"
    if worst_neg_avg is not None and worst_neg_avg < MIN_RESTRAINT_SCORE:
        # Ahead of the positive gates: a rule that fires where it must not is
        # actively harmful, while one that under-fires is merely useless. Ahead
        # of the coverage gate too, because a floor violation seen on part of
        # the pool is still a violation, and naming the harm beats naming the
        # gap in coverage that would have found more of it.
        return "FAIL_OVER_ACTIVATION"
    if summary["negative_gate_incomplete"]:
        # No harm was observed, but the pool was not fully measured, so
        # restraint was not demonstrated either. Passing here would attach a
        # clean average to a population it was never computed over.
        return "FAIL_NEGATIVE_INCOMPLETE"
    if not has_positive_cases:
        return "NO_POSITIVE_CASES"
    if summary["positive_gate_incomplete"]:
        # Under the negative gates on purpose: shipping a rule that might fire
        # where it must not costs more than withholding one that might help.
        return "FAIL_POSITIVE_INCOMPLETE"
    if summary.get("positive_route_mismatches", 0) > 0:
        # One router fronts many sibling references and any sibling resolves
        # for any target, so a routed cell can score well on content the target
        # never supplied. A PASS here would certify the rule on a population
        # that partly did not involve the rule. The score stays in the average
        # (dropping a mechanism's failures would inflate that mechanism); what
        # is withheld is the certification.
        return "FAIL_ROUTE_MISSED_TARGET"
    verdict = _positive_verdict(desc_avg, baseline_avg)
    if verdict == "PASS" and not has_negative_cases:
        # Last, not first. The defect an empty negative pool causes is a false
        # certification: the restraint floor compares against nothing, cannot
        # fire, and a clean positive result then reads as a clean run. Every
        # gate above already withholds the certification on its own evidence,
        # so preempting them would replace an actionable defect with a coverage
        # complaint and would drop a genuine threshold failure out of the
        # rollback set. Only the PASS is unearned, so only the PASS is taken.
        # The scenario loader refuses such a file before any spend; this is the
        # fallback for replay and for direct callers that skip that path.
        return "NO_NEGATIVE_CASES"
    return verdict


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _render_caveats(summary: dict[str, Any]) -> list[str]:
    """Every line that qualifies the verdict above it.

    These are the disclosures a reader needs to know the headline number does
    not cover what it appears to. They live together so that adding an
    exclusion without its disclosure is a visible omission rather than a
    silent one.
    """
    lines: list[str] = []
    if summary.get("delta_rounding_disagrees"):
        lines.append(
            "Delta: the archived gap fields subtract two averages that were "
            "each rounded first, which differs from the rounded difference by "
            "up to 0.01. The table prints the measured gap; the archived "
            "fields keep the derivation their record was written with."
        )
    if summary.get("rounding_would_change_verdict"):
        lines.append(
            "Precision: the averages printed below are rounded to 2 decimals "
            "and a gate threshold falls inside that rounding. The verdict was "
            "decided on the measured values, so checking it against the "
            "printed numbers will disagree."
        )
    for label, key in (
        ("Negative", "negative_gate_incomplete"),
        ("Positive", "positive_gate_incomplete"),
    ):
        incomplete = summary.get(key) or []
        if incomplete:
            lines.append(f"{label} pool incomplete at: " + ", ".join(incomplete))
    unreachable = summary.get("unreachable_mechanisms") or []
    if unreachable:
        lines.append(
            "Excluded as unreachable for a routed target: " + ", ".join(unreachable)
        )
    total_jf = summary.get("total_judge_failures", 0)
    gating_jf = summary.get("gating_judge_failures", 0)
    if total_jf != gating_jf:
        # Fire on any divergence. Tying this to `unreachable` alone meant the
        # negative-baseline exclusion printed nothing at all, so a reader saw a
        # clean PASS over a record that holds a judge failure.
        where = summary.get("excluded_judge_failure_cells") or []
        lines.append(
            f"Judge failures: {total_jf} in the record, {gating_jf} on gating "
            + (f"surfaces. Not gated: {', '.join(where)}." if where else "surfaces.")
        )
    # Positive pool only. On a negative case the router is supposed to decline,
    # so counting a miss there would report correct restraint as a defect.
    route_missed = summary.get("positive_route_mismatches", 0)
    if route_missed:
        lines.append(
            f"Routing: {route_missed} positive cell(s) never opened the target "
            "reference, so those scores measure a sibling reference or none"
        )
    legacy = sum(
        summary["per_mechanism"][m].get("legacy_reduced_count", 0)
        + summary["negative_case_per_mechanism"][m].get("legacy_reduced_count", 0)
        for m in MECHANISMS
    )
    if legacy:
        lines.append(
            f"Reduction: {legacy} cell(s) carried no cell_score and were averaged "
            "from the score triple (pre-cell_score artifact)"
        )
    return lines


def render_table(rule_id: str, summary: dict[str, Any]) -> str:
    worst_neg = summary.get("worst_negative_avg")
    if worst_neg is None:
        # An absent floor has two causes and they are not the same thing to go
        # fix. Saying "not measured" beside a table row carrying an average
        # contradicts the row. Both states are read over the gate mechanisms
        # the target can reach, so both say so: on a routed target the table
        # can show `full` fully graded while the floor has no candidate.
        restraint = (
            "no reachable negative-gate mechanism graded on every negative scenario"
            if summary.get("negative_floor_partial")
            else "not measured on any reachable negative-gate mechanism"
        )
    else:
        # `worst_neg` is a min over the gate cells that covered their whole
        # pool. Printing every gate mechanism would name a population wider
        # than the one the number was read off, which is the defect this
        # instrument exists to remove.
        floor_mechs = summary.get("negative_floor_mechanisms")
        if floor_mechs is None:
            # A summary archived before the eligible set was published cannot
            # say which mechanisms set its floor. Falling back to the gate list
            # would reprint the exact mislabel this field exists to remove, so
            # say the population is unrecorded instead of guessing it.
            population = "population not recorded"
        else:
            population = ", ".join(floor_mechs) if floor_mechs else "rule mechanisms"
        source = summary.get("worst_negative_mechanism") or "?"
        graded = summary.get("worst_negative_graded", 0)
        neg_total = summary["negative_case_per_mechanism"][source]["scenario_count"] if (
            source in summary.get("negative_case_per_mechanism", {})
        ) else 0
        restraint = (
            f"worst of [{population}] {worst_neg} (floor {MIN_RESTRAINT_SCORE}), "
            f"from {source} over {graded}/{neg_total} negative scenario(s)"
        )
    dropped = []
    if summary.get("best_mechanism_excluded"):
        dropped.append(
            f"{', '.join(summary['best_mechanism_excluded'])} for partial coverage"
        )
    if summary.get("best_mechanism_unmeasured"):
        dropped.append(
            f"{', '.join(summary['best_mechanism_unmeasured'])} as unmeasured"
        )
    best_excluded = f", excluding {' and '.join(dropped)}" if dropped else ""
    rows = [
        f"\nRule: {rule_id}",
        f"Verdict: {summary['verdict']}",
        (
            f"Best mechanism: {summary['best_mechanism']} "
            f"(avg {summary['best_avg_score']})"
            + best_excluded
            if summary.get("best_mechanism")
            else (
                "Best mechanism: no reachable rule-enhanced mechanism graded on every scenario"
                if summary.get("best_mechanism_partial")
                else "Best mechanism: no reachable rule-enhanced mechanism measured"
            )
        ),
        f"Restraint on negative cases: {restraint}",
    ]
    rows += _render_caveats(summary)
    rows += [
        "",
        "| Mechanism    | Pos avg | Neg avg | Δ vs baseline | Pos graded | Neg graded |",
        "|--------------|---------|---------|---------------|------------|------------|",
    ]
    for mech in MECHANISMS:
        pos_stats = summary["per_mechanism"][mech]
        neg_stats = summary["negative_case_per_mechanism"][mech]
        # A wholly ungraded pool has no average. Printing one reads as a real
        # score: low on the positive side it looks like the mechanism failed,
        # and low on the negative side it looks like total over-activation.
        # Both columns report the absence instead.
        pos_count = _graded_count(pos_stats)
        neg_count = _graded_count(neg_stats)
        pos = pos_stats["avg_score"] if pos_count else "-"
        neg = neg_stats["avg_score"] if neg_count else "-"
        pos_graded = f"{pos_count}/{pos_stats['scenario_count']}"
        neg_graded = f"{neg_count}/{neg_stats['scenario_count']}"
        # Read the published value rather than deriving a third one here: the
        # number on the screen and the number in the record must not drift. A
        # record written before the measured gap existed carries only the
        # derivation it was written with, and that derivation is its record, so
        # render it rather than refusing to display an archived run.
        measured_key = f"delta_{mech}_vs_baseline_measured"
        delta_val = (
            None
            if mech == "baseline"
            else summary.get(measured_key, summary[f"delta_{mech}_vs_baseline"])
        )
        delta = f"{delta_val:+}" if delta_val is not None else ""
        rows.append(
            f"| {mech:<12} | {pos:>7} | {neg:>7} | {delta:>13} "
            f"| {pos_graded:>10} | {neg_graded:>10} |"
        )
    return "\n".join(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eval rule activation across loading mechanisms."
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        required=True,
        help="One or more scenario JSON files (tests/evals/rule-scenarios/*.json).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model identifier.")
    parser.add_argument("--output", help="Write detailed JSON results to this path.")
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=(
            "Optional seed forwarded to OpenAI-compatible providers "
            f"(default: {DEFAULT_SEED})."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip API calls, print plan.",
    )
    parser.add_argument(
        "--judge-repeats",
        type=int,
        default=DEFAULT_JUDGE_REPEATS,
        help="Number of judge samples per response.",
    )
    parser.add_argument(
        "--judge-reducer",
        default=DEFAULT_JUDGE_REDUCER,
        choices=tuple(_SCORE_REDUCERS),
        help="Reducer used for repeated judge samples.",
    )
    return parser.parse_args()


RULES_DIR = (REPO_ROOT / ".claude" / "rules").resolve()
SKILLS_DIR = (REPO_ROOT / ".claude" / "skills").resolve()


def _read_scenarios_json(spath: Path) -> dict[str, Any] | int:
    """Read and parse a scenarios JSON file. Return parsed dict or exit code 2."""
    try:
        raw = spath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        print(f"ERROR: cannot read scenario file {spath}: {exc}", file=sys.stderr)
        return 2
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {spath}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print(
            f"ERROR: scenario file must contain a JSON object: {spath}",
            file=sys.stderr,
        )
        return 2
    return data


def _validate_scenario_gate(
    sc: dict[str, Any], idx: int, spath: Path
) -> int | None:
    """Validate one scenario's ``expected_gate``. Exit code 2 on error.

    An absent gate and a misspelled one both used to read as a positive case,
    so a scenario authored as a negative was graded against the positive rubric
    and then averaged into the positive pool. Refusing the file is the visible
    failure; silently moving a case between pools is an invisible one.
    """
    gate = sc.get("expected_gate")
    if not isinstance(gate, str) or not gate.strip():
        print(
            f"ERROR: scenarios[{idx}].expected_gate must be a non-empty "
            f"string in {spath}. Use {NEGATIVE_GATE!r} for a negative case "
            "or name the gate the scenario expects.",
            file=sys.stderr,
        )
        return 2
    normalized = _normalize_gate(gate)
    if normalized != NEGATIVE_GATE and _is_gate_near_miss(normalized):
        print(
            f"ERROR: scenarios[{idx}].expected_gate {gate!r} reads as a "
            f"near miss of {NEGATIVE_GATE!r} in {spath}. A near miss would be "
            "graded against the positive rubric and averaged into the "
            "positive pool. Use the sentinel exactly, or rename the gate so "
            "it does not resemble it.",
            file=sys.stderr,
        )
        return 2
    return None


def _validate_scenario_pools(scenarios: list[Any], spath: Path) -> int | None:
    """Require both a positive and a negative pool. Exit code 2 on error.

    Separate from the per-scenario shape checks above because it is a different
    question. Those ask whether each entry is well formed; this asks whether the
    set of entries can answer anything. Both pools are knowable without a single
    API call, so refuse here rather than spending a run that cannot answer.
    They are checked together because they are the same defect: a gate computed
    over an empty pool cannot fail, and a gate that cannot fail has not been run.
    """
    if not scenarios:
        print(
            f"ERROR: {spath} declares no scenarios. Every gate would pass "
            "over an empty pool, so the run would certify the rule without "
            "measuring it once.",
            file=sys.stderr,
        )
        return 2
    positives: list[Any] = []
    negatives: list[Any] = []
    for sc in scenarios:
        gate = _normalize_gate(sc.get("expected_gate", ""))
        target = negatives if _is_negative_gate(gate) else positives
        target.append(sc)
    if not positives:
        print(
            f"ERROR: {spath} declares no positive scenario. Every "
            f"expected_gate is {NEGATIVE_GATE!r}, so the run could only ever "
            "report NO_POSITIVE_CASES. Add a scenario whose expected_gate "
            "names the gate the rule should reach.",
            file=sys.stderr,
        )
        return 2
    if not negatives:
        print(
            f"ERROR: {spath} declares no negative scenario, so the restraint "
            "floor would be computed over an empty pool. It cannot fail there, "
            "and the run would report PASS for restraint it never measured. "
            f"Add a scenario whose expected_gate is {NEGATIVE_GATE!r}.",
            file=sys.stderr,
        )
        return 2
    return None


def _validate_scenarios_shape(data: dict[str, Any], spath: Path) -> int | None:
    """Validate scenarios array shape. Return exit code 2 on error, None on ok."""
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list):
        print(f"ERROR: scenarios must be a list in {spath}", file=sys.stderr)
        return 2
    for idx, sc in enumerate(scenarios):
        if not isinstance(sc, dict):
            print(
                f"ERROR: scenarios[{idx}] must be an object in {spath}",
                file=sys.stderr,
            )
            return 2
        gate_error = _validate_scenario_gate(sc, idx, spath)
        if gate_error is not None:
            return gate_error
        for required in ("id", "input"):
            value = sc.get(required)
            if not isinstance(value, str) or not value.strip():
                print(
                    f"ERROR: scenarios[{idx}].{required} must be a non-empty "
                    f"string in {spath}",
                    file=sys.stderr,
                )
                return 2
    return _validate_scenario_pools(scenarios, spath)


def _resolve_rule_path(rule_path_str: str) -> Path | int:
    """Resolve and validate rule_path stays under .claude/rules/ as a .md file."""
    rule_path = (REPO_ROOT / rule_path_str).resolve()
    try:
        rule_path.relative_to(RULES_DIR)
    except ValueError:
        print(
            f"ERROR: rule_path must be under .claude/rules/: {rule_path_str}",
            file=sys.stderr,
        )
        return 2
    if rule_path.suffix != ".md":
        print(
            f"ERROR: rule_path must be a .md file: {rule_path_str}",
            file=sys.stderr,
        )
        return 2
    if not rule_path.is_file():
        print(f"ERROR: rule not found: {rule_path}", file=sys.stderr)
        return 2
    return rule_path


def _resolve_skill_path(skill_path_str: str) -> Path | int:
    """Resolve and validate skill_path stays under .claude/skills/ as SKILL.md.

    The name check runs before the is_file() check so a crafted path targeting
    another file in the skills tree is rejected on name alone. This keeps the
    `full` mechanism from sending arbitrary skill-tree content to the API.
    """
    skill_path = (REPO_ROOT / skill_path_str).resolve()
    try:
        skill_path.relative_to(SKILLS_DIR)
    except ValueError:
        print(
            f"ERROR: skill_path must be under .claude/skills/: {skill_path_str}",
            file=sys.stderr,
        )
        return 2
    if skill_path.name != "SKILL.md":
        print(
            f"ERROR: skill_path must be a SKILL.md file: {skill_path_str}",
            file=sys.stderr,
        )
        return 2
    if not skill_path.is_file():
        print(f"ERROR: skill not found: {skill_path}", file=sys.stderr)
        return 2
    return skill_path


def _resolve_skill_reference(
    skill_path_str: str,
    reference_path_str: str,
) -> tuple[Path, Path] | int:
    """Resolve and validate a skill SKILL.md plus one reference file."""
    skill_path = (REPO_ROOT / skill_path_str).resolve()
    reference_path = (REPO_ROOT / reference_path_str).resolve()
    try:
        skill_path.relative_to(SKILLS_DIR)
    except ValueError:
        print(
            f"ERROR: skill_path must be under .claude/skills/: {skill_path_str}",
            file=sys.stderr,
        )
        return 2
    if skill_path.name != "SKILL.md" or not skill_path.is_file():
        print(f"ERROR: skill_path must point at a SKILL.md file: {skill_path_str}", file=sys.stderr)
        return 2
    references_dir = skill_path.parent / "references"
    try:
        reference_path.relative_to(references_dir.resolve())
    except ValueError:
        print(
            "ERROR: reference_path must be under the skill's references/: "
            f"{reference_path_str}",
            file=sys.stderr,
        )
        return 2
    if reference_path.suffix != ".md" or not reference_path.is_file():
        print(
            f"ERROR: reference_path must point at a .md file: {reference_path_str}",
            file=sys.stderr,
        )
        return 2
    return skill_path, reference_path


def _resolve_target_paths(data: dict[str, Any], spath: Path) -> tuple[Path, Path | None] | int:
    """Resolve either a rule path or a skill target, with or without a reference.

    A scenario file MUST set exactly one of `rule_path` or `skill_path`. When
    `skill_path` is paired with `reference_path`, the skill is measured through
    the two-hop progressive-disclosure route (skill router selects a
    reference). When `skill_path` is set alone, the skill's own SKILL.md front
    door is measured directly, the same way `rule_path` is measured.
    """
    rule_path_str = data.get("rule_path")
    skill_path_str = data.get("skill_path")
    rule_ref = rule_path_str.strip() if isinstance(rule_path_str, str) else ""
    skill_ref = skill_path_str.strip() if isinstance(skill_path_str, str) else ""
    has_rule = bool(rule_ref)
    has_skill = bool(skill_ref)
    if has_rule == has_skill:
        print(
            "ERROR: scenario file must set exactly one of rule_path or "
            f"skill_path in {spath}",
            file=sys.stderr,
        )
        return 2

    if has_rule:
        resolved = _resolve_rule_path(rule_ref)
        if isinstance(resolved, int):
            return resolved
        return resolved, None

    reference_path_str = data.get("reference_path")
    reference_ref = (
        reference_path_str.strip() if isinstance(reference_path_str, str) else ""
    )
    if not reference_ref:
        resolved = _resolve_skill_path(skill_ref)
        if isinstance(resolved, int):
            return resolved
        return resolved, None
    return _resolve_skill_reference(skill_ref, reference_ref)


def _validate_target_id(data: dict[str, Any], spath: Path) -> int | None:
    """Require any declared id to be a non-empty string. Exit code 2 on error.

    The id is the key the published record is written under, and JSON object
    keys are strings. A declared `1` and a declared `"1"` are distinct keys in
    memory, so the duplicate check clears both, and then they collapse to one
    key on serialization and the first target's result is gone from the record
    without a word. Refuse the type here, where it costs nothing, rather than
    losing a measured target at publication.
    """
    for key in ("rule_id", "skill_id"):
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            print(
                f"ERROR: {key} must be a non-empty string in {spath}, got "
                f"{value!r}. The published record is keyed by this value and "
                "JSON keys are strings, so a non-string id would collide with "
                "its own string form and drop a measured target.",
                file=sys.stderr,
            )
            return 2
    return None


def _load_scenarios_file(
    scenario_file: str,
) -> tuple[dict[str, Any], tuple[Path, Path | None]] | int:
    """Return (scenarios_data, resolved target paths) on success, exit code on error.

    A scenario file MUST set exactly one of `rule_path` or `skill_path`.
    `rule_path` MUST resolve to a `.md` file under `.claude/rules/`. `skill_path`
    MUST resolve to a `SKILL.md` file under `.claude/skills/`, optionally paired
    with `reference_path` resolving to a `.md` file under that skill's
    `references/`. A crafted scenario file cannot point at config, secrets, or
    any other repository file: the `full` mechanism would otherwise send that
    content to the LLM API.
    """
    spath = Path(scenario_file)
    if not spath.is_file():
        print(f"ERROR: scenario file not found: {spath}", file=sys.stderr)
        return 2

    parsed = _read_scenarios_json(spath)
    if isinstance(parsed, int):
        return parsed
    scenarios_data = parsed

    shape_err = _validate_scenarios_shape(scenarios_data, spath)
    if shape_err is not None:
        return shape_err

    id_err = _validate_target_id(scenarios_data, spath)
    if id_err is not None:
        return id_err

    resolved = _resolve_target_paths(scenarios_data, spath)
    if isinstance(resolved, int):
        return resolved
    return scenarios_data, resolved


def _process_one_rule(
    api_key: str,
    scenarios_data: dict[str, Any],
    target_paths: tuple[Path, Path | None],
    args: argparse.Namespace,
) -> tuple[str, dict[str, Any] | None, int]:
    """Run all scenarios for one rule or skill. Return (target_id, result_or_none, n_calls)."""
    primary_path, reference_path = target_paths
    if reference_path is not None:
        # A reference target measures one reference, not the skill that fronts
        # it. Defaulting to the skill directory gave every reference under one
        # router the same id, so the label named the umbrella population while
        # the numbers measured a single reference. `.stem` matches the ids the
        # shipped scenario files already declare.
        default_id = reference_path.stem
    elif primary_path.name == "SKILL.md":
        default_id = primary_path.parent.name
    else:
        default_id = primary_path.stem
    rule_id = (
        scenarios_data.get("rule_id")
        or scenarios_data.get("skill_id")
        or default_id
    )
    if reference_path is None:
        rule = parse_rule(primary_path)
    else:
        rule = parse_skill_reference(primary_path, reference_path)
    scenarios = scenarios_data.get("scenarios", [])
    route_calls = len(scenarios) if reference_path is not None else 0
    n_calls = len(scenarios) * len(MECHANISMS) * (1 + args.judge_repeats) + route_calls

    if args.dry_run:
        print(
            f"[DRY-RUN] {rule_id}: {len(scenarios)} scenarios x "
            f"{len(MECHANISMS)} mechanisms x "
            f"{1 + args.judge_repeats} (call + judges)"
            f" + {route_calls} route calls = {n_calls} calls"
        )
        print(f"  description present: {bool(rule['description'])}")
        print(f"  body chars: {len(rule['body'])}")
        return rule_id, None, n_calls

    scenario_results: list[dict[str, Any]] = []
    for sc in scenarios:
        preview = sc.get("desc", "")[:60]
        print(f"  scenario {sc['id']}: {preview}...", file=sys.stderr)
        r = eval_one_scenario(
            api_key,
            rule,
            rule_id,
            sc,
            args.model,
            dry_run=False,
            seed=args.seed,
            judge_repeats=args.judge_repeats,
            judge_reducer=args.judge_reducer,
        )
        scenario_results.append(r)

    summary = aggregate(scenario_results, routed=reference_path is not None)
    print(render_table(rule_id, summary))
    result_paths = {"target_path": str(primary_path.relative_to(REPO_ROOT))}
    if reference_path is not None:
        result_paths["reference_path"] = str(reference_path.relative_to(REPO_ROOT))
    return rule_id, {
        **result_paths,
        "summary": summary,
        "scenarios": scenario_results,
    }, n_calls


def main() -> int:
    args = _parse_args()
    if args.judge_repeats < 1:
        print("ERROR: --judge-repeats must be positive", file=sys.stderr)
        return 2

    if args.dry_run:
        api_key = ""
    else:
        try:
            api_key = _load_api_key()
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 4

        try:
            verify_model_available(api_key, args.model)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2

    all_results: dict[str, Any] = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "rules": {},
    }
    state = _RunState()

    for scenario_file in args.scenarios:
        exit_code = _process_scenario_file(
            scenario_file, api_key, args, all_results, state
        )
        if exit_code is not None:
            # max, not the bare code: a hard refusal stops the run, but an
            # earlier target may already have recorded something worse. A
            # config refusal on file 8 must not lower an API failure seen on
            # file 1, or adding a target could improve the exit.
            return max(state.worst_exit, exit_code)

    if args.dry_run:
        _print_dry_run_summary(state.total_calls)
        # A dry run produces no verdict, so this is 0 today. Returning the
        # accumulated code rather than a literal keeps one exit path: a
        # hardcoded success here would silently swallow anything a later
        # change starts recording during a dry run.
        return state.worst_exit

    if args.output:
        Path(args.output).write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        print(f"\nWrote results: {args.output}")

    return state.worst_exit


class _RunState:
    """Mutable accumulator for the main loop."""

    def __init__(self) -> None:
        # One reduced exit code rather than a boolean per failure kind: the
        # precedence then falls out of the numeric ordering instead of a
        # branch that has to be kept in sync with it.
        self.worst_exit = 0
        self.total_calls = 0
        # Which scenario file claimed each id. Results are stored by id into a
        # plain dict, so without this a second file claiming a taken id would
        # overwrite the first and publish one entry for two measured targets.
        self.claimed_ids: dict[str, str] = {}


def _process_scenario_file(
    scenario_file: str,
    api_key: str,
    args: argparse.Namespace,
    all_results: dict[str, Any],
    state: _RunState,
) -> int | None:
    """Process one scenarios file. Return exit code on hard failure, None on ok."""
    loaded = _load_scenarios_file(scenario_file)
    if isinstance(loaded, int):
        return loaded
    scenarios_data, target_paths = loaded

    rule_id, result, n_calls = _process_one_rule(
        api_key, scenarios_data, target_paths, args
    )
    # Checked before the results are stored and before any spend, so a dry run
    # catches the collision too. Refusing is the visible failure; overwriting
    # is an invisible one that leaves no trace in the published output.
    claimed_by = state.claimed_ids.get(rule_id)
    if claimed_by is not None:
        print(
            f"ERROR: {scenario_file} declares id {rule_id!r}, already claimed "
            f"by {claimed_by}. Two targets cannot publish under one id: the "
            "second would overwrite the first. Set a distinct rule_id or "
            "skill_id in one of them.",
            file=sys.stderr,
        )
        return 2
    state.claimed_ids[rule_id] = scenario_file
    state.total_calls += n_calls

    if result is not None:
        all_results["rules"][rule_id] = result
        state.worst_exit = max(
            state.worst_exit, _classify_verdict(result["summary"]["verdict"])
        )
    return None


def _classify_verdict(verdict: str) -> int:
    """Return the process exit code this verdict implies.

    Codes follow the repository convention: 0 ok, 1 logic, 2 config, 3
    external. NO_POSITIVE_CASES and NO_NEGATIVE_CASES are config errors, not
    logic ones. Each says the scenario file cannot measure one of the two
    pools and reports nothing at all about the rule, so returning 1 would
    attach a rule failure to a file problem and a run could not tell an
    under-firing rule from a misconfigured input. FAIL_JUDGE_ERRORS is external
    so CI can distinguish transient infrastructure trouble from a genuine
    activation failure.

    A run reduces these with max(), which makes the precedence a property of
    the ordering rather than a branch kept in sync with it: external outranks
    config, config outranks logic, and adding a target can only worsen the
    exit, never improve it.
    """
    if verdict == "PASS":
        return 0
    if verdict == "FAIL_JUDGE_ERRORS":
        return 3
    if verdict in ("NO_POSITIVE_CASES", "NO_NEGATIVE_CASES"):
        return 2
    return 1


def _print_dry_run_summary(total_calls: int) -> None:
    est_tokens = total_calls * EST_TOKENS_PER_CALL
    est_cost = est_tokens / 1_000_000 * 3
    print(f"\nTotal calls planned: {total_calls}")
    print(f"Estimated tokens: ~{est_tokens:,} (~${est_cost:.2f} sonnet input rate)")


if __name__ == "__main__":
    sys.exit(main())
