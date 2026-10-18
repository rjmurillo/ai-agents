"""Tests for the merge-base rule of verify_dispatch_closure.py (issues #6415, #6472).

A pull request behind the base ref is not charged with editing files the base
moved after the branch point. Those files are reported STALE instead, and STALE
still fails: the head would run the old copy, so the author must merge the base
ref. Each case builds the pull request first, from the base as it stands, then
moves the base, then runs the check the way the workflow does.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest
import yaml

from scripts.ci import verify_dispatch_closure as vdc
from tests.ci.dispatch_closure_helpers import (  # noqa: F401
    CONFIG,
    GATE,
    HELPER,
    VERIFIER,
    git,
    rev,
    upstream_with_pr,
    write,
)

SECOND = ".claude/skills/demo/scripts/second.py"


def commit_on_base(base: Path, message: str) -> None:
    git(base, "add", "-A")
    git(base, "commit", "-q", "-m", message)


def check(base: Path, upstream: Path, sha: str, capsys: pytest.CaptureFixture[str]) -> dict:
    code = vdc.main(
        [
            "--tool-root",
            str(base),
            "--head-sha",
            sha,
            "--pull-number",
            "1",
            "--remote",
            str(upstream),
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    report["code"] = code
    return report


class TestBehindTheBase:
    def test_a_file_the_base_changed_after_the_branch_point_is_stale(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        write(base, HELPER, "X = 2\n")
        commit_on_base(base, "main moves the helper")

        report = check(base, upstream, sha, capsys)

        assert report["changed"] == []
        assert report["stale"] == [HELPER]
        assert report["code"] == vdc.EXIT_DIFFERS

    def test_a_verifier_the_base_hardened_after_the_branch_point_fails_as_stale(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The head carries the weaker pre-fix verifier; the check must not pass."""
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        write(base, VERIFIER, "import helper\n# hardened\n")
        commit_on_base(base, "main hardens the verifier")

        report = check(base, upstream, sha, capsys)

        assert report["stale"] == [VERIFIER]
        assert report["code"] == vdc.EXIT_DIFFERS

    def test_a_file_the_pull_request_and_the_base_changed_alike_is_not_reported(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {HELPER: "X = 2\n"})
        write(base, HELPER, "X = 2\n")
        commit_on_base(base, "main makes the same change")

        report = check(base, upstream, sha, capsys)

        assert report["changed"] == []
        assert report["stale"] == []
        assert report["code"] == vdc.EXIT_OK

    def test_stale_output_tells_the_author_to_merge_the_base_ref(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        write(base, HELPER, "X = 2\n")
        commit_on_base(base, "main moves the helper")
        argv = ["--tool-root", str(base), "--head-sha", sha, "--pull-number", "1"]

        code = vdc.main([*argv, "--remote", str(upstream)])
        out = capsys.readouterr().out

        assert code == vdc.EXIT_DIFFERS
        assert f"dispatch-closure: STALE {HELPER}" in out
        assert "merge the base ref" in out

    def test_a_file_the_pull_request_edits_is_reported_when_the_base_moved_it_too(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {HELPER: "X = 3\n"})
        write(base, HELPER, "X = 2\n")
        commit_on_base(base, "main moves the helper")

        report = check(base, upstream, sha, capsys)

        assert report["changed"] == [HELPER]
        assert report["code"] == vdc.EXIT_DIFFERS

    def test_an_edit_to_one_file_is_reported_while_a_base_move_of_another_is_not(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {VERIFIER: "import helper\n# edit\n"})
        write(base, HELPER, "X = 2\n")
        commit_on_base(base, "main moves the helper")

        report = check(base, upstream, sha, capsys)

        assert report["changed"] == [VERIFIER]

    def test_a_file_the_base_deleted_is_stale_not_new(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        (base / HELPER).unlink()
        commit_on_base(base, "main deletes the helper")

        report = check(base, upstream, sha, capsys)

        assert report["added"] == []
        assert report["stale"] == [HELPER]
        assert report["code"] == vdc.EXIT_DIFFERS

    def test_a_file_the_pull_request_adds_is_still_new(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(
            base,
            {
                VERIFIER: "import helper\nimport extra\n",
                ".claude/skills/demo/scripts/extra.py": "Y = 2\n",
            },
        )
        write(base, "README.md", "main moved\n")
        commit_on_base(base, "main moves an unrelated file")

        report = check(base, upstream, sha, capsys)

        assert report["added"] == [".claude/skills/demo/scripts/extra.py"]
        assert report["changed"] == [VERIFIER]

    def test_a_verifier_the_base_config_gained_is_stale_not_removed(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        config = {
            "scripts": {
                "claude_code": {
                    "go": f"python3 {VERIFIER} --pull-request {{number}}",
                    "next": f"python3 {SECOND} --pull-request {{number}}",
                }
            },
            "completion_criteria": [],
        }
        write(base, CONFIG, yaml.safe_dump(config))
        write(base, SECOND, "Z = 1\n")
        commit_on_base(base, "main gains a verifier")

        report = check(base, upstream, sha, capsys)

        assert report["removed"] == []
        assert report["changed"] == []
        assert report["stale"] == sorted([CONFIG, SECOND])
        assert report["code"] == vdc.EXIT_DIFFERS

    def test_a_verifier_the_pull_request_deletes_is_still_removed(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream = base.parent / "upstream"
        upstream_with_pr(base, {"README.md": "x\n"})
        git(upstream, "rm", "-q", VERIFIER)
        git(
            upstream,
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "delete",
        )
        sha = rev(upstream)
        git(upstream, "update-ref", "refs/pull/1/head", sha)
        write(base, "README.md", "main moved\n")
        commit_on_base(base, "main moves an unrelated file")

        report = check(base, upstream, sha, capsys)

        assert report["removed"] == [VERIFIER]

    def test_a_symlink_the_base_removed_is_stale_not_added(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        os.symlink("README.md", base / "link")
        commit_on_base(base, "main has a symlink")
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        (base / "link").unlink()
        commit_on_base(base, "main removes the symlink")

        report = check(base, upstream, sha, capsys)

        assert report["symlinks"] == []
        assert report["stale"] == ["link"]
        assert report["code"] == vdc.EXIT_DIFFERS

    def test_a_symlink_the_pull_request_adds_is_still_reported(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        os.symlink("README.md", upstream / "link")
        git(upstream, "add", "-A")
        git(
            upstream,
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "link",
        )
        sha = rev(upstream)
        git(upstream, "update-ref", "refs/pull/1/head", sha)
        write(base, "README.md", "main moved\n")
        commit_on_base(base, "main moves an unrelated file")

        report = check(base, upstream, sha, capsys)

        assert report["symlinks"] == ["link"]

    def test_a_symlink_the_pull_request_retargets_is_still_reported(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        os.symlink("README.md", base / "link")
        commit_on_base(base, "main has a symlink")
        upstream, _sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        (upstream / "link").unlink()
        os.symlink(VERIFIER, upstream / "link")
        git(upstream, "add", "-A")
        git(
            upstream,
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "retarget",
        )
        sha = rev(upstream)
        git(upstream, "update-ref", "refs/pull/1/head", sha)
        (base / "link").unlink()
        commit_on_base(base, "main removes the symlink")

        report = check(base, upstream, sha, capsys)

        assert report["symlinks"] == ["link"]

    def test_a_base_symlink_the_pull_request_retargets_is_reported(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A path match against the base ref tip must not hide a new target."""
        base, _ = trees
        os.symlink("README.md", base / "link")
        commit_on_base(base, "main has a symlink")
        upstream, _sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        (upstream / "link").unlink()
        os.symlink(VERIFIER, upstream / "link")
        git(upstream, "add", "-A")
        git(
            upstream,
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "-m",
            "retarget",
        )
        sha = rev(upstream)
        git(upstream, "update-ref", "refs/pull/1/head", sha)

        report = check(base, upstream, sha, capsys)

        assert report["symlinks"] == ["link"]
        assert report["code"] == vdc.EXIT_DIFFERS


class TestMergeBase:
    def test_no_head_commit_means_no_merge_base(self, trees: tuple[Path, Path]) -> None:
        base, _ = trees

        assert vdc._merge_bases(base, "HEAD", None) == []

    def test_an_unknown_commit_means_no_merge_base(self, trees: tuple[Path, Path]) -> None:
        base, _ = trees

        assert vdc._merge_bases(base, "HEAD", "a" * 40) == []

    def test_the_merge_base_is_the_commit_the_head_branched_from(
        self, trees: tuple[Path, Path], tmp_path: Path
    ) -> None:
        base, _ = trees
        branch_point = rev(base)
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        write(base, "README.md", "main moved\n")
        commit_on_base(base, "main moves")
        vdc.materialize_head(base, 1, sha, tmp_path / "out", remote=str(upstream))

        assert vdc._merge_bases(base, "HEAD", sha) == [branch_point]

    def test_without_a_merge_base_the_comparison_falls_back_to_the_base_ref(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A shallow checkout cannot find the fork point; the check must fail closed."""
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        write(base, HELPER, "X = 2\n")
        commit_on_base(base, "main moves the helper")

        with mock.patch.object(vdc, "_merge_bases", return_value=[]):
            report = check(base, upstream, sha, capsys)

        assert report["changed"] == [HELPER]
        assert report["code"] == vdc.EXIT_DIFFERS

    def test_a_head_given_as_a_work_tree_is_compared_with_the_base_ref_alone(
        self, trees: tuple[Path, Path]
    ) -> None:
        base, head = trees
        write(base, HELPER, "X = 2\n")
        commit_on_base(base, "main moves the helper")

        report = vdc.verify(base, head, "HEAD")

        assert report.changed == [HELPER]
