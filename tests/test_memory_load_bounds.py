"""Resource bounds on the memory load path recall uses (issue #7493, ADR-109 2026-11-20)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from memory_enhancement import serena_integration as si

_BODY = "Move every service behind the gateway.\n"


def _write(tmp_path: Path, text: str, name: str = "note.md") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_file_over_the_limit_is_skipped_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "x" * (si.MAX_MEMORY_BYTES + 1))
    reads: list[Path] = []
    original = Path.read_text

    def counting_read(self: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read)

    assert si.load_memory(path, tmp_path, si.MAX_MEMORY_BYTES) is None

    assert reads == []
    assert "over" in capsys.readouterr().err


def test_a_file_at_the_limit_still_loads(tmp_path: Path) -> None:
    path = _write(tmp_path, "y" * si.MAX_MEMORY_BYTES)

    assert si.MAX_MEMORY_BYTES == 256 * 1024
    assert si.load_memory(path, tmp_path, si.MAX_MEMORY_BYTES) is not None


def test_load_memory_has_no_size_cap_unless_asked(tmp_path: Path) -> None:
    """Health, graph, reflection and the CLI read every file."""
    path = _write(tmp_path, "z" * (si.MAX_MEMORY_BYTES + 1))

    assert si.load_memory(path, tmp_path) is not None


def test_load_memories_reads_a_large_file_too(tmp_path: Path) -> None:
    _write(tmp_path, "z" * (si.MAX_MEMORY_BYTES + 1), "big.md")
    _write(tmp_path, f"# Small\n\n{_BODY}", "small.md")

    assert sorted(m.memory_id for m in si.load_memories(tmp_path)) == ["big", "small"]


@pytest.mark.parametrize(
    "title_yaml",
    ["[a, b]", "{k: v}", "123", "true", "null", "2026-01-02", "[[1, 2], [3]]"],
)
def test_a_non_string_title_is_treated_as_absent(tmp_path: Path, title_yaml: str) -> None:
    path = _write(tmp_path, f"---\ntitle: {title_yaml}\ntags: [x]\n---\n\n{_BODY}", "stem-name.md")

    memory = si.load_memory(path, tmp_path)

    assert memory is not None
    assert memory.title == "stem-name"


def test_a_string_title_is_kept(tmp_path: Path) -> None:
    path = _write(tmp_path, f"---\ntitle: Gateway cutover\ntags: [x]\n---\n\n{_BODY}")

    memory = si.load_memory(path, tmp_path)

    assert memory is not None
    assert memory.title == "Gateway cutover"


def test_an_alias_heavy_title_is_never_stringified(tmp_path: Path) -> None:
    """Nine levels of ten aliases each is 10**9 leaves if anything expands it with str()."""
    levels = ["a0: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    for depth in range(1, 9):
        refs = ", ".join([f"*a{depth - 1}"] * 10)
        levels.append(f"a{depth}: &a{depth} [{refs}]")
    document = "---\n" + "\n".join(levels) + "\ntitle: *a8\n---\n\n" + _BODY
    path = _write(tmp_path, document, "bomb.md")

    started = time.monotonic()
    memory = si.load_memory(path, tmp_path)
    elapsed = time.monotonic() - started

    assert memory is not None
    assert memory.title == "bomb"
    assert elapsed < 5.0


def test_only_scalar_tags_are_kept() -> None:
    value = ["a", 1, 2.5, True, ["nested"], {"k": "v"}, None, ("t",)]

    assert si._parse_tags(value) == ["a", "1", "2.5", "True"]


def test_a_scalar_string_tag_still_wraps_and_non_lists_are_empty() -> None:
    assert si._parse_tags("solo") == ["solo"]
    assert si._parse_tags({"k": "v"}) == []
    assert si._parse_tags(None) == []
