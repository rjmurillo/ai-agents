"""Throwaway git repos and the three suppression-gate entry points.

The staged, push, and CI diff checks must give the same verdict. Tests run
one change through all three with ``ENTRY_POINTS``.

Directive tokens are assembled at runtime so the test files do not trip the
gate they exercise.
"""

from __future__ import annotations

import io
import subprocess
from collections.abc import Callable
from pathlib import Path

from scripts.validation import git_hook_policy as policy


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return its stripped stdout."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    ).stdout.strip()


def init_repo(tmp_path: Path) -> Path:
    """Create an empty repo that stores every byte as written."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "core.autocrlf", "false")
    # A global attributes file can still normalize line endings on add.
    (repo / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("* -text\n", encoding="utf-8")
    return repo


def write(repo: Path, path: str, body: str) -> None:
    """Write ``body`` to ``path`` inside ``repo``, creating parents."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="" keeps "\n" as written, so Windows does not add a CR.
    target.write_text(body, encoding="utf-8", newline="")


DIRECTIVE = "# " + "nosem" + "grep"
NOSEC = "# " + "nos" + "ec"
NOQA = "# " + "no" + "qa"
EXEC_RULE = (
    "python.lang.security.audit.dangerous-os-exec-tainted-env-args."
    "dangerous-os-exec-tainted-env-args"
)
SUBPROCESS_RULE = (
    "python.lang.security.audit.dangerous-subprocess-use-tainted-env-args."
    "dangerous-subprocess-use-tainted-env-args"
)
SOURCE = "src/claude/lib/ptk_run.py"
BASE_BODY = "import os\n\n\ndef launch(command):\n    os.execv(command[0], command)\n"


def allowed(rule: str, indent: str = "    ") -> str:
    """Return a whole-line directive that names ``rule``."""
    return f"{indent}{DIRECTIVE}: {rule}"


def body(directive_line: str) -> str:
    """Return ``BASE_BODY`` with ``directive_line`` above the exec call."""
    return (
        "import os\n\n\ndef launch(command):\n"
        f"{directive_line}\n"
        "    os.execv(command[0], command)\n"
    )


def repo_with_change(tmp_path: Path, path: str, directive_line: str) -> tuple[Path, str]:
    """Commit ``BASE_BODY`` at ``path``, then stage it with ``directive_line``."""
    repo = init_repo(tmp_path)
    write(repo, path, BASE_BODY)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    write(repo, path, body(directive_line))
    git(repo, "add", "-A")
    return repo, base


def _staged(repo: Path, _base: str) -> int:
    return policy.check_staged_suppressions(repo)


def _pushed(repo: Path, base: str) -> int:
    git(repo, "commit", "-q", "-m", "head")
    head = git(repo, "rev-parse", "HEAD")
    stream = io.StringIO(f"refs/heads/feature {head} refs/heads/feature {base}\n")
    return policy.check_pushed_suppressions(stream, repo)


def _ci_diff(repo: Path, base: str) -> int:
    git(repo, "commit", "-q", "-m", "head")
    return policy.check_suppression_diff(base, repo)


ENTRY_POINTS: list[Callable[[Path, str], int]] = [_staged, _pushed, _ci_diff]
ENTRY_IDS = ["staged", "push", "ci-diff"]
