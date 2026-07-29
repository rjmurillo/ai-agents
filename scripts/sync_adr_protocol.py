#!/usr/bin/env python3
"""Audit ADR-to-Protocol sync coverage.

Parses ADR files for RFC 2119 requirements (MUST, SHOULD, MAY) and checks
whether SESSION-PROTOCOL.md references each ADR that contains enforceable
requirements.

EXIT CODES:
  0  - Success: All ADRs with MUST requirements are referenced in protocol
  1  - Error: Gaps detected (ADRs with MUST requirements not referenced)
  2  - Error: Configuration or file access error

See: ADR-035 Exit Code Standardization, ADR-050 ADR-to-Protocol Sync
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Exit codes per ADR-035
EXIT_SUCCESS = 0
EXIT_GAPS_DETECTED = 1
EXIT_CONFIG_ERROR = 2

# RFC 2119 keyword pattern
RFC2119_PATTERN = re.compile(
    r"\b(MUST NOT|MUST|SHALL NOT|SHALL|SHOULD NOT|SHOULD|REQUIRED|"
    r"RECOMMENDED|NOT RECOMMENDED|MAY|OPTIONAL)\b"
)

# ADR number extraction from filename
ADR_NUMBER_PATTERN = re.compile(r"ADR-(\d+)")
INLINE_STATUS_PATTERN = re.compile(r"^\*\*Status\*\*\s*:\s*(.+?)\s*$", re.MULTILINE)

# Matches `_split_frontmatter` in
# .claude/skills/adr-review/scripts/detect_adr_changes.py, which compares
# `lines[0].strip()` against this same literal.
FRONTMATTER_DELIM = "---"

# A status ending on one of these is a wrapped line, not a finished value.
# Used by the corpus regression test to detect truncation.
DANGLING_WORDS = frozenset({"by", "and", "on", "the", "a", "to", "of", "in", "for", "with"})


@dataclass
class AdrRequirements:
    """Requirements extracted from a single ADR."""

    number: int
    title: str
    filepath: Path
    status: str
    must_count: int = 0
    should_count: int = 0
    may_count: int = 0
    referenced_in_protocol: bool = False

    @property
    def has_enforceable_requirements(self) -> bool:
        """Return True if ADR has MUST or MUST NOT requirements."""
        return self.must_count > 0

    @property
    def total_requirements(self) -> int:
        return self.must_count + self.should_count + self.may_count


@dataclass
class SyncReport:
    """Report of ADR-to-Protocol sync audit."""

    adrs: list[AdrRequirements] = field(default_factory=list)

    @property
    def gaps(self) -> list[AdrRequirements]:
        """ADRs with MUST requirements not referenced in protocol."""
        return [
            a
            for a in self.adrs
            if a.has_enforceable_requirements and not a.referenced_in_protocol
        ]

    @property
    def synced(self) -> list[AdrRequirements]:
        """ADRs with MUST requirements that are referenced in protocol."""
        return [
            a
            for a in self.adrs
            if a.has_enforceable_requirements and a.referenced_in_protocol
        ]

    @property
    def informational(self) -> list[AdrRequirements]:
        """ADRs without MUST requirements (informational only)."""
        return [a for a in self.adrs if not a.has_enforceable_requirements]


def parse_adr_title(content: str) -> str:
    """Extract title from ADR markdown content."""
    for line in content.splitlines():
        if line.startswith("# "):
            # Remove "# ADR-NNN: " prefix
            title = line[2:].strip()
            match = re.match(r"ADR-\d+:\s*(.*)", title)
            return match.group(1) if match else title
    return "Unknown"


def _status_from_heading(content: str) -> str | None:
    """Read the prose under a ``## Status`` section, joining wrapped lines.

    ADR-004 wraps its status as "Superseded by" / "[ADR-086](...) on
    2026-07-20.", so reading one line reports the truncated "Superseded by".
    The block ends at a blank line or the next heading.

    Rejected alternative: join only while the text ends on a word from
    :data:`DANGLING_WORDS`. That reads ADR-004 more precisely, but measured
    against the corpus it truncated ADR-072 mid-sentence at "this" and left
    ADR-039 unreadable, because ADR-039 opens with ``**PROVISIONAL**`` and a
    bullet-style stop cannot tell bold emphasis from a list marker. Stopping
    only at a heading loses nothing: no ADR's status block contains a
    subheading, list, fence, quote, or table row.
    """
    in_status = False
    collected: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "## Status":
            in_status = True
            continue
        if not in_status:
            continue
        if not stripped:
            if collected:
                break
            continue
        if stripped.startswith("#"):
            break
        collected.append(stripped)
    return " ".join(collected) or None


def _status_from_inline(content: str) -> str | None:
    """Read a bold ``**Status**:`` line from the preamble.

    Bounded to the text before the first ``##`` heading so a body mention
    cannot be mistaken for lifecycle state.
    """
    preamble = re.split(r"^## ", content, maxsplit=1, flags=re.MULTILINE)[0]
    match = INLINE_STATUS_PATTERN.search(preamble)
    return match.group(1).strip() if match else None


def _status_from_frontmatter(content: str) -> str | None:
    """Read ``status:`` from the YAML frontmatter block (ADR-073).

    Delimiter handling matches the sibling ADR frontmatter reader,
    ``.claude/skills/adr-review/scripts/detect_adr_changes.py``, whose
    ``_split_frontmatter`` compares stripped lines:

        lines = content.splitlines(keepends=True)
        if not lines or lines[0].strip() != FRONTMATTER_DELIM:
            return "", content

    Comparing stripped lines tolerates CRLF and a trailing space on the
    fence. A ``content.startswith("---\\n")`` test does not, and would drop
    frontmatter this repo's other reader accepts.

    Stricter than canonical: that reader hands the block to ``yaml`` and
    needs every key. This one needs a single scalar, so it stays on the
    standard library. ``CONTRIBUTING.md`` and ``.agents/SESSION-PROTOCOL.md``
    both document invoking this script as bare ``python3``, which resolves
    outside the project venv and has no PyYAML guarantee. A third-party
    import here would turn a missing optional dependency into a tool that
    never starts.
    """
    block = _frontmatter_lines(content)
    if block is None:
        return None
    for line in block:
        if not line.startswith("status:"):
            continue
        return _scalar_value(line[len("status:") :])
    return None


def _frontmatter_lines(content: str) -> list[str] | None:
    """Return the lines inside a complete frontmatter block, else None."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == FRONTMATTER_DELIM:
            return lines[1:idx]
    return None


def _scalar_value(raw: str) -> str | None:
    """Resolve a YAML scalar to its text, or None when it is not a scalar."""
    value = raw.strip()
    if not value:
        return None
    if value[0] in "\"'":
        end = value.find(value[0], 1)
        return value[1:end].strip() or None if end > 0 else None
    if value[0] in "[{|>&*!":
        return None
    value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    return value or None


def parse_adr_status(content: str) -> str:
    """Extract status from ADR markdown content.

    The corpus spells status three ways: a ``## Status`` section, a bold
    ``**Status**:`` preamble line, and YAML frontmatter (ADR-073).

    Frontmatter wins because it is the controlled enum. The prose sections
    are unbounded: ADR-071 runs a full debate summary under ``## Status``,
    which is not a lifecycle value. Prose remains the fallback for the 60
    ADRs that carry no frontmatter yet, pending the ADR-073 Phase 2
    backfill.
    """
    for extract in (
        _status_from_frontmatter,
        _status_from_heading,
        _status_from_inline,
    ):
        status = extract(content)
        if status:
            return status
    return "Unknown"


def count_requirements(content: str) -> tuple[int, int, int]:
    """Count RFC 2119 keywords in ADR content.

    Returns (must_count, should_count, may_count).
    MUST includes MUST, MUST NOT, SHALL, SHALL NOT, REQUIRED.
    SHOULD includes SHOULD, SHOULD NOT, RECOMMENDED, NOT RECOMMENDED.
    MAY includes MAY, OPTIONAL.
    """
    must = 0
    should = 0
    may = 0
    for match in RFC2119_PATTERN.finditer(content):
        keyword = match.group(1)
        if keyword in ("MUST", "MUST NOT", "SHALL", "SHALL NOT", "REQUIRED"):
            must += 1
        elif keyword in ("SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED"):
            should += 1
        else:
            may += 1
    return must, should, may


def check_protocol_reference(protocol_content: str, adr_number: int) -> bool:
    """Check if SESSION-PROTOCOL.md references a specific ADR."""
    pattern = re.compile(rf"\bADR-0*{adr_number}\b")
    return bool(pattern.search(protocol_content))


def scan_adrs(adr_dir: Path) -> list[AdrRequirements]:
    """Scan ADR directory and extract requirements from each ADR."""
    results = []
    resolved_adr_dir = adr_dir.resolve()
    for filepath in sorted(adr_dir.glob("ADR-*.md")):
        if not filepath.resolve().is_relative_to(resolved_adr_dir):
            print(
                f"Warning: Skipping {filepath.name} (resolves outside ADR directory).",
                file=sys.stderr,
            )
            continue
        if filepath.name == "ADR-TEMPLATE.md":
            continue
        match = ADR_NUMBER_PATTERN.search(filepath.stem)
        if not match:
            continue
        adr_number = int(match.group(1))
        content = filepath.read_text(encoding="utf-8")
        title = parse_adr_title(content)
        status = parse_adr_status(content)
        must, should, may = count_requirements(content)
        results.append(
            AdrRequirements(
                number=adr_number,
                title=title,
                filepath=filepath,
                status=status,
                must_count=must,
                should_count=should,
                may_count=may,
            )
        )
    return results


def build_report(adr_dir: Path, protocol_path: Path) -> SyncReport:
    """Build sync report by scanning ADRs and checking protocol references."""
    protocol_content = protocol_path.read_text(encoding="utf-8")
    adrs = scan_adrs(adr_dir)
    for adr in adrs:
        adr.referenced_in_protocol = check_protocol_reference(
            protocol_content, adr.number
        )
    return SyncReport(adrs=adrs)


def print_report(report: SyncReport) -> None:
    """Print sync audit report to stdout."""
    print("=" * 70)
    print("ADR-to-Protocol Sync Audit")
    print("=" * 70)
    print()

    # Summary
    total = len(report.adrs)
    enforceable = [a for a in report.adrs if a.has_enforceable_requirements]
    synced = report.synced
    gaps = report.gaps
    informational = report.informational

    print(f"Total ADRs scanned: {total}")
    print(f"  With MUST requirements: {len(enforceable)}")
    print(f"    Referenced in protocol: {len(synced)}")
    print(f"    NOT referenced (gaps): {len(gaps)}")
    print(f"  Informational only: {len(informational)}")
    print()

    # Gaps (most important)
    if gaps:
        print("-" * 70)
        print("GAPS: ADRs with MUST requirements NOT referenced in SESSION-PROTOCOL.md")
        print("-" * 70)
        for adr in gaps:
            print(
                f"  ADR-{adr.number:03d}: {adr.title} "
                f"({adr.must_count} MUST, {adr.should_count} SHOULD) "
                f"[{adr.status}]"
            )
        print()

    # Synced
    if synced:
        print("-" * 70)
        print("SYNCED: ADRs with MUST requirements referenced in SESSION-PROTOCOL.md")
        print("-" * 70)
        for adr in synced:
            print(
                f"  ADR-{adr.number:03d}: {adr.title} "
                f"({adr.must_count} MUST) [{adr.status}]"
            )
        print()

    # Result
    if gaps:
        print(f"RESULT: {len(gaps)} gap(s) detected. Review and update protocol.")
    else:
        print("RESULT: All ADRs with MUST requirements are referenced in protocol.")


def main() -> int:
    """Run ADR-to-Protocol sync audit."""
    parser = argparse.ArgumentParser(
        description="Audit ADR-to-Protocol sync coverage"
    )
    parser.add_argument(
        "--adr-dir",
        type=Path,
        default=Path(".agents/architecture"),
        help="Directory containing ADR files (default: .agents/architecture)",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(".agents/SESSION-PROTOCOL.md"),
        help="Path to SESSION-PROTOCOL.md (default: .agents/SESSION-PROTOCOL.md)",
    )
    args = parser.parse_args()

    if not args.adr_dir.is_dir():
        print(f"Error: ADR directory not found: {args.adr_dir}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    if not args.protocol.is_file():
        print(f"Error: Protocol file not found: {args.protocol}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    report = build_report(args.adr_dir, args.protocol)
    print_report(report)

    return EXIT_GAPS_DETECTED if report.gaps else EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
