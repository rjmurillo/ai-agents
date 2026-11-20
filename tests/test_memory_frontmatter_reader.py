"""The stdlib frontmatter reader in serena_integration (issue #7493, ADR-109 amendment 2026-11-20).

``serena_integration`` guards its ``frontmatter`` and ``yaml`` imports so the
recall path runs under a consumer's bare ``python3``. Without
python-frontmatter it falls back to ``_read_frontmatter_stdlib``. These tests
pin that reader to ``frontmatter.loads`` over this repository's memories, and
load the module with each dependency blocked.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import frontmatter
import pytest

from memory_enhancement import frontmatter_reader as fr
from memory_enhancement import serena_integration as si

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MEMORIES = sorted((_REPO_ROOT / ".serena" / "memories").rglob("*.md"))
_MODULE = "memory_enhancement.serena_integration"
_READER = "memory_enhancement.frontmatter_reader"

_MEMORY_TEXT = (
    "---\ntitle: Gateway cutover\ntags: [migration, gateway]\nconfidence: 0.8\n---\n\n"
    "Move every service behind the gateway.\n"
)


def _load_blocked(monkeypatch: pytest.MonkeyPatch, *blocked: str) -> ModuleType:
    """Import a fresh copy of serena_integration with *blocked* modules unimportable."""
    for name in blocked:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, _MODULE, raising=False)
    monkeypatch.delitem(sys.modules, _READER, raising=False)
    # `from . import frontmatter_reader` prefers the cached package attribute.
    monkeypatch.delattr(sys.modules["memory_enhancement"], "frontmatter_reader", raising=False)
    return importlib.import_module(_MODULE)


def _write_memory(tmp_path: Path, text: str = _MEMORY_TEXT) -> Path:
    path = tmp_path / "gateway-cutover.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_repository_has_memories_to_compare() -> None:
    assert len(_MEMORIES) > 0


@pytest.mark.parametrize(
    "path", _MEMORIES, ids=lambda p: p.relative_to(_REPO_ROOT / ".serena" / "memories").as_posix()
)
def test_stdlib_reader_matches_frontmatter_loads_on_repository_memories(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)

    metadata, body, _fallback = fr.read_frontmatter_stdlib(raw)

    assert metadata == dict(post.metadata)
    assert body == post.content


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "plain markdown, no block\n",
        "---\n---\nbody only\n",
        "---\ntitle: One boundary\nbody\n",
        "---\ntitle: [unclosed\n---\nbody\n",
        "---\n- a\n- b\n---\nlist block\n",
        "\n\n---\ntitle: Leading blank lines\n---\n\nbody\n",
        "-----\ntitle: Long fence\n-----\nbody\n",
        "---\ntitle: Inner rule\n---\nabove\n---\nbelow\n",
    ],
)
def test_stdlib_reader_matches_frontmatter_loads_on_edge_shapes(
    raw: str, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = fr.read_frontmatter(raw)
    capsys.readouterr()

    actual = fr.read_frontmatter_stdlib(raw)

    assert actual == expected


def test_malformed_yaml_warns_and_is_treated_as_plain_markdown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = "---\ntitle: [unclosed\n---\nbody\n"

    metadata, _body, fallback = fr.read_frontmatter_stdlib(raw)

    assert metadata == {}
    assert fallback == raw
    assert "malformed YAML frontmatter" in capsys.readouterr().err


def test_module_imports_and_loads_a_memory_with_frontmatter_and_yaml_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_blocked(monkeypatch, "frontmatter", "yaml")
    path = _write_memory(tmp_path)

    memory = module.load_memory(path, tmp_path)

    assert module.frontmatter_reader.frontmatter is None
    assert module.frontmatter_reader.yaml is None
    assert memory is not None
    assert memory.memory_id == "gateway-cutover"


def test_block_is_stripped_from_content_when_yaml_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_blocked(monkeypatch, "frontmatter", "yaml")

    title, _created, _updated, tags, _confidence, content = module._extract_metadata(_MEMORY_TEXT)

    assert title is None
    assert tags == []
    assert "title:" not in content
    assert not content.startswith("---")
    assert "Move every service behind the gateway." in content


def test_title_is_read_when_only_frontmatter_is_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_blocked(monkeypatch, "frontmatter")
    path = _write_memory(tmp_path)

    memory = module.load_memory(path, tmp_path)

    assert module.frontmatter_reader.frontmatter is None
    assert module.frontmatter_reader.yaml is not None
    assert memory is not None
    assert memory.title == "Gateway cutover"
    assert list(memory.tags) == ["migration", "gateway"]
    assert memory.confidence == pytest.approx(0.8)


def test_extract_metadata_is_unchanged_when_frontmatter_is_available() -> None:
    title, _created, _updated, tags, confidence, content = si._extract_metadata(_MEMORY_TEXT)

    assert si.frontmatter_reader.frontmatter is not None
    assert title == "Gateway cutover"
    assert tags == ["migration", "gateway"]
    assert confidence == pytest.approx(0.8)
    assert content == "Move every service behind the gateway."


def test_save_memory_names_python_frontmatter_when_it_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_blocked(monkeypatch, "frontmatter", "yaml")
    source = _write_memory(tmp_path)
    memory = module.load_memory(source, tmp_path)
    assert memory is not None
    out_dir = tmp_path / "out"

    with pytest.raises(RuntimeError, match="python-frontmatter"):
        module.save_memory(memory, out_dir)

    assert not out_dir.exists()
