"""Verdict parsing, local-axis adaptation, and failure categorization."""

# taste-lint: ignore file-size
# The ceiling wants this split, and the obvious seam is real: the local-axis
# adapter and its payload-evidence helpers are a separate concern from verdict
# parsing. The split is blocked by a packaging contract, not by taste. The
# vendored plugin probe loads this module standalone by file path
# (importlib.util.spec_from_file_location in tests/e2e/test_vendored_review_e2e.py),
# which any sibling import would break, and the 100% branch gate in
# .github/workflows/pytest.yml pins this exact path. Roughly 120 of these lines
# are contract quotations that .claude/rules/canonical-source-mirror.md
# requires verbatim, which is documentation density, not the reasoning burden
# the rule targets. Revisit together with the vendored loader and the pin.

from __future__ import annotations

import json
import re
from typing import TypeGuard

_VERDICT_PATTERN = re.compile(r"VERDICT:\s*([A-Z_]+)")

_KEYWORD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"CRITICAL_FAIL|critical failure|severe issue", re.IGNORECASE), "CRITICAL_FAIL"),
    (re.compile(r"REJECTED|reject|must fix|blocking", re.IGNORECASE), "REJECTED"),
    (re.compile(r"PASS|approved|looks good|no issues", re.IGNORECASE), "PASS"),
    (re.compile(r"WARN|warning|caution", re.IGNORECASE), "WARN"),
]


def get_verdict(output: str) -> str:
    """Parse verdict from raw AI output (legacy CI pipeline).

    Tries explicit ``VERDICT:`` pattern first, then falls back to keyword detection.
    Empty input or no-match returns ``CRITICAL_FAIL`` as a defensive fail-safe:
    in the legacy CI path, an AI agent that produces no output has effectively
    failed catastrophically and the pipeline must block.

    Common values: PASS, WARN, FAIL, REJECTED, CRITICAL_FAIL, NEEDS_REVIEW.

    NOTE: The ``CRITICAL_FAIL`` default differs intentionally from
    ``extract_verdict`` (UNKNOWN on no-match) and ``merge_verdicts`` (UNKNOWN
    on empty). Three parsers, three contracts:

    - ``get_verdict``: legacy AI-output parser; empty -> CRITICAL_FAIL (fail-safe)
    - ``extract_verdict``: structured skill-output parser; no-match -> UNKNOWN (neutral)
    - ``merge_verdicts``: verdict-list aggregator; empty -> UNKNOWN (no info)

    Do not align ``get_verdict`` to UNKNOWN: existing CI callers depend on the
    block-on-empty behavior and tests pin it (test_ai_review.py:92,95).
    """
    if not output or not output.strip():
        return "CRITICAL_FAIL"

    match = _VERDICT_PATTERN.search(output)
    if match:
        return match.group(1)

    for pattern, verdict in _KEYWORD_RULES:
        if pattern.search(output):
            return verdict

    return "CRITICAL_FAIL"


_LABEL_PATTERN = re.compile(r"LABEL:\s*(\S+)")
_MILESTONE_PATTERN = re.compile(r"MILESTONE:\s*(\S+)")


def get_labels(output: str) -> list[str]:
    """Extract ``LABEL:`` entries from AI output."""
    if not output or not output.strip():
        return []
    return [m.group(1) for m in _LABEL_PATTERN.finditer(output) if m.group(1).strip()]


def get_milestone(output: str) -> str:
    """Extract ``MILESTONE:`` entry from AI output. Returns empty string if absent."""
    if not output or not output.strip():
        return ""
    match = _MILESTONE_PATTERN.search(output)
    return match.group(1) if match else ""


FAIL_VERDICTS = frozenset({"CRITICAL_FAIL", "REJECTED", "FAIL", "NEEDS_REVIEW", "NON_COMPLIANT"})


# Tokens accepted by .github/actions/ai-review/action.yml's parse step:
# PASS, WARN, CRITICAL_FAIL, REJECTED, COMPLIANT, NON_COMPLIANT, PARTIAL, FAIL.
# Plus NEEDS_REVIEW (added by Issue #470 fix), UNKNOWN (added by #1934), and
# DID_NOT_RUN (added by #2818/#2821 for infrastructure failures that skipped review).
# merge_verdicts must not treat these CI-valid tokens as unknown garbage.
# PR #1965 coderabbit Y14.
_KNOWN_VERDICT_TOKENS: frozenset[str] = (
    frozenset({"PASS", "WARN", "UNKNOWN", "DID_NOT_RUN", "COMPLIANT", "NON_COMPLIANT", "PARTIAL"})
    | FAIL_VERDICTS
)


def merge_verdicts(verdicts: list[str]) -> str:
    """Aggregate multiple verdicts via priority order.

    Priority (highest first):
        1. Any token in FAIL_VERDICTS -> CRITICAL_FAIL
        2. Any WARN or PARTIAL -> WARN (PARTIAL is warn-equivalent)
        3. Any DID_NOT_RUN, UNKNOWN, or unrecognized token -> UNKNOWN
        4. Empty sequence -> UNKNOWN
        5. All remaining tokens (PASS or COMPLIANT) -> PASS (COMPLIANT is pass-equivalent)

    UNKNOWN downgrades a would-be PASS (caller cannot claim PASS when an axis
    failed to evaluate) but does not override real WARN or CRITICAL_FAIL
    findings. Unrecognized tokens (e.g. lowercase "pass", "FOOBAR") are
    treated as UNKNOWN per DESIGN-008: silently coercing garbage input to
    PASS would undermine the UNKNOWN safety mechanism. PR #1965 cluster J.

    Refs REQ-008-05 (issue #1934), PR #1965.
    """
    if not verdicts:
        return "UNKNOWN"

    for v in verdicts:
        if v in FAIL_VERDICTS:
            return "CRITICAL_FAIL"

    # WARN and PARTIAL are warn-equivalent. PR #1965 coderabbit Y14:
    # PARTIAL is a CI-valid token from the spec-validation flow.
    if "WARN" in verdicts or "PARTIAL" in verdicts:
        return "WARN"

    # Any DID_NOT_RUN, UNKNOWN, or unrecognized token -> UNKNOWN. Do NOT silently
    # coerce unknown tokens to PASS.
    if any(v not in _KNOWN_VERDICT_TOKENS or v in {"DID_NOT_RUN", "UNKNOWN"} for v in verdicts):
        return "UNKNOWN"

    # All remaining tokens are PASS-equivalent (PASS or COMPLIANT).
    return "PASS"


# IGNORECASE is scoped to the label only via (?i:...).
# The token alternation must remain case-sensitive uppercase: a skill emitting
# `Verdict: pass` (lowercase token) is malformed and should return UNKNOWN, not
# silently match `PASS`. Per PR #1965 cursor + gemini review (cluster A):
# global (?mi) caused silent verdict misclassification.
# NEEDS_REVIEW added per PR #1965 coderabbit Y7: it is in FAIL_VERDICTS so a
# skill emitting `Verdict: NEEDS_REVIEW` must be parsed as that token, not
# downgraded to UNKNOWN.
# Template-form rejection per PR #1965 copilot 7k: the axis prompts contain
# literal template lines like `VERDICT: [PASS|WARN|CRITICAL_FAIL]`. Without
# the trailing `(?![|A-Z_])` lookahead, the alternation greedily matches the
# first token (`PASS`) and silently coerces a template echo to a real verdict.
# The lookahead also rejects unknown uppercase tokens that happen to share a
# prefix with a known verdict (e.g., `PASS_THROUGH`).
_EXTRACT_VERDICT_PATTERN = re.compile(
    r"(?m)^\s*(?i:(?:Final\s+)?Verdict):\s*"
    r"\[?(PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|NEEDS_REVIEW|"
    r"NON_COMPLIANT|COMPLIANT|PARTIAL|DID_NOT_RUN|UNKNOWN)(?![|A-Z_])\]?",
)

_LOCAL_REVIEW_AXES = frozenset(
    {
        "code-qualities-assessment",
        "doc-accuracy",
        "golden-principles",
        "taste-lints",
    }
)
_DOC_ACCURACY_GATE_PATTERN = re.compile(
    r"(?m)^\s*(?:\*\*)?Gate:\s*(PASS|FAIL|DID_NOT_RUN)(?![|A-Z_])\b"
)


def extract_verdict(text: str) -> str:
    """Scan text for a verdict marker and return the LAST matched token.

    Matches lines of the form ``Verdict: <TOKEN>`` or ``Final verdict: <TOKEN>``
    (case-insensitive on the label, exact match on the token). Returns the
    LAST match (per axis convention "the response MUST contain a final line
    matching..."); an early example of `Verdict: PASS` inside a code block or
    explanation cannot override the real final verdict. PR #1965 coderabbit Y5.

    Returns ``UNKNOWN`` when no match is found or input is empty.

    Use this to parse skill output that may embed a verdict in multi-line
    markdown, where ``get_verdict`` keyword fallbacks would over-match.

    Refs REQ-008-05 (issue #1934).
    """
    if not text or not text.strip():
        return "UNKNOWN"
    matches = _EXTRACT_VERDICT_PATTERN.findall(text)
    return matches[-1] if matches else "UNKNOWN"


def _load_json_object(text: str) -> dict[str, object] | None:
    """Return a top-level JSON object, or None when stdout is not JSON."""
    if not text or not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _coerce_nonnegative_int(value: object) -> int | None:
    """Return a non-negative integer field, or None when the value is invalid."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


# assess.py short-circuits one label before scoring: `if category ==
# "generated": return _unscored_generated_assessment(file_path)`, so a
# generated entry is counted in `files` and never assessed. `/review` says the
# same in prose: generated artifacts create no local quality finding.
_ASSESSED_CATEGORIES = frozenset({"authored", "test"})
# The full label set `classify_file_category` can return. Anything else is a
# payload shape this adapter does not recognize.
_KNOWN_CATEGORIES = _ASSESSED_CATEGORIES | {"generated"}

# `_unreadable_assessment` keeps the file's real category while setting every
# one of these to confidence 0.0, "so ``check_thresholds`` skips the file",
# so category alone never proves the scanner scored anything. A file in a
# language assess.py does not support (Markdown, JSON) is also all 0.0 under
# the `authored` label, which is the same shape. `_unreadable_assessment`
# alone sets `scoring_failed` true, which is the only field that separates a
# hole in the evidence from a file that was never in scope for scoring.
_QUALITY_FIELDS = ("cohesion", "coupling", "encapsulation", "testability", "non_redundancy")


def _is_scored(entry: dict[str, object]) -> bool:
    """Return True when at least one quality on *entry* carries confidence."""
    for field in _QUALITY_FIELDS:
        quality = entry.get(field)
        if not isinstance(quality, dict):
            continue
        score = quality.get("confidence")
        if isinstance(score, int | float) and not isinstance(score, bool) and score > 0:
            return True
    return False


def _is_unscorable_by_design(entry: dict[str, object]) -> bool:
    """Return True when *entry* is unscored and assess.py says it did not fail.

    Requires ``scoring_failed`` to be present and exactly ``False``. A missing
    field (an older assess.py) or a non-boolean value is not evidence that the
    file was out of scope, so it stays a hole and the axis fails closed.
    """
    return not _is_scored(entry) and entry.get("scoring_failed") is False


_PARSER_SCANNER = "src/claude/skills/code-qualities-assessment/scripts/assess.py"

# The only coupling transitions the review adapter may report as WARN
# (ADR-122). Each JSON field must carry exactly its fixed record.
_PARSER_DEPENDENCY_ADMISSIONS: dict[str, dict[str, object]] = {
    "csharp_parser_dependency_admission": {
        "issue": 7406,
        "file": _PARSER_SCANNER,
        "imports": ["tree_sitter", "tree_sitter_c_sharp"],
        "baseScore": 10.0,
        "headScore": 8.0,
        "authorizedBy": "rjmurillo",
        "authorizedOn": "2026-11-16",
        "authorization": "Maintainer instruction: waiver, full send.",
    },
    "typescript_parser_dependency_admission": {
        "issue": 7435,
        "file": _PARSER_SCANNER,
        "imports": ["tree_sitter", "tree_sitter_c_sharp", "tree_sitter_typescript"],
        "baseScore": 8.0,
        "headScore": 7.0,
        "authorizedBy": "rjmurillo",
        "authorizedOn": "2026-11-18",
        "authorization": (
            "Maintainer instruction: LGTM. Ship. agent- environment is optional. "
            "Package add approved"
        ),
    },
    "python_parser_dependency_admission": {
        "issue": 7436,
        "file": _PARSER_SCANNER,
        "imports": [
            "tree_sitter",
            "tree_sitter_c_sharp",
            "tree_sitter_python",
            "tree_sitter_typescript",
        ],
        "baseScore": 7.0,
        "headScore": 6.0,
        "authorizedBy": "rjmurillo",
        "authorizedOn": "2026-11-18",
        "authorization": (
            "Maintainer instruction: LGTM. Ship. agent- environment is optional. "
            "Package add approved"
        ),
    },
}


# ADR-122 item 10: the adapter's own copy of the eight issue #7493 change
# records. The scanner holds a second copy; a conformance test keeps them equal.
_RENEWED_SEARCH_HEAD = "9128445e248852cd578927c6753b237f68ac510a"
_RENEWED_SHIM_HEAD = "9738fc16fc731f74d61d21ef7bf95240a241a046"
# The decisions that renewed each head pin, keyed by the renewed head blob.
_RENEWAL_NOTES: dict[str, str] = {
    _RENEWED_SEARCH_HEAD: (
        " Maintainer decisions D5 (2026-11-22, issue #7493 comment 7086682234),"
        " D9 (2026-11-23, issue #7493 comment 7120119475), and D12"
        " (2026-11-23, issue #7493 comment 7121288491) renewed this head pin."
        " Maintainer decision D13 (2026-11-23, issue #7493 comment 7121992178)"
        " set the cohesion head score to 2.0."
    ),
    _RENEWED_SHIM_HEAD: (
        " Maintainer decision D12 (2026-11-23, issue #7493 comment 7121288491)"
        " renewed this head pin."
    ),
}

_CHANGE_ADMISSIONS: tuple[dict[str, object], ...] = tuple(
    {
        "issue": 7493,
        "file": file,
        "quality": quality,
        "baseScore": base,
        "headScore": head,
        "baseBlob": base_blob,
        "headBlob": head_blob,
        "authorizedBy": "rjmurillo",
        "authorizedOn": "2026-11-20",
        "authorization": (
            "Maintainer decisions D1 and D2, choice A: "
            "admit all 8 transitions as fixed records in one ADR-122 item."
            + _RENEWAL_NOTES.get(str(head_blob), "")
        ),
    }
    for file, quality, base, head, base_blob, head_blob in (
        (
            "build/scripts/lib_mirror.py",
            "coupling",
            8.0,
            7.0,
            "7477415f3dd715ef624f6cb14f5233d3afda9c48",
            "83f7c976ca63a7af312b05294281f084c5dea7a2",
        ),
        (
            "scripts/memory_enhancement/hooks/user_prompt_submit_memory.py",
            "cohesion",
            6.3,
            4.2,
            "32c45daf664cb0ace70a540d2fbd7088bc03cca8",
            "3d8a383a59c4b6b0ad5a5a6e7cd8cf33fc3d4a88",
        ),
        (
            "scripts/memory_enhancement/hooks/user_prompt_submit_memory.py",
            "coupling",
            6.0,
            3.0,
            "32c45daf664cb0ace70a540d2fbd7088bc03cca8",
            "3d8a383a59c4b6b0ad5a5a6e7cd8cf33fc3d4a88",
        ),
        (
            "scripts/memory_enhancement/search.py",
            "cohesion",
            4.2,
            2.0,
            "1dcb875cc1a14544bf3ff6294a45894fe2ae1106",
            _RENEWED_SEARCH_HEAD,
        ),
        (
            "scripts/memory_enhancement/search.py",
            "coupling",
            5.0,
            3.0,
            "1dcb875cc1a14544bf3ff6294a45894fe2ae1106",
            _RENEWED_SEARCH_HEAD,
        ),
        (
            "templates/hooks/UserPromptSubmit/invoke_memory_recall.py",
            "cohesion",
            9.2,
            7.7,
            "a828ad1f7182aa81effb649de69f5a8b81ff2f1e",
            _RENEWED_SHIM_HEAD,
        ),
        (
            "templates/hooks/invoke_dispatch_claude.py",
            "cohesion",
            5.7,
            4.6,
            "0672c74a1924030150352d7c96a04c0a60024d52",
            "6c83d8f9257a717d614173604abb4a7f4cb83d1c",
        ),
        (
            "tests/build_scripts/test_lib_mirror.py",
            "coupling",
            7.0,
            6.0,
            "e4259bb802bf1c14290e0fca6c425e9611caf532",
            "c8214f85fb74aa7b18ad5f611e88e3a1220cd8b2",
        ),
    )
)


def _delta_matches_record(comparison: dict[str, object], record: dict[str, object]) -> bool:
    """Return True when the delta for the record quality is exactly its transition."""
    deltas = comparison.get("deltas")
    if not isinstance(deltas, list):
        return False
    base, head = record["baseScore"], record["headScore"]
    if not (isinstance(base, float) and isinstance(head, float)):
        return False
    expected = (base, head, round(head - base, 4), "compared")
    return any(
        isinstance(d, dict)
        and d.get("quality") == record["quality"]
        and (d.get("base"), d.get("head"), d.get("delta"), d.get("status")) == expected
        for d in deltas
    )


def _is_admitted_change(comparison: dict[str, object]) -> bool:
    """Return True only when ``change_admissions`` is exactly the regressions' fixed records."""
    records = comparison.get("change_admissions")
    regressions = comparison.get("regressions")
    if not isinstance(records, list) or not records or not isinstance(regressions, list):
        return False
    if comparison.get("evidence_loss") or comparison.get("absolute_gate_reason") is not None:
        return False
    if comparison.get("is_new_file") is not False or comparison.get("change_status") != "M":
        return False
    path = str(comparison.get("file_path", "")).replace("\\", "/")
    blobs = (comparison.get("base_blob"), comparison.get("head_blob"))
    qualities = [r.get("quality") if isinstance(r, dict) else None for r in records]
    if any(not isinstance(quality, str) for quality in qualities + regressions):
        return False
    if len(set(qualities)) != len(qualities) or set(qualities) != set(regressions):
        return False
    return all(
        isinstance(r, dict)
        and r in _CHANGE_ADMISSIONS
        and r["file"] == path
        and blobs == (r["baseBlob"], r["headBlob"])
        and _delta_matches_record(comparison, r)
        for r in records
    )


def _is_admitted_parser_transition(comparison: dict[str, object], field: str) -> bool:
    """Return True only for the exact scanner transition the *field* record admits."""
    record = _PARSER_DEPENDENCY_ADMISSIONS[field]
    if comparison.get(field) != record:
        return False
    base, head = record["baseScore"], record["headScore"]
    assert isinstance(base, float) and isinstance(head, float)
    match comparison:
        case {
            "file_path": str() as file_path,
            "regressions": ["coupling"],
            "evidence_loss": [],
            "is_new_file": False,
            "change_status": "M",
            "deltas": list() as deltas,
        }:
            # The scanner emits one delta per quality, so a second coupling
            # delta is a conflicting payload, never an admitted one.
            coupling = [d for d in deltas if isinstance(d, dict) and d.get("quality") == "coupling"]
            return (
                file_path.replace("\\", "/") == _PARSER_SCANNER
                and comparison.get("absolute_gate_reason") is None
                and coupling
                == [
                    {
                        "quality": "coupling",
                        "base": base,
                        "head": head,
                        "delta": round(head - base, 4),
                        "status": "compared",
                    }
                ]
            )
    return False


# Issue #7525: drops the scanner admits because the change added no
# third-party import root (coupling) or no duplicated line (non_redundancy).
_RULE_ADMISSION_ISSUE = 7525
_RULE_ADMISSION_RULES = {
    "coupling": "no_new_third_party_import",
    "non_redundancy": "no_new_duplicate_lines",
}


def _is_count(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_name_list(value: object) -> TypeGuard[list[str]]:
    return isinstance(value, list) and all(isinstance(name, str) and name for name in value)


def _is_valid_rule_record(quality: str, record: object) -> bool:
    """Return True when *record* proves its rule held for *quality*.

    A quality with no admission rule never validates, so a record cannot turn
    a cohesion or testability regression into WARN.
    """
    rule = _RULE_ADMISSION_RULES.get(quality)
    if rule is None or not isinstance(record, dict):
        return False
    if (record.get("issue"), record.get("rule")) != (_RULE_ADMISSION_ISSUE, rule):
        return False
    if quality == "coupling":
        base, head = record.get("baseThirdParty"), record.get("headThirdParty")
        return _is_name_list(base) and _is_name_list(head) and set(head) <= set(base)
    base, head = record.get("baseDuplicateLines"), record.get("headDuplicateLines")
    return _is_count(base) and _is_count(head) and head <= base


def _rule_admission_verdict(comparison: dict[str, object]) -> str:
    """Return PASS, WARN, FAIL, or UNKNOWN for one comparison without a parser record.

    Evidence loss and any regression without a valid admission fail. A record
    for a quality that did not regress, or one whose own numbers break its
    rule, is a payload this adapter cannot vouch for.
    """
    regressions = comparison.get("regressions") or []
    admissions = comparison.get("rule_admissions")
    if not _is_name_list(regressions):
        return "UNKNOWN"
    if admissions is not None:
        if (
            not isinstance(admissions, dict)
            or not admissions
            or not set(admissions) <= set(regressions)
            or comparison.get("is_new_file") is not False
            or comparison.get("absolute_gate_reason") is not None
            or not all(_is_valid_rule_record(q, r) for q, r in admissions.items())
        ):
            return "UNKNOWN"
    if comparison.get("evidence_loss"):
        return "FAIL"
    if not regressions:
        return "PASS"
    if admissions is None or set(regressions) - set(admissions):
        return "FAIL"
    return "WARN"


def _has_assessed_files(files: list[object], summary: dict[str, object]) -> bool:
    """Return True when the assessment actually evaluated at least one file.

    Requires a positive ``summary.file_count`` that agrees with the length of
    ``files``. A disagreement means the two halves of the payload describe
    different runs, which is not evidence of a pass.

    Requires at least one eligible entry that carries a scored metric. An
    eligible entry that failed to score is a hole in the evidence and blocks
    the pass, even beside scored siblings: ``scoring_failed`` true, a missing
    marker, or a non-boolean marker. An eligible entry that is unscored with
    ``scoring_failed`` exactly false is a file in a language the scanner does
    not support (Markdown, JSON), so it is ignored like a generated entry.
    Generated-only or unsupported-only output is a file list, not a review.
    """
    file_count = summary.get("file_count")
    if isinstance(file_count, bool) or not isinstance(file_count, int):
        return False
    if not (file_count > 0 and file_count == len(files)):
        return False
    # Every entry must be a recognizable assessment. A non-object, or a
    # category this adapter does not know, is output it cannot vouch for, and
    # letting a valid sibling carry it would be the partial-evidence pass this
    # function exists to refuse.
    entries: list[dict[str, object]] = [entry for entry in files if isinstance(entry, dict)]
    if len(entries) != len(files):
        return False
    if not all(entry.get("category") in _KNOWN_CATEGORIES for entry in entries):
        return False
    # Each entry must name a distinct file. assess.py emits `file_path` from
    # the dataclass field of that name, and duplicates cannot occur in a real
    # run, so a repeated or missing identity is a payload padded to satisfy the
    # file_count check while hiding an assessment that never happened.
    paths = [entry.get("file_path") for entry in entries]
    if not all(isinstance(name, str) and name.strip() for name in paths):
        return False
    if len(set(paths)) != len(paths):
        return False
    eligible = [entry for entry in entries if entry.get("category") in _ASSESSED_CATEGORIES]
    # An entry flagged failed is a hole even if a metric looks scored. An
    # unscored entry is a hole unless it is marked as not failed. A scored
    # sibling never covers for either.
    for entry in eligible:
        if entry.get("scoring_failed") is True:
            return False
        if not _is_scored(entry) and not _is_unscorable_by_design(entry):
            return False
    return any(_is_scored(entry) for entry in eligible)


def _has_linted_category(payload: dict[str, object]) -> bool:
    """Return True when taste-lints linted a file, not just counted one.

    Its ``classify_file_category`` returns the same three labels assess.py
    uses, and only authored and test reach a rule.
    """
    by_category = payload.get("files_by_category")
    if not isinstance(by_category, dict):
        return False
    return any(_coerce_nonnegative_int(by_category.get(name)) for name in _ASSESSED_CATEGORIES)


def _has_inventoried_docs(payload: dict[str, object]) -> bool:
    """Return True when doc-accuracy inventoried every changed document.

    ``assessment.documentation_files`` is built from ``DOC_GLOBS``; empty means
    the gate had nothing to check, so its PASS is silence. A non-empty
    inventory is not enough either: ``changed_files`` can name a Markdown file
    the walk pruned, and a gate that examined the rest still reports PASS,
    hiding the one it never opened.
    """
    assessment = payload.get("assessment")
    if not isinstance(assessment, dict):
        return False
    documentation_files = assessment.get("documentation_files")
    if not isinstance(documentation_files, list) or not documentation_files:
        return False
    inventoried = {entry.get("path") for entry in documentation_files if isinstance(entry, dict)}
    changed = assessment.get("changed_files")
    if not isinstance(changed, list):
        # No diff scope, so there is no changed set to be complete against.
        return True
    return all(
        name in inventoried for name in changed if isinstance(name, str) and name.endswith(".md")
    )


def _changed_markdown_missing(assessment: dict[str, object]) -> bool:
    """Return True when a changed Markdown path is absent from the inventory."""
    changed = assessment.get("changed_files")
    if not isinstance(changed, list):
        return False
    docs = assessment.get("documentation_files")
    inventoried = (
        {entry.get("path") for entry in docs if isinstance(entry, dict)}
        if isinstance(docs, list)
        else set()
    )
    return any(
        isinstance(name, str) and name.endswith(".md") and name not in inventoried
        for name in changed
    )


def _clean_same_pr_scan(payload: dict[str, object] | None) -> bool:
    """Return True when a finished same-PR scan left no Markdown unchecked.

    ``/review`` runs ``doc_accuracy.py --same-pr --format gate``. That scan
    reads Python, templates, and data files, so a diff with no Markdown still
    produces an empty ``documentation_files`` list. ``scanned_files`` of zero
    is a finished scan of a diff with nothing to open. A bool is not a count.
    A changed ``.md`` the inventory omitted stays unchecked.
    """
    if not isinstance(payload, dict):
        return False
    assessment = payload.get("assessment")
    if not isinstance(assessment, dict) or _changed_markdown_missing(assessment):
        return False
    same_pr = payload.get("same_pr")
    if not isinstance(same_pr, dict):
        return False
    findings = same_pr.get("findings")
    examined = findings.get("examined") if isinstance(findings, dict) else None
    scanned = examined.get("scanned_files") if isinstance(examined, dict) else None
    return _coerce_nonnegative_int(scanned) is not None


def adapt_local_axis_verdict(
    axis: str,
    output: str,
    exit_code: int,
) -> str:
    """Normalize local-axis outputs into review verdict tokens.

    `/review` chains four local-only skills whose raw contracts are not the
    canonical `Verdict:` line:

    - `code-qualities-assessment` emits JSON and gates by exit code.
    - `doc-accuracy` emits `gate_result.verdict` JSON, or `Gate:` in summary
      mode for older callers.
    - `golden-principles` and `taste-lints` emit JSON with `error_count` and
      `warning_count`, and gate by the exit code quoted below.

    The adapter returns one of PASS, WARN, FAIL, or UNKNOWN so the caller can
    merge the local-axis result with canonical-axis verdicts. Unknown or
    malformed output fails closed to UNKNOWN.
    """
    if axis not in _LOCAL_REVIEW_AXES:
        raise ValueError(f"unknown local review axis: {axis}")

    payload = _load_json_object(output)

    if axis == "code-qualities-assessment":
        if payload is None:
            return "UNKNOWN"
        files = payload.get("files")
        summary = payload.get("summary")
        if not isinstance(files, list) or not isinstance(summary, dict):
            return "UNKNOWN"
        # The skill documents both as gate failures that fail the PR: exit 10
        # is a regressed comparable, exit 11 a new file below thresholds
        # (.claude/skills/code-qualities-assessment/SKILL.md:376-377). WARN let a failing
        # gate be acknowledged and shipped instead of blocking the merge.
        if exit_code in {10, 11}:
            return "FAIL"
        if exit_code != 0:
            return "UNKNOWN"
        # A clean exit over zero files is silence, not a pass: in regression
        # mode assess.py emits `files: []` for a deletion-only diff.
        if not _has_assessed_files(files, summary):
            return "UNKNOWN"
        comparisons = payload.get("comparisons", [])
        if not isinstance(comparisons, list):
            return "UNKNOWN"
        verdicts = ["PASS"]
        for comparison in comparisons:
            if not isinstance(comparison, dict):
                return "UNKNOWN"
            admitted = [
                field
                for field in _PARSER_DEPENDENCY_ADMISSIONS
                if comparison.get(field) is not None
            ]
            if comparison.get("change_admissions") is not None:
                if (
                    admitted
                    or comparison.get("rule_admissions") is not None
                    or not _is_admitted_change(comparison)
                ):
                    return "UNKNOWN"
                verdicts.append("WARN")
                continue
            if admitted:
                if comparison.get("rule_admissions") is not None:
                    return "UNKNOWN"
                if len(admitted) != 1 or not _is_admitted_parser_transition(
                    comparison, admitted[0]
                ):
                    return "UNKNOWN"
                verdicts.append("WARN")
                continue
            verdict = _rule_admission_verdict(comparison)
            if verdict == "WARN":
                verdicts.append(verdict)
            elif verdict != "PASS":
                return verdict
        return merge_verdicts(verdicts)

    if axis == "doc-accuracy":
        gate_verdict: object | None = None
        inventoried_docs = False
        if payload is not None:
            gate_result = payload.get("gate_result")
            if isinstance(gate_result, dict):
                gate_verdict = gate_result.get("verdict")
            inventoried_docs = _has_inventoried_docs(payload)
        if gate_verdict is None:
            # Summary mode prints no examined-file count, so a clean Gate line
            # cannot separate "checked the docs" from "found no docs". It can
            # report FAIL, which needs no such evidence, but never PASS.
            matches = _DOC_ACCURACY_GATE_PATTERN.findall(output)
            gate_verdict = matches[-1] if matches else None
        # check_gate passes whenever no claim contradicts the code, and a run
        # that inventoried nothing has no claims. A deletion-only Markdown diff,
        # or one under EXCLUDE_DIRS, passes without opening a changed file.
        # A same-PR scan that finished with no Markdown left out is not that
        # silence: the gate JSON carries the examined-file count.
        if (
            gate_verdict == "PASS"
            and exit_code == 0
            and (inventoried_docs or _clean_same_pr_scan(payload))
        ):
            return "PASS"
        if gate_verdict == "FAIL" and exit_code == 10:
            return "FAIL"
        if gate_verdict == "DID_NOT_RUN" or exit_code == 1:
            return "UNKNOWN"
        return "UNKNOWN"

    # golden-principles and taste-lints ship one exit-code contract, stated
    # identically in the Exit Codes tables of
    # .claude/skills/golden-principles/SKILL.md and .claude/skills/taste-lints/SKILL.md:
    #   | 0 | No violations found |
    #   | 1 | Script error (bad arguments, file not found) |
    #   | 10 | Violations detected |
    # Read the status before the counts. A scanner that died mid-run still
    # prints whatever counts it had accumulated, so trusting the payload first
    # lets a script error be acknowledged as a WARN, and lets a status the
    # contract never defined be reported as a FAIL.
    if exit_code not in {0, 10}:
        return "UNKNOWN"
    if payload is None:
        return "UNKNOWN"

    error_count = _coerce_nonnegative_int(payload.get("error_count"))
    warning_count = _coerce_nonnegative_int(payload.get("warning_count"))
    if error_count is None or warning_count is None:
        return "UNKNOWN"
    # Both scanners take their file list from a diff, which names deleted
    # paths, then guard `files_scanned += 1` with `if not
    # os.path.isfile(filepath): continue`, so a deletion-only diff exits 0
    # with every count at zero.
    if not _coerce_nonnegative_int(payload.get("files_scanned")):
        return "UNKNOWN"
    # golden-principles narrows once more: applicable_files counts what a GP
    # rule governs, and its axis note says a clean result on a non-toolkit repo
    # "means no rule applied, not that design was reviewed".
    if axis == "golden-principles" and not _coerce_nonnegative_int(payload.get("applicable_files")):
        return "UNKNOWN"
    # taste-lints counts a generated file into files_scanned then skips it
    # without running a rule, so it reports the split in files_by_category.
    if axis == "taste-lints" and not _has_linted_category(payload):
        return "UNKNOWN"
    # Both scanners derive that status from this very field: `if
    # result.error_count > 0: return EXIT_VIOLATIONS` then `return
    # EXIT_SUCCESS` (scan_principles.py main(), taste_lints.py main()).
    # Exit 10 and a positive error_count are therefore one condition, so a
    # disagreement means the status and the payload describe different runs
    # and neither is evidence.
    if exit_code == 10:
        return "FAIL" if error_count > 0 else "UNKNOWN"
    if error_count > 0:
        return "UNKNOWN"
    return "WARN" if warning_count > 0 else "PASS"


_INFRA_PATTERNS = re.compile(
    "|".join(
        [
            r"timed?\s*out",
            r"timeout",
            r"rate\s*limit",
            r"429",
            r"network\s*error",
            r"502\s*Bad\s*Gateway",
            r"503\s*Service\s*Unavailable",
            r"connection\s*(refused|reset|timeout)",
            r"Copilot\s*CLI\s*failed.*with\s*no\s*output",
            r"missing\s*Copilot\s*access",
            r"insufficient\s*scopes",
        ]
    ),
    re.IGNORECASE,
)


def get_failure_category(
    message: str = "",
    stderr: str = "",
    exit_code: int = 0,
) -> str:
    """Categorize failure as INFRASTRUCTURE or CODE_QUALITY.

    Infrastructure failures (timeouts, rate limits, network errors)
    should not block PRs, while code quality failures should.
    """
    if exit_code == 124:
        return "INFRASTRUCTURE"

    if message and message.strip() and _INFRA_PATTERNS.search(message):
        return "INFRASTRUCTURE"

    if stderr and stderr.strip() and _INFRA_PATTERNS.search(stderr):
        return "INFRASTRUCTURE"

    if (not message or not message.strip()) and (not stderr or not stderr.strip()):
        return "INFRASTRUCTURE"

    return "CODE_QUALITY"


_TRACE_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "NEEDS_REVIEW"})
_COMPLETENESS_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "PARTIAL", "NEEDS_REVIEW"})


def spec_validation_failed(
    trace_verdict: str,
    completeness_verdict: str,
) -> bool:
    """Return True if spec validation should block merge.

    Normalizes verdicts to uppercase for case-insensitive comparison.
    """
    trace_upper = trace_verdict.upper() if trace_verdict else ""
    completeness_upper = completeness_verdict.upper() if completeness_verdict else ""
    return trace_upper in _TRACE_FAILURES or completeness_upper in _COMPLETENESS_FAILURES


_JSON_LABELS_PATTERN = re.compile(r'"labels"\s*:\s*\[([^\]]*)\]')
_JSON_MILESTONE_PATTERN = re.compile(r'"milestone"\s*:\s*"([^"]*)"')

SAFE_NAME_PATTERN = re.compile(r"^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _.\-]*[A-Za-z0-9])?$")


def get_labels_from_ai_output(output: str | None) -> list[str]:
    """Parse labels from AI JSON output with security hardening.

    Validates each label against a strict pattern that blocks
    shell metacharacters (; | ` $ etc.) and enforces length limits.
    """
    if not output or not output.strip():
        return []

    match = _JSON_LABELS_PATTERN.search(output)
    if not match:
        return []

    array_content = match.group(1)
    if not array_content or not array_content.strip():
        return []

    labels: list[str] = []
    for raw in array_content.split(","):
        label = raw.strip().strip('"').strip("'")
        if not label or not label.strip():
            continue
        if SAFE_NAME_PATTERN.match(label):
            labels.append(label)
    return labels


def get_milestone_from_ai_output(output: str | None) -> str | None:
    """Parse milestone from AI JSON output with security hardening.

    Returns None if the milestone is missing, empty, or fails validation.
    """
    if not output or not output.strip():
        return None

    match = _JSON_MILESTONE_PATTERN.search(output)
    if not match:
        return None

    milestone = match.group(1)
    if not milestone or not milestone.strip():
        return None

    if SAFE_NAME_PATTERN.match(milestone):
        return milestone
    return None
