"""Tests for scripts/ci/_wiki_links.py, reached through publish_wiki (issue #7202).

Link text may hold an inline code span, as in ``[`page.md`](page.md)``. An earlier
version split each line on code spans first, which cut such a link in half: it was
neither rewritten nor checked, so Home kept raw relative paths that 404 on the wiki.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from scripts.ci import publish_wiki as pw
from scripts.ci._wiki_links import (
    INLINE_LINK_RE,
    mask_code,
    readme_page_order,
    strip_target,
    unmask_code,
)
from tests.ci import publish_wiki_helpers as helpers
from tests.ci.publish_wiki_helpers import (
    BLOB,
    README,
    REPO_URL,
    make_repo,
    symlink_or_skip,
    write,
)

PAGES = {"README.md": "Home", "first-page.md": "first-page", "second-page.md": "second-page"}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


def rewrite(repo: Path, text: str) -> str:
    return pw.rewrite_links(text, repo_root=repo, repo_url=REPO_URL, published=PAGES)


def test_page_link_with_code_span_text_is_rewritten(repo: Path) -> None:
    assert rewrite(repo, "[`first-page.md`](first-page.md#x)") == "[`first-page.md`](first-page#x)"


def test_repo_link_with_code_span_text_becomes_absolute(repo: Path) -> None:
    out = rewrite(repo, "see [`tool.py`](../../scripts/tool.py) now")
    assert out == f"see [`tool.py`]({BLOB}/scripts/tool.py) now"


def test_missing_target_with_code_span_text_is_rejected(repo: Path) -> None:
    with pytest.raises(pw.SourceError, match="does not exist"):
        rewrite(repo, "[`gone.md`](gone.md)")


def test_a_link_inside_a_code_span_stays_untouched_beside_a_real_one(repo: Path) -> None:
    text = "`[a](first-page.md)` and [b](first-page.md)"
    assert rewrite(repo, text) == "`[a](first-page.md)` and [b](first-page)"


def test_mask_code_round_trips() -> None:
    line = "a `x` b ``y`` c"
    masked, spans = mask_code(line)
    assert "`" not in masked
    assert spans == ["`x`", "``y``"]
    assert unmask_code(masked, spans) == line


def test_safe_leaves_ordinary_text_alone() -> None:
    assert pw.safe("plain text: ok") == "plain text: ok"


def test_index_entry_written_with_code_span_text_is_not_an_orphan(repo: Path) -> None:
    write(
        repo,
        "docs/training/README.md",
        "# T\n\n- [`first-page.md`](first-page.md)\n\n- [Second](second-page.md)\n",
    )
    plan = pw.build_plan(repo / pw.SOURCE_DIR, repo, REPO_URL)
    assert [name for _title, name in plan.order] == ["first-page", "second-page"]


def test_index_link_with_a_query_string_is_not_an_orphan(repo: Path) -> None:
    write(repo, "docs/training/README.md", README + "\n- [again](first-page.md?x=1)\n")
    assert pw.build_plan(repo / pw.SOURCE_DIR, repo, REPO_URL).order


def test_strip_target_drops_fragment_and_query() -> None:
    assert strip_target("a.md#x") == "a.md"
    assert strip_target("a.md?q=1#x") == "a.md"
    assert readme_page_order("[a](a.md?q=1)") == ["a.md"]


def test_real_tree_leaves_no_relative_link_in_any_output_file() -> None:
    """Every link in the published files is absolute, a fragment, or a wiki page name."""
    root = Path(__file__).resolve().parents[2]
    plan = pw.build_plan(root / pw.SOURCE_DIR, root, REPO_URL)
    page_names = {name.removesuffix(".md") for name in plan.files}
    leftovers: list[str] = []
    for file_name, text in plan.files.items():
        for line, fenced in pw.split_fenced(text):
            if fenced:
                continue
            masked, _ = mask_code(line)
            for match in INLINE_LINK_RE.finditer(masked):
                target = match.group(2).strip("<>")
                bare = re.split(r"[#?]", target)[0]
                if target.startswith(("http://", "https://", "#")) or bare in page_names:
                    continue
                leftovers.append(f"{file_name}: {target}")
    assert leftovers == []


def test_apply_plan_replaces_a_directory_named_like_a_page(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    (wiki / "Home.md").mkdir(parents=True)
    (wiki / "Home.md" / "inner.txt").write_text("x", encoding="utf-8")
    (wiki / "Old.md").mkdir()
    (wiki / "Old.md" / "inner.txt").write_text("x", encoding="utf-8")
    plan = pw.Plan(files={"Home.md": "home\n"}, order=[])
    pw.apply_plan(plan, wiki)
    assert (wiki / "Home.md").read_text(encoding="utf-8") == "home\n"
    assert not (wiki / "Old.md").exists()


def test_clear_entry_removes_a_symlink_but_not_its_target(tmp_path: Path) -> None:
    target = tmp_path / "keep"
    target.mkdir()
    (target / "f.txt").write_text("x", encoding="utf-8")
    link = tmp_path / "link.md"
    symlink_or_skip(link, target)
    pw.clear_entry(link)
    assert not link.exists() and not link.is_symlink()
    assert (target / "f.txt").exists()
    shutil.rmtree(target)


def refuse_with(error: Exception) -> object:
    def refuse(self: Path, target: Path, target_is_directory: bool = False) -> None:
        raise error

    return refuse


def test_symlink_helper_skips_when_symlinks_are_not_implemented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "symlink_to", refuse_with(NotImplementedError("no symlinks")))
    with pytest.raises(pytest.skip.Exception, match="cannot create symbolic links"):
        symlink_or_skip(tmp_path / "link", tmp_path)


def test_symlink_helper_skips_an_oserror_only_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(helpers, "ON_WINDOWS", True)
    monkeypatch.setattr(Path, "symlink_to", refuse_with(OSError("privilege not held")))
    with pytest.raises(pytest.skip.Exception, match="cannot create symbolic links"):
        symlink_or_skip(tmp_path / "link", tmp_path)


def test_symlink_helper_fails_on_posix_for_an_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken fixture must not turn a guard test into a skip."""
    monkeypatch.setattr(helpers, "ON_WINDOWS", False)
    monkeypatch.setattr(Path, "symlink_to", refuse_with(FileExistsError("exists")))
    with pytest.raises(FileExistsError):
        symlink_or_skip(tmp_path / "link", tmp_path)


def test_symlink_helper_really_creates_a_link(tmp_path: Path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    symlink_or_skip(link, target)
    assert link.is_symlink()
    assert link.read_text(encoding="utf-8") == "x"
