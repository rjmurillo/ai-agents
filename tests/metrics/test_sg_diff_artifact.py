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
from scripts.metrics import sg_diff_reference as sgd

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

    def _boom(_src: object, _dst: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(sgda.os, "replace", _boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        sgda.write_artifact(store_dir, "g" * 64, "head1", "content", ["f.py"], 0)

    leftover = list((store_dir / ("g" * 64)).glob(".tmp-*"))
    assert leftover == []


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


# --- produce_prompt: happy path and fallback wiring --------------------------


def test_produce_prompt_inline_mode_matches_build_inline_prompt(tmp_path: Path) -> None:
    touched = ["a.py"]
    diff_files = [("a.py", "+x\n")]
    prompt, outcome = sgda.produce_prompt(
        "inline", tmp_path / "store", "5" * 64, "head1", touched, diff_files, ""
    )

    assert prompt == sgd.build_inline_prompt(touched, diff_files, "")
    assert outcome == sgda.ProducerOutcome(mode_used="inline", fallback_reason=None, ref=None)


def test_produce_prompt_referenced_mode_writes_and_resolves(tmp_path: Path) -> None:
    touched = ["a.py"]
    diff_files = [("a.py", "+x\n")]
    store_dir = tmp_path / "store"

    prompt, outcome = sgda.produce_prompt(
        "referenced", store_dir, "6" * 64, "head1", touched, diff_files, ""
    )

    assert outcome.mode_used == "referenced"
    assert outcome.fallback_reason is None
    assert outcome.ref is not None
    assert prompt == sgda.build_referenced_prompt(touched, outcome.ref, "")
    assert prompt != sgd.build_inline_prompt(touched, diff_files, "")


def test_produce_prompt_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        sgda.produce_prompt("bogus", tmp_path / "store", "7" * 64, "head1", [], [], "")


@pytest.mark.parametrize(
    "reason", ["missing", "unreadable", "tampered", "cross_repo", "stale", "invalid_ref"]
)
def test_produce_prompt_falls_back_to_exact_inline_on_every_resolve_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    """Proves the wiring: whatever reason resolve() reports, produce_prompt's
    fallback path returns the byte-identical inline prompt (REQ-5). Each
    reason string is independently proven reachable by the direct resolve()
    tests above; this test proves produce_prompt reacts identically to all of
    them, not merely to the one or two easiest to reproduce end to end.
    """
    touched = ["a.py"]
    diff_files = [("a.py", "+x\n")]
    store_dir = tmp_path / "store"

    def _fake_resolve(*_args: object, **_kwargs: object) -> sgda.Resolution:
        return sgda.Resolution(ok=False, text=None, reason=reason)

    monkeypatch.setattr(sgda, "resolve", _fake_resolve)

    prompt, outcome = sgda.produce_prompt(
        "referenced", store_dir, "8" * 64, "head1", touched, diff_files, ""
    )

    assert prompt == sgd.build_inline_prompt(touched, diff_files, "")
    assert outcome.mode_used == "inline"
    assert outcome.fallback_reason == reason
    assert outcome.ref is not None  # the artifact was written; only resolution failed


# --- serve_artifact_tool -----------------------------------------------------


def test_serve_artifact_tool_returns_resolved_text_on_success(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    repo_id = "9" * 64
    ref = sgda.write_artifact(store_dir, repo_id, "head1", "the diff", ["f.py"], 0)

    served = sgda.serve_artifact_tool(store_dir, ref, repo_id, "head1", "INLINE FALLBACK")

    assert served == "the diff"


@pytest.mark.parametrize(
    "expected_repo_id,expected_head",
    [("a1" * 32, "head1"), ("a2" * 32, "wrong-head")],
)
def test_serve_artifact_tool_falls_back_to_inline_text_on_failure(
    tmp_path: Path, expected_repo_id: str, expected_head: str
) -> None:
    store_dir = tmp_path / "store"
    ref = sgda.write_artifact(store_dir, "a2" * 32, "head1", "the diff", ["f.py"], 0)

    served = sgda.serve_artifact_tool(
        store_dir, ref, expected_repo_id, expected_head, "INLINE FALLBACK"
    )

    assert served == "INLINE FALLBACK"


def test_serve_artifact_tool_reports_outcome_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_dir = tmp_path / "store"
    ref = sgda.write_artifact(store_dir, "b1" * 32, "head1", "the diff", ["f.py"], 0)

    sgda.serve_artifact_tool(store_dir, ref, "b1" * 32, "head1", "INLINE FALLBACK")
    sgda.serve_artifact_tool(store_dir, ref, "wrong" * 12 + "aaaa", "head1", "INLINE FALLBACK")

    captured = capsys.readouterr()
    assert "read_diff_artifact ok" in captured.err
    assert "read_diff_artifact fallback reason=" in captured.err
