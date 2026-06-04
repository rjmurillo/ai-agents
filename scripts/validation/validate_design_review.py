#!/usr/bin/env python3
"""DESIGN-REVIEW frontmatter validation for the pre-PR runner.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223). Validates the
YAML frontmatter of ``.agents/architecture/DESIGN-REVIEW-*.md`` files: required
fields, valid status and priority values, and blocking consistency. Re-exported
through ``pre_pr`` so callers and tests keep importing it from there.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from yaml_utils import _parse_yaml_frontmatter  # noqa: E402

_REQUIRED_FRONTMATTER_FIELDS = {"status", "priority", "blocking", "reviewer", "date"}
_VALID_STATUSES = {"APPROVED", "NEEDS_CHANGES", "NEEDS_ADR", "BLOCKED", "REJECTED"}
_VALID_PRIORITIES = {"P0", "P1", "P2"}
_BLOCKING_STATUSES = {"NEEDS_ADR", "BLOCKED", "REJECTED"}


def validate_design_review_frontmatter(repo_root: Path) -> bool:
    """Validate YAML frontmatter in DESIGN-REVIEW documents.

    Checks all .agents/architecture/DESIGN-REVIEW-*.md files for:
    - Presence of YAML frontmatter
    - Required fields (status, priority, blocking, reviewer, date)
    - Valid status and priority values
    - Blocking consistency (blocking=true when status is NEEDS_ADR/BLOCKED/REJECTED)

    Returns True if all files pass or no files exist.
    """
    review_dir = repo_root / ".agents" / "architecture"
    if not review_dir.is_dir():
        print("[WARNING] No .agents/architecture/ directory found")
        return True

    review_files = sorted(review_dir.glob("DESIGN-REVIEW-*.md"))
    if not review_files:
        print("No DESIGN-REVIEW files found. Nothing to validate.")
        return True

    print(f"Validating {len(review_files)} DESIGN-REVIEW file(s)...")

    all_passed = True
    blocking_reviews: list[str] = []

    for filepath in review_files:
        text = filepath.read_text(encoding="utf-8")
        frontmatter = _parse_yaml_frontmatter(text)

        if frontmatter is None:
            print(f"  [FAIL] {filepath.name}: missing YAML frontmatter")
            all_passed = False
            continue

        # Check required fields
        missing = _REQUIRED_FRONTMATTER_FIELDS - set(frontmatter.keys())
        if missing:
            print(f"  [FAIL] {filepath.name}: missing fields: {', '.join(sorted(missing))}")
            all_passed = False
            continue

        # Validate status value
        status = str(frontmatter["status"]).strip()
        if status not in _VALID_STATUSES:
            print(f"  [FAIL] {filepath.name}: invalid status '{status}'")
            all_passed = False

        # Validate priority value
        priority = str(frontmatter["priority"]).strip()
        if priority not in _VALID_PRIORITIES:
            print(f"  [FAIL] {filepath.name}: invalid priority '{priority}'")
            all_passed = False

        # Check blocking consistency
        blocking = frontmatter.get("blocking", False)
        if status in _BLOCKING_STATUSES and not blocking:
            print(
                f"  [WARNING] {filepath.name}: status '{status}' should have blocking: true"
            )

        if blocking and status in _BLOCKING_STATUSES:
            blocking_reviews.append(filepath.name)

        print(f"  [PASS] {filepath.name} (status={status}, blocking={blocking})")

    if blocking_reviews:
        print()
        print(f"[WARNING] {len(blocking_reviews)} blocking review(s) detected:")
        for name in blocking_reviews:
            print(f"  - {name}")
        print("  These will block PR merges via synthesis-panel-gate.yml")

    return all_passed
