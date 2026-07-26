#!/usr/bin/env python3
"""Validate a session log against the committed JSON Schema and protocol rules.

Two layers run, and they own different questions:

* ``.agents/schemas/session-log.schema.json`` owns shape: which fields exist,
  what type each holds, which values are in range. It is the single source of
  truth for that, loaded and enforced here rather than restated in Python.
* The protocol checks below own meaning: that a MUST checklist item is actually
  complete, that its evidence is not an empty string, that a branch name and a
  commit SHA look like one. A JSON Schema cannot express those.

Scope: this validates the one file it is handed. Both call sites
(``git_hook_policy.validate_branch_sessions`` and the ai-session-protocol
workflow) pass only session logs changed on the branch, so enabling schema
enforcement binds new and edited logs. Logs written before enforcement are not
re-validated; editing one surfaces its violations, which is the intended signal.

This is a Python port of Validate-SessionJson.ps1 following ADR-042 migration.

EXIT CODES:
  0  - Success: Session log is valid
  1  - Error: Session log validation failed (invalid JSON, missing fields, or schema violations)
  2  - Error: Unexpected error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import FormatChecker
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

# Add project root to path for imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.path_validation import validate_safe_path  # noqa: E402
from scripts.validation.models import ValidationResult  # noqa: E402

SCHEMA_PATH = _PROJECT_ROOT / ".agents" / "schemas" / "session-log.schema.json"

# jsonschema's built-in FormatChecker ships without a "date-time" checker
# unless the "format" extra (rfc3339-validator) is installed; that extra is
# not a project dependency. The committed schema declares `format:
# "date-time"` (developmentPhase.history[].timestamp), and by default
# jsonschema treats "format" as annotation-only, so that constraint was
# silently unenforced. datetime.fromisoformat (Python 3.11+, this project
# requires >=3.14) accepts RFC 3339's "Z" suffix, so a stdlib-only checker
# covers the one format the schema uses without adding a dependency.
_FORMAT_CHECKER = FormatChecker()


@_FORMAT_CHECKER.checks("date-time")
def _check_date_time(value: object) -> bool:
    """Return whether ``value`` is an RFC 3339 date-time, per the schema's format.

    Non-strings are not this keyword's concern: JSON Schema's "format" applies
    only to the type it names, and "type": "string" elsewhere in the schema
    already rejects a non-string value.
    """
    if not isinstance(value, str):
        return True
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True

# Required session fields
REQUIRED_SESSION_FIELDS = frozenset({"number", "date", "branch", "startingCommit", "objective"})

# Branch naming pattern
BRANCH_PATTERN = re.compile(r"^(feat|fix|docs|chore|refactor|test|ci)/")

# Commit SHA pattern
COMMIT_SHA_PATTERN = re.compile(r"^[a-f0-9]{7,40}$")

# Minimum required session start items (must exist in every session log)
SESSION_START_REQUIRED_ITEMS = frozenset(
    {
        "serenaActivated",
        "serenaInstructions",
        "handoffRead",
        "sessionLogCreated",
        "branchVerified",
        "notOnMain",
    }
)

# Minimum required session end items (must exist in every session log)
SESSION_END_REQUIRED_ITEMS = frozenset(
    {
        "checklistComplete",
        "handoffPreserved",
        "serenaMemoryUpdated",
        "markdownLintRun",
        "changesCommitted",
        "validationPassed",
    }
)

# Evidence patterns that contradict a "complete: true" claim
CONTRADICTION_PATTERNS = re.compile(
    r"(?i)\b(not available|skipped|N/A|deferred|will validate|will run|TODO|pending|TBD)\b"
)

# Subset of CONTRADICTION_PATTERNS tokens that legitimately describe a DIFFERENT
# scope than the item under validation. "deferred" and "pending" routinely appear
# in honest multi-scope evidence ("scorer deferred per PRD 11", "lint passed;
# pending pre-commit final run") where a different piece of work, not the item, is
# deferred. The other tokens (TODO, TBD, N/A, skipped, will run, will validate, not
# available) signal the item itself is incomplete and always flag, EXCEPT that a
# "skipped" token that is a numeric pytest outcome count is exempted separately
# (see _NUMERIC_COUNT_TOKENS and issue #3141). See issue #2007.
_SCOPE_QUALIFIED_TOKENS = frozenset({"deferred", "pending"})

# Words that affirmatively report the item itself was done. When such a word
# precedes a scope-qualified token across a clause boundary, the token is a
# trailing note about other work, not a contradiction of the item.
_AFFIRMATIVE_COMPLETION = re.compile(
    r"(?i)\b(pass|passed|passing|done|created|validated|complete|completed"
    r"|confirmed|verified|ran|listed|used)\b"
)

# A clause boundary separating affirmative completion from a trailing deferral.
# NOTE: Do NOT include ')' here. A closing paren allows false suppression when
# an affirmative word sits inside a parenthetical (e.g., "Report (tests passed)
# pending final sign-off" would suppress incorrectly). Legitimate trailing-note
# suppressions use '.' or ';' separators. See bug 80aca362.
#
# A period only counts as a boundary when it is sentence punctuation (followed
# by whitespace or end of string). A period flanked by digits is part of a
# version or decimal (`v1.5`, `Step 0.5`) and is NOT a clause boundary; treating
# it as one suppressed real contradictions like "Created item v1.5 pending
# review". See bug 0a163adc.
_CLAUSE_BOUNDARY = re.compile(r";|\.(?=\s|$)")

# Negation words that negate an affirmative completion.
# When an affirmative word is preceded by these, optionally separated by a
# single adverb ("not yet validated", "no longer confirmed", "not fully done"),
# it does not indicate completion (e.g., "not passed", "never confirmed").
# See bug ref1_1ef17459 and bug 07f14170 (adverb-separated negation).
# Note: "n't" uses (?<=\w) instead of \b because in contractions like "haven't",
# the "n" is preceded by a letter (no word boundary). See bug 0ea9d246.
_NEGATION_BEFORE_AFFIRMATIVE = re.compile(
    r"(?i)(?:\b(?:not|no|never)\b|(?<=\w)n't\b)"
    r"(?:\s+(?:yet|longer|fully|really|currently|still|quite))?\s*$"
)

# Adversative conjunctions. When one introduces the clause holding the deferral
# token, the deferral contradicts the preceding completion ("Tests passed. But
# we deferred the deploy") rather than noting separate work, so it must NOT be
# suppressed. See bug (gemini) on ordering/contrast false negatives.
_CONTRAST_CONJUNCTION = re.compile(r"(?i)\b(but|however|except|though|although)\b")

# pytest summarizes outcomes as counts like "21 skipped" or "45 xfailed". A
# "skipped" token that is immediately preceded by a digit (ignoring whitespace)
# is such a numeric test-outcome count, not a skipped validation step, so it must
# not flag as a contradiction. Only "skipped" collides with pytest count output;
# the other CONTRADICTION_PATTERNS tokens never appear as "<N> token" counts.
# See issue #3141.
#
# The count must be a standalone number: either at the start of the string or
# immediately after a delimiter (comma, semicolon, colon). This prevents false
# suppression when a numeric identifier precedes "skipped" (e.g. "step 21 skipped",
# "PR #3141 skipped", "v2.1 skipped") where the number is part of an identifier,
# not a pytest outcome count.
_NUMERIC_COUNT_TOKENS = frozenset({"skipped"})
_DIGIT_BEFORE_TOKEN = re.compile(r"(?:^|[,;:]\s*)\d+\s*$")

# Legacy field name for backward compatibility with existing session logs.
# Issue #868: "handoffNotUpdated" with Complete=false was a confusing double negative.
# New logs use "handoffPreserved" (level=MUST, Complete=true when satisfied).
_LEGACY_HANDOFF_FIELD = "handoffNotUpdated"


def get_case_insensitive(data: dict[str, Any], key: str) -> Any | None:  # noqa: ANN401
    """Get value from dict with case-insensitive key lookup.

    Args:
        data: Dictionary to search.
        key: Key to find (case-insensitive).

    Returns:
        Value if found, None otherwise.
    """
    for k, v in data.items():
        if k.lower() == key.lower():
            return v
    return None


def has_case_insensitive(data: dict[str, Any], key: str) -> bool:
    """Check if dict has key (case-insensitive).

    Args:
        data: Dictionary to search.
        key: Key to find (case-insensitive).

    Returns:
        True if key exists, False otherwise.
    """
    for k in data:
        if k.lower() == key.lower():
            return True
    return False


def validate_session_section(session: dict[str, Any], result: ValidationResult) -> None:
    """Validate the session section of the log.

    The schema owns shape: which fields exist and what types they hold. This
    function owns meaning: protocol checks the schema cannot express.

    Args:
        session: The session section data.
        result: ValidationResult to update with errors/warnings.
    """
    # Validate branch pattern
    branch = session.get("branch")
    if branch and not BRANCH_PATTERN.match(branch):
        result.warnings.append(f"Branch '{branch}' doesn't follow conventional naming")

    # Validate commit SHA format
    commit = session.get("startingCommit")
    if commit and not COMMIT_SHA_PATTERN.match(str(commit)):
        result.errors.append(f"Invalid commit SHA format: {commit}")


def _token_in_parentheses(text: str, token_start: int) -> bool:
    """Return True if the character at token_start sits inside an open parenthesis.

    Scans the prefix before the token tracking parenthesis depth. A positive
    depth means the token is part of a parenthetical aside.

    Args:
        text: Full evidence string.
        token_start: Index where the matched token begins.

    Returns:
        True if the token is inside unmatched parentheses.
    """
    depth = 0
    for char in text[:token_start]:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
    return depth > 0


def _is_scope_qualified(evidence: str, match: re.Match[str]) -> bool:
    """Return True if a contradiction token applies to a different scope.

    Only "deferred" and "pending" can be scope-qualified (see
    _SCOPE_QUALIFIED_TOKENS). They are treated as non-contradicting when either:

    1. The token sits inside a parenthetical aside, or
    2. An affirmative completion word precedes the token across a clause boundary
       (the evidence reports the item done, then notes other deferred work).
       A clause boundary is a semicolon, or a period acting as sentence
       punctuation (followed by whitespace or end of string); a period inside a
       version or decimal such as "v1.5" is not a boundary, and a closing
       parenthesis is deliberately excluded (parentheticals are handled by rule
       1 above).

    The affirmative completion must not be negated (directly or via an adverb,
    e.g. "not yet validated"), the clause boundary must sit BETWEEN the
    affirmative word and the token, and the deferral's own clause must not open
    with an adversative conjunction ("but", "however") that ties the deferral
    back to the completion.

    Every other token, and a bare "deferred"/"pending" with no affirmative
    context, always counts as a contradiction.

    Args:
        evidence: Full evidence string.
        match: A single CONTRADICTION_PATTERNS match within the evidence.

    Returns:
        True if the matched token describes a different scope (suppress warning).
    """
    if match.group(0).lower() not in _SCOPE_QUALIFIED_TOKENS:
        return False
    if _token_in_parentheses(evidence, match.start()):
        return True
    prefix = evidence[: match.start()]
    # Iterate over ALL affirmative matches, returning True if any non-negated
    # match has a clause boundary separating it from the deferral token AND no
    # adversative conjunction follows that boundary.
    for affirmative in _AFFIRMATIVE_COMPLETION.finditer(prefix):
        # Check if the affirmative word is negated (e.g., "not passed",
        # "not yet validated"). Negated affirmatives do not indicate completion.
        prefix_before_affirmative = prefix[: affirmative.start()]
        if _NEGATION_BEFORE_AFFIRMATIVE.search(prefix_before_affirmative):
            continue
        # The boundary must sit AFTER the affirmative word and before the token,
        # so search only the segment between them. Use the LAST boundary (not
        # first) so `deferral_clause` starts at the clause containing the actual
        # deferral token, not an intermediate clause. See bug a317fc68.
        suffix_after_affirmative = prefix[affirmative.end() :]
        boundaries = list(_CLAUSE_BOUNDARY.finditer(suffix_after_affirmative))
        if not boundaries:
            continue
        boundary = boundaries[-1]
        # If the deferral's clause opens with an adversative conjunction, the
        # deferral contradicts the completion rather than noting separate work.
        # Use match() on lstripped text to check only the clause opening, not
        # mid-clause uses like "everything but X". See bug ref1_dda37e6b.
        deferral_clause = suffix_after_affirmative[boundary.end() :].lstrip()
        if _CONTRAST_CONJUNCTION.match(deferral_clause):
            continue
        return True
    return False


def _is_numeric_test_count(evidence: str, match: re.Match[str]) -> bool:
    """Return True if the token is a pytest numeric outcome count.

    pytest reports outcomes as "<N> skipped" (for example
    "14434 passed, 21 skipped, 45 xfailed"). A digit immediately before a
    "skipped" token marks a test-outcome count, which is normal successful
    evidence, not a skipped validation step. See issue #3141.

    Args:
        evidence: Full evidence string.
        match: A single CONTRADICTION_PATTERNS match within the evidence.

    Returns:
        True if the matched token is a numeric test-outcome count.
    """
    if match.group(0).lower() not in _NUMERIC_COUNT_TOKENS:
        return False
    return bool(_DIGIT_BEFORE_TOKEN.search(evidence[: match.start()]))


def _has_contradiction(evidence: str) -> bool:
    """Return True if evidence contradicts a "complete: true" claim.

    Flags any CONTRADICTION_PATTERNS token unless it is a scope-qualified
    "deferred"/"pending" that points at a different subject, or a "skipped"
    token that is a numeric pytest outcome count ("21 skipped"). A genuine
    contradiction (an item-itself deferral, "TODO", a bare token) still flags
    even when scope-qualified tokens appear elsewhere in the same string.

    Args:
        evidence: The evidence string to inspect.

    Returns:
        True if at least one unqualified contradiction token is present.
    """
    return any(
        not _is_scope_qualified(evidence, match) and not _is_numeric_test_count(evidence, match)
        for match in CONTRADICTION_PATTERNS.finditer(evidence)
    )


def validate_must_item(
    check_data: dict[str, Any],
    item_name: str,
    section_name: str,
    result: ValidationResult,
) -> None:
    """Validate a MUST requirement item.

    Args:
        check_data: The check item data.
        item_name: Name of the item being checked.
        section_name: Section name for error messages.
        result: ValidationResult to update with errors/warnings.
    """
    is_complete = get_case_insensitive(check_data, "complete")
    evidence = get_case_insensitive(check_data, "evidence")
    level = get_case_insensitive(check_data, "level")

    if level == "MUST" and not is_complete:
        result.errors.append(f"Incomplete MUST: {section_name}.{item_name}")

    if level == "MUST" and is_complete and not evidence:
        result.warnings.append(f"Missing evidence: {section_name}.{item_name}")

    if level == "MUST" and is_complete and evidence and isinstance(evidence, str):
        if _has_contradiction(evidence):
            result.warnings.append(
                f"Evidence contradiction: {section_name}.{item_name} "
                f"is complete but evidence suggests otherwise: {evidence!r}"
            )


def validate_checklist_section(
    section_data: dict[str, Any],
    required_items: frozenset[str],
    section_name: str,
    result: ValidationResult,
) -> None:
    """Validate all MUST items in a checklist section.

    Checks both the minimum required items and any additional items
    in the section that declare level == "MUST".

    Args:
        section_data: The section data (e.g. sessionStart or sessionEnd).
        required_items: Minimum items that must exist in the section.
        section_name: Section name for error messages.
        result: ValidationResult to update with errors/warnings.
    """
    # Collect all items to validate: required items + any item with level MUST
    items_to_check: set[str] = set(required_items)
    for item_name, item_data in section_data.items():
        if isinstance(item_data, dict):
            level = get_case_insensitive(item_data, "level")
            if level in ("MUST", "MUST NOT"):
                items_to_check.add(item_name)

    for item_name in items_to_check:
        if item_name in section_data:
            validate_must_item(section_data[item_name], item_name, section_name, result)
        else:
            result.errors.append(f"Missing required item: {section_name}.{item_name}")


def validate_session_start(session_start: dict[str, Any], result: ValidationResult) -> None:
    """Validate the sessionStart section.

    Args:
        session_start: The sessionStart section data.
        result: ValidationResult to update with errors/warnings.
    """
    validate_checklist_section(session_start, SESSION_START_REQUIRED_ITEMS, "sessionStart", result)


def validate_session_end(session_end: dict[str, Any], result: ValidationResult) -> None:
    """Validate the sessionEnd section.

    Args:
        session_end: The sessionEnd section data.
        result: ValidationResult to update with errors/warnings.
    """
    # Backward compatibility (issue #868): legacy logs use "handoffNotUpdated"
    # instead of "handoffPreserved". Swap the required item for legacy logs.
    required = SESSION_END_REQUIRED_ITEMS
    if _LEGACY_HANDOFF_FIELD in session_end and "handoffPreserved" not in session_end:
        required = (required - {"handoffPreserved"}) | {_LEGACY_HANDOFF_FIELD}

    validate_checklist_section(session_end, required, "sessionEnd", result)

    # Legacy MUST NOT check: Complete=true means HANDOFF.md was modified (violation).
    if _LEGACY_HANDOFF_FIELD in session_end and "handoffPreserved" not in session_end:
        check_data = session_end[_LEGACY_HANDOFF_FIELD]
        is_complete = get_case_insensitive(check_data, "complete")
        level = get_case_insensitive(check_data, "level")
        if level == "MUST NOT" and is_complete:
            result.errors.append("MUST NOT violated: HANDOFF.md was modified (read-only)")


def validate_protocol_compliance(
    protocol: dict[str, Any],
    result: ValidationResult,
) -> None:
    """Validate the protocolCompliance section.

    Args:
        protocol: The protocolCompliance section data.
        result: ValidationResult to update with errors/warnings.
    """
    # protocolCompliance.required already names both sections, so the schema
    # reports either one missing. These guards exist only to hand the checks
    # below a mapping, not to restate that fact.
    if isinstance(protocol.get("sessionStart"), dict):
        validate_session_start(protocol["sessionStart"], result)

    if isinstance(protocol.get("sessionEnd"), dict):
        validate_session_end(protocol["sessionEnd"], result)


def _load_schema() -> dict[str, Any]:
    """Read the committed schema.

    Not cached: this process validates one file and exits, so a cache would
    only hide a read error behind a stale hit.
    """
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema


def _describe(error: jsonschema.ValidationError) -> str:
    """Render a schema violation with the path a contributor can act on."""
    location = ".".join(str(part) for part in error.absolute_path) or "(root)"
    return f"Schema: {location}: {error.message}"


def validate_against_schema(data: object, result: ValidationResult) -> None:
    """Append every schema violation in ``data`` to ``result``.

    Reports all violations rather than the first, so one commit round fixes the
    log instead of one field per round. A missing or unreadable schema file, or
    a schema that is itself invalid, is an error, not a silent pass: the schema
    layer has checked nothing and must say so. This does not stop the protocol
    checks in ``validate_session_log``, which do not depend on the schema and
    still run for a dict-shaped payload.

    The validator comes from ``validator_for``, which reads the schema's own
    ``$schema`` key. The committed schema declares draft-07, and pinning a
    different draft here would silently change what several keywords mean.

    Passes ``_FORMAT_CHECKER`` so ``format`` keywords (currently just
    ``date-time``) are actually enforced instead of treated as annotations.
    """
    try:
        schema = _load_schema()
    except (OSError, json.JSONDecodeError) as exc:
        result.errors.append(f"Schema: cannot load {SCHEMA_PATH.name}, schema layer skipped: {exc}")
        return

    try:
        validator = validator_for(schema)(schema, format_checker=_FORMAT_CHECKER)
        # Sort by the stringified path, not the raw one: absolute_path mixes
        # str (object keys) and int (array indices), and comparing across
        # errors whose paths share a prefix but diverge in element type
        # raises TypeError before a single result reaches the caller.
        errors = sorted(
            validator.iter_errors(data),
            key=lambda e: tuple(str(part) for part in e.absolute_path),
        )
    except SchemaError as exc:
        result.errors.append(
            f"Schema: {SCHEMA_PATH.name} is not a valid schema, schema layer skipped: {exc}"
        )
        return

    for error in errors:
        result.errors.append(_describe(error))


def validate_session_log(data: object) -> ValidationResult:
    """Validate a session log against the committed schema and protocol rules.

    Args:
        data: Whatever ``json.loads`` produced. A session log is an object, but
            any JSON value can reach here, so the type is the parser's, not the
            schema's. The schema reports a non-object; the protocol checks below
            need a mapping and are skipped without one.

    Returns:
        ValidationResult with errors and warnings.
    """
    result = ValidationResult()

    validate_against_schema(data, result)

    # A valid session log must be a JSON object at the root. If it's not (e.g.,
    # an array or primitive), the schema validation above already reported the
    # error; we cannot run protocol checks on a non-mapping value.
    if not isinstance(data, dict):
        return result

    # The schema already reported either section as missing. Restating it here
    # would print the same fact twice under two spellings; these branches exist
    # only so the protocol checks below get a mapping to walk.
    if isinstance(data.get("session"), dict):
        validate_session_section(data["session"], result)

    if isinstance(data.get("protocolCompliance"), dict):
        validate_protocol_compliance(data["protocolCompliance"], result)

    return result


def load_session_file(session_path: Path) -> tuple[object | None, str | None]:
    """Load and parse a session log file.

    Args:
        session_path: Path to the session log file.

    Returns:
        Tuple of (parsed data, error message). Data is None if error occurred.
        The data may be any valid JSON value (object, array, string, etc.).
    """
    if not session_path.exists():
        return None, f"Session file not found: {session_path}"

    try:
        content = session_path.read_text(encoding="utf-8")
    except OSError as e:
        return None, f"Could not read session file: {e}"

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in session file: {session_path}"
        error_msg += f"\nSyntax error at line {e.lineno}, position {e.colno}"

        # Show context
        lines = content.split("\n")
        if e.lineno <= len(lines):
            error_msg += f"\nNear: {lines[e.lineno - 1]}"

        error_msg += f"\nError details: {e.msg}"
        error_msg += "\n\nCommon fixes:"
        error_msg += "\n  - Remove trailing commas from arrays/objects"
        error_msg += "\n  - Ensure all strings are properly quoted"
        error_msg += f"\n  - Validate JSON structure with: python -m json.tool '{session_path}'"

        return None, error_msg

    return data, None


def report_results(
    session_path: Path,
    result: ValidationResult,
    pre_commit: bool = False,
) -> None:
    """Report validation results to stdout.

    Args:
        session_path: Path to the session file.
        result: Validation result to report.
        pre_commit: If True, use compact output for pre-commit hook.
    """
    if not pre_commit:
        print()
        print("=== Session Validation ===")
        print(f"File: {session_path}")

    if result.is_valid:
        if not pre_commit:
            print()
            print("[PASS] Session log is valid")
    else:
        if pre_commit:
            print("Session validation FAILED:")
            for error in result.errors:
                print(f"  {error}")
        else:
            print()
            print("[FAIL] Validation errors:")
            for error in result.errors:
                print(f"  - {error}")

    if result.warnings and not pre_commit:
        print()
        print("[WARN] Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "session_path",
        type=Path,
        help="Path to the session log JSON file",
    )
    parser.add_argument(
        "--pre-commit",
        action="store_true",
        help="Suppress verbose output when called from pre-commit hook",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point. Returns exit code.

    Returns:
        0 on success, 1 on validation failure, 2 on unexpected error.
    """
    try:
        args = parse_args()

        # Validate the user-provided path against the project root
        try:
            validated_path = validate_safe_path(args.session_path, _PROJECT_ROOT)
        except (ValueError, FileNotFoundError) as e:
            print(f"ERROR: Invalid path provided: {e}", file=sys.stderr)
            return 1

        # Load session file using the validated path
        # load_session_file returns (data, error) where error is non-None only
        # for I/O or parse failures. A JSON `null` root is valid JSON that
        # parses to Python None with no error; that case must reach schema
        # validation, which will reject the non-object root with a clear message.
        data, error = load_session_file(validated_path)
        if error is not None:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1

        # Validate session log
        result = validate_session_log(data)

        # Report results
        report_results(validated_path, result, args.pre_commit)

        return 0 if result.is_valid else 1

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
