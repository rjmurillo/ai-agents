"""Issue #6506: a link-spelled path under an unrelated outer ``.git`` fails closed.

``find_repo_root`` picks the outermost ``.git`` ancestor when a symlink sits
below it, so a path spelled through that link is refused. Split from
``test_atomic_write_confinement.py`` to keep both files under the taste
file-size limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import atomic_write  # noqa: E402


def _plant_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")


def _fake_checkout(root: Path) -> Path:
    (root / ".git").mkdir(parents=True)
    return root


def test_a_link_spelled_path_to_a_real_checkout_under_an_outer_git_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the fail-closed limit: an outer ``.git`` above the link becomes the root (#6506).

    ``outer`` is an unrelated repository (a dotfiles repo). ``outer/src`` links
    to ``data``, where ``data/repo`` is the real checkout. This layout cannot be
    told apart from a planted link to a nested checkout, so a path spelled
    through the link is refused. The resolved spelling of the same file is
    accepted, which is why callers pass resolved paths.
    """
    outer = _fake_checkout(tmp_path / "outer")
    data = tmp_path / "data"
    (data / "repo" / ".git").mkdir(parents=True)
    (data / "repo" / "d").mkdir()
    _plant_symlink(outer / "src", data)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    spelled = outer / "src" / "repo" / "d" / "file.md"

    assert atomic_write.find_repo_root(spelled) == outer
    with pytest.raises(OSError, match="symlinked ancestor"):
        atomic_write.publish_bytes_atomically(spelled, b"new\n")
    assert not (data / "repo" / "d" / "file.md").exists()

    resolved = spelled.resolve()
    assert atomic_write.find_repo_root(resolved) == (data / "repo").resolve()
    atomic_write.publish_bytes_atomically(resolved, b"new\n")
    assert resolved.read_bytes() == b"new\n"


def test_a_link_spelled_path_is_refused_when_the_cwd_is_inside_the_real_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cwd anchor does not rescue a link-spelled path: it is not lexically under the cwd."""
    outer = _fake_checkout(tmp_path / "outer")
    data = tmp_path / "data"
    (data / "repo" / ".git").mkdir(parents=True)
    (data / "repo" / "d").mkdir()
    _plant_symlink(outer / "src", data)
    monkeypatch.chdir(data / "repo")

    with pytest.raises(OSError, match="symlinked ancestor"):
        atomic_write.publish_bytes_atomically(outer / "src" / "repo" / "d" / "file.md", b"x\n")
    assert not (data / "repo" / "d" / "file.md").exists()
