#!/usr/bin/env python3
"""Block the Glob tool on code symbols when an LSP can navigate them.

Claude Code PreToolUse hook (matcher: Glob) for ADR-062 conditional LSP-first
enforcement. Ported from the claude-code-lsp-enforcement-kit (nesaminua, MIT,
v2.3.2), file ``kit/hooks/lsp-first-glob-guard.js``. It closes the gap where an
agent locates a symbol by filename glob (for example ``*UserService*``) instead
of using a symbol-navigation tool, bypassing the Grep and Read guards. The kit
blocks unconditionally; this port conditions the block on LSP availability so a
miss degrades to allowing the raw tool (fail-open), never a deadlock.

Canonical kit decision shape (``lsp-first-glob-guard.js:37-58``), quoted
character-for-character (canonical-source-mirror.md):

    if (data.tool_name !== 'Glob') process.exit(0);
    const pattern = String(data.tool_input?.pattern ?? '').trim();
    if (!pattern) process.exit(0);
    ...
    const tokens = pattern
      .split(/[*/.\\{}\\[\\]()!?,\\s|+-]+/)
      .map(t => t.trim())
      .filter(Boolean);
    const symbolTokens = tokens.filter(t => isCodeSymbol(t));
    if (symbolTokens.length === 0) process.exit(0);

Stricter/looser/different than canonical
----------------------------------------
- CONDITIONAL block (the load-bearing ADR-062 difference): the kit blocks any
  symbol-shaped glob token regardless of LSP availability. This port blocks only
  when (a) a token is a code symbol AND (b) a ``symbol_navigation`` provider is
  configured for the glob's code-extension target, or, for a bare symbol glob
  with no extension, for any configured programming language in the repo. Any
  other case ALLOWS (exit 0). Mandatory per release-it.md fail-open.
- SHARED symbol detection: token detection uses
  ``scripts.hook_utilities.lsp_symbols.is_code_symbol`` (the verbatim
  ``lsp-first-guard.js`` port), not the glob guard's own larger ``skipExact``
  set. The lib's short-lowercase and casing rules already reject the dir and
  framework stems the kit listed explicitly; the result is equivalent for glob
  tokens and avoids a second, drifting allowlist.
- DROPPED structured-block stdout JSON and the hardcoded NON_CODE_PATH denylist;
  capability detection in ``lsp_provider`` (sourced from ``.serena/project.yml``)
  replaces the denylist, and the recovery guidance replaces the dashboard JSON.
- ADDED ``LSP_GATE_MODE=warn`` advisory mode, ``SKIP_LSP_GATE`` kill switch, and
  consumer-repo skip (ADR-062 Sections 5, 6), mirroring the sibling guards.

Hook Type: PreToolUse (matcher: Glob)
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (not Glob, empty/no-symbol pattern, no provider for the target,
        warn mode, kill switch, consumer repo, any fail-open path)
    2 = Block (symbol-shaped glob token with an available symbol_navigation
        provider, default block mode)
"""

from __future__ import annotations

import json
import os
import re
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
        if _cur.parent == _cur:  # pragma: no cover - filesystem root, marker found first
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
    EXTENSION_TO_SERENA_LANGUAGE,
    PROGRAMMING_SERENA_LANGUAGES,
    PROVIDERS,
    SYMBOL_NAVIGATION,
    detect_providers,
)
from hook_utilities.lsp_symbols import is_code_symbol, strip_zero_width  # noqa: E402

_HOOK_NAME = "lsp-glob-guard"
_WARN_MODE = "warn"

# Port of the kit token splitter (``lsp-first-glob-guard.js:52-55``): strip glob
# metacharacters, separators, and operators to isolate alphabetic tokens.
_TOKEN_SPLIT = re.compile(r"[*/.\\{}\[\]()!?,\s|+\-]+")
# Trailing file extension of a glob: a final ``.<alnum>`` run. Matching on the
# raw pattern avoids the dotfile trap (stripping ``*`` from ``**/*.json`` leaves
# ``/.json``, which ``Path.suffix`` reads as a hidden file with no extension).
_EXTENSION_RE = re.compile(r"\.([A-Za-z0-9]+)$")


def _coerce_str(value: object) -> str:
    """Coerce a tool_input value to a stripped string, never raising.

    Mirrors the kit's ``String(data.tool_input?.pattern ?? '')`` coercion so a
    non-string pattern becomes a benign string rather than crashing.
    """
    if value is None:
        return ""
    return str(value).strip()


def find_glob_symbols(pattern: str) -> list[str]:
    """Return the symbol-shaped tokens of a Glob pattern.

    Ports ``lsp-first-glob-guard.js:52-58``: split on glob metacharacters and
    separators, drop empties, and keep tokens that ``is_code_symbol`` recognizes.
    Zero-width characters are stripped first so an invisible split cannot bypass
    the ASCII checks.
    """
    cleaned = strip_zero_width(pattern)
    tokens = [tok.strip() for tok in _TOKEN_SPLIT.split(cleaned)]
    return [tok for tok in tokens if tok and is_code_symbol(tok)]


def glob_extension(pattern: str) -> str:
    """Return the trailing file extension of a glob, or '' if none.

    ``*UserService*.ts`` -> ``.ts``; ``**/*.json`` -> ``.json``;
    ``*UserService*`` -> ``''``; ``src/**`` -> ``''``.
    """
    match = _EXTENSION_RE.search(pattern.strip())
    return f".{match.group(1)}" if match else ""


def resolve_providers(pattern: str, project_dir: str) -> list[str]:
    """Resolve the symbol_navigation providers relevant to a glob pattern.

    Two cases:
      - The glob names a file extension (``*Foo*.ts``): ask the provider layer
        whether that extension is symbol-navigation capable. A non-code or
        non-symbol-navigable extension (``.md``) yields an empty list (allow).
      - The glob is a bare symbol search (``*UserService*``, no extension): it
        searches code files by symbol name, so probe each configured programming
        language and return the first non-empty provider list. Empty means no
        symbol-navigation LSP is configured for code in this repo (allow).
    """
    extension = glob_extension(pattern)
    if extension:
        return detect_providers(f"x{extension}", SYMBOL_NAVIGATION, project_dir)
    for probe_ext, language in EXTENSION_TO_SERENA_LANGUAGE.items():
        if language not in PROGRAMMING_SERENA_LANGUAGES:
            continue
        providers = detect_providers(f"x{probe_ext}", SYMBOL_NAVIGATION, project_dir)
        if providers:
            return providers
    return []


def build_guidance(pattern: str, symbols: list[str], providers: list[str]) -> str:
    """Build LSP-first recovery guidance for a blocked symbol-shaped glob.

    Names, per provider, the find_symbol / find_referencing_symbols tool to use
    (PascalCase -> definition, else references) plus the activate_project +
    initial_instructions recovery path for the post-compaction case where Serena
    is configured but inactive.
    """
    lines = [
        f"LSP-FIRST: Glob pattern '{pattern}' contains {len(symbols)} code "
        f"symbol(s): {', '.join(symbols)}.",
        "Find files by symbol name with a symbol-navigation tool, not a glob:",
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
        "Globbing by extension or lowercase concept (for example '*.ts', "
        "'*auth*') is allowed."
    )
    lines.append(
        "Recovery if the LSP is unavailable: call "
        "mcp__serena__activate_project then mcp__serena__initial_instructions, "
        "or set SKIP_LSP_GATE=true to bypass."
    )
    return "\n".join(lines)


def _emit_warn(guidance: str) -> None:
    """Emit guidance as an exit-0 advisory (LSP_GATE_MODE=warn)."""
    print(json.dumps({"systemMessage": guidance}))
    print(f"{_HOOK_NAME}: warn mode, allowing Glob (advisory only)", file=sys.stderr)


def _emit_block(guidance: str, symbols: list[str]) -> None:
    """Emit guidance as a blocking message (default block mode)."""
    print(guidance)
    print(
        f"{_HOOK_NAME}: blocked Glob on code symbol(s) {', '.join(symbols)}",
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


def _evaluate(hook_input: dict) -> tuple[str, list[str], list[str]] | None:
    """Decide whether a Glob call should block.

    Returns ``(pattern, symbols, providers)`` when the pattern carries a code
    symbol and a symbol_navigation provider is available; otherwise ``None``.
    """
    if hook_input.get("tool_name") != "Glob":
        return None
    tool_input = hook_input.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    pattern = _coerce_str(tool_input.get("pattern"))
    if not pattern:
        return None
    symbols = find_glob_symbols(pattern)
    if not symbols:
        return None
    providers = resolve_providers(pattern, get_project_directory())
    if not providers:
        return None
    return pattern, symbols, providers


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

        pattern, symbols, providers = decision

        if lsp_runtime_down():
            warn_once_lsp_down(_HOOK_NAME, get_project_directory())
            return 0

        guidance = build_guidance(pattern, symbols, providers)
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
