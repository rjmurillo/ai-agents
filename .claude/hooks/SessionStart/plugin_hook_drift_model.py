#!/usr/bin/env python3
# taste-lint: ignore naming -- the `invoke_` prefix marks a registered hook
# entry point so a reader can tell which files a harness launches. This file is
# a library imported by `invoke_plugin_hook_drift_check.py` and is registered
# nowhere, so the prefix would assert the opposite of what is true and place it
# in the namespace hook-anchoring checks scan. It sits beside its only caller
# rather than in `.claude/lib/` because a lib import failing at module scope
# would break the hook's fail-open contract, while a sibling file always ships
# with the hook that imports it.
"""What a plugin root's manifests say it enforces, and what may be said about it.

Split out of `invoke_plugin_hook_drift_check.py`: the hook owns the scan, the
comparison, and the message; this module owns reading a plugin root and turning
its manifests into comparable units. Both halves were one 700-line file, which
put the security-relevant part (nothing from an untrusted manifest is echoed)
in the same breath as directory walking.

Two schemas and one indirection live here:

- Claude nests registrations under `hooks` inside each matcher group, and the
  command usually names `invoke_dispatch_claude.py --group <id>` rather than a
  hook. Real membership is in `dispatch_groups.json`, so registrations expand
  to their shims before anything is compared.
- Copilot CLI puts registrations directly under the event with the command in
  `bash`, per `scripts/validation/hook_contracts.py::parse_copilot_hooks`.

Unknown is never "empty". Every function here returns None when it cannot
resolve a shape, because an empty set downstream reads as the deliberate
"registers nothing" state, and those are opposite verdicts.

Refs: issue #5085.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from plugin_hook_drift_safety import (
    command_unit,
    path_token,
    sanitize_label,
)

PLUGIN_MANIFEST_REL = Path(".claude-plugin") / "plugin.json"
HOOKS_MANIFEST_REL = Path("hooks") / "hooks.json"
DISPATCH_MANIFEST_REL = Path("hooks") / "dispatch_groups.json"


# Resource ceilings. A same-named plugin root under the scanned trees is
# attacker-influenceable, and this runs at session start, so an unbounded
# manifest is a denial-of-service surface (CWE-400): reading it can exhaust
# memory, and rendering it can flood the session context until startup times
# out. Both the bytes read and the number of registrations parsed are capped,
# and a manifest over either ceiling is reported as not compared rather than
# parsed partially, because a partial parse would manufacture drift in both
# directions against a source that is fine.
MAX_MANIFEST_BYTES = 512 * 1024
MAX_REGISTRATIONS = 500

_DISPATCH_ENTRYPOINT = "invoke_dispatch_claude.py"
_GROUP_ARGUMENT = re.compile(r"--group[=\s]+([A-Za-z0-9._-]{1,64})")

CLAUDE_SCHEMA = "claude"
COPILOT_SCHEMA = "copilot"


def read_plugin_name(root: Path) -> str | None:
    """Read a plugin root's declared ``name``; None when absent or malformed.

    Goes through the same bounded reader as every other manifest. This one is
    read for every directory the scan visits, so an unbounded read here would
    be the cheapest denial-of-service surface in the hook: a single oversized
    `plugin.json` anywhere under the scanned trees would be loaded in full.
    """
    name, _ = read_plugin_identity(root)
    return name


def read_plugin_identity(root: Path) -> tuple[str | None, bool]:
    """``(declared name, unreadable)`` for one candidate plugin root.

    ``unreadable`` separates "there is no plugin manifest here, so this is not
    a plugin root" from "there is one and this hook could not read it". The
    second is not a clean skip: an oversized or corrupt `plugin.json` on the
    real install would otherwise drop that install from the scan silently, and
    the message would go on to claim no installed copy exists.
    """
    data, error = _read_json_object(root / PLUGIN_MANIFEST_REL)
    if data is None:
        missing = bool(error and error.startswith("no hook manifest"))
        return None, not missing
    name = data.get("name")
    return (name if isinstance(name, str) and name else None), False


def _matcher_text(entry: dict[str, object]) -> str | None:
    """Normalize a registration's ``matcher``, or None when its type is wrong.

    Mirrors `scripts/validation/hook_contracts.py::parse_copilot_hooks`, which
    rejects the same shapes rather than coercing them:

        matcher = registration.get("matcher")
        if matcher is not None and not isinstance(matcher, str):
            ... "has a matcher of type ..., expected string or null"

    An earlier `entry.get("matcher") or ""` collapsed every falsy value to the
    same normalized matcher as an absent one, so an install carrying a garbage
    matcher compared equal to a source that has no matcher at all.
    """
    matcher = entry.get("matcher")
    if matcher is None:
        return ""
    if not isinstance(matcher, str):
        return None
    return matcher


def _is_named(value: object) -> bool:
    """True for a non-empty string, the shape every named manifest field takes."""
    return isinstance(value, str) and bool(value)


def _shim_basenames(shims: object) -> list[str] | None:
    """Sanitized shim basenames, or None for any shape the dispatcher rejects.

    An empty list is None, not an empty result: `validate_group` raises
    "group shims must not be empty", so a group with no shims is a malformed
    manifest rather than a group that enforces nothing.
    """
    if not isinstance(shims, list) or not shims:
        return None
    names: list[str] = []
    for shim in shims:
        if not isinstance(shim, dict):
            return None
        name = shim.get("file")
        if not _is_named(name):
            return None
        names.append(sanitize_label(PurePosixPath(str(name).replace("\\", "/")).name))
    return names


def dispatch_membership(groups: object, group_id: str) -> tuple[str, ...] | None:
    """What a dispatch group enforces, or None when it cannot be resolved.

    Each entry is ``"<event>/<mode>/<shim basename>"``. Event and mode belong in
    the comparison because the dispatcher acts on them: a group that moved from
    `PreToolUse`/`gate` to `SessionStart`/`observe` no longer enforces the same
    policy even when every shim name is unchanged, and comparing basenames
    alone would call those two installs identical.

    Mirrors the contract `.claude/lib/claude_hook_dispatch.py::validate_group`
    enforces at lines 132 to 150, which reads in part:

        if not isinstance(event, str) or not event:
            raise TypeError("group event must be a non-empty string")
        ...
        if not shims:
            raise ValueError("group shims must not be empty")

    so an empty ``shims`` list is rejected here too rather than accepted as a
    group that enforces nothing.

    Stricter/looser/different than canonical: this does not re-check mode
    against `_MODE_BY_EVENT`, nor the shim path-traversal rules. Those are the
    dispatcher's job at run time, and duplicating the table here would make
    this hook fail whenever that table changed. This only needs the fields to
    be present and comparable.

    None is deliberately not "the group is empty". An install whose manifest
    this hook cannot resolve enforces an unknown set, and the caller must say
    unknown rather than compare against nothing.
    """
    if not isinstance(groups, dict):
        return None
    group = groups.get(group_id)
    if not isinstance(group, dict):
        return None
    event = group.get("event")
    mode = group.get("mode")
    if not _is_named(event) or not _is_named(mode):
        return None
    names = _shim_basenames(group.get("shims"))
    if names is None:
        return None
    prefix = f"{sanitize_label(event, 40)}/{sanitize_label(mode, 40)}"
    return tuple(sorted(f"{prefix}/{name}" for name in names))


def _expand_command(
    event: str, matcher: str, command: str, groups: object
) -> set[tuple[str, str, str]] | None:
    """Units one Claude registration enforces, expanding a dispatch group."""
    if _DISPATCH_ENTRYPOINT not in command:
        return {(event, matcher, command_unit(command))}
    found = _GROUP_ARGUMENT.search(command)
    if found is None:
        return None
    group_id = found.group(1)
    members = dispatch_membership(groups, group_id)
    if members is None:
        return None
    return {
        (event, matcher, f"{sanitize_label(group_id)}: {sanitize_label(member)}")
        for member in members
    }


def _entry_command(entry: dict[str, object]) -> str | None:
    """The command a Claude registration runs, or None when it is malformed.

    Mirrors `build/scripts/validate_plugin_manifests.py` lines 137 to 144,
    which require both fields of every hook entry:

        if hook.get("type") != "command":
            errors.append(... "`.type`: must be 'command'")
        if not isinstance(hook.get("command"), str):
            errors.append(... "`.command`: required string")

    The earlier `str(entry.get("command", ""))` coerced a missing or non-string
    command into text, so `{"type": "command"}` and `{"command": 7}` both
    produced a plausible-looking unit instead of reporting as malformed.
    """
    if entry.get("type") != "command":
        return None
    command = entry.get("command")
    if not isinstance(command, str):
        return None
    return command


def _group_units(
    event: str, group: object, groups: object
) -> tuple[set[tuple[str, str, str]], int] | None:
    """Units one Claude matcher group enforces, or None if its shape is wrong.

    A non-object group, a group whose "hooks" is missing or not a list, and a
    non-object entry inside that list are all malformed shapes, not "this group
    registers nothing". Skipping any of them would let a broken manifest read
    as the deliberate empty state.
    """
    if not isinstance(group, dict):
        return None
    commands = group.get("hooks")
    if not isinstance(commands, list):
        return None
    matcher = _matcher_text(group)
    if matcher is None:
        return None
    found: set[tuple[str, str, str]] = set()
    parsed = 0
    for entry in commands:
        if not isinstance(entry, dict):
            return None
        command = _entry_command(entry)
        if command is None:
            return None
        units = _expand_command(event, matcher, command, groups)
        if units is None:
            return None
        parsed += 1
        found |= units
    return found, parsed


def registrations(hooks: object, groups: object = None) -> set[tuple[str, str, str]] | None:
    """Flatten a Claude ``hooks`` mapping to ``(event, matcher, unit)`` triples.

    ``groups`` is the parsed ``dispatch_groups.json`` mapping for the same
    plugin root. Registrations that route through the dispatcher expand to the
    shims they actually run; without a resolvable group the answer is None,
    because comparing two dispatcher entry points would call any pair of
    installs identical no matter which hooks they enforce (issue #5085).

    Returns None whenever the mapping is not a shape Claude Code loads, so a
    malformed manifest reports as unreadable rather than as "registers
    nothing", which are opposite verdicts (the same split
    ``scripts/ci/test_installed_plugin_hooks.py`` draws for this manifest).
    """
    if not isinstance(hooks, dict):
        return None
    found: set[tuple[str, str, str]] = set()
    parsed = 0
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            return None
        for group in entries:
            resolved = _group_units(str(event), group, groups)
            if resolved is None:
                return None
            units, count = resolved
            found |= units
            # Count entries parsed, not unique units. Checking the set size let
            # 501 identical registrations collapse to one and slip past the
            # ceiling entirely, which is itself a shape worth reporting: a host
            # told to run the same hook hundreds of times.
            parsed += count
            if parsed > MAX_REGISTRATIONS:
                return None
    return found


# Sentinel for a registration that is legitimately not a command hook, which
# is different from one this parser could not understand.
_SKIP_ENTRY: tuple[str, str] = ("", "")


def _copilot_entry(entry: dict[str, object]) -> tuple[str, str] | None:
    """``(command, matcher)`` for one Copilot registration.

    Returns ``_SKIP_ENTRY`` for a registration of another kind: the canonical
    parser skips those outright (`if registration.get("type") != "command":
    continue`), and reading their `bash` key would report a non-hook as an
    enforced hook. Returns None for a command registration this parser cannot
    understand, which makes the whole manifest unknown rather than short.
    """
    if entry.get("type") != "command":
        return _SKIP_ENTRY
    command = entry.get("bash")
    if command is None:
        command = entry.get("powershell")
    if not isinstance(command, str):
        return None
    matcher = _matcher_text(entry)
    if matcher is None:
        return None
    return command, matcher


def copilot_registrations(hooks: object) -> set[tuple[str, str, str]] | None:
    """Flatten a Copilot CLI ``hooks`` mapping to ``(event, matcher, unit)``.

    Copilot's schema is flatter than Claude's: registrations sit directly under
    the event name and the command lives under ``bash``, per
    `scripts/validation/hook_contracts.py::parse_copilot_hooks`, which states
    "the entries sit directly under the event name, the command lives under
    'bash', and the timeout is spelled 'timeoutSec'". Reading a Copilot
    manifest with Claude's nested parser finds no ``hooks`` key inside any
    entry and yields the empty set, so every stale Copilot install compared
    clean.

    Stricter/looser/different than canonical: `parse_copilot_hooks` reads only
    `bash` and ignores the PowerShell twin, because validating both would
    report every violation twice. This reads `bash` and falls back to
    `powershell` when `bash` is absent, on purpose: the canonical parser is
    checking the repository's own generated manifest, where `bash` is always
    present, while this compares an arbitrary installed copy that may ship
    only the PowerShell launcher. Falling back finds a stale hook that
    ignoring PowerShell would miss. The two are never read together, so no
    unit is doubled.
    """
    if not isinstance(hooks, dict):
        return None
    found: set[tuple[str, str, str]] = set()
    parsed = 0
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            resolved = _copilot_entry(entry)
            if resolved is _SKIP_ENTRY:
                continue
            if resolved is None:
                return None
            command, matcher = resolved
            parsed += 1
            if parsed > MAX_REGISTRATIONS:
                return None
            found.add((str(event), matcher, command_unit(command)))
    return found


def _read_json_object(path: Path) -> tuple[dict[str, object] | None, str | None]:
    """Parse one bounded JSON object file into ``(data, error)``; never both.

    Reads at most ``MAX_MANIFEST_BYTES + 1`` bytes and refuses anything larger,
    so a hostile or merely enormous manifest under the scanned trees cannot
    exhaust memory at session start. The read is capped rather than checked
    with `stat` first, because a size check and a separate full read can
    disagree about a file someone else is writing.
    """
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_MANIFEST_BYTES + 1)
    except FileNotFoundError:
        return None, f"no hook manifest at {path_token(path)}"
    except OSError as exc:
        return None, (f"unreadable hook manifest {path_token(path)}: {type(exc).__name__}")
    if len(raw) > MAX_MANIFEST_BYTES:
        return None, (
            f"hook manifest {path_token(path)} exceeds the "
            f"{MAX_MANIFEST_BYTES}-byte ceiling; not compared"
        )
    # Broad by intent, and scoped to this one call. A deeply nested document
    # raises RecursionError, which is not a ValueError, so it escaped to the
    # hook's outer fail-open handler and aborted the whole pass: one hostile
    # candidate manifest would suppress the drift check for every other
    # install. Any failure to parse one manifest must stay one unreadable
    # manifest, so the parse is not allowed to end the scan.
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        return None, (f"unreadable hook manifest {path_token(path)}: {type(exc).__name__}")
    if not isinstance(data, dict):
        return None, f"hook manifest {path_token(path)} is not a JSON object"
    return data, None


def read_registrations(
    manifest: Path, *, schema: str = CLAUDE_SCHEMA, dispatch: Path | None = None
) -> tuple[set[tuple[str, str, str]] | None, str | None]:
    """Return ``(units, error)`` for one ``hooks/hooks.json``.

    ``dispatch`` points at the sibling ``dispatch_groups.json`` that resolves
    grouped Claude registrations. A missing dispatch manifest is not an error
    on its own; it becomes one only if a registration actually needs it, which
    `registrations` signals by returning None.
    """
    data, error = _read_json_object(manifest)
    if data is None:
        return None, error

    if schema == COPILOT_SCHEMA:
        found = copilot_registrations(data.get("hooks"))
    else:
        groups: object = None
        if dispatch is not None:
            parsed, _ = _read_json_object(dispatch)
            if parsed is not None:
                groups = parsed.get("groups")
        found = registrations(data.get("hooks"), groups)

    if found is None:
        return None, (
            f"hook manifest {path_token(manifest)} has a malformed 'hooks' mapping, "
            f"an unresolvable dispatch group, or more than {MAX_REGISTRATIONS} registrations"
        )
    return found, None


def root_registrations(
    root: Path, schema: str
) -> tuple[set[tuple[str, str, str]] | None, str | None]:
    """Units one plugin root enforces, resolved through its own manifests."""
    return read_registrations(
        root / HOOKS_MANIFEST_REL, schema=schema, dispatch=root / DISPATCH_MANIFEST_REL
    )

