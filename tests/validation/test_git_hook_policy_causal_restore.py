"""The push gate's suppression parser and ADR-review merge scope must hold.

``check_pushed_suppressions`` reads the diff a push would send and blocks
unjustified lint suppressions. Its bypasses are all parser-shaped: a bare
ruff-honored comment, a notebook cell the textual diff renders differently, a
new branch with no merge base, a shallow clone. Each one is a way to land a
suppression the gate was built to catch, so each gets a test.

``check_adr_review_policy`` blocks an ADR change carrying no adr-review
evidence. The exception is a merge in progress: an ADR reviewed on main arrives
in the merge commit with no evidence of its own, and blocking there would wedge
every merge that touches architecture.

The filename is stale and this file no longer tests causal restore. Three
classes covering the causal graph's snapshot-and-restore path were removed with
the graph itself (ADR-089). The two suites left never touched causality; they
shared this file only because both exercise ``git_hook_policy``.

Do not run ``ruff format`` on this file. The fixtures below split their
suppression tokens across adjacent string literals on purpose, so the push
gate's own scanner does not flag this file as introducing what it tests for.
Joining them, which the formatter does, re-arms the trap. Nothing in CI or the
hooks runs ``ruff format``, so the split form survives.

The honest fix for the name is a rename, and it is blocked. The gate diffs with
``--no-renames`` on purpose, so a rename reads as a wholesale add and the one
real suppression here, the ``E402`` on the import below, trips it. Renaming
requires teaching the gate to skip pure renames first. Filed as issue 3635.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy  # noqa: E402


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], returncode, stdout, "")


def _run_suppression_push(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    diff_text: str,
    changed_paths: tuple[str, ...] = ("pkg/module.py",),
    *,
    base: str | None = "c" * 40,
    remote_sha: str = "b" * 40,
    diff_without_no_renames: str | None = None,
    refs_present: bool = False,
    shallow: bool = False,
) -> int:
    head = "a" * 40
    expected_base = base
    if expected_base is None and refs_present and not shallow:
        expected_base = policy.EMPTY_TREE_SHA1
    expected_range = f"{expected_base}..{head}" if expected_base is not None else None
    monkeypatch.setattr(policy, "_check_history_integrity", lambda root: 0)
    monkeypatch.setattr(policy, "_merge_base", lambda root, base_ref, head_ref: base)
    monkeypatch.setattr(policy, "_commit_ref_exists", lambda root, ref: refs_present)
    monkeypatch.setattr(policy, "_is_shallow_repository", lambda root: shallow)
    monkeypatch.setattr(policy, "_empty_tree_sha", lambda root: policy.EMPTY_TREE_SHA1)

    def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["ls-tree", "-r"]:
            assert "-z" in args, "ls-tree must use -z for NUL-separated output"
            assert args[-1] == head
            return _completed("\0".join(changed_paths) + "\0")
        if args[0] == "diff" and "--name-only" in args and "--diff-filter=ACMRT" in args:
            for flag in policy.TEXTUAL_DIFF_FLAGS:
                assert flag in args
            assert "-z" in args, "diff --name-only must use -z for NUL-separated output"
            assert "--no-renames" in args, "diff --name-only must use --no-renames"
            assert expected_range is not None
            assert expected_range in args
            return _completed("\0".join(changed_paths) + "\0")
        if "diff" in args and "--unified=0" in args:
            assert expected_range is not None
            assert expected_range in args
            for flag in policy.TEXTUAL_DIFF_FLAGS:
                assert flag in args
            if "--no-renames" not in args and diff_without_no_renames is not None:
                return _completed(diff_without_no_renames)
            separator = args.index("--")
            assert tuple(args[separator + 1 :]) == changed_paths
            return _completed(diff_text)
        if args[0] == "show":
            return _completed("")
        raise AssertionError(f"unexpected git call: {args!r}")

    monkeypatch.setattr(policy, "_run_git", _run_git)
    stdin = io.StringIO(f"refs/heads/topic {head} refs/heads/topic {remote_sha}\n")
    return policy.check_pushed_suppressions(stdin, repo_root)


def _tool(name: str) -> str:
    resolved = shutil.which(name)
    assert resolved is not None, f"{name} is required for this regression test"
    return resolved


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _run(["git", *args], repo)
    assert result.returncode == 0, result.stderr
    return result


def _init_push_repo(repo: Path) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", base_sha)
    _git(repo, "checkout", "-b", "topic")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _point_origin_main_at_head(repo: Path) -> str:
    """Make the local `origin/main` cache agree with what this repo has at HEAD."""
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", head)
    return head


def _run_real_suppression_push(repo: Path, head: str) -> int:
    stdin = io.StringIO(f"refs/heads/topic {head} refs/heads/topic {'0' * 40}\n")
    return policy.check_pushed_suppressions(stdin, repo)


def _write_ruff_notebook(path: Path, source: str) -> None:
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [source],
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook), encoding="utf-8")


class TestPushedSuppressionPolicy:
    def test_bare_noqa_is_honored_by_ruff_and_blocked_by_push_gate(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        comment = "# no" "qa"
        analyzer_file = tmp_path / "ruff_bare_noqa.py"
        analyzer_file.write_text(f"import os  {comment}\n", encoding="utf-8")
        analyzer = _run([_tool("ruff"), "check", "--select", "F401", str(analyzer_file)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+import os  {comment}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:1" in capsys.readouterr().err

    def test_bare_type_ignore_is_honored_by_mypy_and_blocked_by_push_gate(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        comment = "# type" ": ignore"
        analyzer_file = tmp_path / "mypy_bare_type_ignore.py"
        analyzer_file.write_text(f"value: int = 'wrong'  {comment}\n", encoding="utf-8")
        analyzer = _run([_tool("mypy"), "--show-error-codes", str(analyzer_file)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -0,0 +1 @@
+value: int = 'wrong'  {comment}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:1" in capsys.readouterr().err

    def test_newly_added_type_ignore_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# type" ": ignore[arg-type]"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,0 +2 @@
+value = call()  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        err = capsys.readouterr().err
        assert "security suppression comments detected" in err
        assert "pkg/module.py:2" in err

    def test_pre_existing_type_ignore_touched_elsewhere_is_allowed(self, tmp_path, monkeypatch):
        diff = """diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -2 +2 @@
-old = 1
+new = 1
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_added_file_with_type_ignore_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# type" ": ignore[assignment]"
        diff = f"""diff --git a/pkg/new.py b/pkg/new.py
new file mode 100644
--- /dev/null
+++ b/pkg/new.py
@@ -0,0 +1,2 @@
+from pkg import value
+result = value  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff, ("pkg/new.py",)) == 1
        assert "pkg/new.py:2" in capsys.readouterr().err

    def test_type_ignore_on_context_line_adjacent_to_edit_is_allowed(self, tmp_path, monkeypatch):
        suppression = "# type" ": ignore[arg-type]"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,2 +1,2 @@
 value = call()  {suppression}
-old = 1
+new = 1
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_added_plus_plus_line_with_nosec_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# no" "sec"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,0 +4 @@
+++counter  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:4" in capsys.readouterr().err

    def test_no_prefix_diff_with_nosec_addition_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# no" "sec"
        diff = f"""diff --git pkg/module.py pkg/module.py
--- pkg/module.py
+++ pkg/module.py
@@ -1,0 +3 @@
+value = call()  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:3" in capsys.readouterr().err

    def test_rename_into_scanned_suffix_with_existing_suppression_is_blocked(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# no" "sec"
        rename_only_diff = """diff --git a/pkg/payload.txt b/pkg/payload.py
similarity index 100%
rename from pkg/payload.txt
rename to pkg/payload.py
"""
        no_rename_diff = f"""diff --git a/pkg/payload.txt b/pkg/payload.py
deleted file mode 100644
--- a/pkg/payload.txt
+++ /dev/null
@@ -1 +0,0 @@
-value = call()
diff --git a/pkg/payload.py b/pkg/payload.py
new file mode 100644
--- /dev/null
+++ b/pkg/payload.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                no_rename_diff,
                ("pkg/payload.py",),
                diff_without_no_renames=rename_only_diff,
            )
            == 1
        )
        assert "pkg/payload.py:1" in capsys.readouterr().err

    def test_new_branch_without_merge_base_is_config_error(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# type" ": ignore[arg-type]"
        diff = f"""diff --git a/source.py b/source.py
new file mode 100644
--- /dev/null
+++ b/source.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                diff,
                ("source.py",),
                base=None,
                remote_sha="0" * 40,
            )
            == 2
        )
        err = capsys.readouterr().err
        assert "could not determine push base for new branch" in err
        assert "fetch origin/main" in err
        assert "unshallow" in err

    def test_new_branch_with_merge_base_scans_only_pushed_range(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# type" ": ignore[arg-type]"
        diff = f"""diff --git a/source.py b/source.py
new file mode 100644
--- /dev/null
+++ b/source.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                diff,
                ("source.py",),
                base="d" * 40,
                remote_sha="0" * 40,
            )
            == 1
        )
        assert "source.py:1" in capsys.readouterr().err

    def test_removed_line_starting_with_two_dashes_does_not_shift_added_line_number(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# no" "sec"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -10,2 +10,1 @@
--- removed content line
+real = 1  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        assert "pkg/module.py:10" in capsys.readouterr().err

    def test_diff_attribute_cannot_hide_added_suppression(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        suppression = "# no" "sec"
        (repo / ".gitattributes").write_text("scripts/tls_probe.py -diff\n", encoding="utf-8")
        script = repo / "scripts" / "tls_probe.py"
        script.parent.mkdir()
        script.write_text(f"import ssl\nssl.PROTOCOL_SSLv3  {suppression}\n", encoding="utf-8")
        head = _commit(repo, "add hidden suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_external_diff_cannot_hide_added_suppression(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        # Create a portable external-diff stub that swallows all output
        stub = tmp_path / "ext-diff-stub"
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
        _git(repo, "config", "diff.external", str(stub))
        suppression = "# no" "sec"
        path = repo / "pkg" / "module.py"
        path.parent.mkdir()
        path.write_text(f"import ssl\nssl.PROTOCOL_SSLv3  {suppression}\n", encoding="utf-8")
        head = _commit(repo, "add external hidden suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_textconv_driver_cannot_hide_added_suppression(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        _git(repo, "config", "diff.hide.textconv", "true")
        (repo / ".gitattributes").write_text("*.py diff=hide\n", encoding="utf-8")
        suppression = "# no" "sec"
        path = repo / "pkg" / "module.py"
        path.parent.mkdir()
        path.write_text(f"import ssl\nssl.PROTOCOL_SSLv3  {suppression}\n", encoding="utf-8")
        head = _commit(repo, "add textconv hidden suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_suppression_suffixes_cover_ruff_count_ratchet_scan_globs(self):
        assert policy._ruff_scan_suffixes() <= policy.SECURITY_SUPPRESSION_SUFFIXES
        assert {".pyi", ".ipynb", ".pyw"} <= policy.SECURITY_SUPPRESSION_SUFFIXES

    def test_pyi_suppression_is_honored_by_ruff_and_blocked_by_push_gate(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        comment = "# no" "qa"
        analyzer_file = tmp_path / "stub.pyi"
        analyzer_file.write_text(f"import os  {comment}\n", encoding="utf-8")
        analyzer = _run([_tool("ruff"), "check", "--select", "F401", str(analyzer_file)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        diff = f"""diff --git a/pkg/stub.pyi b/pkg/stub.pyi
--- a/pkg/stub.pyi
+++ b/pkg/stub.pyi
@@ -0,0 +1 @@
+import os  {comment}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff, ("pkg/stub.pyi",)) == 1
        assert "pkg/stub.pyi:1" in capsys.readouterr().err

    def test_pyw_suppression_is_honored_by_bandit_and_blocked_by_push_gate(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        comment = "# no" "sec"
        path = repo / "tools" / "legacy_tls.pyw"
        path.parent.mkdir()
        path.write_text(
            "import ssl\n"
            "ssl.wrap_socket(ssl_version=ssl.PROTOCOL_SSLv3)  "
            f"{comment}\n",
            encoding="utf-8",
        )
        analyzer = _run([_tool("bandit"), "-q", str(path)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        head = _commit(repo, "add pyw suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_notebook_unicode_escape_suppression_is_honored_by_ruff_and_blocked(
        self,
        tmp_path,
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_push_repo(repo)
        path = repo / "notebooks" / "analysis.ipynb"
        path.parent.mkdir()
        _write_ruff_notebook(path, "import os  # no" "qa\n")
        path.write_text(
            path.read_text(encoding="utf-8").replace("no" "qa", "no\\u0071a"),
            encoding="utf-8",
        )
        analyzer = _run([_tool("ruff"), "check", "--select", "F401", str(path)], _ROOT)
        assert analyzer.returncode == 0, analyzer.stdout + analyzer.stderr
        head = _commit(repo, "add notebook suppression")

        assert _run_real_suppression_push(repo, head) == 1

    def test_true_orphan_branch_scans_from_empty_tree(self, tmp_path, monkeypatch, capsys):
        suppression = "# type" ": ignore[arg-type]"
        diff = f"""diff --git a/source.py b/source.py
new file mode 100644
--- /dev/null
+++ b/source.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                diff,
                ("source.py",),
                base=None,
                remote_sha="0" * 40,
                refs_present=True,
                shallow=False,
            )
            == 1
        )
        assert "source.py:1" in capsys.readouterr().err

    def test_shallow_new_branch_without_merge_base_stays_config_error(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        suppression = "# type" ": ignore[arg-type]"
        diff = f"""diff --git a/source.py b/source.py
new file mode 100644
--- /dev/null
+++ b/source.py
@@ -0,0 +1 @@
+value = call()  {suppression}
"""

        assert (
            _run_suppression_push(
                monkeypatch,
                tmp_path,
                diff,
                ("source.py",),
                base=None,
                remote_sha="0" * 40,
                refs_present=True,
                shallow=True,
            )
            == 2
        )
        err = capsys.readouterr().err
        assert "could not determine push base for new branch" in err
        assert "unshallow" in err


class TestAdrReviewPolicyMergeScope:
    def test_non_merge_adr_without_review_evidence_is_blocked(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: False)
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        result = policy.check_adr_review_policy(
            [".agents/architecture/ADR-999-test.md"],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_merge_in_progress_with_staged_adr_from_main_is_allowed(self, tmp_path, monkeypatch):
        path = ".agents/architecture/ADR-120-reviewed-on-main.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"main adr")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: None)
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: ["main-parent"],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: b"main adr",
            raising=False,
        )

        result = policy.check_adr_review_policy(
            [path],
            tmp_path,
        )

        assert result == 0

    def test_merge_in_progress_with_branch_authored_adr_is_gated(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        path = ".agents/architecture/ADR-999-branch-authored-during-merge.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"authored adr")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: b"branch adr")
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: ["main-parent"],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: b"main adr",
            raising=False,
        )
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        result = policy.check_adr_review_policy(
            [path],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_merge_in_progress_with_conflicted_adr_is_gated_when_stage_zero_is_absent(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        path = ".agents/architecture/ADR-998-conflicted.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: None)
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        result = policy.check_adr_review_policy(
            [path],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_merge_of_a_shared_branch_tip_allows_content_already_on_main(
        self,
        tmp_path,
        monkeypatch,
    ):
        """The exemption has to follow the content, not the merge parent.

        `_approved_merge_head_commits` keeps only parents that are ancestors of
        `origin/main`, so it covers merging main in directly. It does not cover
        the other way a branch takes main's work: someone else merges main into
        the shared branch and pushes, and the next author merges that remote
        tip. The parent is then the branch, not main, so every ADR main
        contributed reads as branch-authored and the gate demands review
        evidence for a file the author never opened.

        Comparing the staged blob against `origin/main` closes that without
        widening the gate, because content that already sits on main already
        cleared this policy on the pull request that put it there.
        """
        path = ".agents/architecture/ADR-089-arrived-through-the-branch.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"main adr")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: None)
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: [],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_merge_head_commits",
            lambda root: ["the-shared-branch-tip"],
            raising=False,
        )
        blobs = {"the-shared-branch-tip": b"main adr", "origin/main": b"main adr"}
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: blobs.get(commit),
            raising=False,
        )

        assert policy.check_adr_review_policy([path], tmp_path) == 0

    def test_an_adr_reverted_to_a_stale_origin_main_during_a_merge_is_still_gated(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Content sitting on main is not a licence to put it back.

        A local `origin/main` ref goes stale the moment someone else pushes.
        Matching content against it alone would let an author revert an ADR to
        the stale state mid-merge and walk past the gate, and the revert would
        then overwrite the newer copy on the next push. Reverting is a fresh
        decision no matter how old the bytes are, so the content has to arrive
        through the merge as well as match main.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-001-superseded.md"
        adr.write_text("# ADR 001\n\nthe old position.\n", encoding="utf-8")
        _commit(repo, "old position")
        # The local ref stops here. Someone else already pushed the revision.
        head = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", head)
        adr.write_text("# ADR 001\n\nthe revised position.\n", encoding="utf-8")
        _commit(repo, "revised position")

        _git(repo, "checkout", "-b", "feature")
        (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
        _commit(repo, "feature work")
        _git(repo, "branch", "sibling")
        _git(repo, "checkout", "sibling")
        (repo / "sibling.txt").write_text("sibling\n", encoding="utf-8")
        _commit(repo, "sibling work")
        _git(repo, "checkout", "feature")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "sibling"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-001-superseded.md"
        adr.write_text("# ADR 001\n\nthe old position.\n", encoding="utf-8")
        _git(repo, "add", relative)

        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_an_adr_a_collaborator_wrote_on_the_shared_branch_is_still_gated(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Arriving through the merge is not enough on its own.

        A collaborator can write an ADR on the shared branch and push it. The
        content then sits on a merge parent without ever having been reviewed
        on main. Exempting it because the merge carried it would let any pair
        of branches walk an ADR onto main with no review evidence at all, so
        the content has to match main as well as arrive through the merge.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-003-collaborator.md"
        adr.write_text("# ADR 003\n\nthe reviewed position.\n", encoding="utf-8")
        _commit(repo, "reviewed position")
        head = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", head)

        _git(repo, "checkout", "-b", "shared")
        adr.write_text("# ADR 003\n\nthe collaborator position.\n", encoding="utf-8")
        _commit(repo, "collaborator writes the adr on the branch")

        _git(repo, "checkout", "main")
        _git(repo, "checkout", "-b", "feature")
        (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
        _commit(repo, "feature work")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "shared"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-003-collaborator.md"
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_an_approved_merge_parent_exempts_content_origin_main_does_not_carry(
        self,
        tmp_path,
        monkeypatch,
    ):
        """The approved-parent rule has to keep working on its own.

        Merging an older main commit brings content that the local `origin/main`
        tip no longer carries, so the blob comparison against main cannot
        exempt it and the ancestry rule is the only thing that can. Without
        this the ancestry rule could be deleted outright and every other test
        here would stay green.
        """
        path = ".agents/architecture/ADR-002-an-earlier-main.md"
        blobs = {"an-approved-parent": b"earlier main", "origin/main": b"later main"}
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"earlier main")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: None)
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: ["an-approved-parent"],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_merge_head_commits",
            lambda root: ["an-approved-parent"],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: blobs.get(commit),
            raising=False,
        )

        assert policy.check_adr_review_policy([path], tmp_path) == 0

    def test_a_carrier_branch_cannot_launder_a_reversion_past_a_stale_origin_main(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Matching a stale `origin/main` is not evidence of review.

        Requiring the blob to sit on a merge parent stops an author typing a
        reversion during someone else's merge, but it does not stop an author
        who builds the merge. Branch off the newer commit, commit the older
        ADR text there, merge that branch back, and both halves of the rule
        are satisfied: the blob is on a merge parent because the author put it
        there, and it matches `origin/main` because `origin/main` is stale.

        The gate cannot tell a stale ref from a current one offline, so it
        asks a different question instead: is the copy this branch already has
        one that main has ever carried. Here it is not, because the newer text
        was written locally and never pushed, which makes the merge a
        regression of local work rather than main's content arriving.

        Found by adversarial security review, Finding 3. It reproduces with no
        write to `.git` and no ref surgery, which is what separates it from
        the other two findings that round returned.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-004-carrier.md"
        adr.write_text("# ADR 004\n\nold reviewed position.\n", encoding="utf-8")
        old = _commit(repo, "the old position")
        _git(repo, "update-ref", "refs/remotes/origin/main", old)

        adr.write_text("# ADR 004\n\nnewer reviewed position.\n", encoding="utf-8")
        newer = _commit(repo, "the newer position, not yet pushed")

        _git(repo, "update-ref", "refs/heads/carrier", newer)
        _git(repo, "checkout", "carrier")
        adr.write_text("# ADR 004\n\nold reviewed position.\n", encoding="utf-8")
        _commit(repo, "carrier quietly restores the old text")

        _git(repo, "checkout", "main")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "carrier"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-004-carrier.md"
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_a_synthetic_merge_head_that_head_already_contains_is_not_a_merge(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """A hand-written `MERGE_HEAD` naming an ancestor is never a real merge.

        `git merge <ancestor>` reports "Already up to date" and writes no
        `MERGE_HEAD` at all, so any `MERGE_HEAD` that HEAD already contains
        was placed there by something other than git. Reading it as a merge
        in progress hands the whole merge exemption to anyone who can write a
        file, and the older commit it names is an approved parent by
        construction, so the reversion it authorises is the exact thing the
        gate exists to catch.

        Found by adversarial security review, Finding 2. Unlike the carrier
        case this one needs a write inside `.git`, and an author who has that
        can also skip the hook outright. It is fixed anyway because the check
        costs one ancestry query and removes a way to get the same result
        while the hook still reports success.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-005-synthetic.md"
        adr.write_text("# ADR 005\n\nold reviewed position.\n", encoding="utf-8")
        old = _commit(repo, "the old position")

        adr.write_text("# ADR 005\n\nnewer reviewed position.\n", encoding="utf-8")
        newer = _commit(repo, "the newer position")
        _git(repo, "update-ref", "refs/remotes/origin/main", newer)

        adr.write_text("# ADR 005\n\nold reviewed position.\n", encoding="utf-8")
        _git(repo, "add", ".")
        (repo / ".git" / "MERGE_HEAD").write_text(f"{old}\n", encoding="utf-8")

        relative = ".agents/architecture/ADR-005-synthetic.md"
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_a_real_merge_of_a_shared_branch_tip_exempts_the_adr_main_contributed(
        self,
        tmp_path,
        monkeypatch,
    ):
        """End-to-end proof against a real repository, no git calls stubbed.

        The monkeypatched checks above describe the shape of the bug. This one
        reproduces it: main gains an ADR, a collaborator merges main into the
        shared branch and the next author merges that branch tip, so MERGE_HEAD
        names the branch and not main. The staged ADR is byte-identical to
        main's copy, so the gate must let it through.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _commit(repo, "base")
        # `local` is cut here rather than by start-point later: the suite's
        # head guard exports GIT_TRACE_REFS, and git 2.43 rejects an explicit
        # commit as a branch point while that trace is on.
        _git(repo, "branch", "local")

        _git(repo, "checkout", "-b", "shared")
        (repo / "branch.txt").write_text("branch work\n", encoding="utf-8")
        _commit(repo, "branch work")

        _git(repo, "checkout", "main")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-089-from-main.md"
        adr.write_text("# ADR 089\n\nmain wrote this.\n", encoding="utf-8")
        _commit(repo, "adr on main")
        main_tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", main_tip)

        # A collaborator merges main into the shared branch and pushes.
        _git(repo, "checkout", "shared")
        _git(repo, "merge", "--no-edit", "main")

        # The author, still on the old branch point, merges that shared tip.
        _git(repo, "checkout", "local")
        (repo / "local.txt").write_text("local work\n", encoding="utf-8")
        _commit(repo, "local work")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "shared"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-089-from-main.md"
        assert policy._merge_in_progress(repo) is True
        assert policy._merge_authored_adr_paths([relative], repo) == []

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 0

    def test_a_real_merge_still_gates_an_adr_the_author_wrote_on_the_branch(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Negative control for the real-repository check above.

        Same repository shape, but the staged ADR differs from main's copy
        because the author edited it during the merge. Nothing on main carries
        that content, so no exemption applies and the gate blocks.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _commit(repo, "base")
        # `local` is cut here rather than by start-point later: the suite's
        # head guard exports GIT_TRACE_REFS, and git 2.43 rejects an explicit
        # commit as a branch point while that trace is on.
        _git(repo, "branch", "local")

        _git(repo, "checkout", "-b", "shared")
        (repo / "branch.txt").write_text("branch work\n", encoding="utf-8")
        _commit(repo, "branch work")

        _git(repo, "checkout", "main")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-089-from-main.md"
        adr.write_text("# ADR 089\n\nmain wrote this.\n", encoding="utf-8")
        _commit(repo, "adr on main")
        main_tip = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "update-ref", "refs/remotes/origin/main", main_tip)

        _git(repo, "checkout", "shared")
        _git(repo, "merge", "--no-edit", "main")

        _git(repo, "checkout", "local")
        (repo / "local.txt").write_text("local work\n", encoding="utf-8")
        _commit(repo, "local work")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "shared"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-089-from-main.md"
        (repo / relative).write_text("# ADR 089\n\nthe author rewrote this.\n", encoding="utf-8")
        _git(repo, "add", relative)

        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_merge_of_a_shared_branch_tip_still_gates_content_main_does_not_have(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Negative control for the check above.

        An ADR written on the branch during the same merge differs from main's
        copy, or main has no copy at all, so the blob comparison must not
        exempt it. Without this the previous test would pass just as well
        against a check that exempted every path once a merge was underway.
        """
        path = ".agents/architecture/ADR-999-written-during-the-merge.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_read_index_blob", lambda root, relative_path: b"authored adr")
        monkeypatch.setattr(policy, "_read_head_blob", lambda root, relative_path: None)
        monkeypatch.setattr(
            policy,
            "_approved_merge_head_commits",
            lambda root: [],
            raising=False,
        )
        monkeypatch.setattr(
            policy,
            "_merge_head_commits",
            lambda root: ["the-shared-branch-tip"],
            raising=False,
        )
        blobs = {"the-shared-branch-tip": b"main adr", "origin/main": b"main adr"}
        monkeypatch.setattr(
            policy,
            "_read_commit_blob_bytes",
            lambda root, commit, relative_path: blobs.get(commit),
            raising=False,
        )
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        assert policy.check_adr_review_policy([path], tmp_path) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_line_endings_alone_do_not_make_a_staged_adr_mains_content(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """The exemption is byte identity, so it has to be read in bytes.

        The blob readers ran `git show` through a text-mode pipe, which
        translates every `\\r\\n` and every lone `\\r` to `\\n` before the bytes are
        handed back. Two blobs that differ only in how they end their lines
        arrived identical, so a staged ADR the merge never carried satisfied
        both blob halves of the rule and left through main's exemption.

        Found by adversarial review round 51.
        """
        repo = _merge_carrying_main_adr(
            tmp_path, b"# ADR 090\n\nmain wrote this.\n", "ADR-090-endings.md"
        )
        relative = ".agents/architecture/ADR-090-endings.md"
        (repo / relative).write_bytes(b"# ADR 090\r\n\r\nmain wrote this.\r\n")
        _git(repo, "add", relative)

        assert policy._read_index_blob(repo, relative) != policy._read_head_blob(repo, relative)
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_two_different_undecodable_blobs_are_not_one_blob(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """Decoding with `errors="replace"` collapses distinct bytes to one.

        Every byte the decoder cannot read becomes U+FFFD, so any two blobs
        that differ only inside undecodable runs compared equal. This is the
        same defect as the line-ending case and the wider half of it: the
        collision needs no agreement about what the differing bytes mean.

        Found by adversarial review round 51.
        """
        repo = _merge_carrying_main_adr(
            tmp_path, b"# ADR 091\n\nmain \xff\xfe wrote this.\n", "ADR-091-endings.md"
        )
        relative = ".agents/architecture/ADR-091-endings.md"
        (repo / relative).write_bytes(b"# ADR 091\n\nmain \x80\x81 wrote this.\n")
        _git(repo, "add", relative)

        assert policy._read_index_blob(repo, relative) != policy._read_head_blob(repo, relative)
        assert policy._merge_authored_adr_paths([relative], repo) == [relative]

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_a_merge_that_carries_crlf_content_keeps_mains_exemption(
        self,
        tmp_path,
    ):
        """Reading the merge parent as text costs the exemption it should grant.

        This is the same normalization seen from the other side. When main's
        own ADR ends its lines with `\r\n`, a text-mode read of the parent
        hands back `\n` while the staged blob still holds what git stored, so
        the two stop matching and an ADR the author never opened is reported
        as branch-authored. Nothing is let through, but review evidence is
        demanded for someone else's file, which is how a gate loses its
        audience.

        Found by adversarial review round 51.
        """
        relative = ".agents/architecture/ADR-094-carried.md"
        carried = b"# ADR 094\r\n\r\nmain wrote this.\r\n"
        repo = _merge_carrying_main_adr(tmp_path, carried, "ADR-094-carried.md")

        assert policy._read_index_blob(repo, relative) == carried
        assert policy._merge_authored_adr_paths([relative], repo) == []

    def test_crlf_content_the_merge_left_alone_is_still_unchanged_from_head(
        self,
        tmp_path,
    ):
        """A path the merge did not touch is recognized by HEAD's bytes.

        The branch wrote this ADR itself and the merge brought something
        else, so the staged copy is what HEAD already had and no merge
        exemption is involved. A text-mode read of HEAD folds the `\r\n`
        endings the branch committed, the staged copy no longer matches, and
        an untouched file is pushed down the merge-exemption path to be
        reported as authored by a merge that never saw it.

        Found by adversarial review round 51.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        (repo / ".gitattributes").write_text("* -text\n", encoding="utf-8")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        _commit(repo, "base")
        _git(repo, "branch", "local")

        (repo / "README.md").write_text("main moved on\n", encoding="utf-8")
        _commit(repo, "main work")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "local")
        relative = ".agents/architecture/ADR-095-branch.md"
        (repo / relative).parent.mkdir(parents=True)
        (repo / relative).write_bytes(b"# ADR 095\r\n\r\nthe branch wrote this.\r\n")
        _commit(repo, "branch adr")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "main"], repo)
        assert merge.returncode == 0, merge.stderr

        assert policy._read_head_blob(repo, relative) == policy._read_index_blob(repo, relative)
        assert policy._merge_authored_adr_paths([relative], repo) == []

    def test_typing_mains_text_during_an_unrelated_merge_is_not_the_merge_carrying_it(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        """The merge-parent clause had no test that failed when it was removed.

        Round 50 claimed every clause of this rule was mutation-proved. It was
        not. The stale-`origin/main` test fails the head-copy clause as well,
        so deleting the merge-parent clause left the whole class green. This
        is the discriminator that separates them: the staged blob matches
        `origin/main`, the copy it replaces is one `origin/main` has carried,
        and the merge carried nothing of the kind.

        The exemption is for what a merge brought in. An author who types the
        text during someone else's merge has not been reviewed by that merge,
        and whether the text is current or a reversion depends on how stale
        `origin/main` is, which this gate cannot see.

        Found by adversarial review round 51.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        adr = adr_dir / "ADR-092-typed.md"
        adr.write_text("# ADR 092\n\nfirst position.\n", encoding="utf-8")
        _commit(repo, "first position")
        _git(repo, "branch", "local")
        _git(repo, "branch", "side")

        adr.write_text("# ADR 092\n\nsecond position.\n", encoding="utf-8")
        _commit(repo, "second position")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "side")
        (repo / "side.txt").write_text("side work\n", encoding="utf-8")
        _commit(repo, "side work")

        _git(repo, "checkout", "local")
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "side"], repo)
        assert merge.returncode == 0, merge.stderr

        relative = ".agents/architecture/ADR-092-typed.md"
        adr.write_text("# ADR 092\n\nsecond position.\n", encoding="utf-8")
        _git(repo, "add", relative)

        staged = policy._read_index_blob(repo, relative)
        merge_parents = policy._merge_head_commits(repo)
        assert policy._blob_is_at_any(repo, merge_parents, relative, staged) is False
        assert policy._read_commit_blob_bytes(repo, "origin/main", relative) == staged
        assert policy._head_copy_is_one_main_has_carried(repo, relative) is True

        assert policy._merge_authored_adr_paths([relative], repo) == [relative]
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([relative], repo) == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_a_rename_does_not_hide_the_history_the_head_copy_came_from(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Renaming an ADR must not turn main's own revision into gated work.

        The head-copy clause asked `rev-list` for the commits touching one
        pathname, which stops at the rename. An ADR renamed on both branches
        and revised on main then failed the clause on the branch's own copy,
        because that copy lived under the former name, and a merge that only
        brought main's revision in demanded review evidence for it.

        Found by adversarial review round 51.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "test@example.invalid")
        _git(repo, "config", "user.name", "Test User")
        adr_dir = repo / ".agents" / "architecture"
        adr_dir.mkdir(parents=True)
        old_name = ".agents/architecture/ADR-093-old.md"
        new_name = ".agents/architecture/ADR-093-new.md"
        # Long enough that a one-line revision still scores as a rename. Git
        # pairs paths at 50% similarity by default, and a three-line fixture
        # would need the threshold lowered to pass, which would be tuning the
        # gate to the test rather than to the documents it guards.
        body = "\n".join(f"Context paragraph {index}." for index in range(20))
        first = f"# ADR 093\n\n{body}\n\nDecision: first position.\n"
        second = f"# ADR 093\n\n{body}\n\nDecision: second position.\n"
        (repo / old_name).write_text(first, encoding="utf-8")
        _commit(repo, "first position")
        _git(repo, "branch", "local")

        _git(repo, "mv", old_name, new_name)
        (repo / new_name).write_text(second, encoding="utf-8")
        _commit(repo, "rename and revise on main")
        _point_origin_main_at_head(repo)

        _git(repo, "checkout", "local")
        _git(repo, "mv", old_name, new_name)
        _commit(repo, "the branch renamed it too")

        # Both sides moved the file, so the merge pairs the renames and takes
        # main's revision on its own. Nothing here is authored by the branch.
        merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "main"], repo)
        assert merge.returncode == 0, merge.stderr
        assert policy._read_index_blob(repo, new_name) == second.encode("utf-8")

        assert policy._head_copy_is_one_main_has_carried(repo, new_name) is True
        assert policy._merge_authored_adr_paths([new_name], repo) == []

        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)
        assert policy.check_adr_review_policy([new_name], repo) == 0

    def test_a_conflict_main_resolved_in_a_merge_is_a_state_main_has_carried(
        self,
        tmp_path,
    ):
        """`git log --raw` says nothing about a merge unless it is asked to.

        Without `-m`, git prints no diff for a merge commit, so an ADR whose
        only appearance in that state was a conflict resolution left no blob id
        behind. A branch sitting on that resolution held content main really
        had carried and still failed the head-copy clause, which demands review
        evidence for a file the branch never opened.

        The revision after the merge is what makes this observable: without it
        the resolution is `origin/main`'s tip and the tip lookup covers it.

        Found by adversarial review round 52.
        """
        repo, name, resolved = _repo_where_main_resolved_an_adr_in_a_merge(tmp_path)

        assert policy._read_head_blob(repo, name) == resolved

        assert policy._head_copy_is_one_main_has_carried(repo, name) is True

    def test_a_users_diff_merges_setting_does_not_hide_the_resolution(
        self,
        tmp_path,
    ):
        """`-m` takes its output format from the user's `log.diffMerges`.

        `-m` means `--diff-merges=on`, and `on` defers to whatever
        `log.diffMerges` says. Set to `combined` or `dense-combined`, the merge
        prints one `::` record instead of one `:` record per parent, and that
        record is laid out differently: the fourth field is the first parent's
        pre-image rather than the post-image. So the resolution blob went
        missing again, and a blob nobody asked about took its place in the set.

        Asking for `separate` by name pins the format the parser was written
        for. The setting is a normal user preference, not an attack, and the
        gate runs on whatever machine the developer configured.

        Found by a bot reviewer on PR #3680.
        """
        repo, name, resolved = _repo_where_main_resolved_an_adr_in_a_merge(
            tmp_path,
            diff_merges="combined",
        )

        assert policy._read_head_blob(repo, name) == resolved

        assert policy._head_copy_is_one_main_has_carried(repo, name) is True

    def test_the_blob_set_is_the_same_under_every_diff_merges_setting(
        self,
        tmp_path,
    ):
        """No user preference may change what this gate accepts.

        `log.diffMerges` has five values and `-m` honours all of them, so the
        set the gate reasons about moved with a setting the developer chose for
        readability. Naming the format instead makes the answer the same on
        every machine, which is the property worth asserting: not that one
        value works, but that the setting is not an input.
        """
        answers = {}
        for setting in ("combined", "dense-combined", "separate", "on", "first-parent"):
            repo, name, _ = _repo_where_main_resolved_an_adr_in_a_merge(
                tmp_path / setting,
                diff_merges=setting,
            )
            answers[setting] = policy._origin_main_blob_ids(repo, name)

        assert len(set(map(frozenset, answers.values()))) == 1, answers

    def test_a_combined_diff_record_is_never_read_as_a_post_image(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Refuse a record shape the field positions do not describe.

        A `::` record carries one pre-image per parent before the post-image,
        so its fourth field is a pre-image and its width grows with the parent
        count. Reading it as a post-image puts a blob in the carried set that
        answers a question nobody asked.

        Naming the format should mean these never arrive. Skipping them is what
        keeps that true when a later git, or a flag someone adds here, produces
        one anyway, and the field positions are not self-describing enough to
        notice on their own.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        combined = (
            "::100644 100644 100644 "
            "1111111111111111111111111111111111111111 "
            "2222222222222222222222222222222222222222 "
            "3333333333333333333333333333333333333333 MM\tdoc.md\n"
            ":100644 100644 "
            "4444444444444444444444444444444444444444 "
            "5555555555555555555555555555555555555555 M\tdoc.md\n"
        )
        monkeypatch.setattr(
            policy,
            "_run_git",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=combined),
        )

        assert policy._origin_main_blob_ids(repo, "doc.md") == {"5" * 40}


def _repo_where_main_resolved_an_adr_in_a_merge(
    tmp_path: Path,
    diff_merges: str | None = None,
) -> tuple[Path, str, bytes]:
    """Build a repo whose ADR reached its current text inside a merge.

    Main and a side branch each revise the ADR, the merge conflicts, and main
    resolves it by hand. Main then revises the file again, which is what makes
    the resolution observable: without that last commit the resolution is
    `origin/main`'s tip and the separate tip lookup accounts for it.

    `local` sits on the resolution, so it holds content main really carried
    and any answer other than True demands review evidence for a file the
    branch never opened.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    if diff_merges is not None:
        _git(repo, "config", "log.diffMerges", diff_merges)
    adr_dir = repo / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    name = ".agents/architecture/ADR-096-contested.md"
    (repo / name).write_text("# ADR 096\n\nbase.\n", encoding="utf-8")
    _commit(repo, "base")

    _git(repo, "checkout", "-b", "sideways")
    (repo / name).write_text("# ADR 096\n\nsideways.\n", encoding="utf-8")
    _commit(repo, "sideways position")

    _git(repo, "checkout", "main")
    (repo / name).write_text("# ADR 096\n\nmainline.\n", encoding="utf-8")
    _commit(repo, "mainline position")

    conflicted = _run(["git", "merge", "--no-edit", "sideways"], repo)
    assert conflicted.returncode != 0, "the fixture needs a real conflict"
    resolved = "# ADR 096\n\nresolved in the merge.\n"
    (repo / name).write_text(resolved, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "--no-edit", "-m", "resolve the ADR while merging")
    _git(repo, "branch", "local")

    (repo / name).write_text("# ADR 096\n\nlater still.\n", encoding="utf-8")
    _commit(repo, "revise after the merge")
    _point_origin_main_at_head(repo)

    _git(repo, "checkout", "local")
    return repo, name, resolved.encode("utf-8")


def _merge_carrying_main_adr(tmp_path: Path, adr_bytes: bytes, name: str) -> Path:
    """Build a repo mid-merge whose staged ADR is the one main contributed.

    The exemption holds here, which is the point: each caller then restages
    bytes that differ from main's only in ways a text-mode pipe erases, so a
    test that still sees an exemption is reporting the normalization and not
    the rule.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _commit(repo, "base")
    _git(repo, "branch", "local")

    adr_dir = repo / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / name).write_bytes(adr_bytes)
    _commit(repo, "adr on main")
    _point_origin_main_at_head(repo)

    _git(repo, "checkout", "local")
    (repo / "local.txt").write_text("local work\n", encoding="utf-8")
    _commit(repo, "local work")
    merge = _run(["git", "merge", "--no-edit", "--no-commit", "--no-ff", "main"], repo)
    assert merge.returncode == 0, merge.stderr
    return repo


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
