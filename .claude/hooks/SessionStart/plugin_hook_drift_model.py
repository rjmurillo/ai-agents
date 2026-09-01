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

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

# Bounds on the on-disk scan. Session start is not the place for an unbounded
# walk: a marketplace clone can carry a full node_modules tree. Depth 5 reaches
# `plugins/marketplaces/<marketplace>/src/copilot-cli`, the deepest plugin root
# this repository publishes.
MAX_SCAN_DEPTH = 5
MAX_SCAN_DIRS = 4000
PRUNED_DIR_NAMES = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv"})


PLUGIN_MANIFEST_REL = Path(".claude-plugin") / "plugin.json"
HOOKS_MANIFEST_REL = Path("hooks") / "hooks.json"
DISPATCH_MANIFEST_REL = Path("hooks") / "dispatch_groups.json"

# Output caps. Everything below is rendered into session context, and an
# installed manifest is attacker-influenceable, so a label is allowlisted
# characters only and bounded in length. `?` marks each dropped character so a
# reader can see that scrubbing happened rather than reading a clean-looking
# name that is not what the manifest said.
MAX_LABEL_CHARS = 80
MAX_PATH_CHARS = 200

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

_UNSAFE_LABEL_CHARS = re.compile(r"[^A-Za-z0-9._/@:+= -]")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SCRIPT_IN_COMMAND = re.compile(r"[A-Za-z0-9._/\\-]+\.(?:py|sh|ps1)")
_DISPATCH_ENTRYPOINT = "invoke_dispatch_claude.py"
_GROUP_ARGUMENT = re.compile(r"--group[=\s]+([A-Za-z0-9._-]{1,64})")

CLAUDE_SCHEMA = "claude"
COPILOT_SCHEMA = "copilot"


def sanitize_label(text: object, limit: int = MAX_LABEL_CHARS) -> str:
    """Reduce untrusted manifest text to inert, length-capped label characters."""
    collapsed = " ".join(str(text).split())
    scrubbed = _UNSAFE_LABEL_CHARS.sub("?", collapsed)
    if len(scrubbed) <= limit:
        return scrubbed
    return scrubbed[:limit] + "[truncated]"


def command_unit(command: str) -> str:
    """Name what a registration runs without echoing the command itself.

    Prefers the basename of the last script path in the command, which is the
    part a reader needs in order to find the hook. A bare identifier is kept as
    written (it is already within the safe alphabet). Anything else, including
    shell text a hostile manifest could have chosen freely, collapses to a
    digest: still stable enough to diff two manifests, but carrying none of the
    attacker's words into the model's context.
    """
    text = " ".join(command.split())
    scripts = _SCRIPT_IN_COMMAND.findall(text)
    if scripts:
        return sanitize_label(PurePosixPath(scripts[-1].replace("\\", "/")).name)
    if _SAFE_TOKEN.match(text):
        return text
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]
    return f"unrecognized command (sha256:{digest})"


def read_plugin_name(root: Path) -> str | None:
    """Read a plugin root's declared ``name``; None when absent or malformed."""
    try:
        data = json.loads((root / PLUGIN_MANIFEST_REL).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name if isinstance(name, str) and name else None


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


def _group_units(event: str, group: object, groups: object) -> set[tuple[str, str, str]] | None:
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
    matcher = str(group.get("matcher") or "")
    found: set[tuple[str, str, str]] = set()
    for entry in commands:
        if not isinstance(entry, dict):
            return None
        units = _expand_command(event, matcher, str(entry.get("command", "")), groups)
        if units is None:
            return None
        found |= units
    return found


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
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            return None
        for group in entries:
            units = _group_units(str(event), group, groups)
            if units is None:
                return None
            found |= units
            if len(found) > MAX_REGISTRATIONS:
                return None
    return found


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

    The PowerShell twin is deliberately not read; it launches the same script
    and would double every unit.
    """
    if not isinstance(hooks, dict):
        return None
    found: set[tuple[str, str, str]] = set()
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            command = entry.get("bash")
            if command is None:
                command = entry.get("powershell")
            if not isinstance(command, str):
                return None
            matcher = entry.get("matcher") or ""
            found.add((str(event), str(matcher), command_unit(command)))
            if len(found) > MAX_REGISTRATIONS:
                return None
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
        return None, f"no hook manifest at {path}"
    except OSError as exc:
        return None, f"unreadable hook manifest {path}: {type(exc).__name__}: {exc}"
    if len(raw) > MAX_MANIFEST_BYTES:
        return None, (
            f"hook manifest {path} exceeds the {MAX_MANIFEST_BYTES}-byte ceiling; not compared"
        )
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        return None, f"unreadable hook manifest {path}: {type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, f"hook manifest {path} is not a JSON object"
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
            f"hook manifest {manifest} has a malformed 'hooks' mapping, "
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


@dataclass(slots=True)
class ScanBudget:
    """Directory-visit budget for one bounded walk, and whether it ran out.

    Exhausting the budget has to reach the reader. A walk that stopped early
    may never have visited the stale install this hook exists to name, and
    reporting that as "matches" or "no installed copy found" is precisely the
    false-clean verdict the check is meant to prevent. Truncation is therefore
    an outcome the caller reads, not an early ``return`` the caller cannot see.
    """

    # Read at construction, not at class creation, so the bound stays one
    # number that tests and callers can lower.
    remaining: int = field(default_factory=lambda: MAX_SCAN_DIRS)
    truncated: bool = False

    def spend(self) -> bool:
        """Consume one directory visit; False once the budget is exhausted."""
        if self.remaining <= 0:
            self.truncated = True
            return False
        self.remaining -= 1
        return True


@dataclass(frozen=True, slots=True)
class InstallReport:
    """Comparison of one installed copy against its source manifest."""

    surface: str
    install_path: Path
    only_in_install: tuple[str, ...]
    only_in_source: tuple[str, ...]
    error: str | None

    @property
    def has_drift(self) -> bool:
        return bool(self.only_in_install or self.only_in_source or self.error)


@dataclass(frozen=True, slots=True)
class ScanOutcome:
    """Everything one pass over the install trees established, and did not.

    ``incomplete`` names each search root whose walk hit ``MAX_SCAN_DIRS``.
    While it is non-empty, no verdict in ``reports`` is a statement about the
    whole tree.
    """

    reports: list[InstallReport] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)
