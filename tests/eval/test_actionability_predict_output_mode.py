"""predict creates its output owner-only (review finding 11)."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.eval._actionability_arms_test_support import (
    FakeCallApi,
    aa,
    heldout_rows,
    install_call_api,
    ok_record,
    pm,
    provider_argv,
    write_corpus_file,
    write_jsonl_file,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


@pytest.fixture
def open_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Record the (flags, mode) of every os.open predict makes, then call the real one."""
    seen: list[tuple[int, int]] = []
    real_open = os.open

    def recording_open(path: str | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        seen.append((flags, mode))
        return real_open(path, flags, mode)

    monkeypatch.setattr(pm.os, "open", recording_open)
    return seen


@pytest.fixture
def wide_umask() -> Iterator[None]:
    """Umask 0, the widest case: only an explicit mode keeps the file private."""
    previous = os.umask(0)
    try:
        yield
    finally:
        os.umask(previous)


def _predict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    install_call_api(monkeypatch, FakeCallApi())
    out = tmp_path / "out" / "pred.jsonl"
    code = aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(2)), out))
    assert code == 0
    return out


class TestOutputMode:
    def test_first_creation_asks_for_owner_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, open_calls: list[tuple[int, int]]
    ) -> None:
        """Platform neutral: the call carries mode 0o600 with create and append flags."""
        _predict(tmp_path, monkeypatch)

        (flags, mode) = open_calls[0]
        assert mode == 0o600
        assert flags & os.O_CREAT
        assert flags & os.O_APPEND

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
    def test_file_mode_is_0600_even_under_a_zero_umask(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wide_umask: None
    ) -> None:
        out = _predict(tmp_path, monkeypatch)

        assert stat.S_IMODE(out.stat().st_mode) == 0o600

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
    def test_a_resumed_file_stays_owner_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wide_umask: None
    ) -> None:
        """Edge: resume rewrites the carried records and appends, and never widens the mode."""
        install_call_api(monkeypatch, FakeCallApi())
        out = write_jsonl_file(tmp_path / "pred.jsonl", [ok_record("H0")])
        out.chmod(0o644)

        code = aa.main(provider_argv(write_corpus_file(tmp_path, heldout_rows(2)), out))

        assert code == 0
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
