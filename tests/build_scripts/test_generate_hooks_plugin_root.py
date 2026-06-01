#!/usr/bin/env python3
"""Regression test for issue #2205: Copilot CLI hook path anchoring.

Copilot CLI runs hooks with ``cwd`` set to the user's working directory,
not the plugin root, so a bare ``./hooks/...`` relative path fails to
locate the vendored script. The generated commands must anchor the
script path to the plugin install location via ``${COPILOT_PLUGIN_ROOT}``
(bash, with a ``${CLAUDE_PLUGIN_ROOT}`` fallback) and
``$env:COPILOT_PLUGIN_ROOT`` (powershell).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_hooks  # noqa: E402

_PLATFORM_YAML = """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  hooks:
    settingsSource: "settings.json"
    scriptSource: "hooks_src"
    outputConfig: "out/hooks.json"
    outputScripts: "out"
    eventRemap:
      PreToolUse: preToolUse
      SessionStart: sessionStart
    eventDrop: []
    matcherPolicy: "inline-script-shim"
    versionField: 1
"""

_SCRIPT_BODY = "import sys\nsys.exit(0)\n"
_COMMAND = "python3 -u .claude/hooks/SessionStart/init.py"


def _materialize(tmp_path: Path) -> Path:
    """Write a minimal platform config, settings.json, and script tree."""
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(_PLATFORM_YAML, encoding="utf-8")

    script = tmp_path / "hooks_src" / "SessionStart" / "init.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(_SCRIPT_BODY, encoding="utf-8")

    settings_obj: dict[str, object] = {
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": _COMMAND}]},
            ],
        },
    }
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(settings_obj, indent=2), encoding="utf-8")
    return cfg


def test_generator_anchors_script_path_to_plugin_root(tmp_path: Path) -> None:
    """Hook commands anchor scripts to the plugin root, not the cwd (#2205)."""
    cfg = _materialize(tmp_path)
    rc, _ = generate_hooks.generate_hooks(cfg, tmp_path)
    assert rc == 0

    out = json.loads((tmp_path / "out" / "hooks.json").read_text(encoding="utf-8"))
    entry = out["hooks"]["sessionStart"][0]
    assert "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/hooks/" in entry["bash"]
    assert "$env:COPILOT_PLUGIN_ROOT/hooks/" in entry["powershell"]
    # The fragile cwd-relative form must be gone from both shells.
    assert '"./hooks/' not in entry["bash"]
    assert '"./hooks/' not in entry["powershell"]
