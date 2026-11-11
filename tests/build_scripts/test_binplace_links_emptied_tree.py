"""Binplace link sweeping when a plugin tree is emptied or absent (issue #7224).

Deleting a template prunes its rendered plugin entry, so the plugin tree can end
up empty. ``link_row`` must still sweep the install links that now dangle, and
must report nothing for a plugin tree that does not exist.
Split from ``test_binplace_links.py`` to keep that file under the size limit.
"""

from __future__ import annotations

import os
import shutil
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
    (plugin / "alpha").mkdir(parents=True)
    (plugin / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
    (plugin / "beta.md").write_text("beta\n", encoding="utf-8")
    return plugin


def _install(root: Path) -> Path:
    return root / ".claude" / "skills"


def test_emptied_plugin_tree_still_sweeps_the_links_to_its_removed_entries(
    tmp_path: Path,
) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    binplace_links.link_row(plugin, install, check=False)
    (plugin / "beta.md").unlink()
    shutil.rmtree(plugin / "alpha")

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 0
    assert not os.path.lexists(install / "alpha")
    assert not os.path.lexists(install / "beta.md")


def test_emptied_plugin_tree_reports_the_dangling_links_as_drift_in_check_mode(
    tmp_path: Path,
) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    binplace_links.link_row(plugin, install, check=False)
    (plugin / "beta.md").unlink()
    shutil.rmtree(plugin / "alpha")

    outcome = binplace_links.link_row(plugin, install, check=True)

    assert outcome.exit_code == 2
    assert os.path.lexists(install / "alpha")


def test_absent_plugin_tree_reports_nothing_and_creates_nothing(tmp_path: Path) -> None:
    install = _install(tmp_path)

    outcome = binplace_links.link_row(tmp_path / "src" / "claude" / "skills", install, check=False)

    assert outcome.exit_code == 0
    assert outcome.written == []
    assert outcome.unowned == []
    assert not install.exists()
