"""STALE alone exits 0; STALE with any blocking finding still exits 1 (issue #6472).

A pull request cannot be required to sit on the latest base, so a file the base
moved after the branch point is reported STALE and does not fail by itself.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.ci import verify_dispatch_closure as vdc
from tests.ci.dispatch_closure_helpers import (
    HELPER,
    VERIFIER,
    git,
    rev,
    upstream_with_pr,
    write,
)


def commit_on_base(base: Path, message: str) -> None:
    git(base, "add", "-A")
    git(base, "commit", "-q", "-m", message)


def check(base: Path, upstream: Path, sha: str, capsys: pytest.CaptureFixture[str]) -> dict:
    argv = ["--tool-root", str(base), "--head-sha", sha, "--pull-number", "1"]
    code = vdc.main([*argv, "--remote", str(upstream), "--json"])
    report = json.loads(capsys.readouterr().out)
    report["code"] = code
    return report


class TestStaleWithABlockingFinding:
    def test_stale_plus_a_differing_file_still_fails(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {VERIFIER: "import helper\n# edited\n"})
        write(base, HELPER, "X = 2\n")
        commit_on_base(base, "main moves the helper")

        report = check(base, upstream, sha, capsys)

        assert report["stale"] == [HELPER]
        assert report["changed"] == [VERIFIER]
        assert report["code"] == vdc.EXIT_DIFFERS

    def test_stale_plus_a_new_symlink_still_fails(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {"README.md": "pull request\n"})
        write(base, HELPER, "X = 2\n")
        commit_on_base(base, "main moves the helper")
        upstream = upstream
        os.symlink("README.md", upstream / "alias.py")
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
            "add symlink",
        )
        sha = rev(upstream)
        git(upstream, "update-ref", "refs/pull/1/head", sha)

        report = check(base, upstream, sha, capsys)

        assert report["stale"] == [HELPER]
        assert report["symlinks"] == ["alias.py"]
        assert report["code"] == vdc.EXIT_DIFFERS


@pytest.mark.parametrize("category", ["changed", "removed", "added", "symlinks", "unresolved"])
def test_stale_plus_each_blocking_category_is_not_clean(category: str) -> None:
    report = vdc.Report(stale=["x"])
    getattr(report, category).append("y")

    assert not report.clean


def test_stale_alone_is_clean() -> None:
    assert vdc.Report(stale=["x"]).clean
