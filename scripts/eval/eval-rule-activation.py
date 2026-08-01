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
    body = f"Skill router:\n\n{skill['body']}\n\nSelected reference:\n\n{reference['body']}"
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


def build_system_prompt(mechanism: str, rule: dict[str, str], rule_id: str) -> str:
    """Construct the system prompt for a given activation mechanism."""
    if mechanism == "baseline":
        return ""
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
        return (
            "The following project rule applies to your work. "
            "Apply it when relevant.\n\n"
            f"{rule['body']}"
        )
    raise ValueError(f"Unknown mechanism: {mechanism}")


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

    is_negative = expected_gate == "skip-rule-not-applicable"
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
    except ValueError:
        return _failed_judge(
            "judge response could not be parsed as JSON",
            raw_judge_response=raw,
        )
    if not isinstance(parsed, dict):
        return _failed_judge(
            "judge returned non-object JSON",
            raw_judge_response=raw,
        )
    if _parsed_names_two_verdicts(parsed):
        return _failed_judge(
            "ambiguous judge output names two verdicts",
            raw_judge_response=raw,
        )
    score_error = _judge_score_shape_error(parsed)
    if score_error is not None:
        return _failed_judge(score_error, raw_judge_response=raw)
    result = {
        "activation_score": _clamp_score(parsed["activation_score"]),
        "citation_score": _clamp_score(parsed["citation_score"]),
        "behavior_score": _clamp_score(parsed["behavior_score"]),
        "reasoning": str(parsed.get("reasoning", ""))[:300],
        "judge_failed": False,
        "raw_judge_response": raw,
    }
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
    reduced["cell_score"] = reducer([_sample_scalar(sample) for sample in graded])
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

# The judge rubric is 1-5. Kept as one authoritative range because two code
# paths police it: the shape gate and the clamp. They disagreed once already,
# and that disagreement is what let an out-of-range score through.
_SCORE_RANGE = range(1, 6)
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
    """Return whether a successfully-parsed payload carries two candidate verdicts.

    A whole-payload strict parse can still fail to name exactly one verdict.
    Valid JSON nests, so a second verdict can sit inside the first as a member,
    a list element, or a quoted string, and the parse still succeeds. A guess
    between two candidates is fabrication, so both are refused.

    A verdict serialized inside a string value is still a second candidate:
    the judge named two answers and choosing one of them is a guess.

    Known limit, measured rather than assumed: this cannot detect a second
    verdict whose field name is not spelled as the literal codepoint sequence.
    Three shapes share that one cause. The name can be split
    (``'activation' '_score'`` as Python adjacent literals), substituted
    (``activation_scоre`` with a Cyrillic о), or interleaved (a zero-width
    space inside it). Each survives any pattern written over the real name, and
    no textual check closes the class, because the encoding space is open.
    Zero of the 264 archived judge payloads contain any of those shapes.
    The exposure is bounded by the top level being the schema-defined answer
    slot, so an undetected second verdict in prose loses to the verdict the
    judge actually filed.
    """
    if _count_score_bearing_objects(parsed) > 1:
        return True
    filed = parsed if isinstance(parsed, dict) else {}
    return any(_string_contradicts_filed_scores(text, filed) for text in _string_values(parsed))


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


def _failed_judge(reason: str, raw_judge_response: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {
        "activation_score": 0,
        "citation_score": 0,
        "behavior_score": 0,
        "reasoning": reason,
        "judge_failed": True,
    }
    if raw_judge_response:
        result["raw_judge_response"] = raw_judge_response
    return result


def _judge_score_shape_error(parsed: dict[str, Any]) -> str | None:
    required_fields = ("activation_score", "citation_score", "behavior_score")
    missing = [field for field in required_fields if field not in parsed]
    if missing:
        return f"judge returned missing score field(s): {', '.join(missing)}"
    for field in required_fields:
        value = parsed[field]
        if not isinstance(value, int) or isinstance(value, bool):
            return f"judge returned non-integral {field}: {type(value).__name__}"
        if value not in _SCORE_RANGE:
            return f"judge returned out-of-range {field}: {value!r}"
    return None


# ---------------------------------------------------------------------------
# Eval driver
# ---------------------------------------------------------------------------


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
        "negative_case": scenario.get("expected_gate") == "skip-rule-not-applicable",
        "mechanisms": {},
    }

    for mechanism in MECHANISMS:
        system = build_system_prompt(mechanism, rule, rule_id)
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
                sample = score_response(api_key, scenario, response, model=model, seed=judge_seed)
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


def _scenario_score_triple(scenario: dict[str, Any], mech: str) -> tuple[float | None, bool, bool]:
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


def _incomplete_mechanisms(
    per_mech: dict[str, dict[str, Any]], mechs: list[str], pool_size: int
) -> list[str]:
    """Mechanisms whose average rests on fewer cells than the pool holds.

    An average over a subset of a pool, published beside a verdict that names
    the whole pool, is a number attached to a population it was never computed
    over. That is the defect this instrument keeps re-growing, so the check
    lives in one place and both pools call it.
    """
    return sorted(m for m in mechs if per_mech[m]["graded_count"] < pool_size)


def _mechanism_summary(pool: list[dict[str, Any]], mech: str) -> dict[str, Any]:
    """Compute avg_score over the graded scenarios for one mechanism."""
    scores: list[float] = []
    failures = 0
    legacy = 0
    for s in pool:
        score, failed, legacy_reduced = _scenario_score_triple(s, mech)
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
        "scenario_count": len(pool),
        "graded_count": len(scores),
        "judge_failures": failures,
        "legacy_reduced_count": legacy,
    }


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
    pos_scenarios = [s for s in scenarios if not s["negative_case"]]
    neg_scenarios = [s for s in scenarios if s["negative_case"]]

    for mech in MECHANISMS:
        summary["per_mechanism"][mech] = _mechanism_summary(pos_scenarios, mech)
        summary["negative_case_per_mechanism"][mech] = _mechanism_summary(neg_scenarios, mech)

    baseline_avg = summary["per_mechanism"]["baseline"]["avg_score"]
    desc_avg = summary["per_mechanism"]["description"]["avg_score"]

    # `description` is the progressive-disclosure gate. The `full` mechanism is
    # retained only as a diagnostic ceiling and cannot rescue a failed front door.
    rule_enhanced = [m for m in MECHANISMS if m != "baseline"]
    # Ranking two mechanisms is the same comparison a delta makes, so it needs
    # the same footing: both averages must cover the whole pool. A mechanism
    # graded on one lucky scenario would otherwise take the headline from a
    # mechanism graded on all of them, and the table would refuse that same
    # comparison one line later as a delta.
    best_mech = max(
        (m for m in rule_enhanced if _fully_graded(summary["per_mechanism"][m])),
        key=lambda m: summary["per_mechanism"][m]["avg_score"],
        default=None,
    )
    best_avg = summary["per_mechanism"][best_mech]["avg_score"] if best_mech else None
    # Distinguish "no cell was graded" from "no mechanism was graded
    # completely". Both leave the headline empty and they are not the same
    # problem to go fix.
    summary["best_mechanism_partial"] = best_mech is None and any(
        summary["per_mechanism"][m]["avg_score"] is not None for m in rule_enhanced
    )

    total_judge_failures = sum(
        summary["per_mechanism"][m]["judge_failures"] for m in MECHANISMS
    ) + sum(summary["negative_case_per_mechanism"][m]["judge_failures"] for m in MECHANISMS)
    # `total_judge_failures` stays the whole-run count, because it is the
    # published record of how the judge behaved. The verdict reads a narrower
    # count: for a routed target `full` is a treatment no deployment performs,
    # so a judge error there says nothing about a surface a user can reach.
    # Failing on it would fail a rule for a broken measurement of something
    # that is not shipped. The two counts are equal whenever nothing is
    # excluded, which is every always-on rule.
    measured_mechs = [m for m in MECHANISMS if not (routed and m == "full")]
    # The negative pool is counted over the mechanisms that actually gate it,
    # not over every measured one. `baseline` carries no rule, so a broken
    # judgement of what the baseline did on a negative case says nothing about
    # the rule and must not fail it. That exclusion is already stated for the
    # restraint floor below; counting failures over a wider set than the floor
    # reads them off contradicted it.
    neg_gate_mechs = ["description"] if routed else [m for m in MECHANISMS if m != "baseline"]
    gating_judge_failures = sum(
        summary["per_mechanism"][m]["judge_failures"] for m in measured_mechs
    ) + sum(summary["negative_case_per_mechanism"][m]["judge_failures"] for m in neg_gate_mechs)

    summary["best_mechanism"] = best_mech
    summary["best_avg_score"] = best_avg
    summary["baseline_avg"] = baseline_avg
    pos_cells = summary["per_mechanism"]
    summary["delta_full_vs_baseline"] = _delta(pos_cells["full"], pos_cells["baseline"])
    summary["delta_description_vs_baseline"] = _delta(
        pos_cells["description"], pos_cells["baseline"]
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
    summary["unreachable_mechanisms"] = [m for m in MECHANISMS if m not in measured_mechs]

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
    # Only mechanisms with a graded negative cell contribute. An ungraded pool
    # has no average to gate on: `_mechanism_summary` reports `None`, which is
    # not comparable against a floor, and `min` over an empty list raises. A
    # suite with no negative scenarios reports that it measured none rather
    # than failing every rule in it.
    gate_mechs = neg_gate_mechs
    gate_cells = {m: summary["negative_case_per_mechanism"][m] for m in gate_mechs}
    graded_neg = [c["avg_score"] for c in gate_cells.values() if c["graded_count"] > 0]
    worst_neg_avg = min(graded_neg) if graded_neg else None
    summary["worst_negative_avg"] = worst_neg_avg
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
    worst_neg_mech = min(
        (m for m in gate_mechs if gate_cells[m]["graded_count"] > 0),
        key=lambda m: gate_cells[m]["avg_score"],
        default=None,
    )
    summary["worst_negative_mechanism"] = worst_neg_mech
    summary["worst_negative_graded"] = (
        gate_cells[worst_neg_mech]["graded_count"] if worst_neg_mech else 0
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

    summary["verdict"] = _decide_verdict(
        summary,
        gating_judge_failures=gating_judge_failures,
        worst_neg_avg=worst_neg_avg,
        has_positive_cases=bool(pos_scenarios),
        desc_avg=desc_avg,
        baseline_avg=baseline_avg,
    )

    return summary


def _fully_graded(cell: dict[str, Any]) -> bool:
    """Whether a cell's average covers every scenario in its pool."""
    return cell.get("avg_score") is not None and cell.get("graded_count") == cell.get(
        "scenario_count"
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
    return _positive_verdict(desc_avg, baseline_avg)


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
    for label, key in (
        ("Negative", "negative_gate_incomplete"),
        ("Positive", "positive_gate_incomplete"),
    ):
        incomplete = summary.get(key) or []
        if incomplete:
            lines.append(f"{label} pool incomplete at: " + ", ".join(incomplete))
    unreachable = summary.get("unreachable_mechanisms") or []
    if unreachable:
        lines.append("Excluded as unreachable for a routed target: " + ", ".join(unreachable))
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
    gate_mechs = summary.get("negative_gate_mechanisms") or []
    if worst_neg is None:
        restraint = "not measured"
    else:
        # `worst_neg` is a min across mechanisms that need not have graded the
        # same scenarios, so printing the mechanism list alone leaves the reader
        # unable to say which one the number came from or how much it covers.
        population = ", ".join(gate_mechs) if gate_mechs else "rule mechanisms"
        source = summary.get("worst_negative_mechanism") or "?"
        graded = summary.get("worst_negative_graded", 0)
        neg_total = (
            summary["negative_case_per_mechanism"][source]["scenario_count"]
            if (source in summary.get("negative_case_per_mechanism", {}))
            else 0
        )
        restraint = (
            f"worst of [{population}] {worst_neg} (floor {MIN_RESTRAINT_SCORE}), "
            f"from {source} over {graded}/{neg_total} negative scenario(s)"
        )
    rows = [
        f"\nRule: {rule_id}",
        f"Verdict: {summary['verdict']}",
        (
            f"Best mechanism: {summary['best_mechanism']} (avg {summary['best_avg_score']})"
            if summary.get("best_mechanism")
            else (
                "Best mechanism: none graded on every scenario"
                if summary.get("best_mechanism_partial")
                else "Best mechanism: none measured"
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
        pos = pos_stats["avg_score"] if pos_stats["graded_count"] else "-"
        neg = neg_stats["avg_score"] if neg_stats["graded_count"] else "-"
        pos_graded = (
            f"{pos_stats.get('graded_count', pos_stats['scenario_count'])}"
            f"/{pos_stats['scenario_count']}"
        )
        neg_graded = f"{neg_stats['graded_count']}/{neg_stats['scenario_count']}"
        delta_val = (
            None if mech == "baseline" else _delta(pos_stats, summary["per_mechanism"]["baseline"])
        )
        delta = f"{delta_val:+}" if delta_val is not None else ""
        rows.append(
            f"| {mech:<12} | {pos:>7} | {neg:>7} | {delta:>13} "
            f"| {pos_graded:>10} | {neg_graded:>10} |"
        )
    return "\n".join(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eval rule activation across loading mechanisms.")
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
        help=(f"Optional seed forwarded to OpenAI-compatible providers (default: {DEFAULT_SEED})."),
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
        for required in ("id", "input"):
            value = sc.get(required)
            if not isinstance(value, str) or not value.strip():
                print(
                    f"ERROR: scenarios[{idx}].{required} must be a non-empty string in {spath}",
                    file=sys.stderr,
                )
                return 2
    return None


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
            f"ERROR: reference_path must be under the skill's references/: {reference_path_str}",
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
            f"ERROR: scenario file must set exactly one of rule_path or skill_path in {spath}",
            file=sys.stderr,
        )
        return 2

    if has_rule:
        resolved = _resolve_rule_path(rule_ref)
        if isinstance(resolved, int):
            return resolved
        return resolved, None

    reference_path_str = data.get("reference_path")
    reference_ref = reference_path_str.strip() if isinstance(reference_path_str, str) else ""
    if not reference_ref:
        resolved = _resolve_skill_path(skill_ref)
        if isinstance(resolved, int):
            return resolved
        return resolved, None
    return _resolve_skill_reference(skill_ref, reference_ref)


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
    default_id = primary_path.parent.name if primary_path.name == "SKILL.md" else primary_path.stem
    rule_id = scenarios_data.get("rule_id") or scenarios_data.get("skill_id") or default_id
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
    return (
        rule_id,
        {
            **result_paths,
            "summary": summary,
            "scenarios": scenario_results,
        },
        n_calls,
    )


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

    all_results: dict[str, Any] = {"rules": {}}
    state = _RunState()

    for scenario_file in args.scenarios:
        exit_code = _process_scenario_file(scenario_file, api_key, args, all_results, state)
        if exit_code is not None:
            return exit_code

    if args.dry_run:
        _print_dry_run_summary(state.total_calls)
        return 0

    if args.output:
        Path(args.output).write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        print(f"\nWrote results: {args.output}")

    if state.external_failure:
        return 3
    return 0 if state.overall_pass else 1


class _RunState:
    """Mutable accumulator for the main loop."""

    def __init__(self) -> None:
        self.overall_pass = True
        self.external_failure = False
        self.total_calls = 0


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

    rule_id, result, n_calls = _process_one_rule(api_key, scenarios_data, target_paths, args)
    state.total_calls += n_calls

    if result is not None:
        all_results["rules"][rule_id] = result
        ok, judge_failed = _classify_verdict(result["summary"]["verdict"])
        if not ok:
            state.overall_pass = False
        if judge_failed:
            state.external_failure = True
    return None


def _classify_verdict(verdict: str) -> tuple[bool, bool]:
    """Return (ok, judge_failed). ok=True only for PASS; judge_failed only for FAIL_JUDGE_ERRORS.

    NO_POSITIVE_CASES is a config error (no positive scenarios = activation
    cannot be validated). FAIL_JUDGE_ERRORS is an external/API failure that
    surfaces as exit code 3 so CI can distinguish transient infrastructure
    problems from genuine activation failures.
    """
    return verdict == "PASS", verdict == "FAIL_JUDGE_ERRORS"


def _print_dry_run_summary(total_calls: int) -> None:
    est_tokens = total_calls * EST_TOKENS_PER_CALL
    est_cost = est_tokens / 1_000_000 * 3
    print(f"\nTotal calls planned: {total_calls}")
    print(f"Estimated tokens: ~{est_tokens:,} (~${est_cost:.2f} sonnet input rate)")


if __name__ == "__main__":
    sys.exit(main())
