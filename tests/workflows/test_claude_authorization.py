#!/usr/bin/env python3
"""Test whether a GitHub event is authorized to invoke Claude Code.

Validates GitHub webhook events against authorization rules:
- Checks for @claude mention in event body/title
- Validates author association (MEMBER, OWNER, COLLABORATOR)
- Allows specific bot accounts (dependabot, renovate, github-actions, etc.)

Provides audit logging to GitHub Actions summary for security compliance.

Per ADR-006, this script extracts complex conditional logic from workflow YAML
to enable testing, debugging, and proper error handling.

This is a Python port of Test-ClaudeAuthorization.ps1 following ADR-042 migration.

EXIT CODES:
  0  - Success: Authorization decision made (stdout: "true" or "false")
  1  - Error: Script error (audit log failure, etc.)
  2  - Error: Double fault (authorization error AND audit logging failure)

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Constants
ALLOWED_ASSOCIATIONS: tuple[str, ...] = ("MEMBER", "OWNER", "COLLABORATOR")

ALLOWED_BOTS: tuple[str, ...] = (
    # Dependency management bots
    "dependabot[bot]",
    "renovate[bot]",
    # GitHub automation
    "github-actions[bot]",
    # AI coding assistant bots (permitted to mention @claude)
    "copilot[bot]",
    "coderabbitai[bot]",
    "cursor[bot]",
    "gemini-ai[bot]",
    "claude-ai[bot]",
    "amazonq[bot]",
    "tabnine[bot]",
)

VALID_EVENTS: tuple[str, ...] = (
    "issue_comment",
    "pull_request_review_comment",
    "pull_request_review",
    "issues",
    "pull_request",
    "workflow_dispatch",
)

# 1 MB body size limit (matches PowerShell 1MB constant)
MAX_BODY_LENGTH: int = 1_048_576

# Case-sensitive regex: @claude not followed by a word character
CLAUDE_MENTION_PATTERN: re.Pattern[str] = re.compile(r"@claude(?!\w)")

logger = logging.getLogger(__name__)


def extract_body(
    event_name: str,
    comment_body: str,
    review_body: str,
    issue_body: str,
    issue_title: str,
    pr_body: str,
    pr_title: str,
) -> str:
    """Extract the relevant body text based on event type.

    For issues and pull_request events, body and title are combined.
    For workflow_dispatch, returns empty string (authorization via association only).
    """
    if event_name in ("issue_comment", "pull_request_review_comment"):
        return comment_body
    if event_name == "pull_request_review":
        return review_body
    if event_name == "issues":
        return f"{issue_body} {issue_title}"
    if event_name == "pull_request":
        return f"{pr_body} {pr_title}"
    # workflow_dispatch: no body, authorization via association only
    return ""


def has_claude_mention(body: str) -> bool:
    """Check for case-sensitive @claude mention with negative lookahead.

    Prevents false positives like @claudette, @claude123, @claude_bot.
    Returns False for empty/whitespace-only bodies.
    """
    if not body or not body.strip():
        return False
    return bool(CLAUDE_MENTION_PATTERN.search(body))


def check_authorization(
    event_name: str,
    actor: str,
    author_association: str,
    body: str,
    mention: bool,
) -> tuple[bool, str]:
    """Determine authorization based on event type, actor, and association.

    Returns a tuple of (is_authorized, reason).
    """
    if event_name == "workflow_dispatch":
        if author_association in ALLOWED_ASSOCIATIONS:
            reason = (
                f"Authorized via workflow_dispatch by privileged user:"
                f" {actor} ({author_association})"
            )
            return True, reason
        reason = (
            f"Access denied: workflow_dispatch by Actor={actor}"
            f" with Association={author_association}"
            f" (requires MEMBER, OWNER, or COLLABORATOR)"
        )
        return False, reason

    if event_name == "pull_request":
        if actor in ALLOWED_BOTS:
            reason = f"Authorized via bot allowlist for pull_request: {actor}"
            return True, reason
        if mention and author_association in ALLOWED_ASSOCIATIONS:
            reason = (
                f"Authorized via @claude mention in PR by:"
                f" {actor} ({author_association})"
            )
            return True, reason
        reason = (
            f"Access denied: pull_request from Actor={actor}"
            f" requires @claude mention and authorized association"
        )
        return False, reason

    # All other events require @claude mention
    if not mention:
        return False, "No @claude mention found in event body/title"

    if actor in ALLOWED_BOTS:
        return True, f"Authorized via bot allowlist: {actor}"

    if author_association in ALLOWED_ASSOCIATIONS:
        return True, f"Authorized via author association: {author_association}"

    reason = (
        f"Access denied: Actor={actor} is not in bot allowlist,"
        f" Association={author_association} is not in allowed list"
    )
    return False, reason


def write_oversize_audit_log(
    summary_path: str,
    event_name: str,
    actor: str,
    body_length: int,
) -> None:
    """Write audit log entry for oversized body denial.

    Raises OSError on write failure.
    """
    timestamp = datetime.now(tz=UTC).isoformat()
    log_entry = (
        "\n## Authorization Denied: Event Body Too Large\n\n"
        f"**Maximum Allowed**: {MAX_BODY_LENGTH} bytes (1 MB)\n"
        f"**Received**: {body_length} bytes\n"
        f"**Event Type**: {event_name}\n"
        f"**Actor**: {actor}\n"
        f"**Timestamp**: {timestamp}\n\n"
        "This may indicate a malformed webhook payload or a potential attack."
        " Legitimate GitHub webhooks should not exceed 1MB.\n"
    )
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(log_entry)


def write_audit_log(
    summary_path: str,
    event_name: str,
    actor: str,
    author_association: str,
    mention: bool,
    is_authorized: bool,
    reason: str,
) -> None:
    """Write authorization audit log to GitHub Actions step summary.

    Raises OSError on write failure.
    """
    timestamp = datetime.now(tz=UTC).isoformat()
    allowed_assoc_str = ", ".join(ALLOWED_ASSOCIATIONS)
    allowed_bots_str = ", ".join(ALLOWED_BOTS)
    log_entry = (
        "\n## Claude Authorization Check\n\n"
        "| Property | Value |\n"
        "|----------|-------|\n"
        f"| **Event Type** | {event_name} |\n"
        f"| **Actor** | {actor} |\n"
        f"| **Author Association** | {author_association} |\n"
        f"| **Has @claude Mention** | {mention} |\n"
        f"| **Authorized** | {is_authorized} |\n"
        f"| **Reason** | {reason} |\n"
        f"| **Timestamp** | {timestamp} |\n\n"
        "### Authorization Rules\n\n"
        f"**Allowed Author Associations**: {allowed_assoc_str}\n"
        f"**Allowed Bots**: {allowed_bots_str}\n\n"
        "### Security Note\n\n"
        "GitHub may deprecate `author_association` from webhook payloads"
        " in the future.\n"
        "This implementation will need to be updated when that deprecation"
        " takes effect.\n"
    )
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(log_entry)


def write_error_audit_log(
    summary_path: str,
    error_message: str,
    event_name: str,
    actor: str,
    author_association: str,
) -> None:
    """Write error audit log to GitHub Actions step summary.

    Raises OSError on write failure (triggers double fault handling).
    """
    timestamp = datetime.now(tz=UTC).isoformat()
    log_entry = (
        "\n## Claude Authorization Check - ERROR\n\n"
        f"**Error**: {error_message}\n"
        f"**Event**: {event_name}\n"
        f"**Actor**: {actor}\n"
        f"**Association**: {author_association}\n"
        f"**Timestamp**: {timestamp}\n\n"
        "Authorization check failed. Review workflow logs for details.\n"
    )
    with open(summary_path, "a", encoding="utf-8") as f:
        f.write(log_entry)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Test whether a GitHub event is authorized to invoke Claude Code.",
    )
    parser.add_argument(
        "--event-name",
        required=True,
        choices=VALID_EVENTS,
        help="GitHub event name",
    )
    parser.add_argument(
        "--actor",
        required=True,
        help="GitHub actor triggering the event",
    )
    parser.add_argument(
        "--author-association",
        default=os.environ.get("AUTHOR_ASSOCIATION", ""),
        help="Author's association with the repository (default: env AUTHOR_ASSOCIATION)",
    )
    parser.add_argument(
        "--comment-body",
        default=os.environ.get("COMMENT_BODY", ""),
        help="Body text of a comment (default: env COMMENT_BODY)",
    )
    parser.add_argument(
        "--review-body",
        default=os.environ.get("REVIEW_BODY", ""),
        help="Body text of a review (default: env REVIEW_BODY)",
    )
    parser.add_argument(
        "--issue-body",
        default=os.environ.get("ISSUE_BODY", ""),
        help="Body text of an issue (default: env ISSUE_BODY)",
    )
    parser.add_argument(
        "--issue-title",
        default=os.environ.get("ISSUE_TITLE", ""),
        help="Title of an issue (default: env ISSUE_TITLE)",
    )
    parser.add_argument(
        "--pr-body",
        default=os.environ.get("PR_BODY", ""),
        help="Body text of a pull request (default: env PR_BODY)",
    )
    parser.add_argument(
        "--pr-title",
        default=os.environ.get("PR_TITLE", ""),
        help="Title of a pull request (default: env PR_TITLE)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the authorization check.

    Returns exit code: 0 for success, 1 for error, 2 for double fault.
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    parser = build_parser()
    args = parser.parse_args(argv)

    event_name: str = args.event_name
    actor: str = args.actor
    author_association: str = args.author_association
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")

    try:
        body = extract_body(
            event_name,
            args.comment_body,
            args.review_body,
            args.issue_body,
            args.issue_title,
            args.pr_body,
            args.pr_title,
        )

        # Check body size limit
        if len(body) > MAX_BODY_LENGTH:
            logger.info(
                "Authorization Denied: Event body exceeds maximum safe length"
                " (%d bytes, received %d bytes)",
                MAX_BODY_LENGTH,
                len(body),
            )
            logger.info("This may indicate a malformed webhook or potential attack")

            if summary_path:
                try:
                    write_oversize_audit_log(
                        summary_path, event_name, actor, len(body)
                    )
                except OSError as audit_err:
                    logger.error(
                        "CRITICAL: Failed to write oversize body audit log"
                        " to GitHub Actions summary: %s."
                        " Authorization cannot proceed without audit trail.",
                        audit_err,
                    )
                    return 1

            print("false")
            return 0

        mention = has_claude_mention(body)

        logger.info("Authorization Check Details:")
        logger.info("  Event: %s", event_name)
        logger.info("  Actor: %s", actor)
        logger.info("  Author Association: %s", author_association)
        logger.info("  Has @claude Mention: %s", mention)

        is_authorized, reason = check_authorization(
            event_name, actor, author_association, body, mention,
        )

        logger.info(
            "Result: %s - %s",
            "Authorized" if is_authorized else "Not authorized",
            reason,
        )

        # Write audit log
        if summary_path:
            try:
                write_audit_log(
                    summary_path,
                    event_name,
                    actor,
                    author_association,
                    mention,
                    is_authorized,
                    reason,
                )
            except OSError as audit_err:
                logger.error(
                    "CRITICAL: Failed to write audit log to GitHub Actions"
                    " summary: %s. Authorization cannot proceed without"
                    " audit trail.",
                    audit_err,
                )
                return 1

        print(str(is_authorized).lower())
        return 0

    except Exception as exc:
        error_msg = str(exc)
        logger.error(
            "Authorization check failed: Event=%s, Actor=%s, Association=%s: %s",
            event_name,
            actor,
            author_association,
            error_msg,
        )

        if summary_path:
            try:
                write_error_audit_log(
                    summary_path, error_msg, event_name, actor, author_association,
                )
            except OSError as audit_err:
                logger.error(
                    "DOUBLE FAULT: Authorization check failed AND audit"
                    " logging failed: %s",
                    audit_err,
                )
                logger.error("Original error: %s", error_msg)
                print("false")
                return 2

        return 1


if __name__ == "__main__":
    sys.exit(main())
