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

For Copilot the expected command shape is taken from the two canonical builders:
``build/scripts/generate_hooks_emit.py::_build_copilot_entry(target_event:
str, script_name: str, *, timeout_sec: int = _DEFAULT_TIMEOUT_SEC)`` for direct
registrations and ``build/scripts/generate_dispatcher.py::dispatcher_entry(
event: str, timeout_sec: int, matcher: str | None = None)`` for consolidated
dispatchers. Dispatcher commands intentionally omit the direct-entry shell
redirects because ADR-068 assigns event-specific output control to the
dispatcher process. For Claude the file is hand-authored, so the gate asserts
the anchoring invariant against the Claude Code platform variable
``${CLAUDE_PLUGIN_ROOT}``. The runtime contract (both CLIs export their
plugin-root variable to the hook process, pointing at the install dir) was
verified empirically; see the Serena memory
``decision-copilot-cli-hook-plugin-root-contract``.

Zero registered hooks is a VALID anchored state (ADR-097 retired every
tool-call hook, leaving both manifests with ``"hooks": {}``). The invariant
this gate enforces, "every hook command anchors to the plugin root", is
satisfied over an empty set, so an empty mapping exits 0 and reports zero
entries examined rather than passing silently
(``.claude/rules/ci-scripts.md`` MUST 11 and MUST 12).

What stays fail-closed, so a BROKEN manifest is still distinguishable from a
deliberately empty one: a missing file, unparseable JSON, and a ``hooks`` key
that is absent or is not a mapping. Re-accretion is guarded separately by
``tests/hooks/test_zero_tool_use_hooks.py``, and regeneration drift by the
generator's own drift gate; neither invariant depends on this gate rejecting
the empty case.

Exit codes (ADR-035): 0 ok, 1 anchoring violation(s), 2 config error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

# Legacy fallback: the Copilot-CLI artifact path. Superseded by platform-
# config discovery (_find_platform_hook_artifacts) which reads this value
# from templates/platforms/copilot-cli.yaml artifacts.hooks.outputConfig.
# Kept so the validator degrades gracefully when the templates directory is
# absent (e.g. a minimal checkout).
_COPILOT_REL = Path("src/copilot-cli/hooks/hooks.json")

# Claude's hooks.json is hand-authored and not covered by any platform yaml's
# artifacts.hooks, so it remains an explicit constant.
_CLAUDE_REL = Path(".claude/hooks/hooks.json")
_COPILOT_FIELDS = ("bash", "powershell", "cwd")

# Claude Code platform variable that resolves to the plugin install dir.
_CLAUDE_ANCHOR = "${CLAUDE_PLUGIN_ROOT}"
# A command that launches a hook script: references a `hooks/<...>.py` path.
_HOOK_SCRIPT_RE = re.compile(r"hooks/\S*\.py")


def _find_platform_hook_artifacts(repo_root: Path) -> tuple[list[Path], list[str]]:
    """Return relative artifact paths and config errors for hook platforms.

    Reads ``templates/platforms/*.yaml`` and collects every
    ``artifacts.hooks.outputConfig`` value. When a new platform is added
    (Cortex, Factory Droid, VS Code), its hooks.json appears here
    automatically and the validator checks it on the next run, enforcing
    fail-closed behaviour for new platforms (fix #2231 item 2).

    Returns an empty artifact list when yaml is unavailable or when no platform
    declares hooks, triggering the legacy _COPILOT_REL fallback.
    """
    try:
        import yaml
    except ImportError:  # pragma: no cover
        return [], []
    platforms_dir = repo_root / "templates" / "platforms"
    if not platforms_dir.is_dir():
        return [], []
    artifacts: list[Path] = []
    errors: list[str] = []
    for yaml_path in sorted(platforms_dir.glob("*.yaml")):
        try:
            cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"cannot read/parse platform config {yaml_path}: {exc}")
            continue
        if not isinstance(cfg, dict):
            errors.append(f"platform config must be a mapping: {yaml_path}")
            continue
        artifacts_cfg = cfg.get("artifacts")
        if "artifacts" in cfg and not isinstance(artifacts_cfg, dict):
            errors.append(f"platform artifacts must be a mapping: {yaml_path}")
            continue
        hooks_cfg = artifacts_cfg.get("hooks") if isinstance(artifacts_cfg, dict) else None
        if (
            isinstance(artifacts_cfg, dict)
            and "hooks" in artifacts_cfg
            and not isinstance(hooks_cfg, dict)
        ):
            errors.append(f"platform hooks must be a mapping: {yaml_path}")
            continue
        output_config = hooks_cfg.get("outputConfig") if isinstance(hooks_cfg, dict) else None
        if isinstance(output_config, str) and output_config.strip():
            artifacts.append(Path(output_config.strip()))
    return artifacts, errors


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"hooks file not found: {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"cannot read/parse {path}: {exc}"


# --- Copilot (generated): compare each entry against the generator -----------


def _load_generators(repo_root: Path) -> tuple[ModuleType, ModuleType]:
    scripts_dir = repo_root / "build" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import generate_dispatcher
    import generate_hooks

    return cast(ModuleType, generate_hooks), cast(ModuleType, generate_dispatcher)


def _script_name(command: str) -> str | None:
    """Extract the hook script filename from a Copilot bash command.

    Handles both the legacy form (a single quoted path) and the guarded
    form introduced by issue #4672 where the command contains multiple
    quoted strings with the dispatch path near the end.
    """
    # Legacy form: exactly one quoted path
    parts = command.split('"')
    if len(parts) == 3:
        return parts[1].rsplit("/", 1)[-1]
    # Guarded form: look for the dispatch .py invocation pattern
    m = re.search(r'/hooks/\w+/([\w.]+\.py)', command)
    if m:
        return m.group(1)
    return None


def _check_copilot_entry(
    generate_hooks: ModuleType,
    generate_dispatcher: ModuleType,
    event: str,
    index: int,
    entry: dict[str, Any],
) -> list[str]:
    bash = entry.get("bash", "")
    if not isinstance(bash, str):
        return [f"copilot {event}[{index}]: missing or non-string 'bash' field"]
    script_name = _script_name(bash)
    if script_name is None:
        return [f"copilot {event}[{index}]: cannot parse script path from bash: {bash!r}"]

    timeout = entry.get("timeoutSec", generate_hooks._DEFAULT_TIMEOUT_SEC)
    if script_name == "_dispatch.py":
        expected = generate_dispatcher.dispatcher_entry(event, timeout)
    else:
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


def _check_copilot(
    repo_root: Path,
    artifact_rel: Path = _COPILOT_REL,
) -> tuple[int, list[str], int]:
    """Return (count_checked, violations, config_error_code).

    ``artifact_rel`` is the repo-relative path to the platform's hooks.json.
    Defaults to ``_COPILOT_REL`` for backwards compatibility; callers that
    use ``_find_platform_hook_artifacts`` pass the discovered path instead.
    """
    doc, err = _load_json(repo_root / artifact_rel)
    if err is not None:
        return 0, [err], 2
    events = doc.get("hooks") if isinstance(doc, dict) else None
    if not isinstance(events, dict):
        # Absent or non-mapping "hooks" key: the manifest is malformed, which
        # stays fail-closed. An EMPTY mapping is a different thing and is
        # handled below.
        return 0, [f"malformed or missing 'hooks' mapping in {artifact_rel}"], 2
    if not events:
        # Deliberately zero registered hooks (ADR-097). The invariant this gate
        # enforces, "every hook command anchors to the plugin root", is
        # satisfied over an empty set. Report zero examined rather than passing
        # silently, per .claude/rules/ci-scripts.md MUST 11 and MUST 12.
        return 0, [], 0
    try:
        generate_hooks, generate_dispatcher = _load_generators(repo_root)
    except ImportError as exc:
        return 0, [f"cannot import hook generators: {exc}"], 2

    violations: list[str] = []
    checked = 0
    for event, entries in events.items():
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if isinstance(entry, dict):
                checked += 1
                violations.extend(
                    _check_copilot_entry(
                        generate_hooks,
                        generate_dispatcher,
                        event,
                        index,
                        entry,
                    )
                )
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
    if not isinstance(doc, dict) or not isinstance(doc.get("hooks"), dict):
        return 0, [f"malformed or missing 'hooks' mapping in {_CLAUDE_REL}"], 2
    # Zero command hooks is valid (ADR-097); an unparseable or structurally
    # wrong manifest is not, and is rejected above.
    commands = _iter_commands(doc)

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
    """Validate all discovered plugin hook artifacts. Returns (exit_code, messages).

    Copilot-side hook artifacts are discovered dynamically from
    ``templates/platforms/*.yaml`` ``artifacts.hooks.outputConfig`` entries so
    that a new platform fails closed when it ships a hooks.json with
    unanchored entries (fix #2231 item 2).  Claude's hooks.json is
    hand-authored and stays as an explicit constant.
    """
    messages: list[str] = []
    violations: list[str] = []
    total_checked = 0
    has_violation = False
    has_config_error = False

    # Discover platform hook artifacts from templates/platforms/*.yaml.
    # Fall back to the hardcoded constant when discovery yields nothing.
    platform_artifacts, platform_errors = _find_platform_hook_artifacts(repo_root)
    if platform_errors:
        has_config_error = True
        messages.extend(platform_errors)
        violations.extend(platform_errors)
    if not platform_artifacts:
        platform_artifacts = [_COPILOT_REL]  # legacy fallback

    for artifact_rel in platform_artifacts:
        label = str(artifact_rel)
        checked, results, config_code = _check_copilot(repo_root, artifact_rel)
        total_checked += checked
        if config_code == 2:
            has_config_error = True
            messages.extend(results)
            violations.extend(results)
        elif results:
            has_violation = True
            messages.extend(results)
            violations.extend(results)
        else:
            messages.append(
                f"{label}: {checked} hook "
                f"{'entry' if checked == 1 else 'entries'} anchored correctly"
            )

    checked, results, config_code = _check_claude(repo_root)
    total_checked += checked
    if config_code == 2:
        has_config_error = True
        messages.extend(results)
        violations.extend(results)
    elif results:
        has_violation = True
        messages.extend(results)
        violations.extend(results)
    else:
        messages.append(
            f"claude: {checked} hook "
            f"{'entry' if checked == 1 else 'entries'} anchored correctly"
        )

    if has_config_error:
        return 2, messages
    if has_violation:
        return 1, violations
    entry_word = "entry" if total_checked == 1 else "entries"
    return 0, [
        f"{total_checked} hook {entry_word} anchored correctly across all plugins"
    ]


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
        print("  Copilot: uv run python build/scripts/build_all.py --platform copilot-cli")
        print("  Claude:  use ${CLAUDE_PLUGIN_ROOT}/hooks/... in .claude/hooks/hooks.json")
        return 1
    for msg in messages:
        print(f"[ERROR] Hook anchoring: {msg}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
