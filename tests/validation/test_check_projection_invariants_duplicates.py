"""Duplicate-key and duplicate-row detection in check_projection_invariants (issue #6506).

Split from ``test_check_projection_invariants.py`` to keep both files under the
500-line limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
import check_projection_invariants as cpi

FM = "---\nname: x\nallowed-tools: {tools}\n---\nbody\n"
EXIT = "# T\n\n## Exit Codes\n\n| Code | Meaning |\n|---|---|\n{rows}\n\n## Next\n"


class TestCountAllowedToolsKeys:
    def test_one_key(self) -> None:
        assert cpi.count_allowed_tools_keys(FM.format(tools="Read")) == 1

    def test_repeated_key_counts_each(self) -> None:
        text = "---\nname: x\nallowed-tools: Read\nallowed-tools: Read, Bash\n---\nbody\n"
        assert cpi.count_allowed_tools_keys(text) == 2

    @pytest.mark.parametrize(
        "second_key",
        ['"allowed-tools":', "'allowed-tools':", "allowed-tools :", '"allowed-tools" :'],
    )
    def test_quoted_or_spaced_repeat_counts(self, second_key: str) -> None:
        text = f"---\nname: x\nallowed-tools: [Read]\n{second_key} [Read, Bash]\n---\nbody\n"
        assert cpi.count_allowed_tools_keys(text) == 2

    @pytest.mark.parametrize("key", ['"allowed-tools":', "'allowed-tools':", "allowed-tools :"])
    def test_quoted_or_spaced_single_key_counts_once(self, key: str) -> None:
        assert cpi.count_allowed_tools_keys(f"---\nname: x\n{key} Read\n---\n") == 1

    @pytest.mark.parametrize("key", ["\"allowed-tools':", "'allowed-tools\":", "xallowed-tools:"])
    def test_mismatched_quotes_and_prefixed_names_do_not_count(self, key: str) -> None:
        assert cpi.count_allowed_tools_keys(f"---\nname: x\n{key} Read\n---\n") == 0

    def test_none(self) -> None:
        assert cpi.count_allowed_tools_keys("---\nname: x\n---\n") == 0

    def test_indented_key_and_body_key_do_not_count(self) -> None:
        text = (
            "---\nname: x\nmeta:\n  allowed-tools: Bash\nallowed-tools: Read\n---\n"
            "allowed-tools: Bash\n"
        )
        assert cpi.count_allowed_tools_keys(text) == 1


class TestExitCodeDuplicates:
    def test_clean_table(self) -> None:
        assert cpi.exit_code_duplicates(EXIT.format(rows="| 0 | ok |\n| 1 | err |")) == []

    def test_no_section(self) -> None:
        assert cpi.exit_code_duplicates("# T\n") == []

    def test_repeated_row(self) -> None:
        problems = cpi.exit_code_duplicates(EXIT.format(rows="| 0 | ok |\n| 0 | changed |"))
        assert problems == ["lists exit code 0 2 times"]

    def test_second_heading(self) -> None:
        text = EXIT.format(rows="| 0 | ok |") + "\n## Exit Codes\n\n| 1 | err |\n"
        assert cpi.exit_code_duplicates(text) == [
            "declares 2 Exit Codes sections; the comparison needs one"
        ]

    def test_second_heading_repeating_a_code_reports_both(self) -> None:
        text = EXIT.format(rows="| 0 | ok |") + "\n## exit codes\n\n| 0 | other |\n"
        assert len(cpi.exit_code_duplicates(text)) == 2
