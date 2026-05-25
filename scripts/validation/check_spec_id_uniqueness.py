#!/usr/bin/env python3
"""Verify spec `id:` frontmatter values are unique within each spec category.

Scans `.agents/specs/{requirements,design,tasks}/*.md`, parses the YAML
frontmatter for the top-level `id:` key, and exits non-zero if any value
collides with another file in the same category.

Per Issue #2068: duplicate REQ/DESIGN/TASK IDs break traceability and any
future spec-graph tooling that joins by ID. README files under each spec
category already require uniqueness; this script enforces it in CI.

Exit codes (per ADR-035):
    0 - all IDs unique
    1 - one or more duplicates detected
    2 - config error (e.g. specs directory missing)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

CATEGORIES = ("requirements", "design", "tasks")
ID_RE = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)


def _read_id(path: Path) -> str | None:
    """Extract the top-level `id:` value from a spec markdown file.

    Only looks inside the YAML frontmatter (the first `---`-delimited block)
    so a stray `id:` mention later in prose does not produce a false match.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    frontmatter = text[3:end]
    m = ID_RE.search(frontmatter)
    return m.group(1) if m else None


def check_category(specs_dir: Path, category: str) -> list[str]:
    """Return a list of error messages for duplicates in one category."""
    cat_dir = specs_dir / category
    if not cat_dir.is_dir():
        return []
    by_id: dict[str, list[Path]] = defaultdict(list)
    for md in sorted(cat_dir.glob("*.md")):
        if md.name.upper() == "README.MD":
            continue
        spec_id = _read_id(md)
        if spec_id is None:
            continue
        by_id[spec_id].append(md)
    errors: list[str] = []
    for spec_id, paths in sorted(by_id.items()):
        if len(paths) > 1:
            joined = ", ".join(str(p.relative_to(specs_dir.parent.parent)) for p in paths)
            errors.append(f"duplicate id `{spec_id}` in {category}/: {joined}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (defaults to two levels above this script).",
    )
    args = parser.parse_args()

    specs_dir = args.repo_root / ".agents" / "specs"
    if not specs_dir.is_dir():
        print(f"[CONFIG] specs directory not found: {specs_dir}", file=sys.stderr)
        return 2

    all_errors: list[str] = []
    for category in CATEGORIES:
        all_errors.extend(check_category(specs_dir, category))

    if all_errors:
        print("[FAIL] Duplicate spec IDs detected (see issue #2068):")
        for err in all_errors:
            print(f"  - {err}")
        print(
            "\nEach spec file under .agents/specs/{requirements,design,tasks}/ "
            "MUST have a unique `id:` in its frontmatter. Rename the duplicate "
            "and update its `id:` to the next free NNN."
        )
        return 1

    print("[PASS] All spec IDs unique across requirements/, design/, tasks/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
