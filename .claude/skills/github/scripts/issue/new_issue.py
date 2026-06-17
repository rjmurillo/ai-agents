#!/usr/bin/env python3
"""Create a new GitHub Issue.

Supports both inline body text and file-based body content.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic failure after argument parsing
    2 - Usage/configuration error (invalid CLI args, file not found)
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

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
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

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)


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
    add_output_format_arg(parser)
    return parser


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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    try:
        assert_gh_authenticated()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 4
        write_skill_error(
            "GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login' first.",
            code,
            error_type="AuthError",
            output_format=fmt,
            script_name="new_issue.py",
        )
        return code

    _stderr_buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(_stderr_buf):
            resolved = resolve_repo_params(args.owner, args.repo)
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

    owner, repo = resolved.owner, resolved.repo

    if not args.title or not args.title.strip():
        write_skill_error(
            "Title cannot be empty.",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="new_issue.py",
        )
        return 2

    body = args.body
    if args.body_file:
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
        body = body_path.read_text(encoding="utf-8")

    gh_args = ["gh", "issue", "create", "--repo", f"{owner}/{repo}", "--title", args.title]

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

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        write_skill_error(
            f"Failed to create issue: {error_str}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="new_issue.py",
        )
        return 3

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

    issue_number = int(match.group(1))

    label_error = _apply_labels(owner, repo, issue_number, output_text, args.labels, fmt)
    if label_error is not None:
        return label_error

    write_skill_output(
        {
            "issue_number": issue_number,
            "url": output_text,
            "title": args.title,
        },
        output_format=fmt,
        human_summary=f"Created issue #{issue_number}: {args.title}",
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
