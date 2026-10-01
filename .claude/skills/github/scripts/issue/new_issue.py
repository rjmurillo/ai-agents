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
``--source human`` also appends ``<!-- source:human -->`` to the body, the
assertion the repository labeler honors (epic #5698, AC-3).

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
import importlib.util
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


def _load_provenance():
    """Load issue_provenance.py from beside this script, by file path.

    Loading by path keeps a same-named module elsewhere on sys.path from
    replacing the provenance rules.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "issue_provenance.py")
    spec = importlib.util.spec_from_file_location("_new_issue_provenance", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load provenance rules: {path}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses in the redactor it loads resolve modules through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


provenance = _load_provenance()


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
        choices=provenance.SOURCES,
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


def _read_body(args: argparse.Namespace, fmt: str) -> str | int:
    if not args.body_file:
        return str(args.body)
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

    # The escaped-newline check runs on the caller's body before the Step 0
    # block is appended; the block's real newlines would otherwise mask it.
    label_error, caller_labels = provenance.split_source_labels(args.labels, args.source)
    evidence_error, step0_block = provenance.step0_evidence(
        args.source, body, args.blocked_by, args.signal
    )
    error = (
        escaped_newline_body_error(body)
        or provenance.marker_error(args.source, body)
        or label_error
        or evidence_error
    )
    if error:
        return _usage_error(error, fmt)
    if step0_block:
        body = f"{body.rstrip()}\n\n{step0_block}" if body.strip() else step0_block
    return provenance.with_human_marker(args.source, body), caller_labels


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
    provenance.ensure_source_label(owner, repo, source_label, args.source)
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
