"""Hermes pack bytecode skip and stale-path report (issue #7659).

Pytest imports a pack's ``lib/`` and skill scripts and leaves ``__pycache__``
under ``src/hermes/``. Before the fix, ``apply_tree`` listed each cache file as
stale, so ``build_all.py --check`` exited 2. The pre-PR staleness gate then said
it "failed without listing stale paths", because the Hermes lines did not use
the ``STALENESS DETECTED`` shape its parser reads.

Coverage:

- positive: a ``.pyc`` in ``__pycache__``, a bare ``.pyc``, a ``.pyo``, and a
  non-bytecode file inside ``__pycache__`` all leave ``check`` at exit 0.
- negative: a real stale file beside the bytecode still fails with count 1; a
  lookalike ``__pycache__x`` folder is not skipped.
- edge: a write run leaves bytecode alone, so a retired pack that holds only a
  cache folder keeps it (git ignores both shapes, so no tracked file remains).
  A ``__pycache__`` symlink is not bytecode: check reports it, write removes it.
- conformance: the real ``apply_tree`` stderr parses through the gate's own
  ``parse_stale_report`` and ``failure_detail``; a file that both it and the
  real ``build_all._print_stale_paths`` block name counts once.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import build_all  # noqa: E402
import hermes_packs  # noqa: E402
from _hermes_pack_helpers import make_repo, make_stanza  # noqa: E402

from scripts.validation.generated_staleness_report import (  # noqa: E402
    UNCHANGED_PREFIX,
    failure_detail,
    parse_stale_report,
)

_PACK = "src/hermes/project-toolkit-one"


def _rendered(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    return repo, stanza


def _plant(repo: Path, rel: str) -> Path:
    path = repo / _PACK / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00bytecode")
    return path


@pytest.mark.parametrize(
    "rel",
    [
        "lib/__pycache__/mod.cpython-314.pyc",
        "skills/alpha/scripts/__pycache__/run.cpython-314.pyc",
        "lib/stray.pyc",
        "lib/stray.pyo",
        "lib/__pycache__/coverage.data",
    ],
)
def test_check_ignores_bytecode_under_a_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], rel: str
) -> None:
    repo, stanza = _rendered(tmp_path)
    _plant(repo, rel)
    capsys.readouterr()

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 0
    captured = capsys.readouterr()
    assert "stale: 0" in captured.out
    assert rel not in captured.out + captured.err


def test_a_real_stale_file_beside_bytecode_still_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, stanza = _rendered(tmp_path)
    _plant(repo, "lib/__pycache__/mod.cpython-314.pyc")
    _plant(repo, "skills/old/SKILL.md")
    capsys.readouterr()

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1
    out = capsys.readouterr().out
    assert "stale: 1" in out
    assert "skills/old/SKILL.md" in out


def test_a_lookalike_cache_folder_is_not_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, stanza = _rendered(tmp_path)
    _plant(repo, "lib/__pycache__x/mod.py")
    capsys.readouterr()

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1
    assert "stale: 1" in capsys.readouterr().out


def test_a_write_run_leaves_bytecode_in_place(tmp_path: Path) -> None:
    repo, stanza = _rendered(tmp_path)
    cache = _plant(repo, "lib/__pycache__/mod.cpython-314.pyc")

    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert cache.is_file()


def test_a_retired_pack_keeps_only_its_cache_folder(tmp_path: Path) -> None:
    repo, _ = _rendered(tmp_path)
    cache = repo / "src/hermes/project-toolkit-two/lib/__pycache__/mod.cpython-314.pyc"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"\x00bytecode")
    only_one = make_stanza(
        packs={"one": {"description": "First pack.", "skills": ["alpha", "beta", "gamma"]}}
    )

    assert hermes_packs.generate_hermes_packs(only_one, repo) == 0
    retired = repo / "src/hermes/project-toolkit-two"
    assert sorted(p.relative_to(retired).as_posix() for p in retired.rglob("*") if p.is_file()) == [
        "lib/__pycache__/mod.cpython-314.pyc"
    ]


def _link_cache_to_an_empty_dir(tmp_path: Path, repo: Path) -> tuple[Path, Path]:
    target = tmp_path / "empty-cache-target"
    target.mkdir()
    link = repo / _PACK / "lib/__pycache__"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        # Windows without Developer Mode denies symlinks (issue #4632).
        pytest.skip(f"symlink creation unavailable: {exc}")
    return link, target


def test_a_write_run_removes_a_cache_symlink(tmp_path: Path) -> None:
    # CPython writes bytecode as regular files, so a symlink is never bytecode.
    # Kept on disk, a link to an empty folder reached ``rmdir`` in the prune.
    repo, stanza = _rendered(tmp_path)
    link, target = _link_cache_to_an_empty_dir(tmp_path, repo)

    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert not link.is_symlink()
    assert target.is_dir()


def test_check_reports_a_cache_symlink_as_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, stanza = _rendered(tmp_path)
    _link_cache_to_an_empty_dir(tmp_path, repo)
    capsys.readouterr()

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1
    captured = capsys.readouterr()
    assert "stale: 1" in captured.out
    assert parse_stale_report(captured.err).paths == (f"{_PACK}/lib/__pycache__",)


def test_check_names_stale_and_drifted_paths_for_the_pre_pr_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, stanza = _rendered(tmp_path)
    _plant(repo, "skills/old/SKILL.md")
    (repo / _PACK / "skills/beta/SKILL.md").write_text("hand edit\n", encoding="utf-8")
    capsys.readouterr()

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1
    # An all-unchanged marker alone would set ``uncommitted_only``; a Hermes
    # line in the same run must clear it, because the hand edit is not regen.
    marker = f"{UNCHANGED_PREFIX} 2 of 2 drifted path(s) match the generators.\n"
    report = parse_stale_report(marker + capsys.readouterr().err)

    stale = f"{_PACK}/skills/old/SKILL.md"
    drifted = f"{_PACK}/skills/beta/SKILL.md"
    assert sorted(report.paths) == sorted([stale, drifted])
    assert report.hint.startswith(UNCHANGED_PREFIX)
    assert report.uncommitted_only is False
    detail = failure_detail(report)
    assert stale in detail
    assert drifted in detail
    assert "without listing stale paths" not in detail


def test_a_file_both_lists_name_counts_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, stanza = _rendered(tmp_path)
    _plant(repo, "skills/old/SKILL.md")
    capsys.readouterr()
    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1
    build_all._print_stale_paths(repo, [f"{_PACK}/skills/old/SKILL.md"], None)

    report = parse_stale_report(capsys.readouterr().err)

    assert report.paths == (f"{_PACK}/skills/old/SKILL.md",)
    assert failure_detail(report).startswith("1 generated path(s) differ from HEAD:")


def test_apply_tree_prefixes_stale_lines_with_the_report_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "out"
    root.mkdir()
    (root / "orphan.md").write_text("x", encoding="utf-8")

    counts = hermes_packs.apply_tree(root, {}, check=True, what_if=False, report_root="src/x")
    assert counts == (0, 1)
    assert parse_stale_report(capsys.readouterr().err).paths == ("src/x/orphan.md",)


@pytest.mark.parametrize(("check", "what_if"), [(False, False), (False, True)])
def test_only_check_prints_staleness_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], check: bool, what_if: bool
) -> None:
    repo, stanza = _rendered(tmp_path)
    _plant(repo, "skills/old/SKILL.md")
    capsys.readouterr()

    hermes_packs.generate_hermes_packs(stanza, repo, check=check, what_if=what_if)
    assert "STALENESS DETECTED" not in capsys.readouterr().err
