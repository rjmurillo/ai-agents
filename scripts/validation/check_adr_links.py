#!/usr/bin/env python3
r"""Detect ADR markdown links that do not resolve or that name the wrong ADR number.

Scans tracked markdown files for links whose target matches ``ADR-\d+.*\.md`` and
reports four violation classes:

``unresolved``
    The target is not a tracked file when resolved relative to the file
    containing the link. Catches stale slugs left behind by an ADR rename, for
    example ``ADR-005-powershell-only.md`` after the file became
    ``ADR-005-powershell-only-scripting.md``. Resolution is against
    ``git ls-files``, not the filesystem: an untracked file at the target path
    must not make a broken tracked link pass locally when the same commit
    fails in a clean checkout (PR #5209 review).

``absolute``
    The target starts with ``/``. A leading slash cannot resolve relative to the
    containing file, and GitHub resolves it against the site root rather than the
    blob tree, so the link renders broken. ``ADR-023`` cited its debate log as
    ``/.agents/critique/ADR-023-debate-log.md`` while the file was present all
    along at ``.agents/critique/ADR-023-debate-log.md``.

``number-mismatch``
    The link text names an ADR number and the target filename names a different
    one. This is the rule no existing gate carries. ``ADR-033`` linked
    ``[ADR-032 Exit Code Standardization](./ADR-032-exit-code-standardization.md)``
    when exit-code standardization is ADR-035 and ADR-032 is EARS requirements
    syntax, so a reader who ignored the dead path and followed the number landed
    on an unrelated decision.

``malformed``
    The link destination carries a nested ``[`` or ``]``, or the destination is
    never closed on its line (``[ADR-080](./ADR-080-model-pin-justification-policy.md``).
    A distinct authoring mistake from a target that simply does not exist.

Scope is tracked ``*.md`` files. Non-markdown files are never scanned, so the
deliberate ``ADR-999`` / ``ADR-099`` / ``ADR-100`` / ``ADR-101`` / ``ADR-102``
constants in the Python test fixtures named by issue #5197 are out of scope by
construction rather than by allowlist entry.

Links inside fenced code blocks are illustrations, not references, and are
skipped.

Exit codes follow ADR-035: 0 clean, 1 violations found, 2 configuration error.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# HISTORICAL_ROOTS and load_allowlist are reused, not copied, so a root added to
# the stale-script-ref exemption list is honoured here without a second edit.
# scripts/validation/stale_script_refs.py:14-27 defines HISTORICAL_ROOTS as a
# tuple of path prefixes; :89-99 defines load_allowlist as a comment-stripping
# line reader returning a set of normalized strings.
from stale_script_refs import HISTORICAL_ROOTS, load_allowlist  # noqa: E402

DEFAULT_BASELINE = Path("scripts/validation/check_adr_links_baseline.txt")

FENCE = re.compile(r"^\s*(?:```|~~~)")
LINK = re.compile(r"\[(?P<text>[^\[\]\n]*)\]\((?P<dest>[^()\n]*)\)")
UNTERMINATED = re.compile(r"\[(?P<text>[^\[\]\n]*)\]\((?P<dest>[^()\n]*)$")
ADR_BASENAME = re.compile(r"^ADR-\d+.*\.md$", re.IGNORECASE)
ADR_ANYWHERE = re.compile(r"ADR-\d+[^\s)]*\.md", re.IGNORECASE)
TEXT_ADR_NUMBER = re.compile(r"\bADR[-\s]?(?P<number>\d{1,4})\b", re.IGNORECASE)
FILE_ADR_NUMBER = re.compile(r"^ADR-(?P<number>\d+)", re.IGNORECASE)
EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "ftp://")


@dataclass(frozen=True)
class Finding:
    """One broken or misleading ADR link in a tracked markdown file."""

    file: str
    line: int
    kind: str
    target: str
    detail: str = ""

    def key(self) -> str:
        """Return the line-independent baseline key for this finding."""
        return f"{self.file}:{self.target}"

    def format(self) -> str:
        """Return the human and machine readable finding line."""
        suffix = f" ({self.detail})" if self.detail else ""
        return f"{self.file}:{self.line}: {self.kind}: {self.target}{suffix}"


def is_historical_path(path: str) -> bool:
    """Return whether path sits in a history-only root that is never repaired."""
    return path.startswith(HISTORICAL_ROOTS)


def git_ls_markdown(repo_root: Path) -> list[str]:
    """Return tracked markdown paths, newest-git-state, normalized to forward slashes."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
    )
    return sorted(entry.replace("\\", "/") for entry in result.stdout.split("\0") if entry)


def split_destination(raw: str) -> str:
    """Return the path part of a markdown link destination.

    Drops an optional ``"title"`` suffix, surrounding angle brackets, and any
    ``#anchor``. Returns an empty string when nothing path-like remains.
    """
    dest = raw.strip()
    if dest.startswith("<") and dest.endswith(">"):
        dest = dest[1:-1].strip()
    if not dest:
        return ""
    path = dest.split()[0]
    return path.split("#", 1)[0]


def is_adr_target(path: str) -> bool:
    """Return whether a link destination points at an ADR markdown file."""
    if not path or path.startswith(EXTERNAL_SCHEMES):
        return False
    basename = path.rsplit("/", 1)[-1]
    return bool(ADR_BASENAME.match(basename))


def adr_number(value: str) -> int | None:
    """Return the leading ADR number in an ADR filename, or None."""
    match = FILE_ADR_NUMBER.match(value)
    return int(match.group("number")) if match else None


def text_adr_number(text: str) -> int | None:
    """Return the first ADR number named in link text, or None."""
    match = TEXT_ADR_NUMBER.search(text)
    return int(match.group("number")) if match else None


def _malformed_findings(file: str, line_number: int, line: str) -> list[Finding]:
    """Return malformed-destination findings for one line."""
    findings: list[Finding] = []
    for match in LINK.finditer(line):
        dest = match.group("dest")
        if ("[" in dest or "]" in dest) and ADR_ANYWHERE.search(dest):
            findings.append(
                Finding(file, line_number, "malformed", dest.strip(), "bracket inside destination")
            )

    unterminated = UNTERMINATED.search(line)
    if unterminated and ADR_ANYWHERE.search(unterminated.group("dest")):
        findings.append(
            Finding(
                file,
                line_number,
                "malformed",
                unterminated.group("dest").strip(),
                "destination never closed",
            )
        )
    return findings


def _resolves_to_tracked_file(file: str, path: str, tracked: frozenset[str]) -> bool:
    """Return whether ``path``, taken relative to ``file``, names a tracked file.

    Resolution is purely lexical against the ``git ls-files`` inventory
    (``tracked``), never against the working-tree filesystem. An untracked
    file sitting at the target path would make ``Path.exists()`` pass locally
    for a link that is broken in a clean checkout, and the identical commit
    would then fail in CI while looking clean on the author's machine.

    ``posixpath.normpath`` collapses ``..`` segments without touching disk,
    matching the forward-slash-normalized paths ``git_ls_markdown`` returns.
    A result of ``..`` or one starting with ``../`` has walked out of the
    repository root and is rejected outright, since nothing under
    ``git ls-files`` can ever resolve there.
    """
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(file), path))
    if resolved == ".." or resolved.startswith("../"):
        return False
    return resolved in tracked


def _link_findings(
    file: str, line_number: int, line: str, tracked: frozenset[str]
) -> list[Finding]:
    """Return unresolved, absolute, and number-mismatch findings for one line."""
    findings: list[Finding] = []

    for match in LINK.finditer(line):
        dest = match.group("dest")
        if "[" in dest or "]" in dest:
            continue
        path = split_destination(dest)
        if not is_adr_target(path):
            continue

        # The number check runs whether or not the path resolves. A dead path and
        # a wrong number are separate defects, and reporting only the dead path
        # would surface the wrong number one review round later.
        named = text_adr_number(match.group("text"))
        actual = adr_number(path.rsplit("/", 1)[-1])
        if named is not None and actual is not None and named != actual:
            findings.append(
                Finding(
                    file,
                    line_number,
                    "number-mismatch",
                    path,
                    f"text says ADR-{named:03d}, target is ADR-{actual:03d}",
                )
            )

        if path.startswith("/"):
            findings.append(
                Finding(file, line_number, "absolute", path, "does not resolve from this file")
            )
        elif not _resolves_to_tracked_file(file, path, tracked):
            findings.append(Finding(file, line_number, "unresolved", path))

    return findings


def scan_file(repo_root: Path, file: str, tracked: frozenset[str]) -> list[Finding]:
    """Return every ADR-link finding in one tracked markdown file."""
    path = repo_root / file
    if not path.is_file():
        return []

    findings: list[Finding] = []
    in_fence = False
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        findings.extend(_malformed_findings(file, line_number, line))
        findings.extend(_link_findings(file, line_number, line, tracked))

    return findings


def find_broken_adr_links(
    repo_root: Path,
    *,
    files: list[str] | None = None,
    baseline: set[str] | None = None,
    tracked: frozenset[str] | None = None,
) -> list[Finding]:
    """Return every non-exempt, non-baselined ADR-link finding in the tree.

    ``tracked`` defaults to the live ``git ls-files`` inventory (git is the
    I/O boundary this function owns) and is always the full markdown corpus,
    even when ``files`` narrows which files get scanned: a target-resolution
    check must see every tracked file to answer "does this link's destination
    exist", regardless of which subset is being linted this run. Callers that
    already know the tracked set, or that run against a directory that is not
    a git repository, may pass it explicitly to skip the subprocess call.
    """
    resolved_tracked = tracked if tracked is not None else frozenset(git_ls_markdown(repo_root))
    candidates = files if files is not None else sorted(resolved_tracked)
    allowed = baseline if baseline is not None else load_allowlist(repo_root / DEFAULT_BASELINE)

    findings: list[Finding] = []
    for file in sorted(candidates):
        normalized = file.replace("\\", "/")
        if is_historical_path(normalized):
            continue
        for finding in scan_file(repo_root, normalized, resolved_tracked):
            if finding.key() in allowed or finding.file in allowed:
                continue
            findings.append(finding)
    return findings


def validate_adr_links(repo_root: Path) -> bool:
    """Print broken ADR links and return True when none are found."""
    findings = find_broken_adr_links(repo_root)
    for finding in findings:
        print(finding.format())
    print(f"check_adr_links: {len(findings)} violation(s)")
    return not findings


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Detect broken or wrong-numbered ADR links.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="Baseline file, relative to repo root unless absolute.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the ADR link check."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = Path(args.repo_root).resolve()
        baseline_path = Path(args.baseline)
        if not baseline_path.is_absolute():
            baseline_path = repo_root / baseline_path

        findings = find_broken_adr_links(repo_root, baseline=load_allowlist(baseline_path))
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        print(f"check_adr_links: {exc}", file=sys.stderr)
        return 2

    for finding in findings:
        print(finding.format())
    print(f"check_adr_links: {len(findings)} violation(s)")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
