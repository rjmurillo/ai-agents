#!/usr/bin/env python3
"""Report installed plugin copies whose hook registrations diverge from source.

An installed plugin that still registers a retired guard is worse than no
guard: the block looks authoritative and cites a rule that cannot be found in
the repository. Issue #5085 measured four such guards blocking a live session
after all four had been deleted from `main`, and 45 minutes spent diagnosing a
hook that no longer existed. Nothing in a session told the reader that the
thing which blocked them came from a stale install.

This hook states it. At session start it compares the hook registrations in
this checkout's shipped manifests against every installed copy of the same
plugin it can find on disk, and names the registrations present in an install
but not in the source.

Scope and its limit, stated plainly: the check runs only inside a checkout of
the repository that publishes the plugin, because that checkout is the only
available second opinion. A consumer whose install is stale never receives
this hook at all, since the stale install is what would have to ship it. That
gap is the freshness-resolution question in issue #5085 asks 1 and 2, and it
is not closed here.

Hook Type: SessionStart (non-blocking, fail-open)
Exit Codes:
    0 = Success (always, fail-open)

References:
    - Issue #5085 (installed plugin enforces guards deleted from main)
    - ADR-097 (tool-call hooks retired; the shipped state is zero of them)
    - `.claude/rules/ci-scripts.md` MUST 8, which names
      `~/.claude/plugins/cache` and `~/.copilot/installed-plugins` as the
      copies that "can be arbitrarily old"
"""

from __future__ import annotations

import io
import json
import os
import sys
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# --- Standard hook boilerplate: resolve lib directory ---
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:

    def get_project_directory() -> str:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    def skip_if_consumer_repo(hook_name: str) -> bool:
        agents_path = Path(get_project_directory()) / ".agents"
        if not agents_path.is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False


HOOK_NAME = "plugin-hook-drift-check"

# Bounds on the on-disk scan. Session start is not the place for an unbounded
# walk: a marketplace clone can carry a full node_modules tree. Depth 5 reaches
# `plugins/marketplaces/<marketplace>/src/copilot-cli`, the deepest plugin root
# this repository publishes.
MAX_SCAN_DEPTH = 5
MAX_SCAN_DIRS = 4000
PRUNED_DIR_NAMES = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv"})

PLUGIN_MANIFEST_REL = Path(".claude-plugin") / "plugin.json"
HOOKS_MANIFEST_REL = Path("hooks") / "hooks.json"


@dataclass(frozen=True, slots=True)
class PluginSurface:
    """One shipped plugin root and the install locations that mirror it."""

    label: str
    source_rel: Path
    search_roots: tuple[Path, ...]


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


def copilot_home(home: Path) -> Path:
    """Copilot CLI's home directory, honoring the ``COPILOT_HOME`` override.

    Mirrors `scripts/dev/dogfood_copilot_plugin.py::default_target`, which
    resolves the same directory for the same reason and reads verbatim:

        home_env = os.environ.get("COPILOT_HOME", "").strip()
        home = Path(home_env) if home_env else Path.home() / ".copilot"

    An operator who moved Copilot's home and left this hook pointed at the
    account home would be told "no installed copy" about the very install that
    is enforcing a retired guard.

    Stricter/looser/different than canonical: the fallback uses the ``home``
    passed in rather than `Path.home()`, because every path in this module is
    resolved from an injected home so tests can point it at a fixture. The
    override branch and the strip-to-empty fallback rule are identical.
    """
    override = os.environ.get("COPILOT_HOME", "").strip()
    return Path(override) if override else home / ".copilot"


def plugin_surfaces(home: Path) -> tuple[PluginSurface, ...]:
    """The plugin roots this repository publishes, with their install trees."""
    return (
        PluginSurface(
            label="Claude Code",
            source_rel=Path(".claude"),
            search_roots=(home / ".claude" / "plugins",),
        ),
        PluginSurface(
            label="Copilot CLI",
            source_rel=Path("src") / "copilot-cli",
            search_roots=(copilot_home(home) / "installed-plugins",),
        ),
    )


def read_plugin_name(root: Path) -> str | None:
    """Read a plugin root's declared ``name``; None when absent or malformed."""
    try:
        data = json.loads((root / PLUGIN_MANIFEST_REL).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return name if isinstance(name, str) and name else None


def registrations(hooks: object) -> set[tuple[str, str, str]] | None:
    """Flatten a ``hooks`` mapping to ``(event, matcher, command)`` triples.

    Returns None when the mapping is not the shape Claude Code loads, so a
    malformed manifest reports as unreadable rather than as "registers
    nothing", which are opposite verdicts (the same split
    ``scripts/ci/test_installed_plugin_hooks.py`` draws for this manifest).
    """
    if not isinstance(hooks, dict):
        return None
    found: set[tuple[str, str, str]] = set()
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            return None
        for group in groups:
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher") or ""
            entries = group.get("hooks")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict):
                    found.add((str(event), str(matcher), str(entry.get("command", ""))))
    return found


def read_registrations(manifest: Path) -> tuple[set[tuple[str, str, str]] | None, str | None]:
    """Return ``(registrations, error)`` for one ``hooks/hooks.json``."""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"no hook manifest at {manifest}"
    except (OSError, UnicodeError, ValueError) as exc:
        return None, f"unreadable hook manifest {manifest}: {type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, f"hook manifest {manifest} is not a JSON object"
    found = registrations(data.get("hooks"))
    if found is None:
        return None, f"hook manifest {manifest} has a malformed 'hooks' mapping"
    return found, None


def find_installed_roots(
    search_root: Path, plugin_name: str, budget: ScanBudget | None = None
) -> list[Path]:
    """Bounded breadth-first search for installed copies of ``plugin_name``.

    Symlinked directories are never followed and a matched plugin root is not
    descended into: an install tree may vendor another copy of itself, and one
    session-start walk must not turn into an unbounded one.

    Pass ``budget`` to learn whether the returned list is the whole answer. The
    walk stops when the budget runs out and sets ``budget.truncated``, so a
    caller can tell an exhaustive "not installed here" apart from a search that
    never reached the rest of the tree. Callers that omit ``budget`` get a
    fresh one and discard that distinction.
    """
    if budget is None:
        budget = ScanBudget()
    if not search_root.is_dir():
        return []
    found: list[Path] = []
    queue: deque[tuple[Path, int]] = deque([(search_root, 0)])
    while queue:
        if not budget.spend():
            break
        current, depth = queue.popleft()
        if read_plugin_name(current) == plugin_name:
            found.append(current)
            continue
        if depth >= MAX_SCAN_DEPTH:
            continue
        try:
            children = sorted(current.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name in PRUNED_DIR_NAMES or child.is_symlink() or not child.is_dir():
                continue
            queue.append((child, depth + 1))
    return found


def _describe(triples: set[tuple[str, str, str]]) -> tuple[str, ...]:
    """Render registration triples as stable, readable lines."""
    return tuple(
        f"{event} (matcher {matcher!r}): {command}" for event, matcher, command in sorted(triples)
    )


def compare_install(
    surface_label: str, install_path: Path, source: set[tuple[str, str, str]]
) -> InstallReport:
    """Compare one installed copy's registrations against the source set."""
    installed, error = read_registrations(install_path / HOOKS_MANIFEST_REL)
    if installed is None:
        return InstallReport(surface_label, install_path, (), (), error)
    return InstallReport(
        surface=surface_label,
        install_path=install_path,
        only_in_install=_describe(installed - source),
        only_in_source=_describe(source - installed),
        error=None,
    )


def check_installed_plugins(project_dir: Path, home: Path) -> ScanOutcome:
    """Compare every installed copy found on disk against its shipped source.

    ``notes`` carries per-surface problems that are not a specific install's
    fault, such as a source manifest this checkout cannot read. ``incomplete``
    names each search root the walk could not finish, which caps how much any
    of the reports is allowed to claim.
    """
    outcome = ScanOutcome()
    for surface in plugin_surfaces(home):
        source_root = project_dir / surface.source_rel
        plugin_name = read_plugin_name(source_root)
        if plugin_name is None:
            outcome.notes.append(f"{surface.label}: no readable plugin manifest at {source_root}")
            continue
        source, error = read_registrations(source_root / HOOKS_MANIFEST_REL)
        if source is None:
            outcome.notes.append(f"{surface.label}: {error}")
            continue
        for search_root in surface.search_roots:
            budget = ScanBudget()
            for install_path in find_installed_roots(search_root, plugin_name, budget):
                outcome.reports.append(compare_install(surface.label, install_path, source))
            if budget.truncated:
                outcome.incomplete.append(f"{surface.label}: {search_root}")
    return outcome


def _format_report(report: InstallReport) -> str:
    lines = [f"- `{report.install_path}` ({report.surface})"]
    if report.error:
        lines.append(f"  - unreadable: {report.error}")
    for line in report.only_in_install:
        lines.append(f"  - **only in this install**: {line}")
    for line in report.only_in_source:
        lines.append(f"  - missing from this install: {line}")
    return "\n".join(lines)


# Drift comes in three directions and they call for opposite responses, so the
# summary is keyed on which are actually present. Telling a reader whose
# install is *missing* a hook to go hunt for a retired rule sends them after a
# guard that is not there.
_EXTRAS_GUIDANCE = (
    "A hook that blocks you from one of these paths is enforcing a rule that "
    "may no longer exist in the repository; check here before diagnosing it as "
    "live code. Update the install (`/plugin` for Claude Code) to clear it."
)
_MISSING_GUIDANCE = (
    "These installs are behind this checkout, so a guard you expect to run is "
    "not registered there at all. Update the install (`/plugin` for Claude "
    "Code) to pick the hooks up."
)
_ERROR_GUIDANCE = (
    "Their registrations were never compared, so neither a match nor drift is "
    "established for them. Reinstall to replace the manifest."
)
_MIXED_GUIDANCE = (
    "Each entry below names the direction. A registration only the install has "
    "may enforce a rule that no longer exists in the repository; one only this "
    "checkout has is missing from the install; an unreadable manifest was not "
    "compared at all. Update the install (`/plugin` for Claude Code)."
)

_DRIFT_SUMMARY: dict[tuple[str, ...], tuple[str, str]] = {
    ("extras",): ("register hooks this checkout does not", _EXTRAS_GUIDANCE),
    ("missing",): ("are missing hooks this checkout ships", _MISSING_GUIDANCE),
    ("error",): ("have a hook manifest this check could not read", _ERROR_GUIDANCE),
}
_MIXED_SUMMARY = ("diverge from this checkout's hook registrations", _MIXED_GUIDANCE)


def _drift_kinds(reports: Sequence[InstallReport]) -> tuple[str, ...]:
    """Which of extras, missing, and error are present across ``reports``."""
    present = (
        ("extras", any(report.only_in_install for report in reports)),
        ("missing", any(report.only_in_source for report in reports)),
        ("error", any(report.error for report in reports)),
    )
    return tuple(kind for kind, seen in present if seen)


def _incomplete_block(incomplete: Sequence[str]) -> str:
    """Cap what the rest of the message is allowed to claim, or add nothing."""
    if not incomplete:
        return ""
    roots = "".join(f"\n- incomplete scan: {entry}" for entry in incomplete)
    return (
        "\n\n**This result is not conclusive.** A search stopped at its "
        f"{MAX_SCAN_DIRS}-directory bound before the tree was exhausted, so an "
        f"installed copy past that bound was never compared.{roots}"
    )


def format_message(
    reports: list[InstallReport], notes: list[str], incomplete: Sequence[str] = ()
) -> str:
    """Render the session-start message, stating the clean case explicitly."""
    header = "## Installed Plugin Hook Drift\n\n"
    drifted = [report for report in reports if report.has_drift]
    note_block = "".join(f"\n- note: {note}" for note in notes)
    incomplete_block = _incomplete_block(incomplete)

    if not reports:
        reached = " was reached" if incomplete else " found on disk"
        return (
            header
            + f"No installed copy of this repository's plugins{reached}."
            + note_block
            + incomplete_block
        )

    if not drifted:
        return (
            header
            + f"{len(reports)} installed copy/copies match this checkout's hook "
            + "registrations."
            + note_block
            + incomplete_block
        )

    summary, guidance = _DRIFT_SUMMARY.get(_drift_kinds(drifted), _MIXED_SUMMARY)
    body = "\n".join(_format_report(report) for report in drifted)
    return (
        header
        + f"**{len(drifted)} of {len(reports)} installed copy/copies {summary}.** "
        + guidance
        + note_block
        + incomplete_block
        + "\n\n"
        + body
    )


def _drain_stdin() -> None:
    """Drain stdin to prevent pipe buffer blocking on the harness side."""
    if not sys.stdin.isatty():
        try:
            sys.stdin.read()
        except OSError:
            pass


def _emit_utf8(text: str) -> None:
    """Prefer UTF-8 protocol output, with an ambient-encoding text fallback."""
    stream = sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="strict", newline="\n")
        except (AttributeError, TypeError, ValueError, io.UnsupportedOperation, OSError):
            pass
        else:
            stream.write(text + "\n")
            stream.flush()
            return

    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(bytes(f"{text}\n", encoding="utf-8"))
        buffer.flush()
        return

    stream.write(text + "\n")
    stream.flush()


def main() -> None:
    """Compare installed plugin copies against this checkout and report."""
    _drain_stdin()

    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    outcome = check_installed_plugins(Path(get_project_directory()), Path.home())
    _emit_utf8(format_message(outcome.reports, outcome.notes, outcome.incomplete))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fail-open: never block session start
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)
