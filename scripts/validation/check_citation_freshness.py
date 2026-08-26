#!/usr/bin/env python3
"""Verify ``path:line`` citations on added lines against HEAD content.

Automates the added-lines slice of the manual gate
``.claude/rules/canonical-source-mirror.md`` prescribes; issue #5337
carries the incident record and the cost (each miss reached a paid AI
review round instead of a local deterministic check). For every citation
shaped ``some/path.ext:N`` or ``some/path.ext:N-M`` on a line ADDED since
the base ref (``base...HEAD``), the gate checks that the cited path is
tracked at HEAD, that the cited lines exist there, and that at least one
anchor the citing text names (a backtick span, a double-quoted phrase, an
underscore identifier, or an indented continuation quote) appears within
the cited range; a miss reports where the first anchor actually lives,
which is usually the corrected citation.

Deliberate scope: added lines only, so historical trees (``stale_script_refs``'s
``HISTORICAL_ROOTS``), whose citations were true when written, are never
re-policed. HEAD is the state verified, because HEAD is what a push ships
(``.claude/rules/ci-scripts.md``, "Read the state you are asserting
about, and name the ref"). Anchorless citations get existence and range
checks only, and paths without a ``/`` never match, so illustrative
snippets such as ``auth.ts:47`` stay ignored by construction. Escape
hatch: ``citation-freshness: ignore`` (with a reason) on the citing line
or the line above; line-scoped on purpose, no whole-gate skip.

EXIT CODES (ADR-035): 0 = no findings (prints examined counts so an idle
run is distinguishable from a clean one) or no base ref resolved (prints
``[SKIP]``: with no base there is no added-lines range, which is the
vendor-install and detached-checkout case, not an author push); 1 =
findings; 2 = configuration error (git itself failed)."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
# checks_common transitively imports ``scripts.cli_exec`` (absolute), so the
# repo root must be importable even when this runs as a plain script, not only
# via ``python -m`` or from pre-commit's repo-root cwd (Issue #3073).
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _resolve_default_base_ref, _run_subprocess  # noqa: E402
from stale_script_refs import HISTORICAL_ROOTS  # noqa: E402

IGNORE_MARKER = "citation-freshness: ignore"

# Directory fragments whose files synthesize citations on purpose.
_FIXTURE_FRAGMENTS = ("/fixtures/",)

_EXTENSIONS = (
    "py|md|yml|yaml|json|ps1|psm1|sh|ts|js|toml|txt|ini|cfg|html|css|ipynb"
)

# A citation: a slash-containing repo path with a known extension, then
# :N or :N-M. The path class excludes backticks, quotes, parens, and
# colons, so surrounding markup never leaks into the path.
_CITATION = re.compile(
    rf"(?P<path>[\w.-]+(?:/[\w.-]+)+\.(?:{_EXTENSIONS})):(?P<start>\d+)(?:-(?P<end>\d+))?\b"
)

_URL = re.compile(r"https?://\S+")
_BACKTICK_SPAN = re.compile(r"`+([^`]+)`+")
# Double-quoted phrases are anchors too: prose quotes the cited contract
# ('a KEEP_PIN sweep must cover "at least 8 shared fixtures"'). Minimum 4
# chars so quoted articles and flags stay out.
_DQUOTE_SPAN = re.compile(r'"([^"\n]{4,})"')
_IDENTIFIER = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")
_PATHLIKE = re.compile(rf"^[\w.-]*(?:/[\w.-]+)*\.(?:{_EXTENSIONS})$")
# Inline (non-anchored) form of _PATHLIKE for masking paths mid-line.
_PATHLIKE_INLINE = re.compile(rf"[\w.-]+(?:/[\w.-]+)+\.(?:{_EXTENSIONS})")
_NUMERIC_SPAN = re.compile(r"^\d+(?:-\d+)?$")
_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@")


@dataclass(frozen=True)
class Finding:
    """One citation on an added line that HEAD content contradicts."""

    citing_file: str
    citing_line: int
    citation: str
    reason: str

    def format(self) -> str:
        """Return the finding in file:line: citation: reason form."""
        return f"{self.citing_file}:{self.citing_line}: {self.citation}: {self.reason}"


def _git(repo_root: Path, args: list[str]) -> tuple[int, str, str]:
    """Run git in repo_root, returning (exit_code, stdout, stderr)."""
    result = _run_subprocess(["git", "-C", str(repo_root), *args], timeout=60)
    return cast("tuple[int, str, str]", result)


def _head_tracked_paths(repo_root: Path) -> set[str] | None:
    """Return the set of paths tracked at HEAD, or None on git failure."""
    exit_code, stdout, _stderr = _git(
        repo_root, ["ls-tree", "-r", "-z", "--name-only", "HEAD"]
    )
    if exit_code != 0:
        return None
    return {path for path in stdout.split("\0") if path}


def _added_lines_since_base(
    repo_root: Path, base_ref: str
) -> dict[str, list[tuple[int, str]]] | None:
    """Map citing file -> [(new line number, line text)] for added lines.

    Parses ``git diff -U0 --diff-filter=ACMR base...HEAD``: the committed
    changes this branch would push, excluding deletions (a deleted citing
    file asserts nothing).
    """
    exit_code, stdout, _stderr = _git(
        repo_root,
        [
            "diff",
            "--no-color",
            "-U0",
            "--diff-filter=ACMR",
            f"{base_ref}...HEAD",
        ],
    )
    if exit_code != 0:
        return None

    added: dict[str, list[tuple[int, str]]] = {}
    current_file: str | None = None
    new_lineno = 0
    for raw in stdout.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            current_file = None if target == "/dev/null" else target.removeprefix("b/")
            continue
        hunk = _HUNK_HEADER.match(raw)
        if hunk:
            new_lineno = int(hunk.group("new_start"))
            continue
        if current_file is None:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            added.setdefault(current_file, []).append((new_lineno, raw[1:]))
            new_lineno += 1
    return added


def _is_exempt_citing_file(path: str) -> bool:
    """Return whether a citing file is out of this gate's scope."""
    if path.startswith(HISTORICAL_ROOTS):
        return True
    return any(fragment in path for fragment in _FIXTURE_FRAGMENTS)


class _HeadFileCache:
    """Lazy line-content reads from HEAD, one ``git show`` per file."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._cache: dict[str, list[str] | None] = {}

    def lines(self, path: str) -> list[str] | None:
        """Return the HEAD lines of path, or None if unreadable."""
        if path not in self._cache:
            exit_code, stdout, _stderr = _git(self._repo_root, ["show", f"HEAD:{path}"])
            self._cache[path] = stdout.splitlines() if exit_code == 0 else None
        return self._cache[path]


def _strip_prose_decorations(text: str) -> str:
    """Drop trailing punctuation an anchor picked up from prose."""
    return text.strip().strip(".,:;()[]{}'\"")


def _span_anchor(span: str, citation_text: str) -> str | None:
    """Return a quoted span as an anchor, or None when it is not one.

    The citation itself (or a span containing it), path-shaped spans, bare
    numeric ranges, and CLI flags are not anchors. A short span that is
    merely a substring of the cited path still is one: `model` is a real
    anchor even though the letters appear inside check_model_pins.py's own
    name.
    """
    candidate = _strip_prose_decorations(span)
    if not candidate or len(candidate) < 3 or citation_text in candidate:
        return None
    if _PATHLIKE.match(candidate) or _NUMERIC_SPAN.match(candidate):
        return None
    if candidate.startswith("-") or _CITATION.search(candidate):
        return None
    return candidate


def _anchor_candidates(context_lines: list[str], citation_text: str) -> list[str]:
    """Extract anchor strings the citing text names near a citation.

    ``context_lines`` is the citing line with its immediate neighbors.
    An anchor is text the author asserts lives at the cited location:
    a backtick span, an underscore identifier, or (handled by the
    caller) an indented continuation quote. Paths, URLs, bare numeric
    spans, CLI flags, and the citation itself are never anchors.
    """
    anchors: list[str] = []
    for line in context_lines:
        masked = _URL.sub(" ", line)
        # Triple-quote delimiters would otherwise pair with the opening
        # quote of a real anchor and swallow it.
        masked = masked.replace('"""', " ").replace("'''", " ")
        for span in _BACKTICK_SPAN.findall(masked) + _DQUOTE_SPAN.findall(masked):
            candidate = _span_anchor(span, citation_text)
            if candidate is not None:
                anchors.append(candidate)
        # Mask spans and citations before harvesting bare identifiers so a
        # path segment such as model_pin_manifest never reads as an anchor.
        masked = _BACKTICK_SPAN.sub(" ", masked)
        masked = _DQUOTE_SPAN.sub(" ", masked)
        masked = _CITATION.sub(" ", masked)
        masked = _PATHLIKE_INLINE.sub(" ", masked)
        for identifier in _IDENTIFIER.findall(masked):
            if len(identifier) >= 5:
                anchors.append(identifier)
    seen: set[str] = set()
    unique: list[str] = []
    for anchor in anchors:
        if anchor not in seen:
            seen.add(anchor)
            unique.append(anchor)
    return unique


def _anchor_matches(anchor: str, cited_text: str) -> bool:
    """Return whether an anchor is satisfied by the cited text.

    Both sides are whitespace-normalized so a quoted contract that wraps
    across lines in either file still matches. Prose also qualifies names
    the source never spells (``mod.func`` for a file that only says
    ``def func``), so a dotted anchor matches on its final segment too.
    """
    normalized_anchor = " ".join(anchor.split())
    normalized_text = " ".join(cited_text.split())
    if normalized_anchor in normalized_text:
        return True
    if "." in normalized_anchor:
        tail = normalized_anchor.rsplit(".", 1)[-1]
        return len(tail) >= 3 and tail in normalized_text
    return False


def _indent_width(line: str) -> int:
    """Return the leading-whitespace width after any comment marker."""
    prefix = 0
    while prefix < len(line) and line[prefix] in " \t":
        prefix += 1
    if line[prefix : prefix + 1] == "#":
        rest = line[prefix + 1 :]
        return prefix + 1 + (len(rest) - len(rest.lstrip(" \t")))
    return prefix


def _continuation_quote(citing_lines: list[str], line_index: int) -> str | None:
    """Return the next line's quoted contract when it is indented deeper.

    The model_pin_manifest docstring shape PR #5336 repaired: the citation
    line ends with a colon and the following line indents a verbatim quote
    of the cited contract. That quote is the strongest anchor available,
    so harvest it.
    """
    current = citing_lines[line_index]
    # Markdown requires a blank line before an indented block, so skip
    # whitespace-only lines (bounded) before reading the candidate quote.
    following: str | None = None
    for offset in range(1, 4):
        index = line_index + offset
        if index >= len(citing_lines):
            return None
        if citing_lines[index].strip():
            following = citing_lines[index]
            break
    if following is None:
        return None
    body = following.lstrip(" \t").lstrip("#").strip()
    if len(body) < 3:
        return None
    if _indent_width(following) <= _indent_width(current):
        return None
    if _NUMERIC_SPAN.match(body) or _PATHLIKE.match(body):
        return None
    return body


def _has_ignore_marker(citing_lines: list[str] | None, line_number: int, line_text: str) -> bool:
    """Return whether the citation line or the one above carries the marker."""
    if IGNORE_MARKER in line_text:
        return True
    if citing_lines is None:
        return False
    previous_index = line_number - 2
    return 0 <= previous_index < len(citing_lines) and IGNORE_MARKER in citing_lines[previous_index]


def _check_citation(
    citing_file: str,
    line_number: int,
    line_text: str,
    match: re.Match[str],
    tracked: set[str],
    head_files: _HeadFileCache,
) -> Finding | None:
    """Check one citation match; return a Finding or None."""
    cited_path = match.group("path").removeprefix("./")
    start = int(match.group("start"))
    end_group = match.group("end")
    end = int(end_group) if end_group else start
    citation_text = f"{cited_path}:{match.group('start')}" + (
        f"-{end_group}" if end_group else ""
    )

    if cited_path not in tracked:
        return Finding(citing_file, line_number, citation_text, "cited file not tracked at HEAD")

    cited_lines = head_files.lines(cited_path)
    if cited_lines is None:
        return Finding(citing_file, line_number, citation_text, "cited file unreadable at HEAD")

    if end < start:
        return Finding(
            citing_file, line_number, citation_text, f"cited range is reversed ({start}-{end})"
        )
    if end > len(cited_lines):
        return Finding(
            citing_file,
            line_number,
            citation_text,
            f"cites line {end} but the file has {len(cited_lines)} lines at HEAD",
        )

    citing_lines = head_files.lines(citing_file)
    if _has_ignore_marker(citing_lines, line_number, line_text):
        return None

    # Anchor context is the citing line plus its neighbors: the sentence
    # around a citation regularly wraps, putting the named contract on the
    # lines before or after (all three shapes occur in the PR #5327/#5336
    # corpus, including a wrapped docstring whose named contract sits two
    # lines above its trailing parenthesized citation).
    context = [line_text]
    if citing_lines is not None:
        line_index = line_number - 1
        for offset in (2, 1):
            if 0 <= line_index - offset < len(citing_lines):
                context.insert(0, citing_lines[line_index - offset])
        if line_index + 1 < len(citing_lines):
            context.append(citing_lines[line_index + 1])
        anchors = _anchor_candidates(context, citation_text)
        quote = _continuation_quote(citing_lines, line_index)
        if quote is not None:
            anchors.append(quote)
    else:
        anchors = _anchor_candidates(context, citation_text)

    if not anchors:
        return None

    cited_text = "\n".join(cited_lines[start - 1 : end])
    if any(_anchor_matches(anchor, cited_text) for anchor in anchors):
        return None

    hint = ""
    for anchor in anchors:
        for index, content in enumerate(cited_lines, 1):
            if anchor in content:
                hint = f"; {anchor!r} first appears at line {index}"
                break
        if hint:
            break
    named = ", ".join(repr(anchor) for anchor in anchors[:4])
    return Finding(
        citing_file,
        line_number,
        citation_text,
        f"none of the cited anchors ({named}) appear at lines {start}-{end}{hint}",
    )


def find_stale_citations(repo_root: Path, base_ref: str) -> list[Finding] | None:
    """Return findings for the added-lines range, or None on git failure."""
    tracked = _head_tracked_paths(repo_root)
    if tracked is None:
        return None
    added = _added_lines_since_base(repo_root, base_ref)
    if added is None:
        return None

    head_files = _HeadFileCache(repo_root)
    findings: list[Finding] = []
    files_scanned = 0
    citations_checked = 0
    for citing_file in sorted(added):
        if _is_exempt_citing_file(citing_file):
            continue
        files_scanned += 1
        for line_number, line_text in added[citing_file]:
            for match in _CITATION.finditer(line_text):
                citations_checked += 1
                finding = _check_citation(
                    citing_file, line_number, line_text, match, tracked, head_files
                )
                if finding is not None:
                    findings.append(finding)
    print(
        f"[citation-freshness] examined {citations_checked} citation(s) "
        f"across {files_scanned} changed file(s) vs {base_ref}"
    )
    return findings


def _report_findings(findings: list[Finding]) -> None:
    """Print each finding plus the one-line remediation footer."""
    for finding in findings:
        print(finding.format())
    if findings:
        print(
            f"[citation-freshness] {len(findings)} stale citation(s). Fix the "
            f"line numbers against HEAD, or mark a deliberate exception with "
            f"'{IGNORE_MARKER} -- <reason>' on or above the line."
        )


def validate_citation_freshness(repo_root: Path) -> bool:
    """Gate entry point: print findings, return True when clean.

    Resolving no base ref prints ``[SKIP]`` and passes: with no base there
    is no added-lines range to make claims about, and failing every
    detached or vendor checkout would gate content this check cannot see.
    """
    base_ref = _resolve_default_base_ref(repo_root)
    if base_ref is None:
        print("[SKIP] citation-freshness: no base ref resolved; nothing to diff against")
        return True
    findings = find_stale_citations(repo_root, base_ref)
    if findings is None:
        print("[citation-freshness] git failed while collecting the diff", file=sys.stderr)
        return False
    _report_findings(findings)
    return not findings


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Verify path:line citations on added lines against HEAD."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--base",
        default=None,
        help="Base ref to diff against (default: resolved like pre_pr's other gates).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the citation freshness check as a CLI."""
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"[citation-freshness] not a git repository: {repo_root}", file=sys.stderr)
        return 2

    base_ref = args.base or _resolve_default_base_ref(repo_root)
    if base_ref is None:
        print("[SKIP] citation-freshness: no base ref resolved; nothing to diff against")
        return 0

    findings = find_stale_citations(repo_root, base_ref)
    if findings is None:
        print("[citation-freshness] git failed while collecting the diff", file=sys.stderr)
        return 2
    _report_findings(findings)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
