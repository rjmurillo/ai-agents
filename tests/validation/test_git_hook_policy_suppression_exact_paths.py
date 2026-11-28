"""The suppression gate keys the Semgrep allowlist on the exact file name.

A diff header path is read as git names the file. A decoy whose name differs
from a listed ptk_run.py copy only by spaces must not borrow that copy's entry.
Blob reads keep a lone carriage return, so one physical line stays one line.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy
from tests.validation._suppression_gate_repo import (
    ENTRY_IDS,
    ENTRY_POINTS,
    git,
    init_repo,
    write,
)

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


def _repo_with_decoy(tmp_path: Path, decoy: str | None) -> tuple[Path, str]:
    repo = init_repo(tmp_path)
    write(repo, SOURCE, BASE_BODY)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    write(repo, SOURCE, HEAD_BODY)
    if decoy is not None:
        write(repo, decoy, HEAD_BODY)
    git(repo, "add", "-A")
    return repo, base


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


@pytest.mark.skipif(
    sys.platform == "win32", reason="a backslash is a directory separator on Windows"
)
def test_git_writes_the_header_forms_the_parser_expects(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    write(repo, "seed", "seed\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    for name in (" src/p.py", "tr.py ", "a\\b.py"):
        write(repo, name, "x\n")
    git(repo, "add", "-A")
    diff = git(
        repo, "-c", "core.quotePath=false", "diff", "--cached", "--dst-prefix=b/", "--no-color"
    )
    headers = [line[4:] for line in diff.split("\n") if line.startswith("+++ ")]
    parsed = [policy._exact_diff_header_path(header) for header in headers]
    assert sorted(path or "" for path in parsed) == sorted([" src/p.py", "tr.py ", "a\\b.py"])


def test_blob_readers_keep_a_lone_carriage_return(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "f.py").write_bytes(b"a\rb\r\nc\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    exact = "a\rb\r\nc\n"
    assert policy._index_text_or_none("f.py", repo) == exact
    assert policy._commit_text_or_none("HEAD", "f.py", repo) == exact
    assert policy._commit_text_or_empty("HEAD", "f.py", repo) == exact
    assert policy._commit_text_for_base("HEAD", "f.py", repo) == exact
    assert policy._commit_text_or_empty("HEAD", "missing.py", repo) == ""
    assert policy._commit_text_for_base("HEAD", "missing.py", repo) == ""
