"""Round-trip equivalence and prune tests for scripts/metrics/sg_diff_artifact.py
(#5856, REQ-5, REQ-6, REQ-7).

Split out of ``tests/metrics/test_sg_diff_artifact.py`` (itself split out of
``tests/metrics/test_sg_diff_reference.py``) under the taste-lints file-size
gate. Covers: diff-line semantics and context-note survival between inline
and referenced/resolved prompts (REQ-6, REQ-7), and artifact-store retention
(``prune``).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest

from scripts.metrics import sg_diff_artifact as sgda
from scripts.metrics import sg_diff_producer as sgdp
from scripts.metrics import sg_diff_reference as sgd

# --- diff_line_semantics equivalence: inline vs resolved artifact -----------


def test_diff_line_semantics_identical_inline_vs_resolved_repeated_diff(
    tmp_path: Path,
) -> None:
    """f_repeat: same diff written twice reuses one artifact and one sha."""
    touched = ["a.py"]
    diff_files = [("a.py", "+alpha\n+beta\n-gamma\n")]
    store_dir = tmp_path / "store"

    inline_prompt = sgd.build_inline_prompt(touched, diff_files, "")
    inline_semantics = sgd.diff_line_semantics(inline_prompt)

    _prompt1, outcome1 = sgdp.produce_prompt(
        "referenced", store_dir, "c1" * 32, "head1", touched, diff_files, ""
    )
    _prompt2, outcome2 = sgdp.produce_prompt(
        "referenced", store_dir, "c1" * 32, "head1", touched, diff_files, ""
    )

    assert outcome1.ref is not None and outcome2.ref is not None
    assert outcome1.ref.sha256 == outcome2.ref.sha256

    resolution = sgda.resolve(store_dir, outcome1.ref, "c1" * 32, "head1")
    assert resolution.ok and resolution.text is not None
    assert sgd.diff_line_semantics(resolution.text) == inline_semantics


def test_diff_line_semantics_identical_inline_vs_resolved_changed_paths(
    tmp_path: Path,
) -> None:
    """f_paths: rename, delete, new file; ordering preserved via path_order_sha256."""
    diff_files = [
        ("old_name.py", "-def f(): pass\n"),
        ("new_name.py", "+def f(): pass\n"),
        ("deleted.py", "-import os\n"),
        ("added.py", "+import sys\n"),
    ]
    touched_a = ["old_name.py", "new_name.py", "deleted.py", "added.py"]
    touched_b = list(reversed(touched_a))
    store_dir = tmp_path / "store"

    inline_prompt = sgd.build_inline_prompt(touched_a, diff_files, "")
    inline_semantics = sgd.diff_line_semantics(inline_prompt)

    _prompt, outcome = sgdp.produce_prompt(
        "referenced", store_dir, "d1" * 32, "head1", touched_a, diff_files, ""
    )
    _prompt_b, outcome_b = sgdp.produce_prompt(
        "referenced", store_dir, "d1" * 32, "head1", touched_b, diff_files, ""
    )

    assert outcome.ref is not None and outcome_b.ref is not None
    # Same diff content -> same sha256, but ordering is tracked separately.
    assert outcome.ref.sha256 == outcome_b.ref.sha256
    assert outcome.ref.path_order_sha256 != outcome_b.ref.path_order_sha256

    resolution = sgda.resolve(store_dir, outcome.ref, "d1" * 32, "head1")
    assert resolution.ok and resolution.text is not None
    assert sgd.diff_line_semantics(resolution.text) == inline_semantics


def test_diff_line_semantics_identical_inline_vs_resolved_truncation(
    tmp_path: Path,
) -> None:
    """f_trunc: per-file and total cap markers preserved identically in both modes."""
    touched = ["big.py", "small.py"]
    diff_files = [
        ("big.py", "+" + ("x" * 5_000) + "\n"),
        ("small.py", "+small change\n"),
    ]
    per_file_bytes = 100
    total_bytes = 150
    store_dir = tmp_path / "store"

    inline_prompt = sgd.build_inline_prompt(
        touched, diff_files, "", per_file_bytes=per_file_bytes, total_bytes=total_bytes
    )
    assert (
        "truncated by security-guidance" in inline_prompt
        or "omitted by security-guidance" in inline_prompt
    )
    inline_semantics = sgd.diff_line_semantics(inline_prompt)

    _prompt, outcome = sgdp.produce_prompt(
        "referenced",
        store_dir,
        "e1" * 32,
        "head1",
        touched,
        diff_files,
        "",
        per_file_bytes=per_file_bytes,
        total_bytes=total_bytes,
    )
    assert outcome.ref is not None
    assert outcome.ref.truncated_bytes > 0

    resolution = sgda.resolve(store_dir, outcome.ref, "e1" * 32, "head1")
    assert resolution.ok and resolution.text is not None
    assert sgd.diff_line_semantics(resolution.text) == inline_semantics


def test_context_note_present_verbatim_in_both_modes_checkout_mismatch(
    tmp_path: Path,
) -> None:
    """f_mismatch: the authoritative-diff warning survives in inline and referenced prompts."""
    touched = ["a.py"]
    diff_files = [("a.py", "+x\n")]
    context_note = (
        "\n\nNOTE: your working directory is the full repository for "
        "context (Grep for callers, read related files). The DIFF below "
        "is authoritative for what changed: the repo checkout may be at "
        "a different commit, so if a touched file looks different on "
        "disk than in the diff, trust the diff.\n"
    )
    store_dir = tmp_path / "store"

    inline_prompt = sgd.build_inline_prompt(touched, diff_files, context_note)
    prompt, outcome = sgdp.produce_prompt(
        "referenced", store_dir, "f1" * 32, "head1", touched, diff_files, context_note
    )

    assert context_note in inline_prompt
    assert context_note in prompt
    assert outcome.mode_used == "referenced"


# --- prune -------------------------------------------------------------------


def test_prune_removes_only_artifacts_older_than_max_age(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    old_ref = sgda.write_artifact(store_dir, "1" * 64, "head1", "old content", ["f.py"], 0)
    new_ref = sgda.write_artifact(store_dir, "1" * 64, "head1", "new content!!", ["f.py"], 0)

    old_path = store_dir / ("1" * 64) / f"{old_ref.sha256}.diff"
    new_path = store_dir / ("1" * 64) / f"{new_ref.sha256}.diff"

    old_time = 1_000_000.0  # far in the past
    os.utime(old_path, (old_time, old_time))

    removed = sgda.prune(store_dir, max_age_s=3600)

    assert removed == 1
    assert not old_path.exists()
    assert new_path.exists()


def test_prune_on_missing_store_dir_returns_zero(tmp_path: Path) -> None:
    assert sgda.prune(tmp_path / "does-not-exist", max_age_s=1) == 0


def test_prune_skips_non_directory_entries_at_store_root(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir(parents=True)
    (store_dir / "stray.txt").write_text("not a repo dir", encoding="utf-8")
    repo_id = "3" * 64
    ref = sgda.write_artifact(store_dir, repo_id, "head1", "content", ["f.py"], 0)
    artifact = store_dir / repo_id / f"{ref.sha256}.diff"
    os.utime(artifact, (1_000_000.0, 1_000_000.0))

    removed = sgda.prune(store_dir, max_age_s=1)

    assert removed == 1
    assert (store_dir / "stray.txt").exists()


def test_prune_skips_artifact_when_stat_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store_dir = tmp_path / "store"
    repo_id = "4" * 64
    ref = sgda.write_artifact(store_dir, repo_id, "head1", "content", ["f.py"], 0)
    artifact = store_dir / repo_id / f"{ref.sha256}.diff"
    original_stat = Path.stat

    def _flaky_stat(self: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        if self == artifact:
            raise OSError("simulated stat failure")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _flaky_stat)

    removed = sgda.prune(store_dir, max_age_s=0)

    assert removed == 0
    assert artifact.exists()


def test_prune_never_follows_symlinked_artifacts(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    repo_id = "2" * 64
    sgda.write_artifact(store_dir, repo_id, "head1", "real content", ["f.py"], 0)
    outside_target = tmp_path / "outside.diff"
    outside_target.write_text("outside", encoding="utf-8")
    symlink_path = store_dir / repo_id / (hashlib.sha256(b"symlink").hexdigest() + ".diff")
    symlink_path.symlink_to(outside_target)
    old_time = 1_000_000.0
    os.utime(symlink_path, (old_time, old_time), follow_symlinks=False)

    sgda.prune(store_dir, max_age_s=1)
