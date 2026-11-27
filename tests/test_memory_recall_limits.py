"""Output, parse, and verification limits and recall notes (issue #7493, ADR-109 2026-11-20)."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memory_enhancement import frontmatter_reader as fr
from memory_enhancement import recall_log, search
from memory_enhancement import serena_integration as si
from memory_enhancement.__main__ import main as cli_main
from memory_enhancement.hooks import user_prompt_submit_memory as hook
from memory_enhancement.models import Citation, SourceType
from memory_enhancement.search import SearchResult
from memory_enhancement.verification import MAX_VERIFY_BYTES, cited_file_exceeds

_BODY = "Move every service behind the gateway.\n"
_WORDS = "gateway cutover service migration rollout memory recall"


def _repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    directory = tmp_path / ".serena" / "memories"
    directory.mkdir(parents=True)
    return directory


def _memory(directory: Path, name: str, title: str | None = None, body: str = _BODY) -> Path:
    front = f"---\ntitle: {title}\n---\n\n" if title is not None else f"# {name}\n\n"
    path = directory / f"{name}.md"
    path.write_text(front + body, encoding="utf-8")
    return path


def _result(title: str, snippet: str = "s") -> SearchResult:
    return SearchResult(
        memory_id="m",
        file_path=Path("/nonexistent/.serena/memories/m.md"),
        confidence=0.5,
        title=title,
        snippet=snippet,
        citation_status="unverified",
        relevance=1.0,
    )


@pytest.fixture(autouse=True)
def _fresh_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recall_log, "_seen", set())


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# --- title cap and block cap -------------------------------------------------


def test_a_200_kb_title_is_cut_to_200_characters_at_parse_time(tmp_path: Path) -> None:
    directory = _repo(tmp_path)
    path = _memory(directory, "gateway-cutover", title=(_WORDS + " ") * 4000)
    assert path.stat().st_size > 200_000

    memory = si.load_memory(path, directory)

    assert memory is not None
    assert len(memory.title) == si.MAX_TITLE_CHARS == 200


def test_a_title_of_200_characters_or_fewer_is_unchanged(tmp_path: Path) -> None:
    directory = _repo(tmp_path)
    path = _memory(directory, "gateway-cutover", title="Gateway cutover")

    memory = si.load_memory(path, directory)

    assert memory is not None and memory.title == "Gateway cutover"


def test_a_200_kb_title_never_reaches_the_recalled_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _repo(tmp_path)
    _memory(directory, "gateway-cutover", title=(_WORDS + " ") * 4000)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    out = hook.recall_block("gateway cutover")

    assert "<memory-context>" in out
    assert len(out) <= hook.MAX_BLOCK_CHARS
    assert "gateway cutover service migration" in out
    assert out.count("gateway cutover service migration rollout memory recall") < 5


@pytest.mark.parametrize("count", [1, 3, 10])
def test_the_block_is_at_most_1600_characters_and_ends_with_the_sentinel(count: int) -> None:
    results = [_result("t" * 200_000, "x" * 5000) for _ in range(count)]

    out = hook._format_memory_context(results)

    assert hook.MAX_BLOCK_CHARS == 1600
    assert len(out) <= 1600
    assert out.startswith("<memory-context>\n")
    assert out.endswith("\n</memory-context>")
    assert out.count("</memory-context>") == 1


def test_the_last_entry_is_cut_cleanly_and_marked(capsys: pytest.CaptureFixture[str]) -> None:
    results = [_result("a", "x" * 3000), _result("b", "y" * 3000), _result("c", "z" * 3000)]

    out = hook._format_memory_context(results)

    assert len(out) <= 1600
    assert "[truncated]" in out
    assert "### a " in out and "### b " not in out
    assert "recalled block cut at 1600 characters" in capsys.readouterr().err


def test_a_small_block_is_unchanged_and_silent(capsys: pytest.CaptureFixture[str]) -> None:
    out = hook._format_memory_context([_result("t", "body")])

    assert "[truncated]" not in out
    assert out.endswith("Source: /nonexistent/.serena/memories/m.md\n\n</memory-context>")
    assert capsys.readouterr().err == ""


# --- citation read bound -----------------------------------------------------


def _cite(target: str, kind: SourceType = SourceType.FILE) -> Citation:
    return Citation(source_type=kind, target=target, context="")


def test_the_verify_bound_is_256_kib() -> None:
    assert MAX_VERIFY_BYTES == 256 * 1024


def test_cited_file_over_the_bound_is_detected_for_line_and_function_citations(
    tmp_path: Path,
) -> None:
    (tmp_path / "big.py").write_text("x" * (MAX_VERIFY_BYTES + 1), encoding="utf-8")

    assert cited_file_exceeds(_cite("big.py:1"), tmp_path, MAX_VERIFY_BYTES)
    assert cited_file_exceeds(_cite("big.py::f", SourceType.FUNCTION), tmp_path, MAX_VERIFY_BYTES)


def test_a_file_at_the_bound_or_a_citation_that_reads_nothing_is_not_flagged(
    tmp_path: Path,
) -> None:
    (tmp_path / "ok.py").write_text("x" * MAX_VERIFY_BYTES, encoding="utf-8")
    (tmp_path / "big.py").write_text("x" * (MAX_VERIFY_BYTES + 1), encoding="utf-8")

    assert not cited_file_exceeds(_cite("ok.py:1"), tmp_path, MAX_VERIFY_BYTES)
    assert not cited_file_exceeds(_cite("big.py"), tmp_path, MAX_VERIFY_BYTES)
    assert not cited_file_exceeds(_cite("missing.py:1"), tmp_path, MAX_VERIFY_BYTES)
    assert not cited_file_exceeds(_cite("../outside.py:1"), tmp_path, MAX_VERIFY_BYTES)
    assert not cited_file_exceeds(_cite("7", SourceType.ISSUE), tmp_path, MAX_VERIFY_BYTES)


def _memory_citing(tmp_path: Path, target: str) -> Path:
    directory = _repo(tmp_path)
    return _memory(directory, "gateway-cutover", body=f"Body.\n\n[cite:file]({target})\n")


def test_a_big_cited_file_makes_the_status_unverified_without_reading_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _memory_citing(tmp_path, "big.py:3")
    (tmp_path / "big.py").write_text("x\n" * (MAX_VERIFY_BYTES // 2 + 10), encoding="utf-8")
    verify = MagicMock()
    monkeypatch.setattr(search, "verify_citation", verify)

    (result,) = search.rank_results([path], tmp_path, max_verify_bytes=MAX_VERIFY_BYTES)

    verify.assert_not_called()
    assert result.citation_status == "unverified"


def test_control_without_the_bound_the_big_file_is_verified(tmp_path: Path) -> None:
    path = _memory_citing(tmp_path, "big.py:3")
    (tmp_path / "big.py").write_text("x\n" * (MAX_VERIFY_BYTES // 2 + 10), encoding="utf-8")

    (result,) = search.rank_results([path], tmp_path)

    assert result.citation_status == "verified"


def test_a_small_cited_file_is_still_verified_under_the_bound(tmp_path: Path) -> None:
    path = _memory_citing(tmp_path, "small.py:2")
    (tmp_path / "small.py").write_text("a\nb\nc\n", encoding="utf-8")

    (result,) = search.rank_results([path], tmp_path, max_verify_bytes=MAX_VERIFY_BYTES)

    assert result.citation_status == "verified"


# --- RecursionError ----------------------------------------------------------


def test_a_recursion_error_skips_that_file_with_one_stderr_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _repo(tmp_path)
    path = _memory(directory, "gateway-cutover")

    def deep(_raw: str):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(si, "_extract_metadata", deep)

    assert si.load_memory(path, directory) is None

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert len(lines) == 1 and "nesting too deep" in lines[0]


def test_deeply_nested_yaml_does_not_abort_loading_the_other_files(tmp_path: Path) -> None:
    directory = _repo(tmp_path)
    nested = "[" * 20000 + "]" * 20000
    (directory / "bomb.md").write_text(f"---\ntitle: {nested}\n---\n\n{_BODY}", encoding="utf-8")
    _memory(directory, "fine")

    memories = si.load_memories(directory)

    assert "fine" in [m.memory_id for m in memories]


def test_control_load_memory_still_parses_a_normal_file(tmp_path: Path) -> None:
    directory = _repo(tmp_path)

    assert si.load_memory(_memory(directory, "fine"), directory) is not None


# --- opt-in caps: the CLI scores every match ---------------------------------


def test_the_search_cli_scores_all_sixty_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _repo(tmp_path)
    for i in range(60):
        _memory(directory, f"note-{i:02d}")
    loaded: list[Path] = []
    real = si.load_memory

    def counting(file_path, memories_dir=None, max_bytes=None):
        loaded.append(file_path)
        return real(file_path, memories_dir, max_bytes)

    monkeypatch.setattr(search, "load_memory", counting)

    code = cli_main(
        ["--repo-root", str(tmp_path), "--memories-dir", str(directory), "search", "gateway"]
    )

    assert code == 0
    assert len(loaded) == 60
    assert "candidate cap" not in capsys.readouterr().err


def test_search_memories_defaults_to_no_cap(tmp_path: Path) -> None:
    import inspect

    for function in (search.search_memories, search.rank_results):
        parameters = inspect.signature(function).parameters
        assert parameters["max_candidates"].default is None
        assert parameters["max_memory_bytes"].default is None
        assert parameters["max_verify_bytes"].default is None


def test_recall_passes_every_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _repo(tmp_path)
    _memory(directory, "gateway-cutover")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    seen: dict[str, object] = {}
    real = search.search_memories

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(search, "search_memories", spy)

    hook.recall_block("gateway cutover")

    assert seen["max_candidates"] == search.MAX_CANDIDATES == 50
    assert seen["max_memory_bytes"] == si.MAX_MEMORY_BYTES
    assert seen["max_verify_bytes"] == MAX_VERIFY_BYTES


def test_recall_skips_a_memory_over_256_kib_but_the_cli_path_loads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _repo(tmp_path)
    _memory(directory, "gateway-big", body="gateway " * 40_000)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    assert hook.recall_block("gateway big") == ""
    assert [r.memory_id for r in search.search_memories("gateway big", directory)] == [
        "gateway-big"
    ]


# --- recall notes: one line per cut, no content ------------------------------


def _lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().err.splitlines() if line.strip()]


def test_candidate_truncation_notes_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _repo(tmp_path)
    for i in range(60):
        _memory(directory, f"note-{i:02d}", body="SECRET-BODY gateway\n")

    search.search_memories("gateway", directory, repo_root=tmp_path, max_candidates=50)

    lines = _lines(capsys)
    assert lines == ["memory-recall: scoring 50 of 60 matching memories (candidate cap)"]


def test_no_note_when_the_cap_is_not_reached(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _repo(tmp_path)
    for i in range(5):
        _memory(directory, f"note-{i}")

    search.search_memories("gateway", directory, repo_root=tmp_path, max_candidates=50)

    assert _lines(capsys) == []


def test_deadline_reached_notes_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _repo(tmp_path)
    paths = [_memory(directory, f"note-{i}") for i in range(3)]
    clock = Clock()
    monkeypatch.setattr(time, "monotonic", clock)

    search.rank_results(paths, tmp_path, deadline=clock.now - 1.0)

    assert _lines(capsys) == [
        "memory-recall: deadline reached, returning the memories scored so far"
    ]


def test_deadline_spent_before_the_file_search_notes_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = Clock()
    monkeypatch.setattr(time, "monotonic", clock)
    monkeypatch.setattr(search, "resolve_tool", lambda name, roots=(): f"/usr/bin/{name}")

    assert search._search_with_ripgrep("gateway", tmp_path, clock.now - 1.0, tmp_path) is None

    assert _lines(capsys) == ["memory-recall: deadline reached before the file search started"]


@pytest.mark.parametrize("tool", ["rg", "grep"])
def test_a_tool_timeout_notes_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tool: str
) -> None:
    monkeypatch.setattr(search, "resolve_tool", lambda name, roots=(): f"/usr/bin/{name}")

    def timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    function = search._search_with_ripgrep if tool == "rg" else search._search_with_grep

    assert function("gateway", tmp_path, None, tmp_path) is None

    assert _lines(capsys) == [f"memory-recall: {tool} timed out after 5s"]


def test_a_symlinked_memories_dir_notes_the_directory_and_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    outside = tmp_path / "outside"
    _memory(_repo_dir(outside), "gateway-cutover")
    serena = tmp_path / "repo" / ".serena"
    serena.mkdir()
    try:
        (serena / "memories").symlink_to(outside / ".serena" / "memories", target_is_directory=True)
    except OSError as exc:  # pragma: no cover
        pytest.skip(f"symlinks unavailable: {exc}")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "repo"))

    assert hook.recall_block("gateway cutover") == ""

    (line,) = _lines(capsys)
    assert line == (
        f"memory-recall: ignoring {tmp_path / 'repo' / '.serena' / 'memories'}: "
        "it resolves outside the repository"
    )


def _repo_dir(root: Path) -> Path:
    directory = root / ".serena" / "memories"
    directory.mkdir(parents=True)
    return directory


def test_a_missing_memories_dir_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    assert hook.recall_block("gateway cutover") == ""
    assert _lines(capsys) == []


def test_a_missing_yaml_parser_notes_once_per_process(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(fr, "yaml", None)
    raw = "---\ntitle: T\n---\n\nbody\n"

    fr.read_frontmatter_stdlib(raw)
    fr.read_frontmatter_stdlib(raw)
    fr.read_frontmatter_stdlib(raw)

    assert _lines(capsys) == [
        "memory-recall: no YAML parser available, memory frontmatter metadata is ignored"
    ]


def test_a_present_yaml_parser_is_silent(capsys: pytest.CaptureFixture[str]) -> None:
    fr.read_frontmatter_stdlib("---\ntitle: T\n---\n\nbody\n")

    assert _lines(capsys) == []


def test_notes_never_carry_prompt_or_memory_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = _repo(tmp_path)
    for i in range(60):
        _memory(directory, f"note-{i:02d}", title="TITLE-TEXT", body="BODY-TEXT gateway\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    hook.recall_block("gateway PROMPT-TEXT")

    err = capsys.readouterr().err
    assert "memory-recall:" in err
    for secret in ("TITLE-TEXT", "BODY-TEXT", "PROMPT-TEXT", "gateway"):
        assert secret not in err


# --- containment edge cases ---------------------------------------------------


def test_a_project_dir_with_no_git_ancestor_recalls_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = tmp_path / "not-a-repo"
    _memory(_repo_dir(bare), "gateway-cutover")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(bare))

    assert hook.recall_block("gateway cutover") == ""


def test_a_per_file_symlink_pointing_outside_the_repository_is_not_recalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    secret = outside / "gateway-secret.md"
    secret.write_text("# Gateway secret\n\nOUTSIDE-CONTENT gateway\n", encoding="utf-8")
    try:
        (directory / "gateway-secret.md").symlink_to(secret)
    except OSError as exc:  # pragma: no cover
        pytest.skip(f"symlinks unavailable: {exc}")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    assert "OUTSIDE-CONTENT" not in hook.recall_block("gateway secret")


def test_control_a_regular_file_in_the_same_layout_is_recalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _repo(tmp_path)
    _memory(directory, "gateway-secret", body="INSIDE-CONTENT gateway\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

    assert "INSIDE-CONTENT" in hook.recall_block("gateway secret")
