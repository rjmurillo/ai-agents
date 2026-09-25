"""Tests for scripts/metrics/sg_diff_producer.py (#5856, REQ-5, REQ-7): the
producer's fallback wiring and the read-time tool's re-verification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.metrics import sg_diff_artifact as sgda
from scripts.metrics import sg_diff_producer as sgdp
from scripts.metrics import sg_diff_reference as sgd

# --- produce_prompt: happy path and fallback wiring --------------------------


def test_produce_prompt_inline_mode_matches_build_inline_prompt(tmp_path: Path) -> None:
    touched = ["a.py"]
    diff_files = [("a.py", "+x\n")]
    prompt, outcome = sgdp.produce_prompt(
        "inline", tmp_path / "store", "5" * 64, "head1", touched, diff_files, ""
    )

    assert prompt == sgd.build_inline_prompt(touched, diff_files, "")
    assert outcome == sgdp.ProducerOutcome(mode_used="inline", fallback_reason=None, ref=None)


def test_produce_prompt_referenced_mode_writes_and_resolves(tmp_path: Path) -> None:
    touched = ["a.py"]
    diff_files = [("a.py", "+x\n")]
    store_dir = tmp_path / "store"

    prompt, outcome = sgdp.produce_prompt(
        "referenced", store_dir, "6" * 64, "head1", touched, diff_files, ""
    )

    assert outcome.mode_used == "referenced"
    assert outcome.fallback_reason is None
    assert outcome.ref is not None
    assert prompt == sgdp.build_referenced_prompt(touched, outcome.ref, "")
    assert prompt != sgd.build_inline_prompt(touched, diff_files, "")


def test_produce_prompt_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        sgdp.produce_prompt("bogus", tmp_path / "store", "7" * 64, "head1", [], [], "")


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

    monkeypatch.setattr(sgdp, "resolve", _fake_resolve)

    prompt, outcome = sgdp.produce_prompt(
        "referenced", store_dir, "8" * 64, "head1", touched, diff_files, ""
    )

    assert prompt == sgd.build_inline_prompt(touched, diff_files, "")
    assert outcome.mode_used == "inline"
    assert outcome.fallback_reason == reason
    assert outcome.ref is not None  # the artifact was written; only resolution failed


@pytest.mark.parametrize(
    "write_error",
    [
        OSError("simulated full disk"),
        ValueError("write_artifact: repo_id must be 64 lowercase hex chars, got 'bad'"),
    ],
)
def test_produce_prompt_falls_back_to_exact_inline_when_write_artifact_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_error: Exception
) -> None:
    """REQ-5's fallback covers a failed write, not only a failed resolve: a
    full disk or permission error raises OSError from write_artifact's
    os.replace/mkdir, and a malformed repo_id raises ValueError from its
    _HEX64_RE guard. Both must fall back to the exact inline prompt with
    fallback_reason="write_failed", never propagate, and never reach
    resolve() (there is no ref to resolve).
    """
    touched = ["a.py"]
    diff_files = [("a.py", "+x\n")]
    store_dir = tmp_path / "store"

    def _fake_write_artifact(*_args: object, **_kwargs: object) -> sgda.ArtifactRef:
        raise write_error

    monkeypatch.setattr(sgdp, "write_artifact", _fake_write_artifact)

    prompt, outcome = sgdp.produce_prompt(
        "referenced", store_dir, "a" * 64, "head1", touched, diff_files, ""
    )

    assert prompt == sgd.build_inline_prompt(touched, diff_files, "")
    assert outcome.mode_used == "inline"
    assert outcome.fallback_reason == "write_failed"
    assert outcome.ref is None


# --- serve_artifact_tool -----------------------------------------------------


def test_serve_artifact_tool_returns_resolved_text_on_success(tmp_path: Path) -> None:
    store_dir = tmp_path / "store"
    repo_id = "9" * 64
    ref = sgda.write_artifact(store_dir, repo_id, "head1", "the diff", ["f.py"], 0)

    served = sgdp.serve_artifact_tool(store_dir, ref, repo_id, "head1", "INLINE FALLBACK")

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

    served = sgdp.serve_artifact_tool(
        store_dir, ref, expected_repo_id, expected_head, "INLINE FALLBACK"
    )

    assert served == "INLINE FALLBACK"


def test_serve_artifact_tool_reports_outcome_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_dir = tmp_path / "store"
    ref = sgda.write_artifact(store_dir, "b1" * 32, "head1", "the diff", ["f.py"], 0)

    sgdp.serve_artifact_tool(store_dir, ref, "b1" * 32, "head1", "INLINE FALLBACK")
    sgdp.serve_artifact_tool(store_dir, ref, "wrong" * 12 + "aaaa", "head1", "INLINE FALLBACK")

    captured = capsys.readouterr()
    assert "read_diff_artifact ok" in captured.err
    assert "read_diff_artifact fallback reason=" in captured.err


def test_produce_prompt_falls_back_to_inline_where_no_follow_writes_are_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sgda, "_NO_FOLLOW_WRITES_SUPPORTED", False)
    touched = ["a.py"]
    diff_files = [("a.py", "+x\n")]

    prompt, outcome = sgdp.produce_prompt(
        "referenced", tmp_path / "store", "a" * 64, "head1", touched, diff_files, ""
    )

    assert prompt == sgd.build_inline_prompt(touched, diff_files, "")
    assert outcome.fallback_reason == "write_failed"
