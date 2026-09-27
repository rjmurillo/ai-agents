"""Shared fixture builders for the split ``test_effective_context_*`` suites.

Not a test module itself (leading underscore, matching ``_adr_debate_repo.py``
in this directory): pytest does not collect it. ``_write``,
``_build_claude_copilot_tree``, ``_init_git_repo``, ``_commit_all``, and
``FakeCompletedProcess`` are each used by more than one of
``test_effective_context.py``, ``test_effective_context_ratchet.py``,
``test_effective_context_sources.py``, ``test_effective_context_claude.py``,
and ``test_effective_context_copilot.py`` (the split of the original,
1196-line ``test_effective_context.py``, issue #4880 taste-lints follow-up),
so they live once here rather than duplicated per file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _write(root: Path, rel_path: str, content: str) -> int:
    """Write a UTF-8 text file and return its byte length."""
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def _build_claude_copilot_tree(root: Path) -> dict[str, int]:
    """A small tree exercising every Claude/Copilot layer for one target.

    Target: ``a/b/target.py``. Returns the byte length of every file written,
    keyed by its repo-relative path, so tests can assert exact totals.
    """
    sizes: dict[str, int] = {}
    sizes["CLAUDE.md"] = _write(root, "CLAUDE.md", "# root\n\n@AGENTS.md\n")
    sizes["AGENTS.md"] = _write(root, "AGENTS.md", "root agents body\n")
    sizes[".claude/CLAUDE.md"] = _write(root, ".claude/CLAUDE.md", "dot-claude root\n")
    sizes["a/CLAUDE.md"] = _write(root, "a/CLAUDE.md", "@AGENTS.md\n")
    sizes["a/AGENTS.md"] = _write(root, "a/AGENTS.md", "a-level agents\n")
    # a/b has no CLAUDE.md: nested layer for Claude stops growing there.
    sizes[".claude/rules/always.md"] = _write(
        root, ".claude/rules/always.md", "no frontmatter\nalways loaded\n"
    )
    sizes[".claude/rules/scoped.md"] = _write(
        root,
        ".claude/rules/scoped.md",
        '---\npaths:\n  - "**/*.py"\n---\n\nscoped to python\n',
    )
    sizes[".claude/rules/other.md"] = _write(
        root,
        ".claude/rules/other.md",
        '---\npaths:\n  - "**/*.cs"\n---\n\nscoped to csharp, should not match\n',
    )
    sizes[".github/copilot-instructions.md"] = _write(
        root, ".github/copilot-instructions.md", "copilot repo instructions\n"
    )
    sizes[".github/instructions/scoped.instructions.md"] = _write(
        root,
        ".github/instructions/scoped.instructions.md",
        '---\napplyTo: "**/*.py"\n---\n\nscoped to python\n',
    )
    sizes[".github/instructions/other.instructions.md"] = _write(
        root,
        ".github/instructions/other.instructions.md",
        '---\napplyTo: "**/*.cs"\n---\n\nscoped to csharp, should not match\n',
    )
    (root / "a" / "b").mkdir(parents=True, exist_ok=True)
    (root / "a" / "b" / "target.py").write_text("print('hi')\n", encoding="utf-8")
    return sizes


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def _commit_all(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", message], cwd=root, check=True)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


class FakeCompletedProcess:
    """Stand-in for `subprocess.CompletedProcess`, for stubbing `copilot`.

    Used by both the ratchet/observe suite and the CLI suite to fake
    `copilot instruction list --json` without a live binary.
    """

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
