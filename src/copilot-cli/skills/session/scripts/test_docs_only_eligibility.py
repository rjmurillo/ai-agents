#!/usr/bin/env python3
"""Check if changed files qualify for the docs-only QA skip.

Tests whether every changed file in a commit range is a Markdown file and
whether its code-block content (fenced or indented) is byte-identical
between the base and head revisions. `.agents/SESSION-PROTOCOL.md` defines
"docs-only" as: all modified files are documentation files, and changes
are strictly editorial (spelling, grammar, or formatting) with no changes
to code, configuration, tests, workflows, or code blocks of any kind.

This script is self-contained (stdlib only, no third-party markdown
parser) because it ships inside a plugin root (`.claude/skills/`) and
`.claude/rules/plugin-self-containment.md` forbids a skill script from
depending on upstream-only `scripts/` modules. The fence/indented-code
detection below is a conservative regex scan, not a full CommonMark
parse: it can flag prose as code (for example, four-space-indented list
continuation text) but never the reverse, so a false positive only costs
an unnecessary QA report, never a missed code change. Fail closed.

Exit codes follow ADR-035:
    0 - Success (always returns 0, eligibility is in JSON output)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess

_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
_FENCE_START_PATTERN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_INDENTED_CODE_PATTERN = re.compile(r"^(?: {4,}|\t)")
_DOC_EXTENSIONS = (".md",)


def _is_doc_file(path: str) -> bool:
    """Test whether a path is a documentation file eligible for docs-only."""
    return path.lower().endswith(_DOC_EXTENSIONS)


def _code_block_lines(markdown: str) -> list[str]:
    """Return every line this scan attributes to a fenced or indented code block.

    Fenced blocks are tracked by opening marker character (backtick or
    tilde); the closing fence must repeat that same character at least
    three times, matching CommonMark's requirement, with up to three
    leading spaces. An indented line (four spaces or a tab) outside a
    fence is also treated as code, which over-flags list-continuation
    prose but never under-flags an actual indented code block.
    """
    lines = markdown.split("\n")
    result: list[str] = []
    in_fence = False
    fence_char = ""
    close_pattern = re.compile("")
    for line in lines:
        if in_fence:
            result.append(line)
            if close_pattern.match(line):
                in_fence = False
            continue
        fence_match = _FENCE_START_PATTERN.match(line)
        if fence_match:
            in_fence = True
            fence_char = fence_match.group(1)[0]
            close_pattern = re.compile(rf"^ {{0,3}}{re.escape(fence_char)}{{3,}}\s*$")
            result.append(line)
            continue
        if _INDENTED_CODE_PATTERN.match(line):
            result.append(line)
    return result


def _run_git(command: list[str]) -> tuple[str | None, str | None]:
    """Run one git query and fail closed on command errors."""
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git command failed"
        return None, detail
    return result.stdout, None


def _name_status_paths(output: str) -> list[str]:
    """Return every old and new path from git name-status output."""
    paths: list[str] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        paths.extend(path for path in parts[1:] if path)
    return paths


def _changed_files(base_ref: str, head_ref: str) -> tuple[list[str] | None, str | None]:
    """Return paths changed by the branch's own commits in a fixed range.

    Uses ``git log --first-parent --no-merges`` so upstream changes
    introduced by merging the base branch into the session branch are
    excluded, matching the investigation-eligibility checker's approach
    (issue #4915).
    """
    command = [
        "git",
        "log",
        "--first-parent",
        "--no-merges",
        "--name-status",
        "--find-renames",
        "--no-ext-diff",
        "--format=",
        f"{base_ref}..{head_ref}",
        "--",
    ]
    output, error = _run_git(command)
    if error:
        return None, error
    return sorted(set(_name_status_paths(output or ""))), None


def _content_at(ref: str, path: str) -> str | None:
    """Return a file's content at ``ref``, or None when absent there."""
    output, error = _run_git(["git", "show", f"{ref}:{path}"])
    if error:
        return None
    return output


def _file_is_editorial(base_ref: str, head_ref: str, path: str) -> bool:
    """Test whether a file's code-block content is unchanged between refs."""
    old_content = _content_at(base_ref, path)
    new_content = _content_at(head_ref, path)
    old_code = _code_block_lines(old_content) if old_content is not None else []
    new_code = _code_block_lines(new_content) if new_content is not None else []
    return old_code == new_code


def build_parser() -> argparse.ArgumentParser:
    """Build the docs-only eligibility CLI parser."""
    parser = argparse.ArgumentParser(
        description="Check whether changed files qualify for docs-only QA skip.",
    )
    parser.add_argument(
        "--base-ref",
        required=True,
        help="Start of the commit range (exclusive).",
    )
    parser.add_argument(
        "--head-ref",
        required=True,
        help="End of the commit range (inclusive).",
    )
    return parser


def _error_output(error: str) -> dict[str, object]:
    return {
        "Eligible": False,
        "ChangedFiles": [],
        "Violations": [],
        "Error": error,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not _COMMIT_PATTERN.fullmatch(args.base_ref):
        print(json.dumps(_error_output(f"Invalid base ref: {args.base_ref!r}"), indent=2))
        return 0
    if not _COMMIT_PATTERN.fullmatch(args.head_ref):
        print(json.dumps(_error_output(f"Invalid head ref: {args.head_ref!r}"), indent=2))
        return 0

    changed_files, error = _changed_files(args.base_ref, args.head_ref)
    if error:
        print(json.dumps(_error_output(error), indent=2))
        return 0

    changed_files = changed_files or []
    violations: list[str] = []
    for path in changed_files:
        if not _is_doc_file(path):
            violations.append(f"{path}: not a documentation file")
            continue
        if not _file_is_editorial(args.base_ref, args.head_ref, path):
            violations.append(f"{path}: code block content changed")

    output = {
        "Eligible": len(violations) == 0,
        "ChangedFiles": changed_files,
        "Violations": violations,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
