"""The head fetch of verify_dispatch_closure.py is depth-limited (issue #6506).

The check runs under pull_request_target and fetches a ref the PR author controls.
A bounded depth caps the commits that one fork can make the runner download.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from scripts.ci import verify_dispatch_closure as vdc
from tests.ci.dispatch_closure_helpers import HELPER, rev, upstream_with_pr


def _fetch_args(spy: mock.Mock) -> list[str]:
    seen = [list(c.args[0]) for c in spy.call_args_list]
    return next(c for c in seen if "fetch" in c)


def test_the_head_fetch_carries_the_depth_limit(
    trees: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, _ = trees
    upstream, sha = upstream_with_pr(base, {HELPER: "X = 99\n"})
    spy = mock.Mock(wraps=subprocess.run)
    monkeypatch.setattr(vdc.subprocess, "run", spy)

    vdc.materialize_head(base, 1, sha, tmp_path / "out", remote=str(upstream))

    assert f"--depth={vdc.HEAD_FETCH_DEPTH}" in _fetch_args(spy)


def test_a_head_within_the_limit_still_has_a_merge_base(
    trees: tuple[Path, Path], tmp_path: Path
) -> None:
    """Positive: the bound must not break the STALE labelling that #6418 added."""
    base, _ = trees
    upstream, sha = upstream_with_pr(base, {HELPER: "X = 99\n"})

    vdc.materialize_head(base, 1, sha, tmp_path / "out", remote=str(upstream))

    assert vdc._merge_base(base, "HEAD", sha) == rev(base)


def test_a_head_beyond_the_limit_loses_the_merge_base_but_still_materializes(
    trees: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edge: past the bound the label degrades to None. The files are still written."""
    base, _ = trees
    upstream, sha = upstream_with_pr(base, {HELPER: "X = 99\n"})
    monkeypatch.setattr(vdc, "HEAD_FETCH_DEPTH", 1)
    dest = tmp_path / "out"

    vdc.materialize_head(base, 1, sha, dest, remote=str(upstream))

    assert (dest / HELPER).read_text(encoding="utf-8") == "X = 99\n"
    assert vdc._merge_base(base, "HEAD", sha) is None
