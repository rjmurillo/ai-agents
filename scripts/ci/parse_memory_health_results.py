#!/usr/bin/env python3
"""Parse memory health report results into GitHub Actions step outputs.

Extracted from ``.github/workflows/memory-health.yml`` under ADR-006 (no logic
in workflow YAML). Issue #3541.

The report is produced by ``memory_enhancement health --json``, which emits a
flat object. Every key this module reads is listed in ``_FIELD_SOURCES`` and
``_STALE_LIST_KEY`` so a contract test can compare them against a payload from
the real producer rather than against a hand-written fixture. Issue #3971.

Anything the producer could not have emitted is fatal: a missing or empty
file, unparseable JSON, a non-object payload, an absent key, or a
``stale_memories`` that is not a list. The ``jq`` shell this replaces was
tolerant of all of them, and that tolerance is the bug. The producer step runs
under ``continue-on-error``, so a crash or a regression arrives here as
malformed input; reading it as "no stale memories" turns a broken gate into a
green "Pass", which is exactly how #3971 stayed hidden.

Values are still rendered rather than type-checked. The count fields only
reach a PR comment, so a wrong-typed one is cosmetic. ``stale_memories`` is
checked because it alone decides whether the gate passes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Output name -> key emitted by ``_cmd_health`` in memory_enhancement/__main__.
_FIELD_SOURCES: dict[str, str] = {
    "total": "total_memories",
    "health_score": "health_score",
    "broken_citations": "broken_citations",
    "stale_citations": "stale_citations",
    "unverified_citations": "unverified_citations",
}

# The producer emits the stale memories as a list, not a count.
_STALE_LIST_KEY = "stale_memories"


def producer_keys_read() -> frozenset[str]:
    """Return every producer key this script reads.

    The contract test compares this against the keys a real health report
    carries. Deriving the set from the same tables the parser uses is what
    makes that test a contract rather than a restatement.
    """
    return frozenset(_FIELD_SOURCES.values()) | {_STALE_LIST_KEY}


def _write_outputs(pairs: list[tuple[str, str]], output_path: str | None) -> None:
    """Append ``key=value`` lines to the GitHub Actions output file."""
    if not output_path:
        for key, value in pairs:
            print(f"{key}={value}")
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in pairs:
            handle.write(f"{key}={value}\n")


def _render(value: object) -> str:
    """Render a report value the way ``jq`` rendered it for the shell."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def parse_results(results: Path) -> list[tuple[str, str]]:
    """Return the step outputs for a health report.

    Raises:
        ValueError: The file is empty, is not a JSON object, omits a key the
            parser reads, or carries a non-list ``stale_memories``.
        json.JSONDecodeError: The file is not valid JSON.
        OSError: The file is missing or unreadable.
    """
    raw = results.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError(
            "report is empty, which means the health command exited without "
            "writing output"
        )

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"report is a {type(payload).__name__}, not an object")

    missing = sorted(producer_keys_read() - payload.keys())
    if missing:
        raise ValueError(f"report is missing keys the producer emits: {missing}")

    stale = payload[_STALE_LIST_KEY]
    if not isinstance(stale, list):
        raise ValueError(
            f"{_STALE_LIST_KEY} is a {type(stale).__name__}, not a list, so the "
            "stale gate cannot be trusted"
        )

    pairs = [(name, _render(payload[key])) for name, key in _FIELD_SOURCES.items()]
    pairs.append(("stale", str(len(stale))))
    pairs.append(("has_stale", "true" if stale else "false"))
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="health-report.json",
        help="Path to the memory health JSON report.",
    )
    args = parser.parse_args(argv)

    results = Path(args.results)
    try:
        pairs = parse_results(results)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"::error::Could not read {results.name}: {exc}")
        return 1

    _write_outputs(pairs, os.environ.get("GITHUB_OUTPUT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
