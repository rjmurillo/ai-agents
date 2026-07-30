"""Tests for ADR-015 workflow artifact retention compliance (Issue #3981).

ADR-015 mandates ``retention-days: 7`` for standard artifacts and
``retention-days: 1`` for operational / temporary artifacts.  Any other value
is a violation.

Test categories
---------------
Positive controls
    Conforming values (1, 7) are accepted by ``is_conforming()``.
Negative controls
    Non-conforming values (30, 90) are detected and returned by
    ``violations()``.
Isolating negative control
    ``test_scanner_finds_values_in_real_tree`` proves the scanner returns at
    least one entry from the live workflow tree.  Without this guard, a scanner
    that always returns ``[]`` would make the conformance assertion vacuously
    pass (Issue #3329).
Edge cases
    Empty text, inline comments, multiple entries in one file.
Real-tree gate
    ``test_all_workflow_retention_conform`` enumerates every workflow under
    ``.github/workflows/`` and asserts zero violations.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scripts.ci import adr015_workflow_retention as scanner

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _workflow_yaml(retention_days: int) -> str:
    """Return minimal workflow YAML containing one upload-artifact step."""
    return textwrap.dedent(
        f"""\
        jobs:
          build:
            steps:
              - name: Upload artifact
                uses: actions/upload-artifact@v4
                with:
                  name: my-artifact
                  path: out/
                  retention-days: {retention_days}
        """
    )


# ---------------------------------------------------------------------------
# Positive controls: conforming values pass
# ---------------------------------------------------------------------------


def test_retention_7_is_conforming() -> None:
    """7-day retention is the ADR-015 standard value."""
    entries = scanner.scan_text(_workflow_yaml(7), Path("dummy.yml"))
    assert len(entries) == 1
    assert scanner.is_conforming(entries[0])


def test_retention_1_is_conforming() -> None:
    """1-day retention is the approved operational exception."""
    entries = scanner.scan_text(_workflow_yaml(1), Path("dummy.yml"))
    assert len(entries) == 1
    assert scanner.is_conforming(entries[0])


def test_violations_returns_empty_for_conforming_file() -> None:
    """violations() yields nothing when every entry is allowed."""
    yaml = textwrap.dedent(
        """\
        jobs:
          a:
            steps:
              - uses: actions/upload-artifact@v4
                with:
                  retention-days: 7
          b:
            steps:
              - uses: actions/upload-artifact@v4
                with:
                  retention-days: 1
        """
    )
    entries = scanner.scan_text(yaml, Path("dummy.yml"))
    assert scanner.violations(entries) == []


# ---------------------------------------------------------------------------
# Negative controls: non-conforming values are detected
# ---------------------------------------------------------------------------


def test_retention_30_is_nonconforming() -> None:
    """30-day retention violates ADR-015."""
    entries = scanner.scan_text(_workflow_yaml(30), Path("dummy.yml"))
    assert len(entries) == 1
    assert not scanner.is_conforming(entries[0])


def test_retention_90_is_nonconforming() -> None:
    """90-day retention violates ADR-015."""
    entries = scanner.scan_text(_workflow_yaml(90), Path("dummy.yml"))
    assert len(entries) == 1
    assert not scanner.is_conforming(entries[0])


def test_violations_returns_only_bad_entries() -> None:
    """violations() filters to non-conforming entries only."""
    yaml = textwrap.dedent(
        """\
        jobs:
          a:
            steps:
              - uses: actions/upload-artifact@v4
                with:
                  retention-days: 7
          b:
            steps:
              - uses: actions/upload-artifact@v4
                with:
                  retention-days: 30
        """
    )
    entries = scanner.scan_text(yaml, Path("dummy.yml"))
    bad = scanner.violations(entries)
    assert len(bad) == 1
    assert bad[0].value == 30


# ---------------------------------------------------------------------------
# Isolating negative control
# ---------------------------------------------------------------------------


def test_scanner_finds_values_in_real_tree() -> None:
    """Scanner returns at least one entry from the live workflow tree.

    A scanner that always returns ``[]`` makes the conformance gate vacuously
    pass.  This test is the isolating negative control that proves the scanner
    actually reads ``retention-days`` values from real workflow files.
    """
    entries = scanner.scan_directory(WORKFLOWS_DIR)
    assert len(entries) >= 1, (
        "scan_directory returned no entries; scanner is broken or the "
        "workflows directory contains no retention-days declarations"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_scan_text_returns_empty_for_file_without_retention() -> None:
    """Files with no retention-days yield an empty list."""
    yaml = textwrap.dedent(
        """\
        jobs:
          build:
            steps:
              - run: echo hello
        """
    )
    assert scanner.scan_text(yaml, Path("dummy.yml")) == []


def test_scan_text_handles_inline_comment() -> None:
    """Inline comments after the value do not break parsing."""
    line = "          retention-days: 7  # ADR-015 standard\n"
    entries = scanner.scan_text(line, Path("dummy.yml"))
    assert len(entries) == 1
    assert entries[0].value == 7


def test_scan_text_reports_correct_line_number() -> None:
    """line_no is 1-based and identifies the exact source line."""
    yaml = "jobs:\n  build:\n    steps:\n      - with:\n          retention-days: 30\n"
    entries = scanner.scan_text(yaml, Path("dummy.yml"))
    assert len(entries) == 1
    assert entries[0].line_no == 5


def test_scan_text_collects_multiple_entries() -> None:
    """All retention-days declarations in one file are captured."""
    yaml = textwrap.dedent(
        """\
        jobs:
          a:
            steps:
              - uses: actions/upload-artifact@v4
                with:
                  retention-days: 7
          b:
            steps:
              - uses: actions/upload-artifact@v4
                with:
                  retention-days: 90
        """
    )
    entries = scanner.scan_text(yaml, Path("dummy.yml"))
    assert len(entries) == 2
    assert entries[0].value == 7
    assert entries[1].value == 90


def test_allowed_days_contains_expected_values() -> None:
    """ALLOWED_DAYS exposes the policy so tests can import it."""
    assert 1 in scanner.ALLOWED_DAYS
    assert 7 in scanner.ALLOWED_DAYS
    assert 30 not in scanner.ALLOWED_DAYS
    assert 90 not in scanner.ALLOWED_DAYS


# ---------------------------------------------------------------------------
# Real-tree gate
# ---------------------------------------------------------------------------


def test_all_workflow_retention_conform() -> None:
    """Every retention-days value in .github/workflows/ satisfies ADR-015.

    Permitted values: 1 (operational) and 7 (standard).

    To add an approved exception, insert an entry into ``_EXCEPTIONS`` in
    ``scripts/ci/adr015_workflow_retention.py`` with the workflow file stem,
    the allowed value, and a justification that cites the approving issue.
    """
    entries = scanner.scan_directory(WORKFLOWS_DIR)
    bad = scanner.violations(entries)
    if bad:
        lines = [f"ADR-015 retention-days violations ({len(bad)}):"]
        for entry in bad:
            try:
                rel = entry.file.relative_to(REPO_ROOT)
            except ValueError:
                rel = entry.file
            lines.append(
                f"  {rel}:{entry.line_no}: {entry.value} days"
                f"  (allowed: {sorted(scanner.ALLOWED_DAYS)})"
            )
        pytest.fail("\n".join(lines))


if __name__ == "__main__":
    import pytest as _pytest

    raise SystemExit(_pytest.main([__file__, "-q"]))
