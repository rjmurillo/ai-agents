"""Verdict parsing, label/milestone extraction, and failure categorization."""

from __future__ import annotations

import re

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


FAIL_VERDICTS = frozenset(
    {"CRITICAL_FAIL", "REJECTED", "FAIL", "NEEDS_REVIEW", "NON_COMPLIANT"}
)


# Tokens accepted by .github/actions/ai-review/action.yml's parse step:
# PASS, WARN, CRITICAL_FAIL, REJECTED, COMPLIANT, NON_COMPLIANT, PARTIAL, FAIL.
# Plus NEEDS_REVIEW (added by Issue #470 fix) and UNKNOWN (added by #1934).
# merge_verdicts must not treat these CI-valid tokens as unknown garbage.
# PR #1965 coderabbit Y14.
_KNOWN_VERDICT_TOKENS: frozenset[str] = (
    frozenset({"PASS", "WARN", "UNKNOWN", "COMPLIANT", "NON_COMPLIANT", "PARTIAL"})
    | FAIL_VERDICTS
)


def merge_verdicts(verdicts: list[str]) -> str:
    """Aggregate multiple verdicts via priority order.

    Priority (highest first):
        1. Any token in FAIL_VERDICTS -> CRITICAL_FAIL
        2. Any WARN -> WARN
        3. Any UNKNOWN OR any unrecognized token (and none of the above) -> UNKNOWN
        4. Empty sequence -> UNKNOWN
        5. All PASS -> PASS

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

    # Any UNKNOWN or any unrecognized token -> UNKNOWN. Do NOT silently
    # coerce unknown tokens to PASS.
    if any(v not in _KNOWN_VERDICT_TOKENS or v == "UNKNOWN" for v in verdicts):
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
_EXTRACT_VERDICT_PATTERN = re.compile(
    r"(?m)^\s*(?i:(?:Final\s+)?Verdict):\s*"
    r"\[?(PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|NEEDS_REVIEW|"
    r"NON_COMPLIANT|COMPLIANT|PARTIAL|UNKNOWN)\]?",
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


_INFRA_PATTERNS = re.compile(
    "|".join([
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
    ]),
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

SAFE_NAME_PATTERN = re.compile(
    r"^(?=.{1,50}$)[A-Za-z0-9](?:[A-Za-z0-9 _.\-]*[A-Za-z0-9])?$"
)


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
