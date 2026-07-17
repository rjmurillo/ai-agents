"""Fail-closed hardening tests for freeform ``apply_patch`` gating (issue #3203).

The adversarial review of the #3203 fix flagged a parser-differential risk: a
patch that mixes a well-formed header with a malformed one had its malformed
line silently skipped, so a benign header could let the whole patch through
while an unrecognized ``***`` structural line went ungated. These tests pin the
fail-closed contract and cover the move-destination and mixed-operation paths
the original suite did not exercise end to end.
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / ".claude" / "hooks" / "PreToolUse"))
sys.path.insert(0, str(_project_root))

from invoke_security_gate import (  # noqa: E402
    extract_patch_paths,
    gate_freeform_patch,
    main,
    malformed_structural_lines,
)


class TestMalformedStructuralLines:
    """Unit tests for the column-0 malformed-marker detector."""

    def test_well_formed_patch_has_no_malformed_lines(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Add File: probe.txt\n"
            "+content\n"
            "*** Update File: src/app.py\n"
            "@@\n-a\n+b\n"
            "*** Move to: src/app2.py\n"
            "*** Delete File: old.md\n"
            "*** End Patch\n"
        )
        assert malformed_structural_lines(patch) == []

    def test_missing_space_after_stars_is_malformed(self) -> None:
        # The reviewer's exact example: ``***Update File:`` (no space) is not a
        # recognized header, so the parser cannot attribute a path to it.
        patch = (
            "*** Begin Patch\n"
            "*** Add File: probe.txt\n"
            "+probe\n"
            "***Update File: src/auth/login.py\n"
            "@@\n-old\n+new\n"
            "*** End Patch\n"
        )
        assert malformed_structural_lines(patch) == ["***Update File: src/auth/login.py"]

    def test_unknown_keyword_is_malformed(self) -> None:
        assert malformed_structural_lines("*** Rename File: a -> b\n") == [
            "*** Rename File: a -> b"
        ]

    def test_empty_path_header_is_malformed(self) -> None:
        # ``*** Add File:`` with no path names no file: it cannot be gated.
        assert malformed_structural_lines("*** Add File:\n") == ["*** Add File:"]

    def test_indented_content_starting_with_stars_is_not_malformed(self) -> None:
        # A Markdown horizontal rule inside an Update hunk appears as a context
        # line ``" ***"`` (leading diff-prefix space) or an added line
        # ``"+***"``. Neither sits at column 0, so neither is a structural
        # marker and neither may be flagged (would false-block legit patches).
        patch = (
            "*** Begin Patch\n"
            "*** Update File: README.md\n"
            "@@\n"
            " ***\n"       # context line: a Markdown horizontal rule
            "+*** New\n"   # added line whose content begins with ***
            "-*** Old\n"   # removed line whose content begins with ***
            "*** End Patch\n"
        )
        assert malformed_structural_lines(patch) == []

    def test_non_patch_string_has_no_structural_lines(self) -> None:
        assert malformed_structural_lines("just a random string") == []

    def test_context_line_with_file_header_content_not_extracted_as_path(self) -> None:
        # A context line (leading space) whose content looks like a file header
        # must not be extracted as a touched path. The ``***`` keyword sits at
        # column 1 (not column 0), so it is diff content, not a structural marker.
        # This regression test pins the column-0 anchor fix for issue #3203
        # adversarial review: ``_PATCH_FILE_HEADER`` must use ``^\*\*\*``, not
        # ``^\s*\*\*\*``, so context lines cannot spoof file headers.
        patch = (
            "*** Begin Patch\n"
            "*** Update File: docs/readme.md\n"
            "@@\n"
            " *** Update File: src/auth/login.ts\n"  # context line, not a header
            "+new content\n"
            "*** End Patch\n"
        )
        paths = extract_patch_paths(patch)
        assert paths == ["docs/readme.md"]
        assert "src/auth/login.ts" not in paths


class TestGateFreeformPatchFailClosed:
    """``gate_freeform_patch`` fails closed on a malformed column-0 ``***`` header.

    "Malformed" is scoped to a column-0 ``***`` structural line that matches
    neither a well-formed file header nor ``*** Begin/End Patch``; the gate
    cannot attribute a path to it, so it blocks (exit 2).
    """

    def test_partial_parse_fails_closed(self, capsys: pytest.CaptureFixture[str]) -> None:
        # A benign ``Add File`` header must not let a malformed auth header ride
        # through ungated. The whole patch fails closed (exit 2).
        patch = (
            "*** Begin Patch\n"
            "*** Add File: probe.txt\n"
            "+probe\n"
            "***Update File: src/auth/login.py\n"
            "@@\n-old\n+new\n"
            "*** End Patch\n"
        )
        assert gate_freeform_patch(patch) == 2
        assert "Security Gate Error" in capsys.readouterr().out

    def test_whitespace_only_path_fails_closed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A file header with a whitespace-only path is not well-formed: no path
        # can be attributed, so it must fail closed instead of being silently
        # skipped (issue #3203 adversarial review).
        patch = (
            "*** Begin Patch\n"
            "*** Add File:   \n"
            "+probe\n"
            "*** End Patch\n"
        )
        assert gate_freeform_patch(patch) == 2
        assert "Security Gate Error" in capsys.readouterr().out


class TestMainFreeformFailClosed:
    """End-to-end ``main()`` coverage for the hardened fail-closed paths."""

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_main_fails_closed_on_partial_parse(
        self, mock_stdin: StringIO, capsys: pytest.CaptureFixture[str]
    ) -> None:
        patch_text = (
            "*** Begin Patch\n"
            "*** Add File: probe.txt\n"
            "+probe\n"
            "***Update File: src/auth/login.py\n"
            "@@\n-old\n+new\n"
            "*** End Patch\n"
        )
        hook_input = {"tool_name": "Edit", "tool_input": patch_text}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        assert "Security Gate Error" in capsys.readouterr().out

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_main_blocks_mixed_benign_and_auth_operations(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # One benign add plus one auth update in the same patch: the auth path
        # is gated even though a benign path precedes it.
        patch_text = (
            "*** Begin Patch\n"
            "*** Add File: docs/readme.md\n"
            "+hello\n"
            "*** Update File: src/auth/login.ts\n"
            "@@\n-a\n+b\n"
            "*** End Patch\n"
        )
        hook_input = {"tool_name": "Edit", "tool_input": patch_text}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        assert "Security Review Required" in capsys.readouterr().out

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_main_blocks_non_auth_file_moved_into_auth_path(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # The source file is non-auth, but the ``Move to`` destination lands in
        # an auth directory: the destination path must be gated.
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: src/util/helpers.ts\n"
            "*** Move to: src/auth/helpers.ts\n"
            "*** End Patch\n"
        )
        hook_input = {"tool_name": "Edit", "tool_input": patch_text}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        assert "src/auth/helpers.ts" in capsys.readouterr().out
