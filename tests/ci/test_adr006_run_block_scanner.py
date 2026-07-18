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


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
