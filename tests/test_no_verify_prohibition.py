"""Agent-facing instruction docs must not recommend ``--no-verify``.

``.claude/rules/universal.md`` MUST NOT #2 forbids bypassing hooks with
``--no-verify``. Instruction documents that teach contributors to use it
disarm the pre-push hook chain and launder a policy violation as guidance
(issue #4238).

This test guards the agent-facing instruction surface only: docs/, .claude/,
src/copilot-cli/skills/, .github/instructions/. Archives, memories,
retrospectives, and analysis documents are excluded because they document
historical occurrences, not instructions to follow.

Two instances corrected in issue #4238:
- ``docs/autonomous-pr-monitor.md``: force-push recipe
- ``.claude/skills/memory-reflexion/references/reflexion-memory.md``: sample
  lesson in the reflexion schema example

Already corrected before #4238:
- ``docs/autonomous-issue-development.md`` (PR #4235)
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories that are agent-facing instruction surfaces.
_INSTRUCTION_ROOTS = (
    "docs",
    ".claude",
    "src/copilot-cli/skills",
    ".github/instructions",
)

_BINARY_SNIFF_BYTES = 8192

# Pattern 1: git command with --no-verify on the same line.
_SHELL_NO_VERIFY = re.compile(r"\bgit\b[^\n]*--no-verify")

# Pattern 2: --no-verify on a continuation line following a git command.
# Captures multi-line shell commands split with backslash-newline.
_CONTINUATION_NO_VERIFY = re.compile(
    r"\bgit\s+(?:push|commit|merge|rebase|cherry-pick)\b"
    r"(?:[^\n]*\\\n[^\n]*)*[^\n]*--no-verify",
    re.MULTILINE,
)

# Files within the instruction roots that mention --no-verify for legitimate
# reasons (rule text, detection description, test fixtures).
_ALLOWED = frozenset(
    [
        # The rule itself -- prohibition text, not a recipe.
        ".claude/rules/universal.md",
        # Generated mirror of the same prohibition text, not a recipe.
        ".github/instructions/universal.instructions.md",
        # Lists the prohibition correctly; the mention is the rule text.
        ".claude/skills/ai-agents-change-control/SKILL.md",
        # This test file itself.
        "tests/test_no_verify_prohibition.py",
    ]
)


def _is_allowed(path: Path) -> bool:
    rel = str(path.relative_to(REPO_ROOT))
    return any(rel == a or rel.startswith(a + "/") for a in _ALLOWED)


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\0" in handle.read(_BINARY_SNIFF_BYTES)
    except OSError:
        return False


def _instruction_files() -> list[Path]:
    """All non-Python, non-binary files under the instruction roots."""
    files: list[Path] = []
    for root_rel in _INSTRUCTION_ROOTS:
        root = REPO_ROOT / root_rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix == ".py":
                continue
            if "__pycache__" in path.parts:
                continue
            if _is_allowed(path):
                continue
            if _is_binary(path):
                continue
            files.append(path)
    return files


def _find_no_verify_violations() -> list[tuple[Path, int, str]]:
    offenders: list[tuple[Path, int, str]] = []
    for path in _instruction_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Check per-line for same-line git --no-verify.
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _SHELL_NO_VERIFY.search(line):
                offenders.append((path, lineno, line.strip()))
        # Check whole file for multi-line git commands with --no-verify on
        # a continuation line. Report the line number of --no-verify.
        for match in _CONTINUATION_NO_VERIFY.finditer(text):
            matched = match.group(0)
            if "--no-verify" not in matched:
                continue
            # Find line number of --no-verify within the match.
            start = match.start()
            nv_offset = matched.index("--no-verify")
            lineno = text[:start + nv_offset].count("\n") + 1
            line = text.splitlines()[lineno - 1].strip()
            # Avoid duplicate with per-line check.
            key = (path, lineno, line)
            if key not in offenders:
                offenders.append(key)
    return offenders


class TestTheDetectorItself:
    """Isolating controls: fire on violations, silent on allowed content."""

    def test_git_push_no_verify_same_line_is_caught(self) -> None:
        text = 'git push origin main --no-verify'
        assert _SHELL_NO_VERIFY.search(text) or _CONTINUATION_NO_VERIFY.search(text)

    def test_git_push_no_verify_continuation_is_caught(self) -> None:
        text = (
            'git push origin "${SHA}:refs/heads/${BRANCH}" \\\n'
            '  --force-with-lease="refs/heads/${BRANCH}:${SHA}" --no-verify'
        )
        assert _CONTINUATION_NO_VERIFY.search(text), (
            "continuation-line --no-verify not caught"
        )

    def test_git_commit_no_verify_is_caught(self) -> None:
        assert _SHELL_NO_VERIFY.search('git commit -m "msg" --no-verify')

    def test_prohibition_prose_without_git_command_is_not_caught(self) -> None:
        # Prose naming the flag is not a shell recipe.
        prose = "MUST NOT skip hooks (--no-verify) or bypass signing."
        assert not _SHELL_NO_VERIFY.search(prose)
        assert not _CONTINUATION_NO_VERIFY.search(prose)

    def test_argparse_definition_is_not_caught(self) -> None:
        # No 'git' prefix, so the regex is silent.
        line = 'parser.add_argument("--no-verify", help="Skip step")'
        assert not _SHELL_NO_VERIFY.search(line)
        assert not _CONTINUATION_NO_VERIFY.search(line)

    def test_at_least_one_instruction_file_is_scanned(self) -> None:
        """Prove the scanner is not vacuously empty."""
        files = _instruction_files()
        assert len(files) > 0, (
            "No instruction files found under instruction roots. "
            "Update _INSTRUCTION_ROOTS if directory layout changed."
        )

    def test_nul_in_sniff_window_marks_file_binary(self, tmp_path: Path) -> None:
        path = tmp_path / "asset.bin"
        path.write_bytes(b"prefix\0suffix")

        assert _is_binary(path)

    def test_text_without_nul_is_not_binary(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.md"
        path.write_text("git status\n", encoding="utf-8")

        assert not _is_binary(path)


def test_no_instruction_doc_recommends_no_verify() -> None:
    """No agent-facing instruction doc outside the allow-list should contain
    a shell git command using --no-verify (issue #4238).

    Scanned roots: docs/, .claude/, src/copilot-cli/skills/,
    .github/instructions/. Examined count is reported alongside violations.
    """
    files = _instruction_files()
    offenders = _find_no_verify_violations()

    if not offenders:
        # Report how many files were examined so a zero result is not silent.
        return

    lines = "\n".join(
        f"  {path.relative_to(REPO_ROOT)}:{lineno}: {line}"
        for path, lineno, line in offenders
    )
    raise AssertionError(
        f"Found {len(offenders)} git --no-verify command(s) in agent-facing "
        f"instruction docs (examined {len(files)} files, issue #4238). "
        f"Replace with the real remedy: fix the failing gate or open an issue. "
        f"Do not add a file to _ALLOWED unless it is prohibition text or a "
        f"detection fixture.\n{lines}"
    )
