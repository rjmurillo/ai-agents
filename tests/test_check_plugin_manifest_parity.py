"""Tests for build/scripts/check_plugin_manifest_parity.py (fix #2222)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "build" / "scripts" / "check_plugin_manifest_parity.py"


def _make_wrapper(tmp_path: Path, *, claude_ver: str, copilot_ver: str) -> Path:
    """Write a small wrapper that overrides _MANIFESTS and calls main()."""
    claude_manifest = tmp_path / "claude_plugin.json"
    copilot_manifest = tmp_path / "copilot_plugin.json"
    claude_manifest.write_text(json.dumps({"version": claude_ver}), encoding="utf-8")
    copilot_manifest.write_text(json.dumps({"version": copilot_ver}), encoding="utf-8")
    wrapper = tmp_path / "run.py"
    wrapper.write_text(
        f"import sys, importlib.util, pathlib\n"
        f"spec = importlib.util.spec_from_file_location('parity', {str(SCRIPT)!r})\n"
        f"mod = importlib.util.module_from_spec(spec)\n"
        f"sys.modules['parity'] = mod\n"
        f"spec.loader.exec_module(mod)\n"
        f"mod._MANIFESTS = (\n"
        f"    pathlib.Path({str(claude_manifest)!r}),\n"
        f"    pathlib.Path({str(copilot_manifest)!r}),\n"
        f")\n"
        f"sys.exit(mod.main())\n",
        encoding="utf-8",
    )
    return wrapper


def test_matching_versions_exit_0(tmp_path: Path) -> None:
    wrapper = _make_wrapper(tmp_path, claude_ver="1.0.0", copilot_ver="1.0.0")
    rc = subprocess.run([sys.executable, str(wrapper)], timeout=15).returncode
    assert rc == 0


def test_mismatched_versions_exit_1(tmp_path: Path) -> None:
    wrapper = _make_wrapper(tmp_path, claude_ver="1.0.1", copilot_ver="1.0.0")
    rc = subprocess.run([sys.executable, str(wrapper)], timeout=15).returncode
    assert rc == 1


def test_real_repo_manifests_currently_match() -> None:
    """Regression: real repo manifests must match (fixes drift from #2203)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"plugin manifest version mismatch:\n{result.stdout}\n{result.stderr}"
    )
