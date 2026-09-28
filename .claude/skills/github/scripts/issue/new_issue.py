#!/usr/bin/env python3
"""Create a new GitHub Issue.

Supports both inline body text and file-based body content.

On success the JSON envelope carries ``Data.number`` (the created issue number
as an int) and ``Data.url`` so ``--output-format json`` callers can capture the
new number programmatically (issue #2767). ``Data.issue_number`` is retained as
an alias for existing callers.

Provenance (issue #5700): ``--source`` is required and records who selected the
work. ``human`` means an explicit human request selected this issue. An owner
login, a human-started session, or a user approving publication is not that.
``agent`` covers everything else and needs Step 0 evidence: ``--blocked-by``
(Q3, who is blocked on what) and ``--signal`` (Q5, the signal that proves it),
or a body that already carries a ``## Step 0`` block with ``### Q3`` and
``### Q5``. Every input check runs before any network call. The
``source:<value>`` label is created in the target repository when missing and
passed to ``gh issue create`` itself, so an issue never exists without it.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic failure after argument parsing
    2 - Usage/configuration error (invalid CLI args, file not found, missing or
        invalid --source, missing or hedged Step 0 evidence, conflicting
        source label)
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import subprocess
import sys
from pathlib import Path

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)
from github_core.validation import escaped_newline_body_error

# The redactor ships beside this script as a byte-identical copy of the spec
# skill's redact_secrets.py, so an installed plugin needs no toolkit checkout.
_issue_dir = os.path.dirname(os.path.abspath(__file__))
if _issue_dir not in sys.path:
    sys.path.insert(0, _issue_dir)

from redact_secrets import redact

_SOURCES = ("human", "agent")
_SOURCE_LABELS = frozenset(f"source:{source}" for source in _SOURCES)
_SOURCE_LABEL_COLOR = "ededed"
_SOURCE_LABEL_DESCRIPTIONS = {
    "human": "Work selected by an explicit human request",
    "agent": "Work selected by an agent",
}

# Phrase column of the canonical hedge phrase list, copied verbatim and in order
# from skills/spec-generator/references/spec-step0-gates.md (the table that ends
# at the <!-- step0:hedge-table-end --> marker). Match rule, quoted from that
# file: "Case-insensitive word-boundary match: `\bphrase\b`".
_HEDGE_PHRASES = (
    "would be nice",
    "would be useful",
    "would be helpful",
    "we believe",
    "we expect",
    "we anticipate",
    "we predict",
    "we hope",
    "we assume",
    "stakeholders want",
    "users want",
    "customers want",
    "should we",
    "might be useful",
    "might be needed",
    "could be useful",
    "probably",
    "eventually",
    "someday",
    "down the road",
    "nice to have",
)

# The same file exempts the technical term `eventually-consistent`. Its gate
# parser keys the exemption by phrase and lists eight entries, "consistent"
# plus seven single-punctuation variants:
#     "eventually": {"consistent", "consistent.", "consistent,", ...}
# Different than canonical: this script strips trailing punctuation before the
# lookup instead of enumerating it, so "consistent.)" is exempt here too.
_HEDGE_TECHNICAL_SUFFIXES = {"eventually": frozenset({"consistent"})}
_TRAILING_PUNCTUATION = ".,;:)!?"

_STEP0_HEADING = re.compile(r"^##[ \t]+Step 0\b[^\n]*$", re.MULTILINE)
_LEVEL2_HEADING = re.compile(r"^##[ \t]", re.MULTILINE)
_HEADING_LINE = re.compile(r"^[ \t]*#{1,6}[ \t]", re.MULTILINE)
_STEP0_KEYS = ("Q3", "Q5")

# Markers that confirm a real authentication failure in gh stderr. A transient
# REST 5xx (the 503 "Unicorn" page in issue #3139) contains none of these, so
# it classifies as an external ApiError (exit 3), not an AuthError (exit 4).
# Copied verbatim from close_issue.py::_AUTH_ERROR_MARKERS
# (.claude/skills/github/scripts/issue/close_issue.py) to keep gh failure
# classification consistent across the issue scripts.
_AUTH_ERROR_MARKERS = (
    "credential",
    "not logged in",
    "bad credentials",
    "could not authenticate",
    "authentication",
    "requires authentication",
)


def _is_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)


def _classify_gh_failure(message: str) -> tuple[int, str]:
    """Classify a failed gh operation by its stderr.

    A confirmed auth failure maps to exit 4 / AuthError; every other failure,
    including a transient HTTP 5xx or timeout, maps to exit 3 / ApiError so a
    GitHub outage is not misreported as invalid credentials (issue #3139).
    """
    if _is_auth_error(message):
        return 4, "AuthError"
    return 3, "ApiError"


def _write_github_output(outputs: dict[str, str]) -> None:
    """Write key=value pairs to GITHUB_OUTPUT if available."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    try:
        with open(output_file, "a", encoding="utf-8") as fh:
            for key, value in outputs.items():
                fh.write(f"{key}={value}\n")
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a new GitHub Issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--title", required=True, help="Issue title")

    body_group = parser.add_mutually_exclusive_group()
    body_group.add_argument("--body", default="", help="Issue body text")
    body_group.add_argument("--body-file", default="", help="Path to file containing issue body")

    parser.add_argument(
        "--labels",
        default="",
        help='Comma-separated list of labels (e.g., "bug,P1,needs-triage")',
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=_SOURCES,
        help=(
            "Who selected this work. 'human' only for an explicit human request "
            "for this issue; 'agent' for anything an agent chose, even when a "
            "human approved publishing it. Applies the source:<value> label."
        ),
    )
    parser.add_argument(
        "--blocked-by",
        default="",
        help=(
            "Step 0 Q3: who is blocked, and on what. Required with --source agent "
            "unless the body already carries a Step 0 block."
        ),
    )
    parser.add_argument(
        "--signal",
        default="",
        help=(
            "Step 0 Q5: the metric, log, run, or ticket that proves the gap. "
            "Required with --source agent unless the body already carries a "
            "Step 0 block."
        ),
    )
    add_output_format_arg(parser)
    return parser


def _usage_error(message: str, fmt: str) -> int:
    write_skill_error(
        message,
        2,
        error_type="InvalidParams",
        output_format=fmt,
        script_name="new_issue.py",
    )
    return 2


def _is_technical_term(phrase: str, text_after: str) -> bool:
    words = text_after.lstrip(" \t-").split(maxsplit=1)
    first_word = words[0].rstrip(_TRAILING_PUNCTUATION) if words else ""
    return first_word in _HEDGE_TECHNICAL_SUFFIXES.get(phrase, frozenset())


def _hedge_match(text: str) -> str | None:
    """Return the first canonical hedge phrase in ``text``, or None."""
    lowered = text.lower()
    for phrase in _HEDGE_PHRASES:
        matches = re.finditer(r"\b" + re.escape(phrase) + r"\b", lowered)
        if any(not _is_technical_term(phrase, lowered[m.end() :]) for m in matches):
            return phrase
    return None


def _answer_error(field: str, answer: str, required_when: str) -> str | None:
    """Validate one Step 0 answer: present, heading-free, hedge-free."""
    if not answer.strip():
        return f"{field} is required when {required_when}"
    if _HEADING_LINE.search(answer):
        return f"{field} must not contain a Markdown heading line"
    phrase = _hedge_match(answer)
    if phrase:
        return f"{field} contains hedge phrase '{phrase}'"
    return None


def _step0_section(body: str) -> str | None:
    """Return the text under the body's ``## Step 0`` heading, or None."""
    heading = _STEP0_HEADING.search(body)
    if heading is None:
        return None
    rest = body[heading.end() :]
    next_section = _LEVEL2_HEADING.search(rest)
    return rest[: next_section.start()] if next_section else rest


def _step0_answer(section: str, key: str) -> str:
    """Return the text under ``### <key>`` inside a Step 0 section."""
    match = re.search(
        rf"^###[ \t]+{key}\b[^\n]*\n(.*?)(?=^[ \t]*#{{1,6}}[ \t]|\Z)",
        section,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _body_evidence_error(source: str, section: str, blocked_by: str, signal: str) -> str | None:
    if blocked_by or signal:
        return "Body already carries a Step 0 block; drop --blocked-by and --signal."
    required_when = "--source=agent" if source == "agent" else "the body carries a Step 0 block"
    for key in _STEP0_KEYS:
        error = _answer_error(f"Step 0 ### {key}", _step0_answer(section, key), required_when)
        if error:
            return error
    return None


def _render_step0(blocked_by: str, signal: str) -> str:
    q3 = redact(blocked_by.strip()).text
    q5 = redact(signal.strip()).text
    return f"## Step 0\n\n### Q3\n\n{q3}\n\n### Q5\n\n{q5}\n"


def _flag_evidence(source: str, blocked_by: str, signal: str) -> tuple[str | None, str]:
    if source != "agent" and not (blocked_by or signal):
        return None, ""
    answers = (("--blocked-by", blocked_by, "--signal"), ("--signal", signal, "--blocked-by"))
    for flag, answer, other_flag in answers:
        required_when = "--source=agent" if source == "agent" else f"{other_flag} is given"
        error = _answer_error(flag, answer, required_when)
        if error:
            return error, ""
    return None, _render_step0(blocked_by, signal)


def _step0_evidence(source: str, body: str, blocked_by: str, signal: str) -> tuple[str | None, str]:
    """Validate Step 0 evidence from the body or the flags, never both.

    Returns ``(error, block)``: an error message, or the rendered Step 0 block
    to append (empty when the body already carries one or none is needed).
    """
    section = _step0_section(body)
    if section is not None:
        return _body_evidence_error(source, section, blocked_by, signal), ""
    return _flag_evidence(source, blocked_by, signal)


def _split_source_labels(labels: str, source: str) -> tuple[str | None, str]:
    """Return ``(error, caller labels minus the source label)``.

    GitHub label names are case-insensitive, so ``SOURCE:AGENT`` counts.
    """
    expected = f"source:{source}"
    kept: list[str] = []
    for label in (part.strip() for part in labels.split(",")):
        lowered = label.lower()
        if lowered in _SOURCE_LABELS and lowered != expected:
            return f"--labels carries {lowered}, which conflicts with --source {source}", ""
        if label and lowered not in _SOURCE_LABELS:
            kept.append(label)
    return None, ",".join(kept)


def _read_body(args: argparse.Namespace, fmt: str) -> str | int:
    if not args.body_file:
        return args.body
    body_path = Path(args.body_file)
    if not body_path.exists():
        write_skill_error(
            f"Body file not found: {args.body_file}",
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name="new_issue.py",
        )
        return 2
    return body_path.read_text(encoding="utf-8")


def _validate_request(args: argparse.Namespace, fmt: str) -> tuple[str, str] | int:
    """Run every input check before any network call (issue #5700).

    Returns:
        ``(body, caller_labels)`` with any Step 0 block appended, or an int
        exit code after writing the error envelope.
    """
    if not args.title or not args.title.strip():
        return _usage_error("Title cannot be empty.", fmt)

    body = _read_body(args, fmt)
    if isinstance(body, int):
        return body

    label_error, caller_labels = _split_source_labels(args.labels, args.source)
    evidence_error, step0_block = _step0_evidence(
        args.source, body, args.blocked_by, args.signal
    )
    if step0_block:
        body = f"{body.rstrip()}\n\n{step0_block}" if body.strip() else step0_block
    error = label_error or evidence_error or escaped_newline_body_error(body)
    if error:
        return _usage_error(error, fmt)
    return body, caller_labels


def _ensure_source_label(owner: str, repo: str, label: str, source: str) -> None:
    """Create the source label in the target repository when it is missing.

    Best effort by design. ``gh issue create --label`` resolves every label
    name before it sends the create mutation and fails with "could not add
    label" when one is missing, so the create call is the fail-closed point:
    a failure here (no triage permission, timeout) cannot leave an unlabeled
    issue, it only lets the create call report the missing label.
    """
    gh_args = [
        "gh",
        "label",
        "create",
        label,
        "--repo",
        f"{owner}/{repo}",
        "--color",
        _SOURCE_LABEL_COLOR,
        "--description",
        _SOURCE_LABEL_DESCRIPTIONS[source],
    ]
    try:
        result = subprocess.run(
            gh_args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"Could not ensure label {label}: {exc}", file=sys.stderr)
        return

    detail = (result.stderr or result.stdout or "").strip()
    if result.returncode != 0 and "already exists" not in detail.lower():
        print(f"Could not ensure label {label}: {detail}", file=sys.stderr)


def _apply_labels(
    owner: str,
    repo: str,
    issue_number: int,
    url: str,
    labels: str,
    fmt: str,
) -> int | None:
    """Apply labels to an already-created issue.

    Label application runs as a separate ``gh issue edit`` call so a missing
    label does not lose the created issue. On failure, emit the standard error
    envelope carrying the issue number and URL so automation can repair labels
    rather than re-create the issue.

    Returns:
        ``None`` on success (or when no labels were requested), otherwise the
        exit code to return from ``main``.
    """
    if not labels or not labels.strip():
        return None

    label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()]
    if not label_list:
        return None

    gh_args = ["gh", "issue", "edit", str(issue_number), "--repo", f"{owner}/{repo}"]
    for lbl in label_list:
        gh_args.extend(["--add-label", lbl])

    try:
        result = subprocess.run(
            gh_args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        write_skill_error(
            "gh issue edit timed out after 30s",
            3,
            error_type="Timeout",
            output_format=fmt,
            script_name="new_issue.py",
            extra={"issue_number": issue_number, "url": url},
        )
        return 3

    if result.returncode == 0:
        return None

    error_str = result.stderr.strip() or result.stdout.strip()
    write_skill_error(
        f"Issue #{issue_number} created but label application failed: {error_str}",
        3,
        error_type="ApiError",
        output_format=fmt,
        script_name="new_issue.py",
        extra={"issue_number": issue_number, "url": url},
    )
    return 3


def _resolve_auth_and_repo(
    owner: str,
    repo: str,
    fmt: str,
) -> tuple[str, str] | int:
    """Resolve owner/repo, emitting a JSON envelope on failure.

    No ``gh auth status`` preflight runs here. That preflight blocked working
    GraphQL creates during a transient REST 503 because gh relabels the 503 as
    an invalid token (issue #3139). Authentication is instead classified from
    the actual ``gh issue create`` failure in ``main``.

    Returns:
        ``(owner, repo)`` on success, or an int exit code after writing the
        error envelope so ``main`` can propagate it immediately.
    """
    _stderr_buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(_stderr_buf):
            resolved = resolve_repo_params(owner, repo)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        message = _stderr_buf.getvalue().strip() or "Could not resolve repository parameters."
        write_skill_error(
            message,
            code,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="new_issue.py",
        )
        return code

    return resolved.owner, resolved.repo


def _create_issue(
    owner: str,
    repo: str,
    title: str,
    body: str,
    source_label: str,
    fmt: str,
) -> tuple[int, str] | int:
    """Run ``gh issue create`` and return the created issue.

    Classifies the actual operation failure (issue #3139): a missing gh binary
    or a confirmed auth failure maps to exit 4; a 5xx, timeout, or unparseable
    result maps to exit 3.

    The source label travels in this call, not in the later ``gh issue edit``,
    so a label failure creates no issue instead of an unlabeled one.

    Returns:
        ``(issue_number, url_text)`` on success, or an int exit code after
        writing the error envelope so ``main`` can propagate it immediately.
    """
    gh_args = [
        "gh",
        "issue",
        "create",
        "--repo",
        f"{owner}/{repo}",
        "--title",
        title,
        "--label",
        source_label,
    ]
    if body and body.strip():
        gh_args.extend(["--body", body])

    try:
        result = subprocess.run(
            gh_args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        write_skill_error(
            "gh issue create timed out after 30s",
            3,
            error_type="Timeout",
            output_format=fmt,
            script_name="new_issue.py",
        )
        return 3
    except FileNotFoundError:
        write_skill_error(
            "GitHub CLI (gh) is not installed or not on PATH. Run 'gh auth login' first.",
            4,
            error_type="AuthError",
            output_format=fmt,
            script_name="new_issue.py",
        )
        return 4

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        code, error_type = _classify_gh_failure(error_str)
        write_skill_error(
            f"Failed to create issue: {error_str}",
            code,
            error_type=error_type,
            output_format=fmt,
            script_name="new_issue.py",
        )
        return code

    output_text = result.stdout.strip()
    match = re.search(r"issues/(\d+)", output_text)
    if not match:
        write_skill_error(
            f"Could not parse issue number from result: {output_text}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="new_issue.py",
        )
        return 3

    return int(match.group(1)), output_text


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    request = _validate_request(args, fmt)
    if isinstance(request, int):
        return request
    body, caller_labels = request

    auth_result = _resolve_auth_and_repo(args.owner, args.repo, fmt)
    if isinstance(auth_result, int):
        return auth_result
    owner, repo = auth_result

    source_label = f"source:{args.source}"
    _ensure_source_label(owner, repo, source_label, args.source)
    create_result = _create_issue(owner, repo, args.title, body, source_label, fmt)
    if isinstance(create_result, int):
        return create_result
    issue_number, output_text = create_result

    label_error = _apply_labels(owner, repo, issue_number, output_text, caller_labels, fmt)
    if label_error is not None:
        return label_error

    write_skill_output(
        {
            "number": issue_number,
            "issue_number": issue_number,
            "url": output_text,
            "title": args.title,
            "source": args.source,
        },
        output_format=fmt,
        human_summary=f"Created issue #{issue_number} ({source_label}): {args.title}",
        script_name="new_issue.py",
    )

    _write_github_output(
        {
            "success": "true",
            "issue_number": str(issue_number),
            "issue_url": output_text,
        }
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
