#!/usr/bin/env python3
"""Scan the live markdown corpus for real frontmatter-parser disagreement.

Evidence for `.agents/analysis/frontmatter-parser-build-vs-buy.md`: establishes
whether the divergence documented in issue #5275 is active breakage or a latent
trap. Compares `yaml_utils`, `generate_adr_index`'s regex, and `python-frontmatter`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import frontmatter  # noqa: E402

from scripts.validation.yaml_utils import _parse_yaml_frontmatter  # noqa: E402

# Quoted verbatim from build/scripts/generate_adr_index.py:84.
_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$")

ROOTS = (
    ".agents/architecture",
    ".serena/memories",
    ".claude/skills",
    "src",
    "templates",
)


def main() -> int:
    files = [p for root in ROOTS for p in (REPO_ROOT / root).rglob("*.md")]
    print(f"scanned {len(files)} markdown files under {len(ROOTS)} roots")

    disagreements: list[tuple[str, bool, bool, object]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text.startswith("---"):
            continue
        via_yaml_utils = _parse_yaml_frontmatter(text) is not None
        via_index_re = _FRONTMATTER_RE.match(text) is not None
        try:
            via_library: object = bool(frontmatter.loads(text).metadata)
        except Exception as exc:
            via_library = f"RAISE:{type(exc).__name__}"
        if not (via_yaml_utils is via_index_re is via_library):
            disagreements.append(
                (str(path.relative_to(REPO_ROOT)), via_yaml_utils, via_index_re, via_library)
            )

    print(f"\nfiles where the three parsers disagree: {len(disagreements)}")
    for rel, a, b, c in disagreements:
        print(f"  {rel}\n    yaml_utils={a}  index_re={b}  library={c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
