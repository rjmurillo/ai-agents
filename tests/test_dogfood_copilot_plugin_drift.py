"""Drift-detection tests for the Copilot dogfood-install helper.

Split from ``test_dogfood_copilot_plugin.py`` to keep both files under the
500-line taste ceiling. Covers what ADR-092 changed: the manifests carry no
``version``, so ``_is_stale`` keys on a content fingerprint of the shipped tree
instead. A version-keyed detector read None on both sides and never fired.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev" / "dogfood_copilot_plugin.py"

_spec = importlib.util.spec_from_file_location("dogfood_copilot_plugin", _SCRIPT)
assert _spec is not None and _spec.loader is not None
dogfood = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dogfood)


def _make_plugin_root(path: Path, marker: str = "shipped") -> Path:
    """Create a minimal plugin root whose hook body carries marker."""
    (path / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "project-toolkit"}), encoding="utf-8"
    )
    (path / "hooks").mkdir(exist_ok=True)
    (path / "hooks" / "guard.py").write_text(marker, encoding="utf-8")
    return path


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return _make_plugin_root(tmp_path / "src" / "copilot-cli", "shipped")


@pytest.fixture
def target(tmp_path: Path) -> Path:
    return tmp_path / "installed" / "ai-agents" / "project-toolkit"


def test_fingerprint_ignores_dogfood_marker(source: Path, target: Path) -> None:
    # The marker exists only in the target, so it must not read as drift.
    before = dogfood._content_fingerprint(source)
    dogfood.dogfood_install(source, target)
    assert (target / ".dogfood").is_file()
    assert dogfood._content_fingerprint(target) == before


def test_fingerprint_ignores_pycache_written_after_install(source: Path, target: Path) -> None:
    # Running a hook from the installed copy leaves bytecode behind. That is
    # not a source edit and must not fire the advisory.
    dogfood.dogfood_install(source, target)
    cache = target / "hooks" / "__pycache__"
    cache.mkdir()
    (cache / "guard.cpython-314.pyc").write_bytes(b"\x00\x01")
    (target / "hooks" / "guard.pyc").write_bytes(b"\x00")
    assert dogfood._is_stale(source, target) is False


def test_fingerprint_detects_unversioned_hook_edit(source: Path, target: Path) -> None:
    # ADR-092 deletes the manifest version, so content is the only drift
    # signal left. An edited hook body with an identical manifest is stale.
    dogfood.dogfood_install(source, target)
    (source / "hooks" / "guard.py").write_text("edited", encoding="utf-8")
    assert dogfood._is_stale(source, target) is True
    stale, message = dogfood.dogfood_check(source, target)
    assert stale is True
    assert "--install" in message


def test_fingerprint_detects_added_and_removed_files(source: Path, target: Path) -> None:
    dogfood.dogfood_install(source, target)
    (source / "hooks" / "extra.py").write_text("new", encoding="utf-8")
    assert dogfood._is_stale(source, target) is True
    (source / "hooks" / "extra.py").unlink()
    assert dogfood._is_stale(source, target) is False
    (source / "hooks" / "guard.py").unlink()
    assert dogfood._is_stale(source, target) is True


def test_shipped_manifest_carries_no_version() -> None:
    # Regression for the ADR-092 hole: the real manifest has no version, so a
    # version-keyed detector read None on both sides and never fired. This
    # test fails the day someone re-couples drift detection to the field.
    root = Path(__file__).resolve().parents[1]
    manifest = root / "src" / "copilot-cli" / ".claude-plugin" / "plugin.json"
    assert "version" not in json.loads(manifest.read_text(encoding="utf-8"))


def test_check_flags_drift_on_the_real_shipped_tree(tmp_path: Path) -> None:
    # End to end against the shipped versionless manifest: install the real
    # hooks directory, edit one file, and the advisory must exit non-zero.
    root = Path(__file__).resolve().parents[1]
    shipped_manifest = (root / "src" / "copilot-cli" / ".claude-plugin" / "plugin.json").read_text(
        encoding="utf-8"
    )
    src = tmp_path / "src" / "copilot-cli"
    (src / ".claude-plugin").mkdir(parents=True)
    (src / ".claude-plugin" / "plugin.json").write_text(shipped_manifest, encoding="utf-8")
    shutil.copytree(root / "src" / "copilot-cli" / "hooks", src / "hooks")
    tgt = tmp_path / "installed" / "project-toolkit"
    dogfood.dogfood_install(src, tgt)
    assert dogfood.dogfood_check(src, tgt)[0] is False

    # Any tracked file in the shipped tree exercises the fingerprint; the
    # property under test is drift detection, not the file's language. ADR-097
    # retired every hook script, so the tree carries no .py file to edit and a
    # `.py`-only glob raised IndexError here. Widening to any file keeps the
    # test driving the real shipped tree whatever that tree currently holds.
    candidates = sorted(path for path in (src / "hooks").rglob("*") if path.is_file())
    assert candidates, "shipped hooks tree is empty; nothing to drift"
    hook = candidates[0]
    hook.write_text(hook.read_text(encoding="utf-8") + "\n# drift marker\n", encoding="utf-8")
    stale, message = dogfood.dogfood_check(src, tgt)
    assert stale is True
    assert "--install" in message
