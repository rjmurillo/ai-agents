#!/usr/bin/env python3
"""Shape guard for issue #2205: Copilot CLI hook path anchoring.

Copilot CLI runs hooks with ``cwd`` set to the user's working directory,
not the plugin root, so a bare ``./hooks/...`` relative path fails to
locate the vendored script. The generated commands must anchor the
script path to the plugin install location with the SAME fallback order
in both shells: ``COPILOT_PLUGIN_ROOT`` first, then ``CLAUDE_PLUGIN_ROOT``.

This module is a fast STRING-SHAPE check only. It cannot prove the path
resolves at runtime, nor catch a wrong environment-variable name (a test
that pins output to itself is the canonical-source-mirror anti-pattern;
see ``.claude/rules/canonical-source-mirror.md``). The runtime contract,
including resolution under a non-plugin ``cwd`` and the cross-shell
fallback, is enforced by ``test_generate_hooks_runtime_contract.py``.
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
      PreToolUse: PreToolUse
      SessionStart: SessionStart
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
    entry = out["hooks"]["SessionStart"][0]
    # bash: POSIX parameter-expansion fallback COPILOT -> CLAUDE.
    assert "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/hooks/" in entry["bash"]
    # powershell: if/else subexpression with the SAME fallback order.
    assert (
        "$(if ($env:COPILOT_PLUGIN_ROOT) "
        "{$env:COPILOT_PLUGIN_ROOT} else {$env:CLAUDE_PLUGIN_ROOT})/hooks/"
    ) in entry["powershell"]
    # Both shells reference both variables (symmetric fallback).
    for shell in ("bash", "powershell"):
        assert "COPILOT_PLUGIN_ROOT" in entry[shell]
        assert "CLAUDE_PLUGIN_ROOT" in entry[shell]
    # The fragile cwd-relative form must be gone from both shells.
    assert '"./hooks/' not in entry["bash"]
    assert '"./hooks/' not in entry["powershell"]
