"""Size cap on the shared body-file reader (issue #6917).

GitHub refuses a body over 65536 characters, so the reader refuses a larger
file before any API call, and never reads much more than the cap into memory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.github_core.repo import REPO_ROOT_OK
from tests.containment_fixtures import _github_core_modules
from tests.test_body_file_reader_security import READERS, RefusedError

pytestmark = pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "getuid"),
    reason="owner and mode bits are POSIX only",
)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake repo root as the only approved root, with an owner-only drafts dir."""
    root = tmp_path.resolve() / "repo"
    (root / "drafts").mkdir(parents=True)
    (root / "drafts").chmod(0o700)
    for module in _github_core_modules("repo"):
        monkeypatch.setattr(module, "resolve_repo_root", lambda **_kwargs: (root, REPO_ROOT_OK))
    for module in _github_core_modules("validation"):
        monkeypatch.setattr(module, "_candidate_temp_roots", lambda: [])
        monkeypatch.setattr(module, "_candidate_git_dir_roots", lambda: [])
    monkeypatch.chdir(root)
    monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    return root


def _body(repo: Path, text: str) -> Path:
    path = repo / "drafts" / "body.md"
    path.write_text(text, encoding="utf-8", newline="")
    path.chmod(0o600)
    return path


def _readers():
    return list(_github_core_modules("body_file"))


def test_cap_matches_github_limit() -> None:
    for module in _readers():
        assert module.MAX_BODY_CHARS == 65536
        assert module.MAX_BODY_BYTES == 4 * 65536


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize(
    "text",
    ["", "x", "x" * 65536, "é" * 65536, "\U0001f600" * 65536],
    ids=["empty", "one-char", "ascii-at-cap", "two-byte-at-cap", "four-byte-at-cap"],
)
def test_accepts_body_at_or_under_the_cap(repo: Path, script: str, text: str) -> None:
    body = _body(repo, text)
    try:
        assert READERS[script](body, repo) == text
    except RefusedError:
        # Some scripts refuse an empty body after the reader returns it.
        assert text == "", script


@pytest.mark.parametrize("script", sorted(READERS))
@pytest.mark.parametrize(
    "text",
    ["x" * 65537, "é" * 65537, "x" * (4 * 65536 + 1)],
    ids=["one-char-over", "two-byte-one-char-over", "over-byte-cap"],
)
def test_refuses_body_over_the_cap(repo: Path, script: str, text: str) -> None:
    body = _body(repo, "## Summary\n" + text)
    with pytest.raises(RefusedError):
        READERS[script](body, repo)


def test_refuses_over_cap_with_a_clear_message(repo: Path) -> None:
    body = _body(repo, "x" * 65537)
    for module in _readers():
        with pytest.raises(ValueError, match="65536-character body limit"):
            module.read_body_file_text(str(body))


def test_refuses_over_byte_cap_before_reading(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file over the byte cap is refused from its size, so no read starts."""
    body = _body(repo, "x" * (4 * 65536 + 1))
    real_fdopen = os.fdopen

    def _no_read(*args, **kwargs):
        raise AssertionError("the reader opened the file for reading")

    for module in _readers():
        monkeypatch.setattr(module.os, "fdopen", _no_read)
        try:
            with pytest.raises(ValueError, match="body limit"):
                module.read_body_file_text(str(body))
        finally:
            monkeypatch.setattr(module.os, "fdopen", real_fdopen)


def test_refuses_a_file_that_grows_after_the_size_check(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stat says small, the read finds more: the char cap still refuses it."""
    body = _body(repo, "x" * 65537)
    for module in _readers():
        real_fstat = module.os.fstat

        def _small_fstat(descriptor: int, _real=real_fstat):
            result = _real(descriptor)
            fields = list(result)
            fields[6] = 10  # st_size
            return os.stat_result(fields)

        monkeypatch.setattr(module.os, "fstat", _small_fstat)
        try:
            with pytest.raises(ValueError, match="body limit"):
                module.read_body_file_text(str(body))
        finally:
            monkeypatch.setattr(module.os, "fstat", real_fstat)


def test_crlf_counts_after_newline_translation(repo: Path) -> None:
    """Text mode turns CRLF into LF, so 65536 CRLF lines-worth fits once translated."""
    body = _body(repo, "\r\n" * 65536)
    for module in _readers():
        assert module.read_body_file_text(str(body)) == "\n" * 65536


def _open_descriptors() -> int:
    return len(os.listdir("/proc/self/fd"))


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="needs /proc/self/fd")
@pytest.mark.parametrize("size", [65537, 4 * 65536 + 1], ids=["char-cap", "byte-cap"])
def test_refusal_closes_the_descriptor(repo: Path, size: int) -> None:
    body = _body(repo, "x" * size)
    for module in _readers():
        before = _open_descriptors()
        with pytest.raises(ValueError, match="body limit"):
            module.read_body_file_text(str(body))
        assert _open_descriptors() == before


def test_reads_at_most_one_char_past_the_cap(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = _body(repo, "x" * 10)
    sizes: list[int] = []
    real_fdopen = os.fdopen

    class _Spy:
        def __init__(self, handle) -> None:
            self._handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            self._handle.close()

        def read(self, size: int = -1) -> str:
            sizes.append(size)
            return self._handle.read(size)

    for module in _readers():
        monkeypatch.setattr(module.os, "fdopen", lambda *a, **k: _Spy(real_fdopen(*a, **k)))
        try:
            assert module.read_body_file_text(str(body)) == "x" * 10
        finally:
            monkeypatch.setattr(module.os, "fdopen", real_fdopen)
        assert sizes == [module.MAX_BODY_CHARS + 1]
        sizes.clear()


@pytest.mark.parametrize(
    ("raw", "accepted"),
    [
        (b"\r" * 65536, True),
        (b"\r\n" * 65537, False),
        (b"x" * 65536 + b"\xff", False),
        (b"x" * 100 + b"\xff", False),
    ],
    ids=["lone-cr-at-cap", "crlf-one-over", "invalid-utf8-past-cap", "invalid-utf8-under-cap"],
)
def test_newline_and_encoding_edges(repo: Path, raw: bytes, accepted: bool) -> None:
    body = repo / "drafts" / "body.md"
    body.write_bytes(raw)
    body.chmod(0o600)
    for module in _readers():
        if accepted:
            assert len(module.read_body_file_text(str(body))) == 65536
        else:
            # A UnicodeDecodeError is a ValueError, so either refusal counts.
            with pytest.raises(ValueError):
                module.read_body_file_text(str(body))
