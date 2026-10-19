"""Nested symlinks in a binplace entry are refused, and a refused entry
must not leave its earlier install link reachable."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BUILD_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "build" / "scripts"
if str(_BUILD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BUILD_SCRIPTS))

import binplace_links  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs Developer Mode on Windows"
)


def _plugin(root: Path) -> Path:
    plugin = root / "src" / "claude" / "skills"
    (plugin / "alpha" / "scripts").mkdir(parents=True)
    (plugin / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
    (plugin / "alpha" / "scripts" / "run.py").write_text("print(1)\n", encoding="utf-8")
    (plugin / "beta.md").write_text("beta\n", encoding="utf-8")
    return plugin


def _install(root: Path) -> Path:
    return root / ".claude" / "skills"


def test_refused_nested_symlink_withdraws_a_previously_installed_link(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    assert binplace_links.link_row(plugin, install, check=False).exit_code == 0
    assert (install / "alpha").is_symlink()
    (tmp_path / "outside").mkdir()
    (plugin / "alpha" / "scripts" / "sub").symlink_to(
        tmp_path / "outside", target_is_directory=True
    )

    check = binplace_links.link_row(plugin, install, check=True)
    assert check.exit_code == 2
    assert (install / "alpha").is_symlink(), "check mode writes nothing"

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 2
    assert not (install / "alpha").is_symlink()
    assert (install / "beta.md").is_symlink(), "other entries stay linked"


def test_refused_entry_keeps_a_real_directory_at_the_install_path(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (install / "alpha").mkdir(parents=True)
    (install / "alpha" / "mine.txt").write_text("edit\n", encoding="utf-8")
    (plugin / "alpha" / "SKILL.link").symlink_to("SKILL.md")

    binplace_links.link_row(plugin, install, check=False)

    assert (install / "alpha" / "mine.txt").read_text(encoding="utf-8") == "edit\n"


def test_symlink_nested_inside_an_entry_is_refused(tmp_path: Path, capsys) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (tmp_path / "outside").mkdir()
    nested = plugin / "alpha" / "scripts" / "sub"
    nested.symlink_to(tmp_path / "outside", target_is_directory=True)

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 2
    assert str(nested) in outcome.drifted
    assert str(nested) in capsys.readouterr().err
    assert not (install / "alpha").exists(), "the unsafe entry is not linked"
    assert (install / "beta.md").is_symlink(), "other entries still link"


def test_nested_symlink_is_refused_in_check_mode(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (plugin / "alpha" / "SKILL.link").symlink_to("SKILL.md")

    outcome = binplace_links.link_row(plugin, install, check=True)

    assert outcome.exit_code == 2
    assert str(plugin / "alpha" / "SKILL.link") in outcome.drifted


def test_clean_tree_with_bytecode_passes(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    cache = plugin / "alpha" / "scripts" / "__pycache__"
    cache.mkdir()
    (cache / "run.cpython-314.pyc").write_bytes(b"\0")

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 0
    assert (install / "alpha").is_symlink()
