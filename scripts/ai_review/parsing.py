"""AI output parsing: verdicts, labels, milestones, failure categorization."""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------

_VERDICT_PATTERN = re.compile(r"VERDICT:\s*([A-Z_]+)")

_KEYWORD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"CRITICAL_FAIL|critical failure|severe issue", re.IGNORECASE), "CRITICAL_FAIL"),
    (re.compile(r"REJECTED|reject|must fix|blocking", re.IGNORECASE), "REJECTED"),
    (re.compile(r"PASS|approved|looks good|no issues", re.IGNORECASE), "PASS"),
    (re.compile(r"WARN|warning|caution", re.IGNORECASE), "WARN"),
]


def get_verdict(output: str) -> str:
    """Parse verdict from AI output.

    Tries explicit ``VERDICT:`` pattern first, then falls back to keyword detection.

    Returns one of: PASS, WARN, REJECTED, CRITICAL_FAIL.
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


# ---------------------------------------------------------------------------
# Label / milestone parsing (LABEL: / MILESTONE: format)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Verdict aggregation
# ---------------------------------------------------------------------------

_FAIL_VERDICTS = frozenset({"CRITICAL_FAIL", "REJECTED", "FAIL"})


def merge_verdicts(verdicts: list[str]) -> str:
    """Aggregate multiple verdicts: CRITICAL_FAIL/REJECTED/FAIL > WARN > PASS."""
    if not verdicts:
        return "PASS"

    for v in verdicts:
        if v in _FAIL_VERDICTS:
            return "CRITICAL_FAIL"

    if "WARN" in verdicts:
        return "WARN"

    return "PASS"


# ---------------------------------------------------------------------------
# Failure categorization
# ---------------------------------------------------------------------------

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
    verdict: str = "",
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


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------

_TRACE_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "NEEDS_REVIEW"})
_COMPLETENESS_FAILURES = frozenset({"CRITICAL_FAIL", "FAIL", "PARTIAL", "NEEDS_REVIEW"})


def spec_validation_failed(
    trace_verdict: str,
    completeness_verdict: str,
) -> bool:
    """Return True if spec validation should block merge.

    PowerShell's ``-in`` is case-insensitive; Python is not.
    We normalize to uppercase for comparison.
    """
    trace_upper = trace_verdict.upper() if trace_verdict else ""
    completeness_upper = completeness_verdict.upper() if completeness_verdict else ""
    return trace_upper in _TRACE_FAILURES or completeness_upper in _COMPLETENESS_FAILURES


# ---------------------------------------------------------------------------
# Security-hardened JSON parsing (labels / milestones)
# ---------------------------------------------------------------------------

_JSON_LABELS_PATTERN = re.compile(r'"labels"\s*:\s*\[([^\]]*)\]')
_JSON_MILESTONE_PATTERN = re.compile(r'"milestone"\s*:\s*"([^"]*)"')

# Strict validation: alphanumeric start, optional middle with safe chars,
# alphanumeric end, max 50 chars total.
_SAFE_NAME_PATTERN = re.compile(
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
        if _SAFE_NAME_PATTERN.match(label):
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

    if _SAFE_NAME_PATTERN.match(milestone):
        return milestone
    return None
