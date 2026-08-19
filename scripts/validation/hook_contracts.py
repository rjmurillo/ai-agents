#!/usr/bin/env python3
"""Validate Claude Code hook contracts between settings.json and hook scripts.

Parses .claude/settings.json and validates that every referenced hook script:
1. Exists on disk
2. Documents its hook type in docstring
3. Documents exit codes consistent with hook type semantics
4. Has reasonable timeout values (when specified)

Exit codes follow ADR-035:
    0 - Success (no violations, or non-CI mode)
    1 - Logic error (violations found, CI mode)
    2 - Config error (settings.json not found or invalid)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Hook types where exit code 2 = block
BLOCKING_HOOK_TYPES = frozenset(
    {"PreToolUse", "PermissionRequest", "Stop", "SubagentStop", "UserPromptSubmit"}
)

# Hook types where exit code is always 0 (non-blocking)
NON_BLOCKING_HOOK_TYPES = frozenset(
    {
        "SessionStart",
        "SessionEnd",
        "PostToolUse",
        "PostToolUseFailure",
        "Notification",
        "SubagentStart",
        "PreCompact",
        "TeammateIdle",
        "TaskCompleted",
    }
)

ALL_HOOK_TYPES = BLOCKING_HOOK_TYPES | NON_BLOCKING_HOOK_TYPES

# Timeout bounds in seconds
MIN_TIMEOUT = 1
MAX_TIMEOUT = 300

# Pattern to extract script path from command string
_SCRIPT_PATH_PATTERN = re.compile(
    r"(?:python3?|\"?\$(?:_interp|_i)\"?)\s+(?:-\w+\s+)*\"?([^;>|&\s]+\.py)\"?(?:\s|;|$)"
)

# Plugin registrations address their scripts through the harness-provided
# plugin root. Inside the checkout that publishes the plugin, that root is a
# real directory, so resolving it lets the same contract cover the published
# surface. Each surface publishes from a different one.
CLAUDE_ROOT = ".claude"
COPILOT_ROOT = "src/copilot-cli"

#
# The default clause excludes both braces, so a nested fallback like
# ${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}} is not consumed up to the inner
# brace. The shipped copilot-cli registrations use exactly that form; a pattern
# that allowed { in the default matched only the inner expansion and left a
# stray } in the extracted path, which reads as a missing script.
_PLUGIN_ROOT_PATTERN = re.compile(
    r"\$\{(?:CLAUDE|COPILOT)_PLUGIN_ROOT(?::-[^{}]*)?\}|\$_ptr"
)

# A nested default needs more than one pass: the inner expansion resolves
# first, which turns the outer one into the simple form the pattern matches.
_MAX_PLUGIN_ROOT_PASSES = 5

# Pattern to detect PowerShell commands
_PWSH_PATTERN = re.compile(r"(?:pwsh|powershell)\s+.*\.ps1(?:\s|$)", re.IGNORECASE)

# ANSI color codes (disabled when NO_COLOR is set or in CI)
_USE_COLOR = not (os.environ.get("NO_COLOR") or os.environ.get("CI"))
_COLOR_RESET = "\033[0m" if _USE_COLOR else ""
_COLOR_RED = "\033[31m" if _USE_COLOR else ""
_COLOR_YELLOW = "\033[33m" if _USE_COLOR else ""
_COLOR_GREEN = "\033[32m" if _USE_COLOR else ""
_COLOR_CYAN = "\033[36m" if _USE_COLOR else ""


@dataclass
class Violation:
    """A hook contract violation."""

    hook_type: str
    script: str
    category: str
    message: str


@dataclass
class HookEntry:
    """A parsed hook entry from settings.json."""

    hook_type: str
    script_path: str
    command: str
    matcher: str | None = None
    timeout: int | None = None
    status_message: str | None = None


@dataclass
class ContractReport:
    """Summary of hook contract validation."""

    entries: list[HookEntry] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.violations) == 0


def _resolve_script_path(base_path: Path, script_path: str) -> Path | None:
    """Resolve a script path and verify it stays within base_path."""
    try:
        candidate = (base_path / script_path).resolve(strict=False)
        candidate.relative_to(base_path.resolve())
    except (ValueError, OSError):
        return None
    return candidate


def _resolve_plugin_root(path: str, root: str = CLAUDE_ROOT) -> str:
    """Substitute plugin-root expansions until none are left.

    One pass is not enough for a nested default: resolving the inner
    ${CLAUDE_PLUGIN_ROOT} is what turns the outer expansion into a form the
    pattern can match. The pass count is bounded so a pathological string
    cannot spin.

    ``root`` is the checkout directory that publishes the surface being read.
    The same registration text ships on two surfaces, and the expansion means a
    different directory on each, so the caller that knows which file it opened
    supplies it.
    """
    for _ in range(_MAX_PLUGIN_ROOT_PASSES):
        resolved = _PLUGIN_ROOT_PATTERN.sub(root, path)
        if resolved == path:
            return resolved
        path = resolved
    return path


def extract_script_path(command: str, root: str = CLAUDE_ROOT) -> str | None:
    """Extract the Python script path from a hook command string."""
    match = _SCRIPT_PATH_PATTERN.search(command)
    if not match:
        return None
    return _resolve_plugin_root(match.group(1), root).strip("\"'")


_GROUP_FLAG_PATTERN = re.compile(r"--group\s+([A-Za-z0-9_.-]+)")

# Only the dispatcher fans a registration out to a group. Keying expansion on
# the bare --group flag would mis-expand any hook that happens to take one.
DISPATCHER_SCRIPT_NAME = "invoke_dispatch_claude.py"

DISPATCH_GROUPS_PATH = Path(CLAUDE_ROOT) / "hooks" / "dispatch_groups.json"
PLUGIN_HOOKS_PATH = Path(CLAUDE_ROOT) / "hooks" / "hooks.json"

# The Copilot surface registers the same shims through a different file shape.
# Its entries sit directly under the event rather than inside a nested "hooks"
# list, carry the command under "bash" rather than "command", and spell the
# timeout "timeoutSec". It also dispatches per event directory instead of
# through one script taking --group, so its shim membership lives in a manifest
# beside each dispatcher rather than in one central map.
COPILOT_HOOKS_PATH = Path(COPILOT_ROOT) / "hooks" / "hooks.json"
COPILOT_DISPATCHER_NAME = "_dispatch.py"
COPILOT_MANIFEST_NAME = "_manifest.json"


def _load_dispatch_groups(base_path: Path) -> tuple[dict, list[Violation]]:
    """Read the group membership map the dispatcher fans out to.

    A missing file is not a violation: a checkout with no grouped hooks is
    legitimate. A malformed one is, because the dispatcher would fail at
    runtime, and it fails closed: every dispatched tool call is blocked.
    """
    path = base_path / DISPATCH_GROUPS_PATH
    if not path.is_file():
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {}, [
            Violation(
                hook_type="dispatcher",
                script=str(DISPATCH_GROUPS_PATH),
                category="invalid_dispatch_groups",
                message=f"Cannot read {DISPATCH_GROUPS_PATH}: {exc}",
            )
        ]
    if not isinstance(data, dict):
        return {}, [
            Violation(
                hook_type="dispatcher",
                script=str(DISPATCH_GROUPS_PATH),
                category="invalid_dispatch_groups",
                message=f"{DISPATCH_GROUPS_PATH} must be a JSON object, got {type(data).__name__}",
            )
        ]
    groups = data.get("groups")
    if not isinstance(groups, dict):
        # invoke_dispatch_claude._load_group raises TypeError here and the
        # dispatcher fails closed, so accepting it would let a file that blocks
        # every tool call at runtime pass the contract check.
        found = "missing" if "groups" not in data else type(groups).__name__
        return {}, [
            Violation(
                hook_type="dispatcher",
                script=str(DISPATCH_GROUPS_PATH),
                category="invalid_dispatch_groups",
                message=(
                    f"{DISPATCH_GROUPS_PATH} 'groups' property must be an object, got {found}"
                ),
            )
        ]
    return groups, []


def _expand_dispatch_group(
    entry: HookEntry, groups: dict
) -> tuple[list[HookEntry], list[Violation]]:
    """Add the shims a dispatcher registration actually runs.

    Since group dispatch (#3153) a registration names a group, not a script, so
    validating the command alone checks the dispatcher over and over and never
    checks the hooks. The shims are the code that runs, so they are what the
    contract has to cover.

    The dispatcher entry is kept alongside the shims rather than replaced by
    them. The harness runs it either way, so dropping it on an unresolvable
    group would stop checking that the dispatcher itself exists and documents
    its exit codes, on exactly the registrations most likely to be broken.

    Expansion is keyed on the dispatcher script name, not on the presence of a
    --group flag, so an ordinary hook that takes a --group argument is left
    alone.
    """
    script = extract_script_path(entry.command)
    if script is None or Path(script).name != DISPATCHER_SCRIPT_NAME:
        return [entry], []
    match = _GROUP_FLAG_PATTERN.search(entry.command)
    if not match:
        return [entry], []
    name = match.group(1)

    def _fail(category: str, message: str) -> tuple[list[HookEntry], list[Violation]]:
        return [entry], [
            Violation(
                hook_type=entry.hook_type,
                script=entry.script_path,
                category=category,
                message=f"Hook dispatches to group '{name}', which {message}",
            )
        ]

    # The categories below mirror the outcomes the Claude runtime already
    # distinguishes across invoke_dispatch_claude._load_group and
    # claude_hook_dispatch.validate_group: KeyError for an absent group,
    # TypeError for a non-object group, TypeError for a non-string or empty
    # event, TypeError for a non-list 'shims', and no error at all for an empty
    # list. Reporting a wrong type as "does not define" sends the reader to add
    # a group that is already there.
    #
    # Not mirrored: the event-to-mode pairing. This module never reads 'mode',
    # and tests/hooks/test_dispatch_groups_parity.py already asserts the pairing
    # over the real manifest, so repeating it here would be two owners for one
    # rule.
    if name not in groups:
        return _fail("unknown_dispatch_group", f"{DISPATCH_GROUPS_PATH} does not define")
    spec = groups[name]
    if not isinstance(spec, dict):
        return _fail(
            "malformed_dispatch_group",
            f"{DISPATCH_GROUPS_PATH} defines as {type(spec).__name__}, not an object; "
            "the dispatcher fails closed on it",
        )
    event = spec.get("event")
    if not isinstance(event, str) or not event:
        # claude_hook_dispatch.validate_group raises TypeError on a missing,
        # null, non-string, or empty event and the dispatcher exits 2.
        # Reporting it is the point: coercing to the registration's own hook
        # type instead would let a manifest the runtime refuses to load pass
        # this gate silently. It also has to be caught here, because a
        # non-string escaping into HookEntry.hook_type crashes
        # validate_hook_type_known (unhashable set element) and
        # validate_duplicate_entries (unhashable dict key).
        if event is None:
            found = "null" if "event" in spec else "missing"
        elif isinstance(event, str):
            found = "an empty string"
        else:
            found = type(event).__name__
        return _fail(
            "malformed_dispatch_group",
            f"declares 'event' as {found}, not a non-empty string; "
            "the dispatcher fails closed on it",
        )
    matcher = spec.get("matcher", entry.matcher)
    if matcher is not None and not isinstance(matcher, str):
        # None is a legitimate manifest value (a group that matches every tool
        # for its event), so the check is str-or-None rather than str.
        return _fail(
            "malformed_dispatch_group",
            f"declares 'matcher' as {type(matcher).__name__}, not a string or null",
        )
    shims = spec.get("shims")
    if not isinstance(shims, list):
        return _fail(
            "malformed_dispatch_group",
            f"declares 'shims' as {type(shims).__name__}, not a list; "
            "the dispatcher fails closed on it",
        )
    if not shims:
        return _fail(
            "empty_dispatch_group",
            "lists no shims, so the registration runs nothing",
        )
    expanded: list[HookEntry] = [entry]
    violations: list[Violation] = []
    for shim in shims:
        if not isinstance(shim, dict) or not isinstance(shim.get("file"), str):
            violations.append(
                Violation(
                    hook_type=entry.hook_type,
                    script=entry.script_path,
                    category="malformed_shim",
                    message=f"Group '{name}' has a shim entry with no file path",
                )
            )
            continue
        expanded.append(
            HookEntry(
                hook_type=event,
                script_path=str(Path(".claude") / "hooks" / shim["file"]),
                command=entry.command,
                matcher=matcher,
                timeout=shim.get("timeout", entry.timeout),
                status_message=shim.get("statusMessage"),
            )
        )
    return expanded, violations


def parse_settings(
    settings_path: Path, root: str = CLAUDE_ROOT
) -> tuple[dict, list[HookEntry], list[Violation]]:
    """Parse settings.json and extract all hook entries.

    Returns (raw_settings, hook_entries, parse_violations).
    """
    content = settings_path.read_text(encoding="utf-8")
    settings = json.loads(content)

    hooks_config = settings.get("hooks", {})
    entries: list[HookEntry] = []
    parse_violations: list[Violation] = []

    for hook_type, hook_groups in hooks_config.items():
        if not isinstance(hook_groups, list):
            continue

        for group in hook_groups:
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher")
            group_hooks = group.get("hooks", [])
            if not isinstance(group_hooks, list):
                continue

            for hook in group_hooks:
                if not isinstance(hook, dict):
                    continue
                if hook.get("type") != "command":
                    continue

                command = hook.get("command", "")
                script_path = extract_script_path(command, root)
                if not script_path:
                    if _PWSH_PATTERN.search(command):
                        parse_violations.append(
                            Violation(
                                hook_type=hook_type,
                                script=command,
                                category="unsupported_command",
                                message=(
                                    f"PowerShell hook not validated "
                                    f"(only Python hooks are supported): {command}"
                                ),
                            )
                        )
                    continue

                entries.append(
                    HookEntry(
                        hook_type=hook_type,
                        script_path=script_path,
                        command=command,
                        matcher=matcher,
                        timeout=hook.get("timeout"),
                        status_message=hook.get("statusMessage"),
                    )
                )

    return settings, entries, parse_violations


def parse_copilot_hooks(hooks_path: Path) -> tuple[list[HookEntry], list[Violation]]:
    """Read the Copilot CLI registration file into the shared entry shape.

    The file differs from the Claude one in three ways that all have to be
    absorbed here, so that everything downstream stays surface-agnostic: the
    entries sit directly under the event name, the command lives under "bash",
    and the timeout is spelled "timeoutSec". Once an entry carries a
    repo-relative script path, no later validator needs to know where it came
    from.

    The PowerShell twin of each registration is deliberately not read. It runs
    the same script through a different launcher, so validating it would report
    every violation twice.
    """
    content = hooks_path.read_text(encoding="utf-8")
    data = json.loads(content)

    entries: list[HookEntry] = []
    violations: list[Violation] = []
    if not isinstance(data, dict) or "hooks" not in data:
        # Defaulting to an empty mapping here would turn a file with no
        # registrations at all into a clean zero-entry pass, which is the exact
        # #3384 failure mode: the validator reported success over a surface it
        # had never read.
        if not isinstance(data, dict):
            reason = (
                f"top-level value is {type(data).__name__}, not an object"
            )
        else:
            reason = "required 'hooks' key is missing"
        return entries, [
            Violation(
                hook_type="plugin",
                script=str(COPILOT_HOOKS_PATH),
                category="invalid_plugin_hooks",
                message=f"Copilot registration file is invalid: {reason}",
            )
        ]

    hooks_config = data["hooks"]
    if not isinstance(hooks_config, dict):
        return entries, [
            Violation(
                hook_type="plugin",
                script=str(COPILOT_HOOKS_PATH),
                category="invalid_plugin_hooks",
                message=(
                    f"Copilot registrations declare 'hooks' as "
                    f"{type(hooks_config).__name__}, not an object"
                ),
            )
        ]

    for hook_type, registrations in hooks_config.items():
        if not isinstance(registrations, list):
            # Skipping here would zero out coverage for this event while the
            # run still reported success, so a malformed event reads exactly
            # like an event with nothing registered.
            violations.append(
                Violation(
                    hook_type=hook_type,
                    script=str(COPILOT_HOOKS_PATH),
                    category="invalid_plugin_hooks",
                    message=(
                        f"Copilot registrations for '{hook_type}' are "
                        f"{type(registrations).__name__}, not a list"
                    ),
                )
            )
            continue
        for registration in registrations:
            if not isinstance(registration, dict):
                violations.append(
                    Violation(
                        hook_type=hook_type,
                        script=str(COPILOT_HOOKS_PATH),
                        category="invalid_plugin_hooks",
                        message=(
                            f"Copilot registration under '{hook_type}' is "
                            f"{type(registration).__name__}, not an object"
                        ),
                    )
                )
                continue
            if registration.get("type") != "command":
                continue
            command = registration.get("bash", "")
            if not isinstance(command, str):
                continue
            script_path = extract_script_path(command, COPILOT_ROOT)
            if not script_path:
                continue
            matcher = registration.get("matcher")
            if matcher is not None and not isinstance(matcher, str):
                violations.append(
                    Violation(
                        hook_type=hook_type,
                        script=str(COPILOT_HOOKS_PATH),
                        category="invalid_plugin_hooks",
                        message=(
                            f"Copilot event '{hook_type}' has a matcher of type "
                            f"{type(matcher).__name__}, expected string or null"
                        ),
                    )
                )
                continue
            entries.append(
                HookEntry(
                    hook_type=hook_type,
                    script_path=script_path,
                    command=command,
                    matcher=matcher,
                    timeout=registration.get("timeoutSec"),
                )
            )

    return entries, violations


def _expand_copilot_manifest(
    entry: HookEntry, base_path: Path
) -> tuple[list[HookEntry], list[Violation]]:
    """Fan a Copilot dispatcher registration out to the shims it runs.

    Without this the gate checks that the dispatcher exists and stops, which is
    the same blind spot the Claude side had before group expansion: every shim
    the dispatcher actually runs goes unchecked.

    A missing manifest is a violation rather than a quiet skip. The dispatcher
    reads it at startup and fails closed, so its absence breaks every hook for
    that event.
    """
    script = Path(entry.script_path)
    if script.name != COPILOT_DISPATCHER_NAME:
        return [entry], []

    manifest_path = script.parent / COPILOT_MANIFEST_NAME

    def _fail(category: str, message: str) -> tuple[list[HookEntry], list[Violation]]:
        return [entry], [
            Violation(
                hook_type=entry.hook_type,
                script=str(manifest_path),
                category=category,
                message=message,
            )
        ]

    resolved = _resolve_script_path(base_path, str(manifest_path))
    if resolved is None or not resolved.is_file():
        return _fail(
            "missing_dispatch_manifest",
            f"Dispatcher for {entry.hook_type} has no manifest; it fails closed without one",
        )
    try:
        manifest = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _fail("invalid_dispatch_manifest", f"Dispatch manifest cannot be read: {exc}")
    if not isinstance(manifest, dict):
        return _fail(
            "invalid_dispatch_manifest",
            f"Dispatch manifest is a {type(manifest).__name__}, not an object",
        )

    shims = manifest.get("shims")
    if not isinstance(shims, list) or not shims:
        return _fail(
            "invalid_dispatch_manifest",
            "Dispatch manifest lists no shims, so the registration runs nothing",
        )

    timeouts = manifest.get("timeouts")
    if not isinstance(timeouts, dict):
        timeouts = {}

    expanded: list[HookEntry] = [entry]
    violations: list[Violation] = []
    for shim in shims:
        if not isinstance(shim, str):
            violations.append(
                Violation(
                    hook_type=entry.hook_type,
                    script=str(manifest_path),
                    category="malformed_shim",
                    message=f"Dispatch manifest has a shim entry that is not a path: {shim!r}",
                )
            )
            continue
        expanded.append(
            HookEntry(
                hook_type=entry.hook_type,
                script_path=str(script.parent / shim),
                command=entry.command,
                matcher=entry.matcher,
                timeout=timeouts.get(shim, entry.timeout),
            )
        )
    return expanded, violations


def validate_script_exists(
    entry: HookEntry,
    base_path: Path,
) -> Violation | None:
    """Check that the referenced script file exists within project root."""
    full_path = _resolve_script_path(base_path, entry.script_path)
    if full_path is None:
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="invalid_script_path",
            message=f"Script path escapes project root: {entry.script_path}",
        )
    if not full_path.is_file():
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="missing_script",
            message=f"Script not found: {entry.script_path}",
        )
    return None


def validate_hook_type_known(entry: HookEntry) -> Violation | None:
    """Check that the hook type is a known Claude Code hook type."""
    if entry.hook_type not in ALL_HOOK_TYPES:
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="unknown_hook_type",
            message=f"Unknown hook type: {entry.hook_type}",
        )
    return None


def validate_timeout(entry: HookEntry) -> Violation | None:
    """Check that timeout values are within reasonable bounds."""
    if entry.timeout is None:
        return None
    if not isinstance(entry.timeout, (int, float)):
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="invalid_timeout",
            message=f"Timeout must be a number, got: {type(entry.timeout).__name__}",
        )
    if entry.timeout < MIN_TIMEOUT or entry.timeout > MAX_TIMEOUT:
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="timeout_range",
            message=(f"Timeout {entry.timeout}s outside range [{MIN_TIMEOUT}, {MAX_TIMEOUT}]"),
        )
    return None


_EXIT_DOC_PATTERN = re.compile(r"\bexit[\s_-]?code|\bblock\b", re.IGNORECASE)


def validate_exit_code_docs(
    entry: HookEntry,
    base_path: Path,
) -> Violation | None:
    """Check that script docstring documents exit codes matching hook semantics.

    Blocking hooks should document exit code semantics (0=allow, 2=block).
    """
    full_path = _resolve_script_path(base_path, entry.script_path)
    if full_path is None or not full_path.is_file():
        return None  # Already caught by validate_script_exists

    try:
        content = full_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # The script exists (is_file passed above) but cannot be read. Returning
        # None here would treat an unreadable blocking hook as "docs present",
        # so flag it instead of silently passing the contract check.
        return Violation(
            hook_type=entry.hook_type,
            script=entry.script_path,
            category="unreadable_script",
            message=f"Hook script exists but cannot be read: {exc}",
        )

    # Only check the docstring area (first 30 lines)
    header = "\n".join(content.splitlines()[:30])

    if entry.hook_type in BLOCKING_HOOK_TYPES:
        if not _EXIT_DOC_PATTERN.search(header):
            return Violation(
                hook_type=entry.hook_type,
                script=entry.script_path,
                category="missing_exit_docs",
                message=(
                    f"Blocking hook ({entry.hook_type}) should document "
                    f"exit code semantics (0=allow, 2=block) in docstring"
                ),
            )

    return None


def _duplicate_key(entry: HookEntry) -> tuple[str, str, str | None, str | None]:
    """Identity used to detect a duplicate registration.

    A dispatcher entry (``invoke_dispatch_claude.py``) fans out to whichever
    group its ``--group`` flag names, so two dispatcher registrations that
    share a hook type and matcher are distinct hooks, not duplicates, when
    their groups differ. Include the group in the key for exactly that
    script; every other script keeps the prior three-part identity.
    """
    group: str | None = None
    if Path(entry.script_path).name == DISPATCHER_SCRIPT_NAME:
        match = _GROUP_FLAG_PATTERN.search(entry.command)
        if match:
            group = match.group(1)
    return (entry.hook_type, entry.script_path, entry.matcher, group)


def validate_duplicate_entries(entries: list[HookEntry]) -> list[Violation]:
    """Check for duplicate hook entries (same script under same hook type + matcher).

    Two dispatcher registrations naming different groups are not duplicates;
    see ``_duplicate_key``.
    """
    seen: dict[tuple[str, str, str | None, str | None], HookEntry] = {}
    violations: list[Violation] = []

    for entry in entries:
        key = _duplicate_key(entry)
        if key in seen:
            violations.append(
                Violation(
                    hook_type=entry.hook_type,
                    script=entry.script_path,
                    category="duplicate",
                    message=(
                        f"Duplicate hook entry: {entry.script_path} "
                        f"under {entry.hook_type}"
                        f"{f' (matcher: {entry.matcher})' if entry.matcher else ''}"
                    ),
                )
            )
        else:
            seen[key] = entry

    return violations


def _read_copilot_surface(base_path: Path) -> tuple[list[HookEntry], list[Violation]]:
    """Read and expand the Copilot CLI registrations.

    Absent is legitimate: a checkout that publishes only the Claude plugin has
    no such file. Present but unreadable is not, because the harness would fail
    to register anything.
    """
    hooks_path = base_path / COPILOT_HOOKS_PATH
    if not hooks_path.is_file():
        return [], []
    try:
        entries, violations = parse_copilot_hooks(hooks_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError) as exc:
        return [], [
            Violation(
                hook_type="plugin",
                script=str(COPILOT_HOOKS_PATH),
                category="invalid_plugin_hooks",
                message=f"Copilot hook registrations cannot be read: {exc}",
            )
        ]

    expanded: list[HookEntry] = []
    for entry in entries:
        shims, shim_violations = _expand_copilot_manifest(entry, base_path)
        expanded.extend(shims)
        violations.extend(shim_violations)
    return expanded, violations


def validate_all(
    settings_path: Path,
    base_path: Path,
) -> ContractReport:
    """Run all hook contract validations.

    Args:
        settings_path: Path to settings.json
        base_path: Project root for resolving script paths

    Returns:
        ContractReport with all entries and violations found.
    """
    _, entries, parse_violations = parse_settings(settings_path)

    # The plugin registers its own hooks, so a settings.json-only read leaves
    # the whole published surface unvalidated.
    plugin_path = base_path / PLUGIN_HOOKS_PATH
    if plugin_path.is_file():
        # Attribute a failure here to the plugin file. Letting it escape would
        # surface as a generic read failure in main(), which names the
        # settings path and loses the category.
        try:
            _, plugin_entries, plugin_violations = parse_settings(plugin_path)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            AttributeError,
            TypeError,
        ) as exc:
            parse_violations.append(
                Violation(
                    hook_type="plugin",
                    script=str(PLUGIN_HOOKS_PATH),
                    category="invalid_plugin_hooks",
                    message=f"Plugin hook registrations cannot be read: {exc}",
                )
            )
        else:
            entries.extend(plugin_entries)
            parse_violations.extend(plugin_violations)

    groups, group_violations = _load_dispatch_groups(base_path)
    parse_violations.extend(group_violations)
    # An unusable manifest yields no groups, so expanding against it would
    # report every dispatcher registration as naming an unknown group and bury
    # the one violation that explains all of them. Expansion is skipped, not
    # the entries: the dispatcher registrations stay in the list and are still
    # checked for script existence and exit-code docs. The shims cannot be
    # checked because the file that names them is the thing that failed.
    manifest_unusable = any(
        violation.category == "invalid_dispatch_groups" for violation in group_violations
    )
    if not manifest_unusable:
        expanded: list[HookEntry] = []
        for entry in entries:
            shims, violations = _expand_dispatch_group(entry, groups)
            expanded.extend(shims)
            parse_violations.extend(violations)
        entries = expanded

    copilot_entries, copilot_violations = _read_copilot_surface(base_path)
    entries.extend(copilot_entries)
    parse_violations.extend(copilot_violations)

    report = ContractReport(entries=entries)
    report.violations.extend(parse_violations)

    # Per-entry validations
    for entry in entries:
        for validator in (
            validate_hook_type_known,
            validate_timeout,
        ):
            violation = validator(entry)
            if violation:
                report.violations.append(violation)

        for validator_with_path in (
            validate_script_exists,
            validate_exit_code_docs,
        ):
            violation = validator_with_path(entry, base_path)
            if violation:
                report.violations.append(violation)

    # Cross-entry validations
    report.violations.extend(validate_duplicate_entries(entries))

    return report


def format_console(report: ContractReport) -> str:
    """Format report for console output."""
    lines: list[str] = []

    if report.is_valid:
        lines.append(f"{_COLOR_GREEN}All hook contracts valid{_COLOR_RESET}")
        lines.append(f"{_COLOR_CYAN}   Validated {len(report.entries)} hook entries{_COLOR_RESET}")
        return "\n".join(lines)

    lines.append(f"{_COLOR_RED}Hook contract violations found{_COLOR_RESET}")
    lines.append("")
    lines.append(f"{_COLOR_YELLOW}Found {len(report.violations)} violation(s):{_COLOR_RESET}")
    lines.append("")

    for v in report.violations:
        lines.append(f"  {_COLOR_RED}[{v.category}] {v.hook_type}: {v.script}{_COLOR_RESET}")
        lines.append(f"    {v.message}")

    return "\n".join(lines)


def format_json(report: ContractReport) -> str:
    """Format report as JSON."""
    data = {
        "status": "pass" if report.is_valid else "fail",
        "entriesValidated": len(report.entries),
        "violationCount": len(report.violations),
        "violations": [
            {
                "hookType": v.hook_type,
                "script": v.script,
                "category": v.category,
                "message": v.message,
            }
            for v in report.violations
        ],
    }
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_FORMATTERS = {
    "console": format_console,
    "json": format_json,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate Claude Code hook contracts in settings.json.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("SCAN_PATH", "."),
        help="Project root path (env: SCAN_PATH, default: current directory)",
    )
    parser.add_argument(
        "--settings",
        default=None,
        help="Path to settings.json (default: <path>/.claude/settings.json)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=False,
        help="CI mode: exit non-zero on violations",
    )
    parser.add_argument(
        "--format",
        choices=("console", "json"),
        default=os.environ.get("OUTPUT_FORMAT", "console"),
        dest="output_format",
        help="Output format (env: OUTPUT_FORMAT, default: console)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    base_path = Path(args.path).resolve()
    if not base_path.is_dir():
        print(f"Error: Path not found: {args.path}", file=sys.stderr)
        return 2

    settings_path = (
        Path(args.settings) if args.settings else base_path / ".claude" / "settings.json"
    )
    if not settings_path.is_file():
        print(
            f"Error: Settings file not found: {settings_path}",
            file=sys.stderr,
        )
        return 2

    try:
        report = validate_all(settings_path, base_path)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        AttributeError,
    ) as exc:
        # OSError and UnicodeDecodeError reach here from the settings read
        # itself: an unreadable file or one holding invalid UTF-8. Without
        # them the script exits on a traceback instead of the ADR-035
        # configuration code, and --settings can name a file that is not
        # settings.json, so the message reports the path it actually read.
        print(
            f"Error: Cannot read hook registrations from {settings_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    formatter = _FORMATTERS[args.output_format]
    print(formatter(report))

    if not report.is_valid and args.ci:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
