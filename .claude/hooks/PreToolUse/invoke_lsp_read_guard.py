#!/usr/bin/env python3
r"""Graduated LSP-first Read gate (ADR-062, conditional enforcement).

Claude Code PreToolUse hook (matcher ``Read``). Ports the read-gate tiers from
the claude-code-lsp-enforcement-kit (nesaminua, MIT, v2.3.2), file
``kit/hooks/lsp-first-read-guard.js``. The conditioning, the state scheme, the
capability split, and the tier thresholds follow ADR-062 (Section 3), not the
kit. This hook is THIN (parse, call lib, decide, format): symbol/provider/state
logic lives in ``hook_utilities`` (clean-architecture.md, ADR-062 Section 9).

Capability: ``SYMBOLS_OVERVIEW`` (Serena ``get_symbols_overview``), which is
available for ALL 8 configured ``.serena/project.yml`` languages including
markdown/json/yaml/toml, per the user directive recorded in ADR-062 Section 3.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, ADR-035 exemption; see ADR-062 Impl Notes):
    0 = Allow (not a Read, non-gated target, no overview provider, soft warn,
        surgical mode, LSP_GATE_MODE=warn, SKIP_LSP_GATE, or any fail-open path)
    2 = Block (Warmup tier with no warmup recorded, or Hard-block tier with
        nav_count below NAV_REQUIRED), only when LSP_GATE_MODE != 'warn'

Canonical kit read-gate tiers (``lsp-first-read-guard.js:30-32, 78-160``),
quoted character-for-character for the load-bearing thresholds and the
dedup-aware next-read computation (canonical-source-mirror.md):

    const FREE_READS = 2;
    const WARN_AT = 3;
    const REQUIRE_NAV_2_AT = 6;
    ...
    const readFiles = Array.isArray(flag.read_files) ? flag.read_files : [];
    const navCount = flag.nav_count || 0;
    const alreadyRead = readFiles.includes(filePath);
    const nextReadNum = alreadyRead ? readFiles.length : readFiles.length + 1;

    if (navCount >= 2 || alreadyRead) { ... process.exit(0); }
    if (nextReadNum <= FREE_READS) { ... process.exit(0); }
    if (nextReadNum === WARN_AT && navCount === 0) { emitWarning(...); ... }
    if (nextReadNum < REQUIRE_NAV_2_AT && navCount < 1) { emitBlock(...); }
    if (nextReadNum >= REQUIRE_NAV_2_AT && navCount < 2) { emitBlock(...); }

Stricter/looser/different than canonical
----------------------------------------
- DIFFERENT tier shape (ADR-062 Section 3, the load-bearing rule): the kit ramps
  Warmup -> 2 free -> warn at 3 -> nav>=1 unlocks reads 4-5 -> nav>=2 (read 6+)
  unlocks all, via the ``REQUIRE_NAV_2_AT = 6`` boundary. ADR-062 collapses the
  two-step nav unlock into a single ``NAV_REQUIRED = 2`` Surgical threshold: any
  read 4+ with ``nav_count < 2`` is a HARD BLOCK (the kit's "1 nav unlocks 4-5"
  middle step is dropped). Surgical (``nav_count >= 2``) allows all. This is
  STRICTER on reads 4-5 (the kit allowed them after 1 nav; this requires 2).
  The Soft-warn tier therefore covers read 3 with ``nav_count < NAV_REQUIRED``
  (nav 0 or 1), not only ``nav_count == 0``: hard-block starts at read 4
  (``next_read_num > WARN_AT``), so read 3 always warns and allows (issue #2200).
  This warns more aggressively on read 3 than the kit: the kit silently allows
  read 3 after one nav, while this port emits an advisory and still allows.
- DIFFERENT conditioning: the kit gates by hard-coded code-extension regex and
  unconditionally blocks Warmup on any code file. This port gates ONLY when an
  overview-capable provider exists for the file type (``detect_providers`` non
  empty); every tier degrades to ALLOW otherwise (ADR-062 Section 3 last line,
  Section 5 fail-open). This is LOOSER: non-configured types are never gated.
- DIFFERENT non-gated set: the kit's allow regexes (``ALLOW_NON_CODE_EXT``,
  ``ALLOW_PATH_PATTERNS``, ...) are project-specific (Tailwind, knowledge-vault,
  node_modules). This port replaces them with the ADR-062 Section 7 always
  bypass set: out-of-repo paths, dotfiles, and TMPDIR/scratch. In-repo
  configured-language files are gated; the language list is the source of truth.
- DIFFERENT writer: the kit's read guard MUTATES state (``writeFlag``) on every
  allow. ADR-062 Section 4 makes the PostToolUse tracker the single
  system-of-record; this guard only READS state. No write occurs here.
- ADDED ``LSP_GATE_MODE`` and ``SKIP_LSP_GATE`` (ADR-062 Section 6): the kit has
  no advisory mode or kill switch. ``warn`` mode converts every BLOCK into the
  same guidance as an exit-0 systemMessage; ``SKIP_LSP_GATE=true`` bypasses all.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    # Fail-open: a navigation guard must never wedge a turn on bootstrap failure.
    sys.exit(0)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import (  # noqa: E402
    FREE_READS,
    NAV_REQUIRED,
    SYMBOLS_OVERVIEW,
    WARN_AT,
    detect_providers,
    get_project_directory,
    is_gated_target,
    normalize_path,
    read_state,
)
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

_SKIP_ENV = "SKIP_LSP_GATE"
_MODE_ENV = "LSP_GATE_MODE"
_WARN_MODE = "warn"


def _note(message: str) -> None:
    """Emit a structured one-line stderr note (no secrets, no payloads)."""
    print(f"lsp-read-guard: {message}", file=sys.stderr)


def build_warmup_block(file_path: str, providers: list[str]) -> str:
    """Build the Warmup-tier guidance (kit ``Gate 1`` message, adapted).

    Names the overview-capable providers and a copy-pasteable warmup call for
    the exact file, so the redirected turn is one call, not a guess.
    """
    lines = [
        "LSP-FIRST BLOCK (Warmup required)",
        f"Read on a configured file needs a symbols-overview call first: {file_path}",
        "Call one of these, then Read:",
    ]
    if "serena" in providers:
        lines.append(f'  mcp__serena__get_symbols_overview("{file_path}")')
    if "native_lsp" in providers:
        lines.append("  LSP documentSymbol on the file (native LSP overview)")
    lines.append(
        f"After warmup: {FREE_READS} free Reads, then {NAV_REQUIRED} nav calls unlock all."
    )
    return "\n".join(lines)


def build_warn_message(file_path: str, next_read_num: int, nav_count: int) -> str:
    """Build the Soft-warn guidance (kit ``Gate 3`` warning, adapted)."""
    remaining = NAV_REQUIRED - nav_count
    current_plural = "call" if nav_count == 1 else "calls"
    remaining_plural = "call" if remaining == 1 else "calls"
    return (
        f"LSP-FIRST WARNING (Read {next_read_num}): consider symbol navigation.\n"
        "Use find_symbol / find_referencing_symbols before more Reads.\n"
        f"You have {nav_count} nav {current_plural}; make {remaining} more {remaining_plural} "
        f"before Read {next_read_num + 1}."
    )

def build_hard_block(
    file_path: str, next_read_num: int, nav_count: int, providers: list[str]
) -> str:
    """Build the Hard-block guidance (kit ``Gate 4/5`` message, adapted)."""
    lines = [
        "LSP-FIRST BLOCK (Surgical mode required)",
        f"Read {next_read_num} requires {NAV_REQUIRED} LSP navigation calls; you have {nav_count}.",
        "Make a navigation call, then Read:",
    ]
    if "serena" in providers:
        lines.append(f'  mcp__serena__find_symbol / get_symbols_overview("{file_path}")')
    if "native_lsp" in providers:
        lines.append("  LSP goToDefinition / findReferences (native LSP)")
    lines.append(f"Blocked: {file_path}")
    return "\n".join(lines)


def _emit_warn(message: str) -> None:
    """Emit an exit-0 advisory systemMessage (kit ``emitWarning``)."""
    print(json.dumps({"systemMessage": message}))


def _decide_block(message: str, file_path: str) -> int:
    """Return the block (2) or warn (0) decision per ``LSP_GATE_MODE``.

    In ``warn`` mode the same guidance is emitted as an exit-0 systemMessage so
    a misfire never wedges a turn (ADR-062 Section 6, single-toggle rollback).
    """
    if os.environ.get(_MODE_ENV, "").strip().lower() == _WARN_MODE:
        _emit_warn(message)
        _note(f"warn-mode advisory for {file_path}")
        return 0
    # Emit guidance on stdout (user transcript, sibling-guard parity) and on
    # stderr (the agent-visible channel for exit-2 PreToolUse blocks, ADR-062).
    print(message)
    print(message, file=sys.stderr)
    _note(f"blocked Read {file_path}")
    return 2


def evaluate(file_path: str, project_dir: str) -> tuple[int, str | None]:
    """Decide the gate outcome for a Read of ``file_path``.

    Pure decision over read-only state (the PostToolUse tracker owns writes).
    Returns ``(exit_code, block_message)``; ``block_message`` is None on allow.
    Graduated tiers per ADR-062 Section 3.
    """
    if not is_gated_target(file_path, project_dir):
        _note(f"non-gated target, allow: {file_path}")
        return 0, None

    providers = detect_providers(file_path, SYMBOLS_OVERVIEW, project_dir)
    if not providers:
        _note(f"no overview provider, allow: {file_path}")
        return 0, None

    state = read_state(project_dir)
    read_files = state["read_files"]
    nav_count = state["nav_count"]
    # Normalize path for consistent dedup with the tracker's normalized storage.
    normalized_path = normalize_path(file_path, project_dir)
    already_read = normalized_path in read_files
    next_read_num = len(read_files) if already_read else len(read_files) + 1

    # Surgical tier: nav threshold met, or this exact file already read.
    if nav_count >= NAV_REQUIRED or already_read:
        _note(f"surgical/allow (nav={nav_count}, already_read={already_read}): {file_path}")
        return 0, None

    # Warmup tier: no warmup recorded -> block (overview call first).
    if not state["warmup_done"]:
        _note(f"warmup-block: {file_path}")
        return _gate_result(build_warmup_block(file_path, providers), file_path)

    # Soft-allow tier: the first FREE_READS reads after warmup pass.
    if next_read_num <= FREE_READS:
        _note(f"free-read {next_read_num}/{FREE_READS}, allow: {file_path}")
        return 0, None

    # Soft-warn tier: read WARN_AT with nav below NAV_REQUIRED -> advisory, still
    # allow. ADR-062 Section 3 hard-blocks from read 4 (next_read_num > WARN_AT);
    # read 3 with one nav must warn, not block (issue #2200). nav_count >=
    # NAV_REQUIRED is already short-circuited by the surgical tier above.
    if next_read_num == WARN_AT and nav_count < NAV_REQUIRED:
        _emit_warn(build_warn_message(file_path, next_read_num, nav_count))
        _note(f"soft-warn read {next_read_num}, allow: {file_path}")
        return 0, None

    # Hard-block tier: reads 4+ with nav below NAV_REQUIRED -> block.
    _note(f"hard-block read {next_read_num} (nav={nav_count}): {file_path}")
    return _gate_result(build_hard_block(file_path, next_read_num, nav_count, providers), file_path)


def _gate_result(message: str, file_path: str) -> tuple[int, str | None]:
    """Apply LSP_GATE_MODE to a would-be block, returning (code, message)."""
    code = _decide_block(message, file_path)
    return code, (message if code == 2 else None)


def main() -> int:
    """Main hook entry point. Returns the exit code."""
    if skip_if_consumer_repo("lsp-read-guard"):
        return 0

    if os.environ.get(_SKIP_ENV, "").strip().lower() == "true":
        _note("SKIP_LSP_GATE=true, allow")
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)

        if hook_input.get("tool_name") != "Read":
            return 0

        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0

        # file_path (Claude) or path (Copilot CLI view); see #2610.
        file_path = str(tool_input.get("file_path") or tool_input.get("path") or "").strip()
        if not file_path:
            return 0

        project_dir = get_project_directory()
        exit_code, _message = evaluate(file_path, project_dir)
        return exit_code

    except Exception as exc:
        # Fail-open on errors (never block on infrastructure issues).
        _note(f"error {type(exc).__name__} - {exc}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
