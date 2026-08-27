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
checks only. A slashless name is verified only when it names a file
tracked at the repository root (``.markdownlint-cli2.yaml:138``), so
illustrative snippets such as ``auth.ts:47`` stay ignored. Escape
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

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
# checks_common transitively imports ``scripts.cli_exec`` (absolute), so the
# repo root must be importable even when this runs as a plain script, not only
# via ``python -m`` or from pre-commit's repo-root cwd (Issue #3073).
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _resolve_default_base_ref  # noqa: E402
from citation_anchors import (  # noqa: E402
    _CITATION,
    _URL,
    _anchor_candidates,
    _anchor_matches,
    _context_lines,
    _continuation_quote,
    _same_line_segment,
)
from citation_head_state import (  # noqa: E402
    HeadReadError,
    _added_lines_since_base,
    _head_tracked_paths,
    _HeadFileCache,
)
from stale_script_refs import HISTORICAL_ROOTS  # noqa: E402

IGNORE_MARKER = "citation-freshness: ignore"

# Directory fragments whose files synthesize citations on purpose.
_FIXTURE_FRAGMENTS = ("/fixtures/",)

# Historical trees this gate exempts beyond stale_script_refs's tuple:
# episode records are point-in-time captures, exactly like sessions and
# retrospectives, and that tuple is another gate's contract to widen.
_EXTRA_HISTORICAL_ROOTS = (".agents/memory/",)

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


def _is_exempt_citing_file(path: str) -> bool:
    """Return whether a citing file is out of this gate's scope."""
    if path.startswith(HISTORICAL_ROOTS) or path.startswith(_EXTRA_HISTORICAL_ROOTS):
        return True
    # The leading slash makes the fragment match a top-level fixtures/
    # directory too, not only nested ones (diff paths are repo-relative).
    return any(fragment in f"/{path}" for fragment in _FIXTURE_FRAGMENTS)


_IGNORE_WITH_REASON = re.compile(re.escape(IGNORE_MARKER) + r"\s+--\s+\S")


def _has_ignore_marker(citing_lines: list[str] | None, line_number: int, line_text: str) -> bool:
    """Return whether the citation line or the one above carries a reasoned marker."""
    if _IGNORE_WITH_REASON.search(line_text):
        return True
    if citing_lines is None:
        return False
    previous_index = line_number - 2
    return 0 <= previous_index < len(citing_lines) and bool(
        _IGNORE_WITH_REASON.search(citing_lines[previous_index])
    )


def _resolve_cited_range(
    citing_file: str,
    line_number: int,
    citation_text: str,
    cited_path: str,
    start: int,
    end: int,
    tracked: set[str],
    head_files: _HeadFileCache,
) -> tuple[list[str] | None, Finding | None]:
    """Resolve the cited lines at HEAD, or the Finding explaining why not."""

    def refusal(reason: str, lines: list[str] | None) -> tuple[list[str] | None, Finding]:
        return lines, Finding(citing_file, line_number, citation_text, reason)

    if cited_path not in tracked:
        return refusal("cited file not tracked at HEAD", None)
    # Range refusals still hand back the cited lines so the caller can
    # append a relocation hint: an out-of-range citation is exactly the
    # moved-content case the hint exists to repair.
    cited_lines = head_files.lines(cited_path)
    if start < 1:
        return refusal(f"cites line {start}; line numbers are 1-based", cited_lines)
    if end < start:
        return refusal(f"cited range is reversed ({start}-{end})", cited_lines)
    if end > len(cited_lines):
        return refusal(
            f"cites line {end} but the file has {len(cited_lines)} lines at HEAD", cited_lines
        )
    return cited_lines, None


def _citation_anchors(
    citation_text: str,
    line_text: str,
    segment: str,
    citing_lines: list[str] | None,
    line_number: int,
) -> list[str]:
    """Collect the anchors the citing sentence names for one citation."""
    line_index = line_number - 1
    anchors: list[str] = _anchor_candidates(
        _context_lines(citing_lines, line_index, line_text, segment), citation_text
    )
    if citing_lines is not None:
        quote = _continuation_quote(citing_lines, line_index)
        if quote is not None:
            anchors.append(quote)
    return anchors


def _relocation_hint(anchors: list[str], cited_lines: list[str]) -> str:
    """Name the line an anchor moved to, or return an empty string.

    Two passes reuse _anchor_matches: exact single lines first (the
    precise answer), then two-line windows so an anchor wrapped across a
    line break in the cited file still yields a repairable hint.
    """
    for anchor in anchors:
        for index, content in enumerate(cited_lines, 1):
            if _anchor_matches(anchor, content):
                return f"; {anchor!r} first appears at line {index}"
    for anchor in anchors:
        for index in range(len(cited_lines) - 1):
            window = f"{cited_lines[index]}\n{cited_lines[index + 1]}"
            if _anchor_matches(anchor, window):
                return f"; {anchor!r} first appears at line {index + 1}"
    return ""


def _anchor_finding(
    citing_file: str,
    line_number: int,
    citation_text: str,
    anchors: list[str],
    cited_lines: list[str],
    start: int,
    end: int,
) -> Finding | None:
    """Judge the citing text's anchors against the cited range."""
    if not anchors:
        return None
    cited_text = "\n".join(cited_lines[start - 1 : end])
    if any(_anchor_matches(anchor, cited_text) for anchor in anchors):
        return None
    hint = _relocation_hint(anchors, cited_lines)
    named = ", ".join(repr(anchor) for anchor in anchors[:4])
    return Finding(
        citing_file,
        line_number,
        citation_text,
        f"none of the cited anchors ({named}) appear at lines {start}-{end}{hint}",
    )


def _check_citation(
    citing_file: str,
    line_number: int,
    line_text: str,
    segment: str,
    match: re.Match[str],
    tracked: set[str],
    head_files: _HeadFileCache,
) -> Finding | None:
    """Check one citation match; return a Finding or None.

    The reasoned ignore marker is consulted first, so it exempts every
    refusal class, a citation to a deliberately removed file included.
    """
    cited_path = match.group("path").removeprefix("./")
    start = int(match.group("start"))
    end_group = match.group("end")
    end = int(end_group) if end_group else start
    citation_text = f"{cited_path}:{match.group('start')}" + (
        f"-{end_group}" if end_group else ""
    )

    citing_lines = head_files.lines(citing_file)
    if _has_ignore_marker(citing_lines, line_number, line_text):
        return None
    cited_lines, finding = _resolve_cited_range(
        citing_file, line_number, citation_text, cited_path, start, end, tracked, head_files
    )
    if finding is not None:
        # A range refusal on a readable file is the moved-content case;
        # the hint that names the new line is what makes the repair
        # mechanical, so it is appended here too.
        if cited_lines is not None:
            anchors = _citation_anchors(
                citation_text, line_text, segment, citing_lines, line_number
            )
            hint = _relocation_hint(anchors, cited_lines)
            if hint:
                finding = Finding(
                    citing_file, line_number, citation_text, finding.reason + hint
                )
        return finding
    if cited_lines is None:
        return None
    return _anchor_finding(
        citing_file,
        line_number,
        citation_text,
        _citation_anchors(citation_text, line_text, segment, citing_lines, line_number),
        cited_lines,
        start,
        end,
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
    try:
        return _scan_added_lines(
            added, tracked, head_files, findings, files_scanned, citations_checked, base_ref
        )
    except HeadReadError as error:
        # An operational git failure mid-run is the config-error exit,
        # never a stale-citation finding against a tracked file.
        print(
            f"[citation-freshness] git could not read {error} at HEAD",
            file=sys.stderr,
        )
        return None


def _scan_added_lines(
    added: dict[str, list[tuple[int, str]]],
    tracked: set[str],
    head_files: _HeadFileCache,
    findings: list[Finding],
    files_scanned: int,
    citations_checked: int,
    base_ref: str,
) -> list[Finding]:
    """Scan every added line for citations; may raise HeadReadError."""
    for citing_file in sorted(added):
        if _is_exempt_citing_file(citing_file):
            continue
        files_scanned += 1
        for line_number, line_text in added[citing_file]:
            # URLs are masked before scanning so an external link shaped
            # like host/org/file.py:N never reads as a repository citation.
            scannable = _URL.sub(" ", line_text)
            matches = list(_CITATION.finditer(scannable))
            for index, match in enumerate(matches):
                # A slashless name is a claim only when a tracked root
                # file backs it; otherwise it is an illustrative snippet
                # (auth.ts:47) and is skipped before it is even counted.
                cited_path = match.group("path").removeprefix("./")
                if "/" not in cited_path and cited_path not in tracked:
                    continue
                citations_checked += 1
                finding = _check_citation(
                    citing_file,
                    line_number,
                    line_text,
                    _same_line_segment(scannable, matches, index),
                    match,
                    tracked,
                    head_files,
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
            f"'{IGNORE_MARKER} -- <reason>' on the citing line or the line "
            f"directly above it."
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
        print("[citation-freshness] git failed while reading repository state", file=sys.stderr)
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
        print("[citation-freshness] git failed while reading repository state", file=sys.stderr)
        return 2
    _report_findings(findings)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
