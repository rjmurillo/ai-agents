"""Tests for ``scripts.testing.packed_refs``."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing.packed_refs import PackedRefsUnresolvedError, lookup_packed_ref

pytestmark = pytest.mark.windows_path


def _oid(index: int, *, length: int = 40) -> str:
    return f"{index:0{length}x}"


def _write_packed_refs(path: Path, lines: list[str], *, newline: str = "\n") -> Path:
    path.write_bytes((newline.join(lines) + newline).encode("utf-8"))
    return path


def test_missing_packed_refs_returns_none(tmp_path: Path) -> None:
    assert lookup_packed_ref(tmp_path / "packed-refs", "refs/heads/main") is None


def test_empty_sorted_packed_refs_returns_none(tmp_path: Path) -> None:
    packed = _write_packed_refs(
        tmp_path / "packed-refs",
        ["# pack-refs with: peeled fully-peeled sorted"],
    )
    assert lookup_packed_ref(packed, "refs/heads/main") is None


def test_small_sorted_packed_refs_resolves_and_misses(tmp_path: Path) -> None:
    packed = _write_packed_refs(
        tmp_path / "packed-refs",
        [
            "# pack-refs with: peeled fully-peeled sorted ",
            f"{_oid(1)} refs/heads/alpha",
            f"{_oid(2)} refs/heads/main",
            f"{_oid(3)} refs/heads/main-extra",
            f"{_oid(4)} refs/tags/v1",
            f"^{_oid(5)}",
        ],
    )
    assert lookup_packed_ref(packed, "refs/heads/alpha") == _oid(1)
    assert lookup_packed_ref(packed, "refs/heads/main") == _oid(2)
    assert lookup_packed_ref(packed, "refs/heads/main-extra") == _oid(3)
    assert lookup_packed_ref(packed, "refs/heads/aaa") is None
    assert lookup_packed_ref(packed, "refs/heads/beta") is None
    assert lookup_packed_ref(packed, "refs/heads/zzz") is None


def test_large_sorted_packed_refs_exercises_binary_search(tmp_path: Path) -> None:
    """File well over 4 KB exercises the binary search across boundaries and peeled tags."""
    entries: list[tuple[str, str]] = []
    lines = ["# pack-refs with: peeled fully-peeled sorted"]
    for idx in range(250):
        name = f"refs/heads/branch-{idx:04d}"
        oid = _oid(idx + 1)
        entries.append((name, oid))
        lines.append(f"{oid} {name}")
    for idx in range(100):
        name = f"refs/tags/tag-{idx:04d}"
        oid = _oid(1000 + idx)
        entries.append((name, oid))
        lines.append(f"{oid} {name}")
        lines.append(f"^{_oid(2000 + idx)}")

    packed = _write_packed_refs(tmp_path / "packed-refs", lines)
    assert packed.stat().st_size > 20_000

    # Every entry across the >20 KB file resolves accurately, exercising exact midpoint
    # hits as well as boundary transitions into the linear scan.
    for name, expected in entries:
        assert lookup_packed_ref(packed, name) == expected

    # Missing refs before, between, and after all packed entries return None.
    assert lookup_packed_ref(packed, "refs/heads/branch-0000-missing") is None
    assert lookup_packed_ref(packed, "refs/heads/0000") is None
    assert lookup_packed_ref(packed, "refs/heads/branch-0124a") is None
    assert lookup_packed_ref(packed, "refs/zzz/after-all") is None


def test_long_line_spanning_midpoint_falls_through_to_linear_scan(tmp_path: Path) -> None:
    """Edge: a single line spanning from midpoint past hi exits binary search cleanly."""
    packed = _write_packed_refs(
        tmp_path / "packed-refs",
        [
            "# pack-refs with: peeled fully-peeled sorted",
            f"{_oid(1)} refs/heads/alpha",
            f"# {'x' * 6000}",
        ],
    )
    assert lookup_packed_ref(packed, "refs/heads/alpha") == _oid(1)
    assert lookup_packed_ref(packed, "refs/heads/missing") is None


def test_large_block_of_peeled_lines_at_tail_does_not_stall_binary_search(tmp_path: Path) -> None:
    """Edge: a large block of peeled/comment lines past midpoint shrinks hi safely."""
    lines = ["# pack-refs with: peeled fully-peeled sorted"]
    for idx in range(100):
        lines.append(f"{_oid(idx + 1)} refs/heads/b-{idx:03d}")
    # Pad the second half of the file with >12 KB of comment/peeled lines.
    lines.extend(f"^{_oid(500 + idx)}" for idx in range(300))
    packed = _write_packed_refs(tmp_path / "packed-refs", lines)

    assert lookup_packed_ref(packed, "refs/heads/b-000") == _oid(1)
    assert lookup_packed_ref(packed, "refs/heads/b-050") == _oid(51)
    assert lookup_packed_ref(packed, "refs/heads/b-099") == _oid(100)
    assert lookup_packed_ref(packed, "refs/heads/b-missing") is None


def test_sha256_oids_crlf_missing_trailing_newline_and_utf8_ref_names(tmp_path: Path) -> None:
    sha256 = _oid(42, length=64)
    packed = tmp_path / "packed-refs"
    packed.write_bytes(
        b"# pack-refs with: peeled fully-peeled sorted\r\n"
        + _oid(1).encode("ascii")
        + b" refs/heads/a-\xff-nonutf8\r\n"
        + sha256.encode("ascii")
        + " refs/heads/caf\u00e9".encode()
    )
    assert lookup_packed_ref(packed, "refs/heads/caf\u00e9") == sha256


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ("", "not sorted"),
        (f"{_oid(1)} refs/heads/main\n", "not sorted"),
        (f"# pack-refs with: peeled fully-peeled\n{_oid(1)} refs/heads/main\n", "not sorted"),
        (f"# pack-refs with: unsorted\n{_oid(1)} refs/heads/main\n", "not sorted"),
        (f"# pack-refs with: sorted\r{_oid(1)} refs/heads/main\r", "not sorted"),
        ("# pack-refs with: sorted\nno-space-line\n", "malformed"),
        ("# pack-refs with: sorted\nshort refs/heads/main\n", "malformed"),
        (f"# pack-refs with: sorted\n{'g' * 40} refs/heads/main\n", "malformed"),
        (f"# pack-refs with: sorted\n{_oid(1)} \n", "malformed"),
        (f"# pack-refs with: sorted\n{_oid(1)}  refs/heads/main\n", "malformed"),
        (f"# pack-refs with: sorted\n{_oid(1)} refs/heads/a\tb\n", "malformed"),
        (
            f"# pack-refs with: sorted\n{_oid(1)} refs/heads/b\n{_oid(2)} refs/heads/a\n",
            "not strictly sorted",
        ),
        (
            f"# pack-refs with: sorted\n{_oid(1)} refs/heads/a\n{_oid(2)} refs/heads/a\n",
            "not strictly sorted",
        ),
    ],
)
def test_unproven_or_malformed_packed_refs_raises(tmp_path: Path, content: str, match: str) -> None:
    packed = tmp_path / "packed-refs"
    packed.write_bytes(content.encode("utf-8"))

    with pytest.raises(PackedRefsUnresolvedError, match=match):
        lookup_packed_ref(packed, "refs/heads/main")


def test_malformed_and_unsorted_entries_caught_during_binary_search(tmp_path: Path) -> None:
    """Binary search itself rejects malformed or out-of-order entries in >4 KB files."""
    lines = ["# pack-refs with: peeled fully-peeled sorted"]
    for idx in range(150):
        lines.append(f"{_oid(idx + 1)} refs/heads/branch-{idx:04d}")
    # Corrupt the middle entry so the first binary-search probe hits it.
    lines[76] = "corrupt-line-no-oid"
    packed = _write_packed_refs(tmp_path / "packed-refs", lines)
    with pytest.raises(PackedRefsUnresolvedError, match="malformed"):
        lookup_packed_ref(packed, "refs/heads/branch-0075")

    # Reversed ordering across binary-search probes raises not strictly sorted.
    lines[76] = f"{_oid(76)} refs/heads/branch-0075"
    for idx in range(100, 130):
        lines[idx] = f"{_oid(idx)} refs/heads/branch-0010"
    packed = _write_packed_refs(tmp_path / "packed-refs", lines)
    with pytest.raises(PackedRefsUnresolvedError, match="not strictly sorted"):
        lookup_packed_ref(packed, "refs/heads/branch-0140")


def test_concurrent_truncation_raises_unresolved(tmp_path: Path) -> None:
    """If a non-atomic writer truncates packed-refs mid-read, fail closed."""
    from scripts.testing.packed_refs import _binary_search_packed_refs, _linear_scan_packed_refs

    packed = _write_packed_refs(
        tmp_path / "packed-refs",
        ["# pack-refs with: sorted", f"{_oid(1)} refs/heads/alpha"],
    )
    with packed.open("rb") as handle:
        header_end = len(handle.readline())
        # Claim hi is far past actual EOF to simulate in-place truncation.
        with pytest.raises(PackedRefsUnresolvedError, match="truncated"):
            _binary_search_packed_refs(handle, header_end, header_end + 10_000, b"refs/heads/main")
        with pytest.raises(PackedRefsUnresolvedError, match="truncated"):
            _linear_scan_packed_refs(handle, header_end, header_end + 500, b"refs/heads/main")


def test_surrogate_ref_name_raises_unresolved(tmp_path: Path) -> None:
    packed = _write_packed_refs(
        tmp_path / "packed-refs",
        ["# pack-refs with: sorted", f"{_oid(1)} refs/heads/main"],
    )
    with pytest.raises(PackedRefsUnresolvedError, match="UTF-8"):
        lookup_packed_ref(packed, "refs/heads/\udcff")


def test_packed_refs_directory_raises_unresolved(tmp_path: Path) -> None:
    packed = tmp_path / "packed-refs"
    packed.mkdir()

    with pytest.raises(PackedRefsUnresolvedError, match="not a regular file"):
        lookup_packed_ref(packed, "refs/heads/main")


def test_packed_refs_fstat_error_raises_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    packed = _write_packed_refs(
        tmp_path / "packed-refs",
        ["# pack-refs with: sorted", f"{_oid(1)} refs/heads/main"],
    )

    def _deny_fstat(_fd: int) -> object:
        raise PermissionError("denied")

    with monkeypatch.context() as mp:
        mp.setattr(os, "fstat", _deny_fstat)
        with pytest.raises(PackedRefsUnresolvedError, match="unreadable"):
            lookup_packed_ref(packed, "refs/heads/main")


def test_packed_refs_open_error_raises_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    packed = _write_packed_refs(
        tmp_path / "packed-refs",
        ["# pack-refs with: sorted", f"{_oid(1)} refs/heads/main"],
    )

    def _deny_open(*_args: object, **_kwargs: object) -> int:
        raise PermissionError("denied")

    with monkeypatch.context() as mp:
        mp.setattr(os, "open", _deny_open)
        with pytest.raises(PackedRefsUnresolvedError, match="unreadable"):
            lookup_packed_ref(packed, "refs/heads/main")
