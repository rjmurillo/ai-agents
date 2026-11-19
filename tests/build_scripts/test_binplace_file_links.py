"""Tests for file-shaped ``link: true`` binplace rows (ADR-119 amendment 2026-11-04).

The ``hooks-json`` row links one file, ``.claude/hooks/hooks.json``, to
``src/claude/hooks/hooks.json`` (owner decision D28, 2026-11-04, REQ-048
TASK-006). Split from ``test_binplace_links.py`` to keep both files under the
500-line taste cap.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BUILD_SCRIPTS = _REPO_ROOT / "build" / "scripts"
if str(_BUILD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BUILD_SCRIPTS))
_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import binplace_links  # noqa: E402
import binplace_manifest  # noqa: E402
from test_binplace_links import _manifest  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs Developer Mode on Windows"
)


def _hooks_json_repo(root: Path) -> tuple[Path, Path]:
    """Build a repo whose only row is the file-shaped ``hooks-json`` link row."""
    (root / ".git").mkdir(exist_ok=True)
    platforms = root / "templates" / "platforms"
    platforms.mkdir(parents=True, exist_ok=True)
    (platforms / "binplace.yaml").write_text(
        'schemaVersion: "1.0"\n'
        "rows:\n"
        "  - class: hooks-json\n"
        "    source: templates/hooks/hooks.json\n"
        "    plugin_tree: src/claude/hooks/hooks.json\n"
        "    install_tree: .claude/hooks/hooks.json\n"
        "    link: true\n",
        encoding="utf-8",
    )
    plugin_file = root / "src" / "claude" / "hooks" / "hooks.json"
    plugin_file.parent.mkdir(parents=True)
    plugin_file.write_text('{"hooks": {}}\n', encoding="utf-8")
    return plugin_file, root / ".claude" / "hooks" / "hooks.json"


def test_file_shaped_link_row_links_one_file_and_allowlists_it(tmp_path: Path) -> None:
    plugin_file, install_file = _hooks_json_repo(tmp_path)

    written = binplace_manifest.binplace(tmp_path, check=False)

    assert written.exit_code == 0
    assert os.readlink(install_file) == "../../src/claude/hooks/hooks.json"
    assert install_file.read_bytes() == plugin_file.read_bytes()
    assert binplace_manifest.binplace(tmp_path, check=True).exit_code == 0
    assert install_file in binplace_manifest.claude_allowlist(tmp_path)
    assert install_file in binplace_manifest.verified_file_links(tmp_path)


def test_file_shaped_link_row_replaces_a_real_copy_and_reports_it_in_check(
    tmp_path: Path,
) -> None:
    _, install_file = _hooks_json_repo(tmp_path)
    install_file.parent.mkdir(parents=True)
    install_file.write_text('{"hooks": {}}\n', encoding="utf-8")

    checked = binplace_manifest.binplace(tmp_path, check=True)

    assert checked.exit_code == 2
    assert str(install_file) in checked.drifted
    assert not install_file.is_symlink()
    assert install_file not in binplace_manifest.verified_file_links(tmp_path)
    binplace_manifest.binplace(tmp_path, check=False)
    assert install_file.is_symlink()


def test_file_shaped_link_with_wrong_target_is_unverified_drift_and_is_repaired(
    tmp_path: Path,
) -> None:
    _, install_file = _hooks_json_repo(tmp_path)
    install_file.parent.mkdir(parents=True)
    (tmp_path / "other.json").write_text("{}\n", encoding="utf-8")
    install_file.symlink_to("../../other.json")

    assert install_file not in binplace_manifest.verified_file_links(tmp_path)
    assert binplace_manifest.binplace(tmp_path, check=True).exit_code == 2
    assert os.readlink(install_file) == "../../other.json"
    binplace_manifest.binplace(tmp_path, check=False)
    assert os.readlink(install_file) == "../../src/claude/hooks/hooks.json"


def test_directory_shaped_link_row_still_refuses_a_symlinked_install_tree(
    tmp_path: Path,
) -> None:
    (tmp_path / "src" / "claude" / "agents").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "agents").symlink_to("../elsewhere", target_is_directory=True)
    _manifest(tmp_path, "    link: true\n")

    with pytest.raises(binplace_manifest.BinplaceConfigError, match="is a symlink"):
        binplace_manifest.load(tmp_path)


def test_file_shaped_link_refuses_a_plugin_file_that_is_a_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plugin_file, install_file = _hooks_json_repo(tmp_path)
    real = tmp_path / "real.json"
    plugin_file.rename(real)
    plugin_file.symlink_to(real)

    outcome = binplace_links.link_file(plugin_file, install_file, check=False)

    assert outcome.exit_code == 2
    assert not install_file.exists()
    assert "refusing to link it" in capsys.readouterr().err


def test_file_shaped_link_with_no_plugin_file_links_nothing(tmp_path: Path) -> None:
    outcome = binplace_links.link_file(
        tmp_path / "src" / "missing.json", tmp_path / ".claude" / "missing.json", check=False
    )

    assert outcome.exit_code == 0
    assert outcome.written == []
    assert not (tmp_path / ".claude").exists()


def test_live_manifest_links_hooks_json_and_hooks_row_skips_it() -> None:
    rows = {row.class_name: row for row in binplace_manifest.load(_REPO_ROOT)}

    assert rows["hooks-json"].link is True
    assert rows["hooks-json"].plugin_tree == _REPO_ROOT / "src" / "claude" / "hooks" / "hooks.json"
    assert rows["hooks"].link is False
    assert binplace_manifest._repo_local_names(_REPO_ROOT, rows["hooks"]) == (
        frozenset({"hooks.json"}) | rows["hooks"].repo_only
    )
