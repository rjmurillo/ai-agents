#!/usr/bin/env python3
"""Parse memory health report results into GitHub Actions step outputs.

Extracted from ``.github/workflows/memory-health.yml`` under ADR-006 (no logic
in workflow YAML). Issue #3541.

Reads the schema that ``scripts/memory_enhancement/__main__.py::_cmd_health``
actually emits. The original version read a ``summary`` object with ``total``,
``healthy``, ``stale``, ``exempt``, and ``errors``. That shape belonged to an
implementation deleted in ``2aeb4fddd``; the surviving one emits flat
top-level keys and no ``summary`` at all, so every field rendered as ``null``
and ``has_stale`` was permanently ``false`` (issue #3971).

Two behaviours from the shell this originally replaced are load-bearing and
still preserved:

* A missing report is not a failure. It emits ``has_stale=false`` and
  ``total_memories=0`` and nothing else, so the downstream comment step still
  runs.
* A stale count that is not an integer reads as "not stale" rather than
  crashing. In shell, ``[ "null" -gt 0 ]`` errored and the ``if`` took its
  else branch; the same outcome is produced here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# The keys ``_cmd_health`` emits that the PR comment renders. Kept as a tuple
# so a regression test can assert it is a subset of the producer's output.
_REPORT_FIELDS = (
    "total_memories",
    "total_citations",
    "valid_citations",
    "stale_citations",
    "broken_citations",
    "unverified_citations",
    "health_score",
)


def _write_outputs(pairs: list[tuple[str, str]], output_path: str | None) -> None:
    """Append ``key=value`` lines to the GitHub Actions output file."""
    if not output_path:
        for key, value in pairs:
            print(f"{key}={value}")
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in pairs:
            handle.write(f"{key}={value}\n")


def _is_stale(value: object) -> bool:
    """Report whether a stale count is a positive integer.

    ``jq`` emits ``null`` for a missing key and the shell comparison that
    consumed it failed rather than raising, so anything non-integral is
    treated as "not stale".
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value > 0


def parse_results(results: Path) -> list[tuple[str, str]]:
    """Return the step outputs for a health report, present or not."""
    if not results.is_file():
        return [("has_stale", "false"), ("total_memories", "0")]

    payload = json.loads(results.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        # A report that is an array or a scalar reads as absent, not fatal,
        # so a malformed report never blocks the comment step.
        payload = {}
    pairs = [(field, _render(payload.get(field))) for field in _REPORT_FIELDS]
    stale_memories = _count(payload.get("stale_memories"))
    pairs.append(("stale_memory_count", _render(stale_memories)))
    pairs.append(("has_stale", "true" if _has_issues(payload) else "false"))
    return pairs


def _has_issues(payload: dict[str, object]) -> bool:
    """Mirror the producer's own issue test so the comment matches the exit code.

    ``_cmd_health`` returns 1 when broken citations, stale citations, or stale
    memories are present. Reading only the citation counts would report Pass on
    a corpus the tool itself considers unhealthy.
    """
    return (
        _is_stale(payload.get("broken_citations"))
        or _is_stale(payload.get("stale_citations"))
        or _count(payload.get("stale_memories")) > 0
    )


def _count(value: object) -> int:
    """Return the length of a list field, or zero for any other shape."""
    return len(value) if isinstance(value, list) else 0


def _render(value: object) -> str:
    """Render a report value the way ``jq`` rendered it for the shell."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


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
    except (json.JSONDecodeError, OSError) as exc:
        print(f"::error::Could not read {results.name}: {exc}")
        return 1

    _write_outputs(pairs, os.environ.get("GITHUB_OUTPUT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
