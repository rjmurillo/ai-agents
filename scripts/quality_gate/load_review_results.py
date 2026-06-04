#!/usr/bin/env python3
"""Load per-agent verdict and infrastructure flags into GITHUB_OUTPUT.

Extracted from the inline ``Load review results`` step in
``.github/workflows/ai-pr-quality-gate.yml`` (ADR-006: no logic in YAML).

For each of the ten quality-gate agents the step reads
``ai-review-results/<agent>-verdict.txt`` and
``ai-review-results/<agent>-infrastructure-failure.txt`` and writes
``<agent>_verdict`` and ``<agent>_infra`` to ``GITHUB_OUTPUT``.

Behavior reproduced verbatim from the original pwsh block, which used
``Get-Content -Raw`` then ``Trim()``:

* Verdict: non-empty file content is trimmed; an empty or missing verdict file
  yields ``NEEDS_REVIEW``. A whitespace-only file trims to the empty string
  (the original ``if ($rawVerdict)`` is truthy for whitespace, then Trim()
  empties it).
* Infra flag: non-empty file content is trimmed; an empty or missing infra file
  yields ``false``.

The agent roster comes from ``quality_gate_agents.QUALITY_GATE_AGENTS`` so the
workflow has a single source of truth.

Args:
    --results-dir  Directory holding the verdict/infra files (default
                   ``ai-review-results``).

Input env vars:
    GITHUB_OUTPUT - path to the GitHub Actions output file.

Exit codes (ADR-035):
    0 - all outputs written
    2 - GITHUB_OUTPUT is not set (config error)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GITHUB_SCRIPTS = _SCRIPT_DIR.parents[1] / ".github" / "scripts"
sys.path.insert(0, str(_GITHUB_SCRIPTS))

from quality_gate_agents import QUALITY_GATE_AGENTS  # noqa: E402


def _read_raw(path: Path) -> str | None:
    """Return file text, or None when the file is absent (mirrors Test-Path)."""

    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def read_verdict(results_dir: Path, agent: str) -> str:
    """Return the trimmed verdict, or ``NEEDS_REVIEW`` when empty/missing."""

    raw = _read_raw(results_dir / f"{agent}-verdict.txt")
    if not raw:
        return "NEEDS_REVIEW"
    return raw.strip()


def read_infra(results_dir: Path, agent: str) -> str:
    """Return the trimmed infra flag, or ``false`` when empty/missing."""

    raw = _read_raw(results_dir / f"{agent}-infrastructure-failure.txt")
    if not raw:
        return "false"
    return raw.strip()


def collect(results_dir: Path) -> list[tuple[str, str, str]]:
    """Return ``(agent, verdict, infra)`` triples in canonical agent order."""

    return [
        (agent, read_verdict(results_dir, agent), read_infra(results_dir, agent))
        for agent in QUALITY_GATE_AGENTS
    ]


def write_outputs(output_path: Path, rows: list[tuple[str, str, str]]) -> None:
    """Append ``<agent>_verdict`` and ``<agent>_infra`` lines to the output."""

    with output_path.open("a", encoding="utf-8") as handle:
        for agent, verdict, infra in rows:
            handle.write(f"{agent}_verdict={verdict}\n")
            handle.write(f"{agent}_infra={infra}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("ai-review-results"),
        help="Directory holding the downloaded verdict/infra files.",
    )
    args = parser.parse_args(argv)

    rows = collect(args.results_dir)

    print("Loaded verdicts:")
    for agent, verdict, infra in rows:
        print(f"  {agent}: {verdict} (infra: {infra})")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        print("error: GITHUB_OUTPUT is not set", file=sys.stderr)
        return 2

    write_outputs(Path(github_output), rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
