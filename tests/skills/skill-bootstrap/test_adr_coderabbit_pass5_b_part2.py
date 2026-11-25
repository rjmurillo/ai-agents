"""Tests for the PR #7527 CodeRabbit pass 5 findings, group B: ``adr_docs`` and ``adr_locate``.

Each section names the finding it pins. ``test_adr_coderabbit_pass5_b.py`` holds the decision
log findings.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import IO, Any

import adr_commits
import adr_docs
import adr_locate
import bootstrap_adr
import pytest
from adr_helpers import write
from draft_helpers import _cand, _scan_file

NYGARD = adr_locate.Style(0, "", 4, 0, None, "# {number}. {title}", adr_locate.NYGARD_HEADINGS)


# ---------------------------------------------------------------------------
# B2: only spaces and tabs may follow a closing fence
# ---------------------------------------------------------------------------


def test_a_tilde_line_with_a_trailing_nonbreaking_space_does_not_close_the_fence() -> None:
    text = "~~~\n~~~ \n## Inside\n~~~\n## Real"

    assert adr_docs.fence_after("~~~", "~~~ ") == "~~~"
    assert adr_docs.fence_after("~~~", "~~~ \t") is None
    assert adr_docs.lines_outside_fences(text) == ["## Real"]


# ---------------------------------------------------------------------------
# B3: a pull request page compares by the selector's host, port and path rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cited", "url", "same"),
    [
        ("https://github.com/org/repo/pull/3", "https://github.com/Org/Repo/pull/3", True),
        ("https://GitHub.com:443/org/repo/pull/3", "https://github.com/org/repo/pull/3", True),
        ("https://github.com/org/repo/pull/3/", "https://github.com:443/ORG/repo/pull/3", True),
        ("http://github.com:443/org/repo/pull/3", "http://github.com/org/repo/pull/3", False),
        ("https://github.com:8443/org/repo/pull/3", "https://github.com/org/repo/pull/3", False),
        ("https://github.com/org/repo/pull/3", "https://github.com/org/other/pull/3", False),
        ("https://example.com/Docs/Page", "https://example.com/docs/page", False),
    ],
)
def test_a_cited_pr_page_suppresses_by_the_selectors_identity(
    cited: str, url: str, same: bool
) -> None:
    existing = adr_docs.ExistingAdrs([("a.md", f"Decided in {cited} after review.")])

    assert existing.names((), (url,), None) is same


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("https://github.com/org/repo/pull/3", "https://GITHUB.com/Org/Repo/pull/3"),
        ("https://github.com:443/org/repo/pull/3", "https://github.com/org/repo/pull/3"),
        ("https://github.com:8443/org/repo/pull/3", "https://github.com/org/repo/pull/3"),
        ("https://github.com/org/repo/pull/3", "https://github.com/org/repo/pull/4"),
    ],
)
def test_the_https_pr_identity_agrees_with_the_selector(left: str, right: str) -> None:
    same = adr_docs._url_identity(left) == adr_docs._url_identity(right)

    assert same is (adr_commits._origin(left) == adr_commits._origin(right))


# ---------------------------------------------------------------------------
# B4: a section's first line keeps its indent through classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("kind", "heading"), [("contributing", "Setup"), ("readme", "Workflow")])
def test_an_indented_backtick_line_at_a_section_start_does_not_hide_a_rule(
    kind: adr_docs.DocKind, heading: str
) -> None:
    doc = f"## {heading}\n\n    ```\n    example\nYou must sign the CLA.\n\n"

    (section,) = adr_docs.rule_sections(kind, doc)

    assert section.body == "    ```\n    example\nYou must sign the CLA."


# ---------------------------------------------------------------------------
# B5: draft refuses a folder it cannot list
# ---------------------------------------------------------------------------


def _unlistable(monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    real = os.scandir

    def scandir(path: Any = ".") -> Any:
        if Path(path).resolve() == folder.resolve():
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", scandir)


def test_draft_into_an_unlistable_scratch_folder_fails_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scratch = tmp_path / "scratch"
    write(scratch, "0001-existing.md", "# 1. Existing\n")
    scan = _scan_file(tmp_path, tmp_path / "gone", _cand())
    _unlistable(monkeypatch, scratch)

    code = bootstrap_adr.main(["draft", "--scan", scan, "--id", "c-1234567", "--out", str(scratch)])

    assert (code, json.loads(capsys.readouterr().out)["error"]) == (2, "io")
    assert os.listdir(scratch) == ["0001-existing.md"]  # the stub covers scandir only


def test_the_locator_still_skips_an_unlistable_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, "docs/adr/0001-x.md", "# 1. X\n")
    write(tmp_path, "docs/decisions/0002-y.md", "# 2. Y\n")
    _unlistable(monkeypatch, tmp_path / "docs/adr")

    found = adr_locate.locate(tmp_path)
    texts = list(adr_locate.read_adr_texts(tmp_path, [("docs/adr", "known")]))

    assert [folder["path"] for folder in found["folders"]] == ["docs/decisions"]
    assert texts == []


def test_a_missing_scratch_folder_still_numbers_from_one(tmp_path: Path) -> None:
    assert adr_locate.adr_files(tmp_path / "missing") == []
    assert adr_locate.folder_style(tmp_path / "missing").highest == 0


# ---------------------------------------------------------------------------
# B8: the opened file is checked, not the path before it
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="no O_NOFOLLOW")
def test_a_file_swapped_for_a_symlink_after_the_check_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = write(tmp_path, "outside.md", "secret text")
    path = write(tmp_path, "0001-x.md", "# 1. X\n")
    real = Path.is_symlink

    def swap(self: Path) -> bool:
        answer = real(self)
        if self == path and not answer:
            path.unlink()
            path.symlink_to(secret)
        return answer

    monkeypatch.setattr(Path, "is_symlink", swap)

    assert adr_locate.read_bounded(path) is None


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs")
def test_a_fifo_or_folder_reads_as_nothing_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "0001-fifo.md"
    os.mkfifo(fifo)
    results: list[str | None] = []
    worker = threading.Thread(target=lambda: results.append(adr_locate.read_bounded(fifo)))
    worker.start()
    worker.join(5)
    if worker.is_alive():  # unblock the open so the test run ends
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        worker.join(5)

    assert results == [None] and adr_locate.read_bounded(tmp_path) is None


# ---------------------------------------------------------------------------
# B11: an oversized ADR costs no read
# ---------------------------------------------------------------------------


class _Spy:
    def __init__(self, handle: IO[bytes], sizes: list[int]) -> None:
        self._handle, self._sizes = handle, sizes

    def __enter__(self) -> _Spy:
        return self

    def __exit__(self, *exc: object) -> None:
        self._handle.close()

    def read(self, size: int = -1) -> bytes:
        self._sizes.append(size)
        return self._handle.read(size)


def _spy_reads(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Every read size, from now on, through ``Path.open`` or the ``open`` ``adr_locate`` calls."""
    sizes: list[int] = []
    real_path_open = Path.open

    def path_open(self: Path, *args: Any, **kwargs: Any) -> _Spy:
        return _Spy(real_path_open(self, *args, **kwargs), sizes)

    def module_open(*args: Any, **kwargs: Any) -> _Spy:
        return _Spy(open(*args, **kwargs), sizes)

    monkeypatch.setattr(Path, "open", path_open)
    monkeypatch.setattr(adr_locate, "open", module_open, raising=False)
    return sizes


def test_oversized_adr_files_are_skipped_without_a_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for n in range(1, 4):
        write(tmp_path, f"docs/adr/000{n}-big.md", "x" * (adr_locate.MAX_READ_BYTES + 1))
    tally = adr_locate.AdrTally()
    reads = _spy_reads(monkeypatch)

    texts = list(adr_locate.read_adr_texts(tmp_path, [("docs/adr", "known")], tally))

    assert texts == [] and reads == []
    assert (tally.read, tally.skipped, tally.cut) == (0, 3, False)


# ---------------------------------------------------------------------------
# B9: a folder at the highest readable number has no next number
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("highest", "following"), [(999_998, 999_999), (999_999, None)])
def test_the_next_number_stops_at_the_highest_readable_number(
    tmp_path: Path, highest: int, following: int | None
) -> None:
    write(tmp_path, f"docs/adr/{highest}-x.md", f"# {highest}. X\n")

    found = adr_locate.locate(tmp_path)

    assert found["folders"][0]["next_number"] == following
    assert found["next_number"] == following


def test_the_locator_limit_is_the_draft_limit() -> None:
    assert adr_locate.MAX_ADR_NUMBER == bootstrap_adr.MAX_ADR_NUMBER


# ---------------------------------------------------------------------------
# B10: the draft H1 escapes a title that starts with Markdown syntax
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("form", "h1"),
    [
        ("# {number}. {title}", "# 7. \\<!-- note --> Adopt x"),
        ("# ADR-{number:03d}: {title}", "# ADR-007: \\<!-- note --> Adopt x"),
    ],
)
def test_the_draft_h1_escapes_a_leading_html_comment(form: str, h1: str) -> None:
    style = adr_locate.Style(1, "", 3, 6, None, form, adr_locate.NYGARD_HEADINGS)

    text = adr_locate.render(style, 7, _cand(title="<!-- note --> Adopt x"), "Proposed")

    assert text.split("\n", 1)[0] == h1


def test_the_slug_still_comes_from_the_original_title(tmp_path: Path) -> None:
    scan = _scan_file(tmp_path, tmp_path / "gone", _cand(title="<!-- note --> Adopt x"))

    result = bootstrap_adr.draft(scan, "c-1234567", str(tmp_path / "scratch"), "Proposed")

    assert Path(result["path"]).name == "0001-note-adopt-x.md"
    assert adr_locate.render(NYGARD, 1, _cand(title="Adopt x"), "Proposed").startswith(
        "# 1. Adopt x"
    )
