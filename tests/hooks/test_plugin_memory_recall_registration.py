#!/usr/bin/env python3
"""Plugin registration of the memory recall group (issue #7493, ADR-085 Decision 7 item 9).

Mirrors the three kinds of test ``tests/hooks/test_plugin_stop_registration.py``
holds for the reflect nudge: the Copilot-side absence regression, the
Claude-side presence regression, and the inverse control that shows the flag
causes the absence. The exclusion is a NON-SECURITY scope choice recorded in
the ``description`` of ``templates/hooks/dispatch_groups.json`` and in ADR-109
(amendment 2026-11-20).
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

from tests.hooks import test_dispatch_groups_parity as parity

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPTS = str(REPO_ROOT / "build" / "scripts")
if BUILD_SCRIPTS not in sys.path:
    sys.path.insert(0, BUILD_SCRIPTS)

from generate_hooks_events import _expand_dispatch_groups

GROUP = "plugin-userpromptsubmit-1-memory_recall"
SHIM = "UserPromptSubmit/invoke_memory_recall.py"
CLAUDE_PLUGIN_HOOKS_DIR = REPO_ROOT / "src" / "claude" / "hooks"
CLAUDE_PLUGIN_HOOKS = CLAUDE_PLUGIN_HOOKS_DIR / "hooks.json"
COPILOT_HOOKS = REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _commands(doc: dict, event: str) -> list[str]:
    return [h["command"] for entry in doc["hooks"].get(event, []) for h in entry["hooks"]]


def test_group_is_a_plugin_surface_user_prompt_submit_group_excluded_from_copilot() -> None:
    spec = parity.MANIFEST["groups"][GROUP]
    assert spec["event"] == "UserPromptSubmit"
    assert spec["mode"] == "gate_all"
    assert spec["surface"] == "plugin"
    assert "advisory" not in spec
    (shim,) = spec["shims"]
    assert shim["file"] == SHIM
    assert shim["copilotExclude"] is True
    assert shim["copilotExcludeIssue"] == "#7493"
    assert shim["copilotExcludeDecision"] == "ADR-109"
    assert re.fullmatch(r"ADR-\d+", shim["copilotExcludeDecision"])


def test_the_manifest_description_records_the_reintroduction_and_cleanup_items() -> None:
    description = parity.MANIFEST["description"]
    tail = description[description.index(f"{GROUP} is a NON-SECURITY exclusion") :]

    assert "Item 7, reintroduction" in tail
    assert "userPromptSubmitted" in tail
    assert "userPromptTransformed live delivery is verified and gated" in tail
    assert "#7493" in tail
    assert "Item 8, cleanup" in tail


def test_claude_plugin_registers_the_group_on_user_prompt_submit_without_advisory() -> None:
    (command,) = _commands(_load(CLAUDE_PLUGIN_HOOKS), "UserPromptSubmit")

    assert f"--group {GROUP};" in command
    assert "--advisory" not in command
    assert "${CLAUDE_PLUGIN_ROOT}/hooks/invoke_dispatch_claude.py" in command


def test_claude_plugin_ships_the_shim_and_the_package() -> None:
    assert (CLAUDE_PLUGIN_HOOKS_DIR / SHIM).is_file()
    assert (REPO_ROOT / "src" / "claude" / "lib" / "memory_enhancement" / "__init__.py").is_file()


def test_copilot_plugin_has_no_entry_for_the_hook() -> None:
    doc = _load(COPILOT_HOOKS)
    assert "invoke_memory_recall" not in json.dumps(doc)
    assert GROUP not in json.dumps(doc)
    assert doc["hooks"].get("UserPromptSubmit", []) == []
    assert doc["hooks"].get("userPromptSubmitted", []) == []


def _expand(manifest_groups: dict, tmp_path: Path) -> dict:
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "dispatch_groups.json").write_text(
        json.dumps({"groups": manifest_groups}), encoding="utf-8"
    )
    return _expand_dispatch_groups(_load(CLAUDE_PLUGIN_HOOKS)["hooks"], hooks_dir)


def test_expansion_omits_the_excluded_shim(tmp_path: Path) -> None:
    expanded = _expand(_load(CLAUDE_PLUGIN_HOOKS_DIR / "dispatch_groups.json")["groups"], tmp_path)

    assert "invoke_memory_recall" not in json.dumps(expanded)


def test_flipping_the_flag_puts_the_hook_back_on_copilot(tmp_path: Path) -> None:
    """Inverse control: the absence above is caused by the flag, not by luck."""
    groups = copy.deepcopy(_load(CLAUDE_PLUGIN_HOOKS_DIR / "dispatch_groups.json")["groups"])
    groups[GROUP]["shims"][0]["copilotExclude"] = False

    expanded = _expand(groups, tmp_path)

    assert "invoke_memory_recall.py" in json.dumps(expanded)
