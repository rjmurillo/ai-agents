"""doc-accuracy gate output through the /review local-axis adapter.

A branch that deletes or renames a Markdown file must adapt to PASS on a
clean run. Before the fix, the old path sat in ``changed_files``, the
adapter saw a partial inventory, and the axis reported UNKNOWN, which
blocks the /review PASS marker.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HELPERS_DIR = str(Path(__file__).resolve().parent)
sys.path.insert(0, _HELPERS_DIR)
try:
    from diff_scope_helpers import commit, git, make_repo, mod
finally:
    # Drop the entry so the helper path does not leak into later test modules.
    sys.path.remove(_HELPERS_DIR)

from scripts.ai_review_common.verdict import adapt_local_axis_verdict


def _run_gate(repo: Path, out_dir: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    rc = mod.main(
        [
            "--target",
            str(repo),
            "--diff-base",
            "HEAD~1",
            "--format",
            "gate",
            "--output-dir",
            str(out_dir),
        ]
    )
    return rc, capsys.readouterr().out


def test_delete_and_edit_adapts_to_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path, {"kept.md": "# Kept\n", "gone.md": "# Gone\n"})
    (repo / "gone.md").unlink()
    (repo / "kept.md").write_text("# Kept, edited\n", encoding="utf-8")
    commit(repo, "delete one doc, edit another")

    rc, output = _run_gate(repo, tmp_path / "out", capsys)

    assert rc == 0
    assert json.loads(output)["assessment"]["changed_files"] == ["kept.md"]
    assert adapt_local_axis_verdict("doc-accuracy", output, rc) == "PASS"


def test_rename_adapts_to_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``--no-renames`` reports a rename as delete plus add; only the new path counts."""
    repo = make_repo(tmp_path, {"old.md": "# Doc\n"})
    git(repo, "mv", "old.md", "new.md")
    commit(repo, "rename doc")

    rc, output = _run_gate(repo, tmp_path / "out", capsys)

    assert rc == 0
    assert json.loads(output)["assessment"]["changed_files"] == ["new.md"]
    assert adapt_local_axis_verdict("doc-accuracy", output, rc) == "PASS"


def test_deletion_only_diff_stays_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Edge: a diff that only deletes docs inventories nothing, so no PASS."""
    repo = make_repo(tmp_path, {"gone.md": "# Gone\n"})
    (repo / "gone.md").unlink()
    commit(repo, "delete the only doc")

    rc, output = _run_gate(repo, tmp_path / "out", capsys)

    assert rc == 0
    assert json.loads(output)["assessment"]["changed_files"] == []
    assert adapt_local_axis_verdict("doc-accuracy", output, rc) == "UNKNOWN"
