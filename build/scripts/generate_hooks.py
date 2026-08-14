#!/usr/bin/env python3
"""Generate Copilot CLI hook config from the configured hook source (REQ-003-007).

Reads ``artifacts.hooks`` from a platform YAML, parses Claude's
``settingsSource`` ``hooks`` object, and copies each registered Python script
under ``.claude/hooks/`` into the Copilot output tree. Matcher registrations
retain one generated shim wrapper each. Every wrapper buffers stdin,
self-filters with the matcher grammar below, and either runs its canonical
body or exits 0 when it does not match. Matcher-free scripts remain direct
copies.

When ``artifacts.hooks.dispatcher`` is true,
``build/scripts/generate_dispatcher.py`` replaces the per-shim host
registrations with one entry per event while retaining those wrappers for
in-process self-filtering. ADR-068 defines its three modes: ``gate`` returns
the first nonzero shim exit, ``observe`` runs every shim and returns 0, and
``advise`` translates exactly one PermissionRequest decision producer.
Per-shim timeout metadata is validated in-process, but the host owns the
aggregate event timeout.

``generate_hooks_events.py`` stages dispatcher artifacts, stale matcher-shim
deletions, and ownership-proven orphan-event file deletions through
``HookGenerationTransaction``. It removes only empty orphan directories after
commit. This keeps regeneration rollback-safe while preserving unknown,
unsafe, and NO-REGEN artifacts. See ADR-068 and
``build/scripts/generate_dispatcher.py`` for the runtime and ownership
contracts.

MATCHER GRAMMAR
---------------

Three classes are supported (see :func:`classify_matcher`):

- ``regex``: pattern starts with ``^`` AND ends with ``$``.
  Example: ``^(Edit|Write)$`` (anchored full-tool-name match).
- ``tool-glob``: pattern matches ``^[A-Za-z_][A-Za-z0-9_]*\\((.*)\\)$``.
  Example: ``Bash(git commit*|gh pr create*)`` (toolName then
  fnmatch on the args). ``|`` inside the parens is OR-folded across
  branches; whitespace in tool args is collapsed before matching.
- ``bare``: anything else; treated as a literal tool name.
  Example: ``mcp__serena__write_memory``.

Adding a new matcher kind requires updating BOTH classifiers
(:func:`classify_matcher` build-time and ``_shim_classify`` runtime,
inlined into the shim template by :func:`_build_shim`) plus the
parametrized tests in ``tests/build_scripts/test_generate_hooks.py``.

FILENAME SCHEME
---------------

When two matchers point at the same source script (e.g. one guard
script registered under both ``Bash(git commit*)`` and
``Bash(gh pr create*)``), the generator writes one shimmed copy per
matcher to the output tree. Filenames carry a sanitized matcher
suffix plus a 6-char SHA-1 hash so distinct matchers MUST produce
distinct filenames; the hash closes a silent-clobber gate-bypass
class of bug. See :func:`_matcher_suffix`.

SHIM CRASH POLICY
-----------------

The shim exits with code 0 when the matcher does not fire (no-op
allow) and returns the wrapped script's exit code when it does fire.
Internal matcher errors use the wrapped hook's declared exception
policy: fail-open hooks warn and exit 0, while every other hook warns
and exits 2.

DEBUG TRACE
-----------

Set ``COPILOT_HOOK_DEBUG=1`` in the environment to make every shim
write a one-line trace to stderr after the dispatch decision. The
trace records the matcher, classified kind, and fired bool. Unset
means no trace and no perf cost beyond a single
``os.environ.get``.

EXIT CODES
----------

- 0: success
- 1: logic error (script not found, copy failure)
- 2: configuration error (missing stanza, malformed JSON, etc.)

Per ADR-035 Exit Code Standardization.

MODULE LAYOUT
-------------

The generator is split across cohesive sibling modules (issue #2223) to
stay under the file-size taste limit. This module is the CLI entry point
and the stable import facade; it re-exports the public names so callers
that ``import generate_hooks`` keep working:

- :mod:`generate_hooks_shim`: matcher classification + shim source.
- :mod:`generate_hooks_body`: script-body manipulation (shim inject/strip).
- :mod:`generate_hooks_emit`: stanza parsing, path resolution, script copy,
  Copilot entry building, and the shared ``GenerateHooksError`` /
  ``GenerateHooksResult`` / ``HookAuditEntry`` value objects.
- :mod:`generate_hooks_events`: per-event handlers and the
  ``generate_hooks`` orchestrator.
- :mod:`generate_dispatcher`: per-event host entries, manifests, matcher
  unions, and ownership checks.
- :mod:`generate_hooks_transaction`: rollback-safe publication and deletion.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

# Matcher classification and shim-source generation.
# Script-body manipulation (shim injection, ``__main__`` epilogue handling).
from generate_hooks_body import (  # noqa: E402, F401
    _extract_original_body,
    _find_shim_bounds,
    _has_fail_open_handler,
    _has_main_function_and_epilogue,
    _split_future_imports,
    _strip_main_epilogue,
    _wrap_body_in_function,
    inject_shim,
    is_shimmed,
    strip_shim,
)

# Script preparation: stanza parsing, paths, copy, entry building, and the
# shared value objects + domain error.
from generate_hooks_emit import (  # noqa: E402, F401
    _DEFAULT_TIMEOUT_SEC,
    GenerateHooksError,
    GenerateHooksResult,
    HookAuditEntry,
    _build_copilot_entry,
    _copy_script,
    _ensure_exact_case_dir,
    _load_hook_source,
    _matcher_suffix,
    _read_stanza,
    _relative_script_target,
    _resolve_paths,
    _resolve_script_path,
)

# Event iteration and orchestration.
from generate_hooks_events import (  # noqa: E402, F401
    _emit_one_hook,
    _handle_event_drop,
    _handle_unknown_event,
    _iter_hooks,
    _process_event,
    generate_hooks,
)
from generate_hooks_shim import (  # noqa: E402, F401
    _SHIM_BEGIN,
    _SHIM_END,
    _TOOL_GLOB_RE,
    MATCHER_BARE,
    MATCHER_REGEX,
    MATCHER_TOOL_GLOB,
    _build_shim,
    classify_matcher,
    glob_or_match,
    normalize_tool_args,
)

# --- CLI ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Platform YAML config (defaults to templates/platforms/copilot-cli.yaml).",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to script's grandparent).",
    )
    p.add_argument("--what-if", action="store_true", help="Dry-run mode.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root or _SCRIPT_DIR.parent.parent
    config_path = args.config or (
        repo_root / "templates" / "platforms" / "copilot-cli.yaml"
    )
    if not config_path.is_file():
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        return 2
    rc, _result = generate_hooks(config_path, repo_root, what_if=args.what_if)
    return int(rc)


if __name__ == "__main__":
    sys.exit(main())
