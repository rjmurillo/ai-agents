#!/usr/bin/env python3
"""Validate docs/agent-catalog.md against templates/agents/*.shared.md.

Regenerates the catalog into an in-memory buffer and compares it to the
committed docs/agent-catalog.md. Exits non-zero when the committed file is
stale or missing, so CI catches a forgotten regeneration before merge.

This validator delegates the drift contract to build/generate_agent_catalog.py
rather than reimplementing the table format. The generator is the single owner
of the contract (canonical-source-mirror.md); this script invokes its
``--check`` path and returns that ADR-035 exit code unchanged.

EXIT CODES (ADR-035):
  0  - Catalog matches the templates.
  1  - Catalog drifted from the templates, or is missing.
  2  - Configuration error (generator or templates directory not found).
  3  - External error (a template could not be read or parsed).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "build"))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the agent-catalog drift check.

    ``argv`` is accepted for symmetry with other validators and for tests; the
    check has no options, so any arguments are ignored.
    """
    _ = argv
    templates_dir = _REPO_ROOT / "templates" / "agents"
    output_path = _REPO_ROOT / "docs" / "agent-catalog.md"

    if not templates_dir.is_dir():
        print(f"Error: templates directory not found: {templates_dir}", file=sys.stderr)
        return 2

    try:
        import generate_agent_catalog  # noqa: PLC0415
    except ImportError as exc:
        print(f"Error: cannot import build/generate_agent_catalog.py: {exc}", file=sys.stderr)
        return 2

    return generate_agent_catalog.main(
        ["--check", "--templates-path", str(templates_dir), "--output", str(output_path)]
    )


if __name__ == "__main__":
    sys.exit(main())
