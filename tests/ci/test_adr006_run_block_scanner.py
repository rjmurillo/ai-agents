"""Tests for the ADR-006 run-block scanner (#3084)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from scripts.ci import adr006_run_block_scanner as scanner


def _big_logic_run() -> str:
    body = "\n".join(f"          echo line {i}" for i in range(12))
    return textwrap.dedent(
        """\
        jobs:
          build:
            steps:
              - run: |
                  if [ -n "$X" ]; then
        """
    ) + body + "\n"


def test_detects_large_logic_block_as_violation():
    blocks = scanner.scan_text(_big_logic_run())
    assert len(blocks) == 1
    block = blocks[0]
    assert block.has_logic is True
    assert block.code_lines > scanner._DEFAULT_THRESHOLD
    assert scanner.is_violation(block, scanner._DEFAULT_THRESHOLD) is True


def test_small_logic_block_is_not_a_violation():
    text = textwrap.dedent(
        """\
        steps:
          - run: |
              if [ -n "$X" ]; then
                echo hi
              fi
        """
    )
    block = scanner.scan_text(text)[0]
    assert block.has_logic is True
    assert scanner.is_violation(block, scanner._DEFAULT_THRESHOLD) is False


def test_large_block_without_logic_is_not_a_violation():
    body = "\n".join(f"      echo plain {i}" for i in range(15))
    text = "steps:\n  - run: |\n" + body + "\n"
    block = scanner.scan_text(text)[0]
    assert block.code_lines > scanner._DEFAULT_THRESHOLD
    assert block.has_logic is False
    assert scanner.is_violation(block, scanner._DEFAULT_THRESHOLD) is False


def test_inline_run_without_block_scalar_is_ignored():
    text = "steps:\n  - run: echo hello world\n"
    assert scanner.scan_text(text) == []


def test_comments_and_blanks_are_not_counted():
    text = textwrap.dedent(
        """\
        steps:
          - run: |
              # a comment
              echo real

              # another comment
              echo real2
        """
    )
    block = scanner.scan_text(text)[0]
    assert block.code_lines == 2


def test_line_number_points_at_run_key():
    text = "steps:\n  - name: x\n  - run: |\n      echo hi\n"
    block = scanner.scan_text(text)[0]
    assert block.line == 3


def test_output_assembly_counts_as_logic():
    text = 'steps:\n  - run: |\n      echo "k=v" >> "$GITHUB_OUTPUT"\n'
    assert scanner.scan_text(text)[0].has_logic is True


def test_variable_assignment_counts_as_logic():
    text = "steps:\n  - run: |\n      FOO=bar\n      echo done\n"
    assert scanner.scan_text(text)[0].has_logic is True


def test_gate_mode_exits_over_max(tmp_path: Path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "x.yml").write_text(_big_logic_run(), encoding="utf-8")
    assert scanner.main(["--root", str(tmp_path), "--max", "0"]) == scanner.EXIT_OVER_MAX
    assert scanner.main(["--root", str(tmp_path), "--max", "5"]) == scanner.EXIT_OK


def test_bad_root_is_config_error(tmp_path: Path):
    assert scanner.main(["--root", str(tmp_path / "absent")]) == scanner.EXIT_CONFIG


def test_json_output_emits_threshold_count_and_violations(tmp_path: Path, capsys):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "x.yml").write_text(_big_logic_run(), encoding="utf-8")

    exit_code = scanner.main(["--root", str(tmp_path), "--format", "json"])

    assert exit_code == scanner.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["threshold"] == scanner._DEFAULT_THRESHOLD
    assert payload["count"] == 1
    violation = payload["violations"][0]
    assert violation["file"].endswith("x.yml")
    assert violation["code_lines"] > scanner._DEFAULT_THRESHOLD


# Parse block modeled on .github/actions/ai-review/action.yml (verdict/labels/
# milestone extraction, lines 680-769), a #2967-listed ADR-006 offender: sed
# and python3 parsing pipes, computed variables, a case dispatch, and
# GITHUB_OUTPUT assembly. sed patterns trimmed to fit the line-length limit;
# the logic markers the scanner keys on are preserved.
_AI_REVIEW_PARSE_BLOCK = textwrap.dedent(
    r"""
    steps:
      - run: |
          output=$(cat /tmp/ai-review-output.txt 2>/dev/null || echo "")
          verdict=$(echo "$output" | sed -n 's/.*VERDICT: *\([A-Z_]*\).*/\1/p' | tail -n 1)
          if [ -z "$verdict" ]; then
            verdict=$(printf '%s' "$output" | python3 -c 'import sys; print(sys.stdin.read())')
          fi
          case "$verdict" in
            PASS|WARN|CRITICAL_FAIL)
              ;;
            *)
              verdict="NEEDS_REVIEW"
              ;;
          esac
          labels_raw=$(echo "$output" | sed -n 's/.*LABEL: *\(.*\)/\1/p' | tr '\n' ',')
          milestone=$(echo "$output" | sed -n 's/.*MILESTONE: *\(.*\)/\1/p' | head -1)
          echo "verdict=$verdict" >> "$GITHUB_OUTPUT"
          echo "labels=$labels_raw" >> "$GITHUB_OUTPUT"
          echo "milestone=$milestone" >> "$GITHUB_OUTPUT"
    """
)


def test_known_violating_parse_block_is_flagged():
    block = scanner.scan_text(_AI_REVIEW_PARSE_BLOCK)[0]
    assert block.has_logic is True
    assert block.code_lines > scanner._DEFAULT_THRESHOLD
    assert scanner.is_violation(block, scanner._DEFAULT_THRESHOLD) is True


def test_large_pure_output_block_is_not_flagged():
    body = "\n".join(f'          echo "line {i}"' for i in range(8))
    body += "\n" + "\n".join(f'          printf "%s\\n" "value {i}"' for i in range(6))
    text = "steps:\n  - run: |\n" + body + "\n"

    block = scanner.scan_text(text)[0]

    assert block.code_lines > scanner._DEFAULT_THRESHOLD
    assert block.has_logic is False
    assert scanner.is_violation(block, scanner._DEFAULT_THRESHOLD) is False


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_block(*lines: str) -> scanner.RunBlock:
    """Build a single run: block from body lines and scan it."""
    body = "\n".join(f"          {line}" for line in lines)
    return scanner.scan_text("steps:\n  - run: |\n" + body + "\n")[0]


class TestProseInOutputCommandsIsNotLogic:
    """English words in a remediation message are not shell keywords.

    ``_LOGIC`` matches ``if``/``for``/``while`` by word boundary. Remediation
    text says things like "Use forward slashes (/) for cross-platform
    compatibility", so a block of pure ``echo`` lines was reported as business
    logic in YAML. Six live blocks were flagged on the words "for" and "if"
    alone. The scanner's own contract already says a pure output block is not
    a violation; these tests pin the fix that makes that true for real prose.
    """

    def test_prose_containing_shell_keywords_is_not_logic(self) -> None:
        """Positive: the bug. Every keyword appears only as English."""
        block = _run_block(
            *(
                f'echo "  {i}. Use forward slashes for cross-platform work"'
                for i in range(8)
            ),
            'echo "Check if the file exists, then retry while it is locked"',
            'echo "Handle the case where the path is absolute"',
            'echo "Review each violation for correctness"',
            'echo "See the docs for guidance"',
        )
        assert block.code_lines > scanner._DEFAULT_THRESHOLD
        assert block.has_logic is False
        assert scanner.is_violation(block, scanner._DEFAULT_THRESHOLD) is False

    def test_real_conditional_beside_prose_is_still_logic(self) -> None:
        """Negative: blanking the message must not hide adjacent shell."""
        block = _run_block(
            *(f'echo "line {i} for the reader"' for i in range(11)),
            'if [ -f out.txt ]; then exit 1; fi',
        )
        assert block.has_logic is True

    def test_command_substitution_inside_quotes_is_still_logic(self) -> None:
        """Negative: a quoted operand that evaluates is not message text."""
        block = _run_block(
            *(f'echo "plain {i}"' for i in range(11)),
            'echo "$(gh pr list --json number)"',
        )
        assert block.has_logic is True

    def test_parameter_expansion_inside_quotes_is_still_logic(self) -> None:
        """Negative: ``${VAR}`` keeps the operand intact."""
        block = _run_block(
            *(f'echo "plain {i}"' for i in range(11)),
            'echo "issue ${ISSUE_NUMBER} for triage" >> notes.txt',
            'RESULT=1',
        )
        assert block.has_logic is True

    def test_redirect_outside_the_quotes_is_still_logic(self) -> None:
        """Negative: only the quoted text is blanked, never the redirect.

        This is the live ``copilot-context-synthesis.yml`` shape: pure echo
        lines that assemble the job summary. Output assembly is a deliberate
        ``_LOGIC`` marker and must survive.
        """
        block = _run_block(
            *(f'echo "summary line {i}" >> $GITHUB_STEP_SUMMARY' for i in range(12)),
        )
        assert block.has_logic is True

    def test_pipe_outside_the_quotes_is_still_logic(self) -> None:
        """Negative: a parsing pipe after the message still counts."""
        block = _run_block(
            *(f'echo "plain {i}"' for i in range(11)),
            'echo "payload" | jq .',
        )
        assert block.has_logic is True

    def test_escaped_quote_does_not_end_the_operand_early(self) -> None:
        """Edge: a backslash-escaped quote stays inside the message."""
        stripped = scanner._strip_static_output(r'echo "a \" for b"')
        assert "for" not in stripped

    def test_escaped_backtick_is_message_text_not_substitution(self) -> None:
        """Edge: escaped backticks are literal, so the operand is blanked."""
        stripped = scanner._strip_static_output(r'echo "share the same \`id\` for now"')
        assert "for" not in stripped

    def test_unescaped_backtick_keeps_the_operand(self) -> None:
        """Edge: a live backtick substitution is not message text."""
        line = 'echo "result `date` for now"'
        assert scanner._strip_static_output(line) == line

    def test_non_output_commands_are_untouched(self) -> None:
        """Edge: only echo and printf are treated as message carriers."""
        line = 'grep "search for this" file.txt'
        assert scanner._strip_static_output(line) == line

    def test_printf_operands_are_blanked_too(self) -> None:
        """Edge: printf carries message text the same way echo does."""
        stripped = scanner._strip_static_output(r'printf "%s\n" "retry for me"')
        assert "for" not in stripped

    def test_the_four_remediation_workflows_are_clean(self) -> None:
        """Edge: the live blocks this fix clears report no violation.

        These four workflows carry exactly one flagged block each, and each is
        a static remediation message. They are the reason issues #3535, #3545,
        #3546, and #3549 were filed; the extraction those issues ask for would
        move help text into a script for no benefit.
        """
        for name in (
            "validate-paths.yml",
            "validate-planning-artifacts.yml",
            "validate-spec-id-uniqueness.yml",
            "validate-vendor-portability.yml",
        ):
            path = REPO_ROOT / ".github" / "workflows" / name
            violations = [
                block
                for block in scanner.scan_text(path.read_text(encoding="utf-8"))
                if scanner.is_violation(block, scanner._DEFAULT_THRESHOLD)
            ]
            assert violations == [], name


# A trailing shell line continuation: one space and one backslash.
_CONT = " \\"
# ``printf`` with a literal backslash-n in its format, not a real newline.
_PRINTF = "printf '%s\\n'"


class TestContinuedMessageLists:
    """A message list spanning lines is still a message list.

    ``_STATIC_OUTPUT_CMD`` keys on the leading command, so operands that
    continue on following lines never reached the stripper.
    ``validate-adr-number-uniqueness.yml`` is flagged on exactly that shape:
    bare quoted prose lines under a ``printf`` continuation.
    """

    def test_prose_on_a_continuation_line_is_not_logic(self) -> None:
        """Positive: operands of a continued printf are message text."""
        block = _run_block(
            _PRINTF + _CONT,
            *(
                f'  "Renumber {i} if a collision is found for it."' + _CONT
                for i in range(11)
            ),
            '  "Numbers are assigned for each ADR."',
        )
        assert block.code_lines > scanner._DEFAULT_THRESHOLD
        assert block.has_logic is False

    def test_a_non_output_command_does_not_carry_continuation(self) -> None:
        """Negative: only echo and printf start a message list."""
        block = _run_block(
            "jq -r '.x'" + _CONT,
            '  --arg mode "run for each item"' + _CONT,
            "  input.json",
        )
        assert block.has_logic is True

    def test_continuation_ends_at_the_first_unbroken_line(self) -> None:
        """Negative: a line after the list ends is scanned normally.

        The following ``grep`` is not a message carrier, so its operand keeps
        its keyword (the contract pinned by
        ``test_non_output_commands_are_untouched``). If continuation state
        never ended, that operand would be blanked and the block would read
        as pure output.
        """
        block = _run_block(
            _PRINTF + _CONT,
            '  "a message"',
            'grep "search for this" file.txt',
        )
        assert block.has_logic is True

    def test_a_substitution_on_a_continuation_line_still_evaluates(self) -> None:
        """Edge: continuation does not blank an operand that can evaluate."""
        block = _run_block(
            _PRINTF + _CONT,
            '  "$(gh pr list --json number)"',
        )
        assert block.has_logic is True

    def test_the_continued_message_workflow_is_clean(self) -> None:
        """Edge: the live block this fix clears reports no violation."""
        path = REPO_ROOT / ".github" / "workflows" / "validate-adr-number-uniqueness.yml"
        violations = [
            block
            for block in scanner.scan_text(path.read_text(encoding="utf-8"))
            if scanner.is_violation(block, scanner._DEFAULT_THRESHOLD)
        ]
        assert violations == []


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
