#!/usr/bin/env python3
"""Gate: every plugin hook artifact anchors its scripts to the plugin root.

Both CLIs run a plugin hook with ``cwd`` set to the user's working directory,
NOT the plugin install dir, so a bare ``./hooks/...`` (or ``.claude/hooks/...``)
relative path fails with "No such file or directory". Issue #2205 hit this on
the Copilot side; the same trap applies to the Claude plugin. This gate keeps
the anchored form the enforced default for BOTH plugin hook files this repo
ships:

  - ``.claude/hooks/hooks.json``        Claude plugin (source ``./.claude``);
                                        anchored to ``${CLAUDE_PLUGIN_ROOT}``.
  - ``src/copilot-cli/hooks/hooks.json`` Copilot plugin (generated); anchored
                                        to ``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}``
                                        (bash) and the PowerShell equivalent.

For Copilot the expected command shape is taken from the generator
(``generate_hooks._build_copilot_entry``), so the gate cannot diverge from the
source of truth (canonical-source-mirror rule). For Claude the file is
hand-authored, so the gate asserts the anchoring invariant against the Claude
Code platform variable ``${CLAUDE_PLUGIN_ROOT}``. The runtime contract (both
CLIs export their plugin-root variable to the hook process, pointing at the
install dir) was verified empirically; see the Serena memory
``decision-copilot-cli-hook-plugin-root-contract``.

Exit codes (ADR-035): 0 ok, 1 anchoring violation(s), 2 config error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_COPILOT_REL = Path("src/copilot-cli/hooks/hooks.json")
_CLAUDE_REL = Path(".claude/hooks/hooks.json")
_COPILOT_FIELDS = ("bash", "powershell", "cwd")

# Claude Code platform variable that resolves to the plugin install dir.
_CLAUDE_ANCHOR = "${CLAUDE_PLUGIN_ROOT}"
# A command that launches a hook script: references a `hooks/<...>.py` path.
_HOOK_SCRIPT_RE = re.compile(r"hooks/\S*\.py")


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"hooks file not found: {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"cannot read/parse {path}: {exc}"


# --- Copilot (generated): compare each entry against the generator -----------


def _load_generator(repo_root: Path) -> ModuleType:
    scripts_dir = repo_root / "build" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import generate_hooks  # noqa: PLC0415

    return generate_hooks


def _script_name(command: str) -> str | None:
    parts = command.split('"')
    if len(parts) != 3:
        return None
    return parts[1].rsplit("/", 1)[-1]


def _check_copilot_entry(
    generate_hooks: ModuleType, event: str, index: int, entry: dict[str, Any]
) -> list[str]:
    bash = entry.get("bash", "")
    if not isinstance(bash, str):
        return [f"copilot {event}[{index}]: missing or non-string 'bash' field"]
    script_name = _script_name(bash)
    if script_name is None:
        return [f"copilot {event}[{index}]: cannot parse script path from bash: {bash!r}"]

    timeout = entry.get("timeoutSec", generate_hooks._DEFAULT_TIMEOUT_SEC)
    expected = generate_hooks._build_copilot_entry(event, script_name, timeout_sec=timeout)
    violations: list[str] = []
    for field in _COPILOT_FIELDS:
        if entry.get(field) != expected[field]:
            violations.append(
                f"copilot {event}[{index}].{field} drifted from the anchored generator form\n"
                f"      got:      {entry.get(field)!r}\n"
                f"      expected: {expected[field]!r}"
            )
    return violations


def _check_copilot(repo_root: Path) -> tuple[int, list[str], int]:
    """Return (count_checked, violations, config_error_code)."""
    doc, err = _load_json(repo_root / _COPILOT_REL)
    if err is not None:
        return 0, [err], 2
    events = doc.get("hooks") if isinstance(doc, dict) else None
    if not isinstance(events, dict) or not events:
        return 0, [f"no hook events in {_COPILOT_REL}"], 2
    try:
        generate_hooks = _load_generator(repo_root)
    except ImportError as exc:
        return 0, [f"cannot import generate_hooks: {exc}"], 2

    violations: list[str] = []
    checked = 0
    for event, entries in events.items():
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if isinstance(entry, dict):
                checked += 1
                violations.extend(_check_copilot_entry(generate_hooks, event, index, entry))
    return checked, violations, 0


# --- Claude (hand-authored): assert the ${CLAUDE_PLUGIN_ROOT} invariant -------


def _iter_commands(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        cmd = node.get("command")
        if isinstance(cmd, str):
            found.append(cmd)
        for value in node.values():
            found.extend(_iter_commands(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_iter_commands(item))
    return found


def _check_claude(repo_root: Path) -> tuple[int, list[str], int]:
    doc, err = _load_json(repo_root / _CLAUDE_REL)
    if err is not None:
        return 0, [err], 2
    commands = _iter_commands(doc)
    if not commands:
        return 0, [f"no command hooks in {_CLAUDE_REL}"], 2

    violations: list[str] = []
    checked = 0
    for cmd in commands:
        if not _HOOK_SCRIPT_RE.search(cmd):
            continue  # not a hook-script launch (e.g. a shell snippet)
        checked += 1
        if _CLAUDE_ANCHOR not in cmd:
            violations.append(
                "claude: hook command is not anchored to "
                f"{_CLAUDE_ANCHOR}; a bare/relative path fails when the plugin's "
                f"cwd is the user dir:\n      got: {cmd!r}"
            )
    return checked, violations, 0


def validate(repo_root: Path) -> tuple[int, list[str]]:
    """Validate both plugin hook artifacts. Returns (exit_code, messages)."""
    messages: list[str] = []
    total_checked = 0
    has_violation = False
    has_config_error = False

    for label, check in (("copilot", _check_copilot), ("claude", _check_claude)):
        checked, results, config_code = check(repo_root)
        total_checked += checked
        if config_code == 2:
            has_config_error = True
            messages.extend(results)
        elif results:
            has_violation = True
            messages.extend(results)
        else:
            messages.append(f"{label}: {checked} hook entr(ies) anchored correctly")

    if has_config_error:
        return 2, messages
    if has_violation:
        return 1, [m for m in messages if "drifted" in m or "not anchored" in m]
    return 0, [f"{total_checked} hook entr(ies) anchored correctly across both plugins"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (default: inferred from this script's location).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code, messages = validate(args.repo_root)
    if code == 0:
        print(f"[PASS] Hook anchoring: {messages[0]}")
        return 0
    if code == 1:
        print("[FAIL] Hook anchoring: unanchored or asymmetric command(s).")
        for msg in messages:
            print(f"  - {msg}")
        print()
        print("Fix: anchor every plugin hook to the plugin root.")
        print("  Copilot: python3 build/scripts/build_all.py --platform copilot-cli")
        print("  Claude:  use ${CLAUDE_PLUGIN_ROOT}/hooks/... in .claude/hooks/hooks.json")
        return 1
    for msg in messages:
        print(f"[ERROR] Hook anchoring: {msg}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
