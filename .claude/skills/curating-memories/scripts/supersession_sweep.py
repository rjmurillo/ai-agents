#!/usr/bin/env python3
"""Supersession sweep: classify memory files for curation (issue #3019).

Detects the append-never-delete pattern: memory files that are fully
resolved or historical but still present as live guidance. The sweep
*proposes* a disposition per file and emits a report. It never edits or
deletes anything.

The classification is a routing signal into verification, never a verdict.
A memory is only archived after a separate, human-confirmed ratification
step that checks the referenced artifacts are actually gone (the
`doc-accuracy` code-as-source-of-truth discipline). A mis-flag on a
load-bearing entry is the exact loss this proposal-only design prevents.

Buckets:
  live                                current guidance, leave alone
  healthy-supersession                struck-through obsolete + dated
                                      banner, current truth visible; the
                                      target shape, leave alone
  resolved-or-historical-but-present  RESOLVED/BLOCKING status co-present
                                      with references to removed artifacts
                                      or per-section historical tags;
                                      propose archive/collapse
  temporal-snapshot-as-live           dated point-in-time doc framed as
                                      current; propose a dated-snapshot
                                      banner

Exit code is always 0: this is a proposal, not a gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

LIVE = "live"
HEALTHY_SUPERSESSION = "healthy-supersession"
RESOLVED_HISTORICAL = "resolved-or-historical-but-present"
TEMPORAL_SNAPSHOT = "temporal-snapshot-as-live"

# Dispositions that warrant a follow-up proposal. healthy-supersession and
# live are both "leave alone", so neither appears in the proposals list.
ACTIONABLE = (RESOLVED_HISTORICAL, TEMPORAL_SNAPSHOT)

_STATUS_RE = re.compile(r"status[^A-Za-z0-9]{0,6}(resolved|blocking)", re.IGNORECASE)
_REMOVED_RE = re.compile(r"\(removed\)", re.IGNORECASE)
_HISTORICAL_RE = re.compile(r"\(historical\)", re.IGNORECASE)
_STRIKE_RE = re.compile(r"~~")
_BANNER_RE = re.compile(
    r"(important|update|superseded|deprecated|note)[^\n)]*\(20\d{2}-\d{2}-\d{2}\)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"20\d{2}-\d{2}-\d{2}")
_SNAPSHOT_FRAME_RE = re.compile(
    r"top[\s\-]?\d+|snapshot|as of|current state",
    re.IGNORECASE,
)

# Thresholds calibrated against the confirmed cases in issue #3019.
MIN_REMOVED_FOR_ROT = 2
MIN_STRIKE_PAIRS_FOR_HEALTHY = 3
HEAD_LINES = 15


@dataclass(frozen=True)
class Signals:
    """Structural signals extracted from a single memory file."""

    status_resolved_blocking: bool
    removed_refs: int
    historical_tags: int
    strikethrough_pairs: int
    dated_banner: bool
    dated_snapshot_frame: bool


def scan_signals(text: str) -> Signals:
    """Extract classification signals from memory file text."""
    head = "\n".join(text.splitlines()[:HEAD_LINES])
    return Signals(
        status_resolved_blocking=bool(_STATUS_RE.search(text)),
        removed_refs=len(_REMOVED_RE.findall(text)),
        historical_tags=len(_HISTORICAL_RE.findall(text)),
        strikethrough_pairs=len(_STRIKE_RE.findall(text)) // 2,
        dated_banner=bool(_BANNER_RE.search(text)),
        dated_snapshot_frame=bool(
            _DATE_RE.search(head) and _SNAPSHOT_FRAME_RE.search(head)
        ),
    )


def _is_resolved_historical(sig: Signals) -> bool:
    """Rot: a done/blocked status still present, pointing at gone artifacts."""
    if not sig.status_resolved_blocking:
        return False
    return sig.removed_refs >= MIN_REMOVED_FOR_ROT or sig.historical_tags >= 1


def _is_healthy_supersession(sig: Signals) -> bool:
    """Target shape: dated banner plus struck-through obsolete content."""
    return sig.dated_banner and sig.strikethrough_pairs >= MIN_STRIKE_PAIRS_FOR_HEALTHY


def classify(sig: Signals) -> str:
    """Map signals to one bucket. Order encodes precedence.

    Rot is checked before healthy-supersession so a resolved doc that also
    has strikethrough is flagged, not excused. Healthy-supersession is
    checked before temporal-snapshot so the dated-banner + strikethrough
    target shape is never mistaken for a stale snapshot. Strikethrough
    density alone never triggers a rot proposal (false-positive guard).
    """
    if _is_resolved_historical(sig):
        return RESOLVED_HISTORICAL
    if _is_healthy_supersession(sig):
        return HEALTHY_SUPERSESSION
    if sig.dated_snapshot_frame:
        return TEMPORAL_SNAPSHOT
    return LIVE


def classify_file(path: Path) -> str:
    """Classify a single memory file by path."""
    return classify(scan_signals(path.read_text(encoding="utf-8")))


@dataclass
class Proposal:
    """A per-file disposition proposal (never an edit)."""

    path: str
    disposition: str
    signals: dict[str, object]


def sweep(root: Path) -> list[Proposal]:
    """Classify every markdown file under root. Returns proposals, no edits."""
    proposals: list[Proposal] = []
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # One unreadable file must not abort a whole-tree sweep. Skip it
            # and surface the reason so the operator can follow up.
            print(f"warning: skipping {path}: {exc}", file=sys.stderr)
            continue
        sig = scan_signals(text)
        proposals.append(
            Proposal(
                path=str(path.relative_to(root)),
                disposition=classify(sig),
                signals=asdict(sig),
            )
        )
    return proposals


def _counts(proposals: list[Proposal]) -> dict[str, int]:
    counts: dict[str, int] = {
        LIVE: 0,
        HEALTHY_SUPERSESSION: 0,
        RESOLVED_HISTORICAL: 0,
        TEMPORAL_SNAPSHOT: 0,
    }
    for proposal in proposals:
        counts[proposal.disposition] = counts.get(proposal.disposition, 0) + 1
    return counts


def render_text(proposals: list[Proposal]) -> str:
    """Human-readable proposal report."""
    counts = _counts(proposals)
    lines = [
        "Supersession sweep (proposal only, no files changed):",
        f"  scanned: {len(proposals)}",
        f"  live: {counts[LIVE]}",
        f"  healthy-supersession (leave alone): {counts[HEALTHY_SUPERSESSION]}",
        "  resolved-or-historical-but-present (propose collapse): "
        f"{counts[RESOLVED_HISTORICAL]}",
        "  temporal-snapshot-as-live (propose dated banner): "
        f"{counts[TEMPORAL_SNAPSHOT]}",
    ]
    flagged = [p for p in proposals if p.disposition in ACTIONABLE]
    if flagged:
        lines.append("")
        lines.append("Proposals (ratify against on-disk/code state before acting):")
        for proposal in flagged:
            lines.append(f"  [{proposal.disposition}] {proposal.path}")
    return "\n".join(lines)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supersession sweep for memories.")
    parser.add_argument(
        "--root",
        default=".serena/memories",
        help="Directory of memory files to scan (default: .serena/memories).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the proposal report as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: root not found: {root}", file=sys.stderr)
        return 0
    proposals = sweep(root)
    if args.json:
        payload = {
            "counts": _counts(proposals),
            "proposals": [asdict(p) for p in proposals],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(render_text(proposals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
