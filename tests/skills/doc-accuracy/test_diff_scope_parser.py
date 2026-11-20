"""Unit tests for the diff parser, overlap test, and gate severity handling."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import WHOLE_FILE_END, make_repo, mod

WHOLE = {"a.md": [[1, WHOLE_FILE_END]]}
NO_NEWLINE = "\\ No newline at end of file\n"


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ("+++ b/a.md\n@@ -3 +3 @@\n-x\n+y\n", {"a.md": [[3, 3]]}),
        ("+++ b/a.md\n@@ -4,2 +3,0 @@\n-x\n-y\n", {"a.md": [[3, 4]]}),
        ("--- a/a.md\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-a\n-b\n", {}),
        (
            "+++ b/a.md\n@@ -2 +2 @@\n-x\n+```bash\n@@ -9,0 +10 @@\n+y\n",
            {"a.md": [[2, 2], [3, 9], [10, 10], [11, WHOLE_FILE_END]]},
        ),
        # A balanced added pair in one hunk leaves later pairing unchanged.
        (
            "+++ b/a.md\n@@ -2,0 +3,3 @@\n+```bash\n+echo\n+```\n@@ -9,0 +12 @@\n+y\n",
            {"a.md": [[3, 5], [12, 12]]},
        ),
        # Open added in hunk 1, close added in hunk 3: only the stretch between.
        (
            "+++ b/a.md\n@@ -1,0 +2 @@\n+```bash\n@@ -5,0 +7 @@\n+y\n@@ -9,0 +12 @@\n+```\n",
            {"a.md": [[2, 2], [3, 6], [7, 7], [8, 11], [12, 12]]},
        ),
        # Removing a whole balanced block leaves later pairing unchanged.
        (
            "+++ b/a.md\n@@ -3,3 +2,0 @@\n-```\n-text\n-```\n@@ -9,0 +7 @@\n+y\n",
            {"a.md": [[2, 3], [7, 7]]},
        ),
        # Swapping one fence line for another in one hunk is even parity.
        (
            "+++ b/a.md\n@@ -3 +3 @@\n-```bash\n+```python\n",
            {"a.md": [[3, 3]]},
        ),
        # A removed column-0 fence flips pairing for everything below it.
        (
            "+++ b/a.md\n@@ -5,2 +4,0 @@\n-```\n-text\n",
            {"a.md": [[4, 5], [6, WHOLE_FILE_END]]},
        ),
        # An indented backtick fence stays fail closed from its own line.
        (
            "+++ b/a.md\n@@ -3,0 +4 @@\n+  ```bash\n",
            {"a.md": [[4, 4], [4, WHOLE_FILE_END]]},
        ),
        (
            "+++ b/a.md\n@@ -5,2 +4,0 @@\n-  ~~~~\n-text\n",
            {"a.md": [[4, 5], [5, WHOLE_FILE_END]]},
        ),
        (
            '+++ "b/caf\\303\\251 \\"q\\".md"\n@@ -1 +1 @@\n-a\n+b\n',
            {'café "q".md': [[1, 1]]},
        ),
        (f"+++ b/a.md\n@@ -1 +1 @@\n-a\n{NO_NEWLINE}+b\n", {"a.md": [[1, 1]]}),
    ],
)
def test_parse_well_formed_patches(patch: str, expected: dict[str, list[list[int]]]) -> None:
    assert mod._parse_unified_zero(patch) == expected


@pytest.mark.parametrize(
    "patch",
    [
        "+++ b/a.md\n@@ -1,0 +1,5 @@\n+one\n+two\n",
        "+++ b/a.md\n@@ -1,0 +1,2 @@\n+one\nstray\n+two\n",
        "+++ b/a.md\n@@ nonsense @@\n",
        "+++ b/a.md\n",
    ],
)
def test_parse_inconsistent_patch_fails_closed(patch: str) -> None:
    assert mod._parse_unified_zero(patch) == WHOLE


def test_hunk_outside_any_file_section_is_rejected() -> None:
    with pytest.raises(ValueError):
        mod._parse_unified_zero("@@ -1 +1 @@\n-a\n+b\n")


def test_claim_overlap_edges() -> None:
    claim = {"line": 10, "end_line": 12, "type": "code_example"}
    assert mod._claim_in_ranges(claim, [[12, 12]])
    assert mod._claim_in_ranges(claim, [[8, 10]])
    assert not mod._claim_in_ranges(claim, [[13, 20]])
    assert not mod._claim_in_ranges(claim, [])


def test_check_gate_never_blocks_on_info() -> None:
    data = {"status": "COMPLETED", "findings": [{"severity": "info"}]}
    for threshold in ("critical", "high", "medium", "low"):
        result = mod.check_gate(data, threshold)
        assert result["verdict"] == "PASS"
        assert result["by_severity"] == {"info": 1}


def test_assessment_has_no_changed_lines_without_diff_base(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"doc.md": "# T\n"})
    assert mod.run_assessment(repo)["changed_lines"] is None


def test_path_normalization_matches_git_and_claim_spellings() -> None:
    assert mod._norm_path("./docs//a.md") == "docs/a.md"
    expected = "docs/a.md" if os.sep == "\\" else "docs\\a.md"
    assert mod._norm_path("docs\\a.md") == expected
    assert mod._parse_unified_zero("+++ b/./a.md\n@@ -1 +1 @@\n-a\n+b\n") == {"a.md": [[1, 1]]}
