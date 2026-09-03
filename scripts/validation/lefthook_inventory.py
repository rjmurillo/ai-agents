#!/usr/bin/env python3
"""Which hook types Lefthook considers configured, asked of Lefthook itself.

Split out of ``check_git_hook_health`` because it is a separate question with
its own failure taxonomy. That gate asks whether git will run the hooks it has;
this asks which hooks should exist. Three fail-opens came from answering the
second question by reading Lefthook's config files here: the reader stopped at
the base file and missed ``-local`` overlays, then dropped hook types missing
from a hand-written allowlist, then returned nothing for ``.jsonc`` because
Python has no parser for it. Each silently degraded the caller to a single
``pre-push`` probe.

``lefthook dump`` answers all three at once. It merges every config file, every
``extends``, and all five supported formats, and it is Lefthook's own answer
rather than a second model of it.

Failures are typed rather than collapsed, because ADR-035 gives them different
exit codes and the repairs differ: a malformed config is not fixed by syncing
dependencies, and a missing runtime is not fixed by editing YAML.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

# `lefthook dump` is a local config merge and answers in about 0.1 seconds.
DUMP_TIMEOUT_SECONDS = 20

# A hook in the dump is a top-level mapping carrying work; the settings beside
# it are scalars, and `templates` and `colors` hold strings. Structural rather
# than an allowlist: the hand-written list this replaces omitted nine of
# Lefthook's 28 hook types and dropped unlisted names silently, so
# `reference-transaction` got no shim and no complaint. This cannot go stale.
# `setup` is its own key (https://lefthook.dev/configuration/setup/): a hook
# declaring only setup instructions and no jobs/commands/scripts is still
# real, dispatching work. Omitting it dropped that hook from the inventory
# under `no_auto_install`, so an absent shim for it was never flagged and
# Git Hook Health reported success on a hook that never ran (CWE-693).
HOOK_WORK_KEYS = frozenset({"jobs", "commands", "scripts", "setup"})

CONFIG_REMEDY = "check lefthook.yml and any -local overlay with: lefthook validate"
RUNTIME_REMEDY = "uv sync --frozen --extra dev"


class LefthookConfigError(RuntimeError):
    """Lefthook ran but its configuration could not be turned into an inventory."""


class LefthookExecutionError(RuntimeError):
    """Lefthook could not be run at all, so the inventory is unobtainable."""


def _is_hook_entry(value: object) -> bool:
    """True when a top-level dump entry declares hook work rather than a setting."""
    return isinstance(value, dict) and bool(HOOK_WORK_KEYS & set(value))


def dump_commands() -> list[list[str]]:
    """Ways to print the merged config as JSON, pinned runtime first.

    ``uv run --frozen`` matches how this repo pins Lefthook, but fails outside a
    uv project, so a bare ``lefthook`` on PATH is tried after it.
    """
    commands = []
    uv = shutil.which("uv")
    if uv:
        commands.append([uv, "run", "--frozen", "lefthook", "dump", "--format", "json"])
    lefthook = shutil.which("lefthook")
    if lefthook:
        commands.append([lefthook, "dump", "--format", "json"])
    return commands


def configured_hook_types(repo_root: Path) -> frozenset[str]:
    """Hook types in the merged Lefthook configuration.

    Raises ``LefthookExecutionError`` when no candidate command could be run to
    completion, and ``LefthookConfigError`` when one ran and produced output
    that is not a configuration mapping.
    """
    commands = dump_commands()
    if not commands:
        raise LefthookExecutionError("no lefthook or uv executable found")
    unreachable = "every candidate command failed"
    rejected = None
    for command in commands:
        try:
            result = subprocess.run(
                command,
                cwd=str(repo_root),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=DUMP_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            unreachable = f"{command[0]} timed out after {DUMP_TIMEOUT_SECONDS}s"
            continue
        except (OSError, subprocess.SubprocessError) as exc:
            unreachable = f"{command[0]} could not run: {exc}"
            continue
        if result.returncode != 0:
            # The process started and returned a verdict. Its only job here is
            # to print the merged config, so a nonzero exit is Lefthook, or the
            # runner in front of it, rejecting the input rather than a failure
            # to reach Lefthook. Classified by whether it ran, not by parsing
            # its message, which would be a second model of Lefthook's output.
            ran = " ".join(command[:2])
            rejected = f"{ran} exited {result.returncode}: {result.stderr.strip()}"
            continue
        return _parse_dump(result.stdout)
    if rejected is not None:
        raise LefthookConfigError(rejected)
    raise LefthookExecutionError(unreachable)


def _parse_dump(stdout: str) -> frozenset[str]:
    """Hook types in one successful dump, or raise ``LefthookConfigError``."""
    try:
        data = json.loads(stdout)
    except ValueError as exc:
        raise LefthookConfigError(f"lefthook dump did not emit JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LefthookConfigError("lefthook dump did not emit a configuration mapping")
    return frozenset(str(key) for key, value in data.items() if _is_hook_entry(value))
