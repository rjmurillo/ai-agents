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
# Plus NEEDS_REVIEW (added by Issue #470 fix), UNKNOWN (added by #1934), and
# DID_NOT_RUN (added by #2818/#2821 for infrastructure failures that skipped review).
# merge_verdicts must not treat these CI-valid tokens as unknown garbage.
# PR #1965 coderabbit Y14.
_KNOWN_VERDICT_TOKENS: frozenset[str] = (
    frozenset(
        {"PASS", "WARN", "UNKNOWN", "DID_NOT_RUN", "COMPLIANT", "NON_COMPLIANT", "PARTIAL"}
    )
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
# so category alone never proves the scanner scored anything.
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


def _has_assessed_files(files: list[object], summary: dict[str, object]) -> bool:
    """Return True when the assessment actually evaluated at least one file.

    Requires a positive ``summary.file_count`` that agrees with the length of
    ``files``. A disagreement means the two halves of the payload describe
    different runs, which is not evidence of a pass.

    Requires at least one eligible entry, and every eligible entry to carry a
    scored metric. Generated-only output is a file list, not a review, and an
    eligible file that failed to score is a hole in the evidence. Generated
    entries are exempt; the scanner never scores them.
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
    if not all(
        isinstance(entry, dict) and entry.get("category") in _KNOWN_CATEGORIES
        for entry in files
    ):
        return False
    eligible = [entry for entry in files if entry.get("category") in _ASSESSED_CATEGORIES]
    return bool(eligible) and all(_is_scored(entry) for entry in eligible)


def _has_linted_category(payload: dict[str, object]) -> bool:
    """Return True when taste-lints linted a file, not just counted one.

    Its ``classify_file_category`` returns the same three labels assess.py
    uses, and only authored and test reach a rule.
    """
    by_category = payload.get("files_by_category")
    if not isinstance(by_category, dict):
        return False
    return any(
        _coerce_nonnegative_int(by_category.get(name)) for name in _ASSESSED_CATEGORIES
    )


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
    inventoried = {
        entry.get("path") for entry in documentation_files if isinstance(entry, dict)
    }
    changed = assessment.get("changed_files")
    if not isinstance(changed, list):
        # No diff scope, so there is no changed set to be complete against.
        return True
    return all(
        name in inventoried
        for name in changed
        if isinstance(name, str) and name.endswith(".md")
    )


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
        return "PASS" if _has_assessed_files(files, summary) else "UNKNOWN"

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
        if gate_verdict == "PASS" and exit_code == 0 and inventoried_docs:
            return "PASS"
        if gate_verdict == "FAIL" and exit_code == 10:
            return "FAIL"
        if gate_verdict == "DID_NOT_RUN" or exit_code == 1:
            return "UNKNOWN"
        return "UNKNOWN"

    # golden-principles and taste-lints ship one exit-code contract, stated
    # identically in .claude/skills/golden-principles/SKILL.md:90-96 and
    # .claude/skills/taste-lints/SKILL.md:100-106:
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
    if axis == "golden-principles" and not _coerce_nonnegative_int(
        payload.get("applicable_files")
    ):
        return "UNKNOWN"
    # taste-lints counts a generated file into files_scanned then skips it
    # without running a rule, so it reports the split in files_by_category.
    if axis == "taste-lints" and not _has_linted_category(payload):
        return "UNKNOWN"
    # Both scanners derive that status from this very field: `if
    # result.error_count > 0: return EXIT_VIOLATIONS` then `return
    # EXIT_SUCCESS` (scan_principles.py:455-457, taste_lints.py:1122-1124).
    # Exit 10 and a positive error_count are therefore one condition, so a
    # disagreement means the status and the payload describe different runs
    # and neither is evidence.
    if exit_code == 10:
        return "FAIL" if error_count > 0 else "UNKNOWN"
    if error_count > 0:
        return "UNKNOWN"
    return "WARN" if warning_count > 0 else "PASS"


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
