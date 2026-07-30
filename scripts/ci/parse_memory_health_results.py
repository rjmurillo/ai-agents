#!/usr/bin/env python3
"""Parse memory health report results into GitHub Actions step outputs.

Extracted from ``.github/workflows/memory-health.yml`` under ADR-006 (no logic
in workflow YAML). Issue #3541, reworked for issue #3971.

This reads the schema ``memory_enhancement health --json`` actually emits, a
flat object produced by ``_cmd_health`` in ``scripts/memory_enhancement``. An
earlier revision read a ``summary`` object belonging to the implementation
deleted in ``2aeb4fddd``; every field it asked for rendered as ``null`` and the
workflow reported a permanent green Pass.

A missing, empty, or unparseable report means the health command crashed. That
is reported as an error rather than defaulting to a green banner, matching the
sibling ``memory-validation.yml`` contract established by issue #2808. The
producing workflow steps set ``continue-on-error``, so a crash there is silent
and this script is the only place it can become visible.

``has_issues`` mirrors the producer's own exit-code predicate so the banner and
the command agree on what "unhealthy" means.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

#: Integer counters copied straight through from the report.
COUNT_FIELDS = (
    "total_memories",
    "total_citations",
    "valid_citations",
    "stale_citations",
    "broken_citations",
    "unverified_citations",
)

#: List-valued fields surfaced to the workflow as lengths.
LENGTH_FIELDS = ("stale_memories", "recommendations")


def _coerce_count(value: object) -> int:
    """Return a non-negative integer for a report counter."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"expected an integer counter, got {value!r}")
    if value < 0:
        raise ValueError(f"expected a non-negative counter, got {value!r}")
    return value


def _coerce_length(value: object) -> int:
    """Return the length of a list-valued report field."""
    if not isinstance(value, list):
        raise ValueError(f"expected a list, got {value!r}")
    return len(value)


def _render_score(value: object) -> str:
    """Render a 0..1 ``health_score`` as a whole-number percentage."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected a numeric health score, got {value!r}")
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"expected health_score between 0.0 and 1.0, got {value!r}")
    return f"{round(value * 100)}%"


def parse_report(payload: object) -> list[tuple[str, str]]:
    """Return the step outputs for a decoded health report.

    Raises ``ValueError`` when the payload is not the shape ``_cmd_health``
    emits. A shape mismatch means the producer and this consumer have drifted
    apart, which is the failure issue #3971 was filed for, so it must not be
    absorbed into a default.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object, got {type(payload).__name__}")

    required = (*COUNT_FIELDS, *LENGTH_FIELDS, "health_score")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"report is missing expected keys: {', '.join(missing)}")

    counts = {field: _coerce_count(payload[field]) for field in COUNT_FIELDS}
    lengths = {field: _coerce_length(payload[field]) for field in LENGTH_FIELDS}

    pairs = [(field, str(counts[field])) for field in COUNT_FIELDS]
    pairs.extend((field, str(lengths[field])) for field in LENGTH_FIELDS)
    pairs.append(("health_score", _render_score(payload["health_score"])))

    has_issues = (
        counts["broken_citations"] > 0
        or counts["stale_citations"] > 0
        or lengths["stale_memories"] > 0
    )
    pairs.append(("has_issues", "true" if has_issues else "false"))
    return pairs


def _write_outputs(pairs: list[tuple[str, str]], output_path: str | None) -> None:
    """Append ``key=value`` lines to the GitHub Actions output file."""
    if not output_path:
        for key, value in pairs:
            print(f"{key}={value}")
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in pairs:
            handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="health-report.json",
        help="Path to the memory health JSON report.",
    )
    args = parser.parse_args(argv)

    results = Path(args.results)
    if not results.is_file() or results.stat().st_size == 0:
        print(
            f"::error::{results.name} is missing or empty, so the health command "
            "crashed. Refusing to report a passing health check."
        )
        return 1

    try:
        payload = json.loads(results.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"::error::Could not read {results.name}: {exc}")
        return 1

    try:
        pairs = parse_report(payload)
    except ValueError as exc:
        print(
            f"::error::{results.name} does not match the schema emitted by "
            f"'memory_enhancement health --json': {exc}"
        )
        return 1

    _write_outputs(pairs, os.environ.get("GITHUB_OUTPUT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
