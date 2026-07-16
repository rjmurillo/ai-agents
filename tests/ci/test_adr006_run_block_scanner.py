"""Tests for the ADR-006 run-block scanner (#3084)."""

from __future__ import annotations

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


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
