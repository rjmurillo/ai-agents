#!/usr/bin/env python3
"""Block the Grep tool on code symbols when an LSP can navigate them.

Claude Code PreToolUse hook (matcher: Grep) for ADR-062 conditional LSP-first
enforcement. Ported from the claude-code-lsp-enforcement-kit (nesaminua, MIT,
v2.3.2), file ``kit/hooks/lsp-first-guard.js``. The kit blocks Grep on any code
symbol unconditionally; this port conditions the block on LSP availability so a
miss degrades to allowing the raw tool (fail-open), never a deadlock.

Canonical kit decision shape (``lsp-first-guard.js:16-61``), quoted
character-for-character (canonical-source-mirror.md):

    if (data.tool_name !== 'Grep') process.exit(0);
    const pattern = String(params.pattern ?? '').trim();
    ...
    if (pattern.length < 4) process.exit(0);
    const parts = pattern.split('|').map(p => p.trim()).filter(Boolean);
    const symbolParts = [];
    for (const part of parts) {
      if (isCodeSymbol(part)) symbolParts.push(part);
    }
    if (symbolParts.length === 0) process.exit(0);
    ...
    process.stderr.write(
      `\\n LSP-FIRST BLOCK: ${symbolParts.length} code symbol(s) in Grep ...`
    );

Canonical kit per-symbol intent (``lsp-first-guard.js:44, 55``):

    const intent = /^[A-Z]/.test(sym) ? 'symbol_search' : 'references';

Stricter/looser/different than canonical
----------------------------------------
- CONDITIONAL block (the load-bearing ADR-062 difference): the kit blocks any
  code symbol in Grep regardless of file type or LSP availability. This port
  blocks only when (a) the pattern part is a code symbol AND (b) the Grep target
  (``path``/``glob``, else the implicit repo scope) is a symbol-navigation-capable
  code file AND (c) a ``symbol_navigation`` provider is configured for that file.
  Any other case ALLOWS (exit 0). This is LOOSER (fewer blocks) by construction
  and is mandatory: a navigation gate that can wedge a turn is unacceptable
  (release-it.md fail-open).
- DROPPED path denylist + glob allowlist regexes: the kit hardcodes
  ``knowledge-vault|.task|.claude|node_modules|logs|docs|supabase/migrations``
  path skips and a ``.(md|txt|log|json|...)`` glob skip. This port replaces both
  with the capability check in ``scripts.hook_utilities.lsp_provider`` (the
  ``.serena/project.yml`` language list is the source of truth), so non-code
  targets are excluded by capability, not by a hand-maintained denylist.
- DROPPED structured-block stdout JSON: the kit prints a
  ``buildStructuredBlockResponse`` object to stdout for dashboards. This port
  emits a one-line stderr note plus the recovery guidance; the structured
  consumer surface is the hook ``audit.log`` (ADR-062 Section 6), not stdout.
- ADDED ``LSP_GATE_MODE`` warn mode: ``LSP_GATE_MODE=warn`` never exits 2; it
  emits the same guidance as an exit-0 ``systemMessage`` (single-toggle rollback,
  ADR-062 Section 6). The kit has no mode toggle.
- ADDED ``SKIP_LSP_GATE`` kill switch and consumer-repo skip (ADR-062 Sections 5,
  6), mirroring ``invoke_skill_first_guard.py``.

Hook Type: PreToolUse (matcher: Grep)
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (not Grep, no provider, non-code target, short/no-symbol pattern,
        warn mode, kill switch, consumer repo, any fail-open path)
    2 = Block (code symbol in Grep on a symbol-navigable code file with an
        available LSP provider, default block mode)
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
if _plugin_root:  # pragma: no cover - deployment layout (env set), not test env
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:  # pragma: no cover - filesystem root, marker always found first
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):  # pragma: no cover - lib always present
    print(
        f"Plugin lib directory not found: {_lib_dir} (CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    # Fail-open: a navigation guard must never wedge a turn on bootstrap failure.
    sys.exit(0)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402
from hook_utilities.lsp_health import (  # noqa: E402
    lsp_runtime_down,
    warn_once_lsp_down,
)
from hook_utilities.lsp_provider import (  # noqa: E402
    PROVIDERS,
    SYMBOL_NAVIGATION,
    detect_providers,
    is_code_target,
    repo_programming_providers,
)
from hook_utilities.lsp_symbols import is_code_symbol  # noqa: E402

_HOOK_NAME = "lsp-grep-guard"
_WARN_MODE = "warn"


def _coerce_str(value: object) -> str:
    """Coerce a tool_input value to a stripped string, never raising.

    Mirrors the kit's ``String(params.pattern ?? '')`` coercion so a non-string
    pattern (number, list) becomes a benign string rather than crashing.
    """
    if value is None:
        return ""
    return str(value).strip()


def _select_target(search_path: str, glob: str) -> str:
    """Pick the target whose extension drives the capability check.

    Grep can be scoped by ``path`` (a file or directory) or ``glob``
    (for example ``*.py``). Prefer ``glob`` when it names an extension, else
    the ``path``. An empty result means Grep is repo-wide with no file-type
    scope, which the caller handles through the repo-level provider probe.
    """
    if glob and Path(glob).suffix:
        return glob
    return search_path


def _is_repo_wide_scope(search_path: str, glob: str) -> bool:
    """True if the Grep scope is a directory tree, not a single file or glob.

    The Grep tool scopes by ``path`` (a file or directory) and/or ``glob`` (for
    example ``*.py``). A directory or repo-wide search names no navigable file
    extension, so ``_select_target`` returns a directory path or an empty string
    and the per-target capability check allows it. This detects that scope so the
    caller can fall back to the repo-level provider probe.

    Returns True when there is no extension-bearing ``glob`` (an explicit
    ``*.md`` glob is the caller deliberately scoping to non-code; do not gate
    that) AND the ``path`` is empty (repo-wide) or resolves inside the repo as a
    directory. An out-of-repo path returns False (fail-open), as does a ``path``
    that already names a file (handled by the per-target check, not here).
    """
    if glob and Path(glob).suffix:
        return False
    if not search_path:
        return True
    resolved = _resolve_in_repo(search_path)
    if resolved is None:
        return False
    return resolved.is_dir()


def _resolve_in_repo(target: str) -> Path | None:
    """Resolve ``target`` under the repo root, or None if it escapes the repo.

    Out-of-repo targets must never be gated; returning None keeps the fail-open
    contract. Resolution failures also return None (fail-open).
    """
    try:
        repo_root = Path(get_project_directory()).resolve()
        candidate = Path(target)
        resolved = (
            candidate.resolve(strict=False)
            if candidate.is_absolute()
            else (repo_root / candidate).resolve(strict=False)
        )
    except (OSError, ValueError):
        return None
    if not resolved.is_relative_to(repo_root):
        return None
    return resolved


def find_code_symbols(pattern: str) -> list[str]:
    """Return the code-symbol parts of a Grep pattern.

    Ports ``lsp-first-guard.js:35-41``: split the pattern on ``|``, trim each
    part, drop empties, and keep the parts that ``is_code_symbol`` recognizes.
    """
    parts = [part.strip() for part in pattern.split("|")]
    return [part for part in parts if part and is_code_symbol(part)]


def build_guidance(symbols: list[str], providers: list[str]) -> str:
    """Build the LSP-first recovery guidance for the blocked symbols.

    Names, per provider, the find_symbol / find_referencing_symbols tool to use
    (kit ``buildSuggestion`` intent: PascalCase -> symbol_search, else
    references) plus the activate_project + initial_instructions recovery path
    for the post-compaction case where Serena is configured but inactive.
    """
    lines = [
        f"LSP-FIRST: Grep pattern has {len(symbols)} code symbol(s): "
        f"{', '.join(symbols)}.",
        "Use a symbol-navigation tool instead of Grep:",
    ]
    for symbol in symbols:
        intent = "definition" if symbol[:1].isupper() else "references"
        lines.append(f"  {symbol}:")
        for provider_key in providers:
            provider = PROVIDERS.get(provider_key)
            if provider is None:
                continue
            tool = provider["tools"].get(intent) or provider["tools"].get("symbol_search")
            if not tool:
                continue
            lines.append(f"    {provider['prefix']}{tool} ({provider['label']})")
    lines.append(
        "Recovery if the LSP is unavailable: call "
        "mcp__serena__activate_project then mcp__serena__initial_instructions, "
        "or set SKIP_LSP_GATE=true to bypass."
    )
    return "\n".join(lines)


def _emit_warn(guidance: str) -> None:
    """Emit guidance as an exit-0 advisory (LSP_GATE_MODE=warn)."""
    print(json.dumps({"systemMessage": guidance}))
    print(f"{_HOOK_NAME}: warn mode, allowing Grep (advisory only)", file=sys.stderr)


def _emit_block(guidance: str, symbols: list[str]) -> None:
    """Emit guidance as a blocking message (default block mode)."""
    print(guidance)
    print(
        f"{_HOOK_NAME}: blocked Grep on code symbol(s) {', '.join(symbols)}",
        file=sys.stderr,
    )


def _bypassed() -> bool:
    """Allow without evaluating: consumer repo or the SKIP_LSP_GATE kill switch (ADR-062)."""
    if skip_if_consumer_repo(_HOOK_NAME):
        return True
    if os.environ.get("SKIP_LSP_GATE", "").strip().lower() == "true":
        print(f"{_HOOK_NAME}: SKIP_LSP_GATE set, allowing", file=sys.stderr)
        return True
    return False


def _evaluate(hook_input: dict) -> tuple[list[str], list[str]] | None:
    """Decide whether a Grep call should block.

    Returns ``(symbols, providers)`` when the call is a code-symbol Grep on a
    symbol-navigable file with an available provider; otherwise ``None`` (allow).
    Ports the tool-specific checks from ``lsp-first-guard.js:16-61``.
    """
    if hook_input.get("tool_name") != "Grep":
        return None
    tool_input = hook_input.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    pattern = _coerce_str(tool_input.get("pattern"))
    if len(pattern) < 4:
        return None
    symbols = find_code_symbols(pattern)
    if not symbols:
        return None
    search_path = _coerce_str(tool_input.get("path"))
    glob = _coerce_str(tool_input.get("glob"))
    target = _select_target(search_path, glob)
    if is_code_target(target, SYMBOL_NAVIGATION):
        providers = detect_providers(
            target, SYMBOL_NAVIGATION, get_project_directory()
        )
        if not providers:
            return None
        return symbols, providers

    # No navigable file/glob extension. A directory or repo-wide Grep
    # (empty path, or a path that is an in-repo directory) still scans navigable
    # code, so gate it when the repo has an active programming-language provider.
    # An out-of-repo path or a provider-less repo stays fail-open.
    if _is_repo_wide_scope(search_path, glob):
        providers = repo_programming_providers(get_project_directory())
        if providers:
            return symbols, providers
    return None


def main() -> int:
    """Main hook entry point. Returns exit code (0 allow, 2 block)."""
    if _bypassed():
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        decision = _evaluate(json.loads(input_json))
        if decision is None:
            return 0

        symbols, providers = decision

        if lsp_runtime_down():
            warn_once_lsp_down(_HOOK_NAME, get_project_directory())
            return 0

        guidance = build_guidance(symbols, providers)
        if os.environ.get("LSP_GATE_MODE", "").lower() == _WARN_MODE:
            _emit_warn(guidance)
            return 0

        _emit_block(guidance, symbols)
        return 2

    except Exception as exc:  # noqa: BLE001 - fail-open is mandatory (ADR-062)
        print(f"{_HOOK_NAME} error: {type(exc).__name__} - {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
