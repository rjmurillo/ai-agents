"""Regression guard: escaped pipe (``\\|``) inside a markdown table cell.

An escaped pipe in a table-cell shell command (e.g. ``grep "A\\|B"``) reaches
the cell content intact and can mask the preceding command's exit code, because
the shell sees two separate commands joined by the pipe. PR #4037 fixed a batch
of these; this guard prevents recurrence.

Scope: all ``.md`` files under ``.claude/skills/`` and
``src/copilot-cli/skills/`` (the canonical skill tree and its generated mirror).

False-positive cases that must NOT fire (tested explicitly below):
- ``\\|`` inside a fenced code block
- A line that is a markdown table delimiter row (``| --- | --- |``)
- A non-table prose line containing ``\\|``

This test is collected by default pytest (``testpaths = ["tests"]`` in
``pyproject.toml``). The sibling test in
``.claude/skills/ai-agents-docs-of-record/tests/`` checks only one skill's
provenance table; this guard covers the full skill tree.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent


def _is_fenced_boundary(line: str) -> bool:
    return bool(re.match(r"^[`~]{3}", line.strip()))


def _is_table_delimiter_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    return bool(re.match(r"^\|[\s\-:|]+\|[\s\-:|]*$", stripped))


def _is_table_data_row(line: str) -> bool:
    return line.strip().startswith("|") and not _is_table_delimiter_row(line)


def _scan_skill_files() -> list[Path]:
    """Collect all Markdown files in skill directories."""
    files = []
    for root in (
        _REPO_ROOT / ".claude" / "skills",
        _REPO_ROOT / "src" / "copilot-cli" / "skills",
    ):
        if root.is_dir():
            files.extend(root.rglob("*.md"))
    return files


def _find_escaped_pipe_rows(files: list[Path]) -> list[str]:
    """Return ``path:lineno: content`` for each table row containing ``\\|``
    used as a shell pipe operator inside a backtick code span.

    Distinguishes two uses of ``\\|`` in markdown tables:
    - Shell pipe: ``\\|`` followed by a shell command word (``grep``, ``wc``,
      ``cut``, ``head``, ``tail``, ``awk``, ``sort``, ``uniq``, ``sed``,
      ``xargs``, ``tee``) -- this is the DEFECT.
    - Type annotation display: ``str \\| None``, ``list \\| None`` etc. --
      this is a LEGITIMATE escape to prevent the literal pipe from being
      treated as a table separator.

    Only the shell-pipe form is flagged; the type-annotation form is excluded.
    """
    # Shell commands that legitimately appear after a pipe operator
    _SHELL_CMDS = re.compile(
        r"\\[|]\s*(?:grep|wc|cut|head|tail|awk|sort|uniq|sed|xargs|tee|cat"
        r"|find|ls|echo|python3?|uv|git|gh|diff|comm)"
    )
    violations: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if _is_fenced_boundary(line):
                in_fence = not in_fence
            if in_fence:
                continue
            if not _is_table_data_row(line):
                continue
            # Check for \\| used as shell pipe inside a backtick span
            for match in re.finditer(r"`([^`]*)`", line):
                if _SHELL_CMDS.search(match.group(1)):
                    try:
                        rel = path.relative_to(_REPO_ROOT).as_posix()
                    except ValueError:
                        rel = str(path)
                    violations.append(f"{rel}:{lineno}: {line.rstrip()[:80]}")
                    break
    return violations


# ---------------------------------------------------------------------------
# Parser helper unit tests
# ---------------------------------------------------------------------------


class TestIsFencedBoundary:
    def test_backtick_fence(self) -> None:
        assert _is_fenced_boundary("```bash")

    def test_tilde_fence(self) -> None:
        assert _is_fenced_boundary("~~~")

    def test_non_fence(self) -> None:
        assert not _is_fenced_boundary("| foo | bar |")


class TestIsTableDelimiterRow:
    def test_standard(self) -> None:
        assert _is_table_delimiter_row("| --- | --- |")

    def test_aligned(self) -> None:
        assert _is_table_delimiter_row("| :--- | ---: |")

    def test_data_row(self) -> None:
        assert not _is_table_delimiter_row("| foo | bar |")

    def test_prose(self) -> None:
        assert not _is_table_delimiter_row("Some prose here")


class TestEscapedPipeInFencedBlock:
    """False-positive control: escaped pipe inside a fence must not fire."""

    def test_fenced_block_not_flagged(self, tmp_path: Path) -> None:
        md = tmp_path / "fenced.md"
        md.write_text(
            "```bash\n"
            '| grep "A\\|B" file\n'
            "```\n"
        )
        assert _find_escaped_pipe_rows([md]) == []


class TestEscapedPipeInProseNotFlagged:
    """A ``\\|`` outside a table row is not the defect."""

    def test_prose_line_not_flagged(self, tmp_path: Path) -> None:
        md = tmp_path / "prose.md"
        md.write_text('Run `grep "A\\|B"` to see matches.\n')
        assert _find_escaped_pipe_rows([md]) == []


class TestEscapedPipeInTableRowDetected:
    """Positive cases: escaped pipe in a table data row fires."""

    def test_escaped_pipe_in_cell_detected(self, tmp_path: Path) -> None:
        md = tmp_path / "bad.md"
        md.write_text(
            "| Step | Command |\n"
            "| --- | --- |\n"
            "| Count | `ls .serena/memories/ \\| wc -l` |\n"
        )
        violations = _find_escaped_pipe_rows([md])
        assert len(violations) == 1
        assert "bad.md" in violations[0]

    def test_clean_table_not_flagged(self, tmp_path: Path) -> None:
        md = tmp_path / "clean.md"
        md.write_text(
            "| Step | Command |\n"
            "| --- | --- |\n"
            "| Count | `git grep -c -e foo -e bar .` |\n"
        )
        assert _find_escaped_pipe_rows([md]) == []


# ---------------------------------------------------------------------------
# Repo-wide regression guard
# ---------------------------------------------------------------------------


def test_no_escaped_pipes_in_skill_table_rows() -> None:
    """No skill Markdown file has an escaped pipe (``\\|``) in a table row.

    An escaped pipe in a table-cell shell command can mask the preceding
    command's exit code. PR #4037 fixed a batch; this guard prevents
    recurrence.

    False positives correctly excluded:
    - ``\\|`` inside fenced code blocks
    - Prose lines (not table rows)
    - The table delimiter row (``| --- | --- |``)

    If this test fails, fix by rewriting the command to avoid ``\\|``:
    use ``grep -e pattern1 -e pattern2`` or ``set -- ...; echo $#`` instead.
    """
    files = _scan_skill_files()
    violations = _find_escaped_pipe_rows(files)
    assert violations == [], (
        f"{len(violations)} escaped pipe(s) found in skill table rows:\n"
        + "\n".join(violations[:20])
    )
