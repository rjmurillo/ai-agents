"""Tests for scripts/metrics/sg_diff_artifact.py (#5856, REQ-5, REQ-7): the
content-addressed artifact store's write/resolve/produce/serve contract.

Split out of ``tests/metrics/test_sg_diff_reference.py`` alongside the source
split (taste-lints file-size gate). Prompt-building and capping tests stay in
that sibling file. The round-trip equivalence tests (diff-line semantics and
context-note survival between inline and referenced/resolved prompts) and the
``prune`` tests are further split into
``tests/metrics/test_sg_diff_artifact_equivalence.py`` to stay under the same
gate.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from scripts.metrics import sg_diff_artifact as sgda

# --- write_artifact / resolve happy path and permissions -------------------


def test_write_artifact_then_resolve_round_trips(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    ref = sgda.write_artifact(store_dir, "a" * 64, "deadbeef", "hello diff", ["f.py"], 0)

    resolution = sgda.resolve(store_dir, ref, "a" * 64, "deadbeef")

    assert resolution.ok
    assert resolution.reason == "ok"
    assert resolution.text == "hello diff"


def test_write_artifact_sets_directory_and_file_permissions(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    repo_id = "b" * 64
    ref = sgda.write_artifact(store_dir, repo_id, "head1", "content", ["f.py"], 0)

    repo_dir = store_dir / repo_id
    artifact = repo_dir / f"{ref.sha256}.diff"

    assert stat.S_IMODE(repo_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(artifact.stat().st_mode) == 0o600


def test_write_artifact_cleans_up_temp_file_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store_dir = tmp_path / "store"

    def _boom(_src: object, _dst: object, **_dir_fds: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(sgda.os, "replace", _boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        sgda.write_artifact(store_dir, "9" * 64, "head1", "content", ["f.py"], 0)

    leftover = list((store_dir / ("9" * 64)).glob(".tmp-*"))
    assert leftover == []


def test_write_artifact_rejects_non_hex_repo_id(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"

    with pytest.raises(ValueError, match="repo_id must be 64 lowercase hex"):
        sgda.write_artifact(store_dir, "g" * 64, "head1", "content", ["f.py"], 0)

    # No path was built or created from the rejected repo_id: reject before
    # any mkdir/chmod, the same CWE-22 ordering `resolve` already applies.
    assert not store_dir.exists()


def test_write_artifact_rejects_traversal_repo_id(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"

    with pytest.raises(ValueError, match="repo_id must be 64 lowercase hex"):
        sgda.write_artifact(
            store_dir, "../../../etc/passwd" + "a" * 45, "head1", "content", ["f.py"], 0
        )

    assert not (tmp_path / "etc").exists()


def test_write_artifact_is_content_addressed_idempotent(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    repo_id = "c" * 64

    ref1 = sgda.write_artifact(store_dir, repo_id, "head1", "same diff text", ["f.py"], 0)
    ref2 = sgda.write_artifact(store_dir, repo_id, "head1", "same diff text", ["f.py"], 0)

    assert ref1.sha256 == ref2.sha256
    artifacts = list((store_dir / repo_id).glob("*.diff"))
    assert len(artifacts) == 1


# --- resolve: each failure reason, driven directly --------------------------


def test_resolve_missing_when_artifact_never_written(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    fake = sgda.ArtifactRef(
        sha256="a" * 64,
        size=5,
        repo_id="b" * 64,
        head="head1",
        path_order_sha256="c" * 64,
        truncated_bytes=0,
    )

    resolution = sgda.resolve(store_dir, fake, "b" * 64, "head1")

    assert resolution == sgda.Resolution(ok=False, text=None, reason="missing")


def test_resolve_unreadable_on_permission_denied(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    repo_id = "d" * 64
    ref = sgda.write_artifact(store_dir, repo_id, "head1", "secret diff", ["f.py"], 0)
    artifact = store_dir / repo_id / f"{ref.sha256}.diff"
    os.chmod(artifact, 0)

    try:
        resolution = sgda.resolve(store_dir, ref, repo_id, "head1")
    finally:
        os.chmod(artifact, 0o600)  # restore so tmp_path cleanup can remove it

    if os.geteuid() == 0:
        pytest.skip("running as root; chmod 0 does not deny root read access")
    assert resolution.reason == "unreadable"
    assert resolution.ok is False


def test_resolve_unreadable_when_artifact_path_is_a_symlink(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    repo_id = "e" * 64
    real_ref = sgda.write_artifact(store_dir, repo_id, "head1", "real diff", ["f.py"], 0)
    decoy = sgda.write_artifact(store_dir, repo_id, "head1", "decoy diff content!", ["f.py"], 0)
    decoy_path = store_dir / repo_id / f"{decoy.sha256}.diff"
    real_path = store_dir / repo_id / f"{real_ref.sha256}.diff"
    real_path.unlink()
    real_path.symlink_to(decoy_path)

    resolution = sgda.resolve(store_dir, real_ref, repo_id, "head1")

    assert resolution == sgda.Resolution(ok=False, text=None, reason="unreadable")


def test_resolve_tampered_when_bytes_change_same_length(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    repo_id = "f" * 64
    ref = sgda.write_artifact(store_dir, repo_id, "head1", "0123456789", ["f.py"], 0)
    artifact = store_dir / repo_id / f"{ref.sha256}.diff"
    artifact.write_bytes(b"9876543210")  # same length, different bytes -> sha mismatch

    resolution = sgda.resolve(store_dir, ref, repo_id, "head1")

    assert resolution == sgda.Resolution(ok=False, text=None, reason="tampered")


def test_resolve_tampered_on_size_mismatch(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    repo_id = "0" * 64
    ref = sgda.write_artifact(store_dir, repo_id, "head1", "0123456789", ["f.py"], 0)
    artifact = store_dir / repo_id / f"{ref.sha256}.diff"
    artifact.write_bytes(artifact.read_bytes() + b"EXTRA")

    resolution = sgda.resolve(store_dir, ref, repo_id, "head1")

    assert resolution.ok is False
    assert resolution.reason == "tampered"


def test_resolve_cross_repo_when_repo_id_mismatches(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    ref = sgda.write_artifact(store_dir, "1" * 64, "head1", "content", ["f.py"], 0)

    resolution = sgda.resolve(store_dir, ref, "2" * 64, "head1")

    assert resolution == sgda.Resolution(ok=False, text=None, reason="cross_repo")


def test_resolve_stale_when_head_mismatches(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    ref = sgda.write_artifact(store_dir, "3" * 64, "head1", "content", ["f.py"], 0)

    resolution = sgda.resolve(store_dir, ref, "3" * 64, "head2")

    assert resolution == sgda.Resolution(ok=False, text=None, reason="stale")


@pytest.mark.parametrize(
    "bad_sha256,bad_repo_id",
    [
        ("../../../etc/passwd" + "a" * 45, "4" * 64),
        ("4" * 64, "../../../etc/passwd" + "a" * 45),
        ("not-hex" * 8, "4" * 64),
        ("4" * 63, "4" * 64),  # too short
    ],
)
def test_resolve_invalid_ref_rejects_traversal_and_malformed_hex(
    tmp_path: Path, bad_sha256: str, bad_repo_id: str
) -> None:
    store_dir = tmp_path / "store"
    fake = sgda.ArtifactRef(
        sha256=bad_sha256,
        size=1,
        repo_id=bad_repo_id,
        head="head1",
        path_order_sha256="4" * 64,
        truncated_bytes=0,
    )

    resolution = sgda.resolve(store_dir, fake, "4" * 64, "head1")

    assert resolution == sgda.Resolution(ok=False, text=None, reason="invalid_ref")
    # No file was created anywhere store_dir's parents could reach via traversal.
    assert not (tmp_path / "etc").exists()


def test_write_artifact_refuses_a_preexisting_directory_open_to_other_users(
    tmp_path: Path,
) -> None:
    store_dir = tmp_path / "store"
    repo_id = "c" * 64
    open_dir = store_dir / repo_id
    open_dir.mkdir(parents=True)
    open_dir.chmod(0o755)

    with pytest.raises(PermissionError, match="readable by other users"):
        sgda.write_artifact(store_dir, repo_id, "head1", "diff", ["f.py"], 0)
    assert list(open_dir.iterdir()) == []


def test_write_artifact_refuses_a_symlinked_repo_directory(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    repo_id = "d" * 64
    (store_dir / repo_id).symlink_to(outside, target_is_directory=True)

    with pytest.raises(PermissionError, match="is a symlink"):
        sgda.write_artifact(store_dir, repo_id, "head1", "private diff", ["f.py"], 0)
    assert list(outside.iterdir()) == []


def test_write_artifact_no_follow_open_blocks_a_symlink_swapped_in_after_the_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    repo_id = "e" * 64
    (store_dir / repo_id).symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(sgda.Path, "is_symlink", lambda _self: False)

    with pytest.raises(OSError):
        sgda.write_artifact(store_dir, repo_id, "head1", "private diff", ["f.py"], 0)
    assert list(outside.iterdir()) == []



def test_write_artifact_raises_oserror_where_no_follow_writes_are_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sgda, "_NO_FOLLOW_WRITES_SUPPORTED", False)
    store_dir = tmp_path / "store"

    with pytest.raises(OSError, match="unsupported"):
        sgda.write_artifact(store_dir, "f" * 64, "head1", "diff", ["f.py"], 0)
    assert not store_dir.exists()
