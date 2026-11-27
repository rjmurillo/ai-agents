"""The suppression gate keys the Semgrep allowlist on the exact file name.

A diff header path is read as git names the file. A decoy whose name differs
from a listed ptk_run.py copy only by spaces must not borrow that copy's entry.
Blob reads keep a lone carriage return, so one physical line stays one line.
"""

from __future__ import annotations

import io
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy

DIRECTIVE = "# " + "nosem" + "grep"  # assembled so this file does not trip its own gate
EXEC_RULE = (
    "python.lang.security.audit.dangerous-os-exec-tainted-env-args."
    "dangerous-os-exec-tainted-env-args"
)
SOURCE = "src/claude/lib/ptk_run.py"
ALLOWED_LINE = f"    {DIRECTIVE}: {EXEC_RULE}"
BASE_BODY = "import os\n\n\ndef launch(command):\n    os.execv(command[0], command)\n"
HEAD_BODY = (
    f"import os\n\n\ndef launch(command):\n{ALLOWED_LINE}\n    os.execv(command[0], command)\n"
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()


def _init(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "core.autocrlf", "false")
    # A global attributes file can still normalize line endings on add.
    (repo / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("* -text\n", encoding="utf-8")
    return repo


def _write(repo: Path, path: str, body: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def _repo_with_decoy(tmp_path: Path, decoy: str | None) -> tuple[Path, str]:
    repo = _init(tmp_path)
    _write(repo, SOURCE, BASE_BODY)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _write(repo, SOURCE, HEAD_BODY)
    if decoy is not None:
        _write(repo, decoy, HEAD_BODY)
    _git(repo, "add", "-A")
    return repo, base


def _staged(repo: Path, _base: str) -> int:
    return policy.check_staged_suppressions(repo)


def _pushed(repo: Path, base: str) -> int:
    _git(repo, "commit", "-q", "-m", "head")
    head = _git(repo, "rev-parse", "HEAD")
    stream = io.StringIO(f"refs/heads/feature {head} refs/heads/feature {base}\n")
    return policy.check_pushed_suppressions(stream, repo)


def _ci_diff(repo: Path, base: str) -> int:
    _git(repo, "commit", "-q", "-m", "head")
    return policy.check_suppression_diff(base, repo)


ENTRY_POINTS: list[Callable[[Path, str], int]] = [_staged, _pushed, _ci_diff]
ENTRY_IDS = ["staged", "push", "ci-diff"]


@pytest.mark.parametrize("entry_point", ENTRY_POINTS, ids=ENTRY_IDS)
@pytest.mark.parametrize(
    ("decoy", "expected"),
    [
        pytest.param(None, 0, id="real-copy-only"),
        pytest.param(" " + SOURCE, 1, id="leading-space"),
        pytest.param("  " + SOURCE, 1, id="two-spaces"),
    ],
)
def test_decoy_name_cannot_borrow_a_listed_entry(
    tmp_path: Path,
    entry_point: Callable[[Path, str], int],
    decoy: str | None,
    expected: int,
) -> None:
    repo, base = _repo_with_decoy(tmp_path, decoy)
    assert entry_point(repo, base) == expected


@pytest.mark.parametrize("name", [SOURCE + " ", " " + SOURCE + " ", "src\\claude\\lib\\ptk_run.py"])
def test_diff_keys_a_decoy_header_by_its_own_name(name: str) -> None:
    header = f"+++ b/{name}\t" if " " in name else f'+++ "b/{name.replace(chr(92), chr(92) * 2)}"'
    diff = f"diff --git a/x b/x\n--- /dev/null\n{header}\n@@ -0,0 +1 @@\n+{ALLOWED_LINE}\n"
    assert policy._suppression_violations_in_diff("f" * 40, diff) == [f"ffffffffffff:{name}:1"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("b/pkg/a.py", "pkg/a.py", id="plain"),
        pytest.param("b/ src/p.py\t", " src/p.py", id="space-tab"),
        pytest.param("b/tr.py \t", "tr.py ", id="trailing-space-tab"),
        pytest.param('"b/a\\\\b.py"', "a\\b.py", id="quoted-backslash"),
        pytest.param("/dev/null", None, id="deletion"),
    ],
)
def test_exact_header_path_keeps_the_name_git_reports(raw: str, expected: str | None) -> None:
    assert policy._exact_diff_header_path(raw) == expected


def test_git_writes_the_header_forms_the_parser_expects(tmp_path: Path) -> None:
    repo = _init(tmp_path)
    _write(repo, "seed", "seed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    for name in (" src/p.py", "tr.py ", "a\\b.py"):
        _write(repo, name, "x\n")
    _git(repo, "add", "-A")
    diff = _git(
        repo, "-c", "core.quotePath=false", "diff", "--cached", "--dst-prefix=b/", "--no-color"
    )
    headers = [line[4:] for line in diff.split("\n") if line.startswith("+++ ")]
    parsed = sorted(policy._exact_diff_header_path(header) for header in headers)
    assert parsed == sorted([" src/p.py", "tr.py ", "a\\b.py"])


def test_blob_readers_keep_a_lone_carriage_return(tmp_path: Path) -> None:
    repo = _init(tmp_path)
    (repo / "f.py").write_bytes(b"a\rb\r\nc\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    exact = "a\rb\r\nc\n"
    assert policy._index_text_or_none("f.py", repo) == exact
    assert policy._commit_text_or_none("HEAD", "f.py", repo) == exact
    assert policy._commit_text_or_empty("HEAD", "f.py", repo) == exact
    assert policy._commit_text_for_base("HEAD", "f.py", repo) == exact
    assert policy._commit_text_or_empty("HEAD", "missing.py", repo) == ""
    assert policy._commit_text_for_base("HEAD", "missing.py", repo) == ""
