"""Canonical: scripts/hook_utilities/lsp_provider.py. Sync via scripts/sync_plugin_lib.py.

Ported from the claude-code-lsp-enforcement-kit (nesaminua, MIT, v2.3.2),
file ``kit/hooks/lib/detect-lsp-provider.js``. PURE module: no side effects,
no network, no live MCP probe. Availability is a configuration-only check, so
"configured != active": a language listed in ``.serena/project.yml`` with the
``serena`` MCP server registered counts as available even if the server is not
running this turn (for example after a compaction deactivates Serena). The
fail-open design at the tool-call boundary (the guards) handles the gap; this
module reports eligibility from configuration alone (ADR-062 Section 8).

Canonical kit provider registry (``detect-lsp-provider.js:42-85``), quoted
character-for-character for the load-bearing shape (canonical-source-mirror.md):

    const PROVIDERS = {
      cclsp: {
        label:        'cclsp',
        prefix:       'mcp__cclsp__',
        matchToken:   'cclsp',
        tools: {
          definition:       'find_definition',
          references:       'find_references',
          symbol_search:    'find_workspace_symbols',
          implementation:   'find_implementation',
          hover:            'get_hover',
          diagnostics:      'get_diagnostics',
          incoming_calls:   'get_incoming_calls',
          outgoing_calls:   'get_outgoing_calls',
        },
        warmup: { tool: 'get_diagnostics', note: '...' },
      },
      serena: {
        label:        'Serena',
        prefix:       'mcp__serena__',
        matchToken:   'serena',
        tools: {
          definition:       'find_symbol',
          references:       'find_referencing_symbols',
          symbol_search:    'find_symbol',
          implementation:   'find_symbol',
          hover:             null,
          diagnostics:       null,
          incoming_calls:   'find_referencing_symbols',
          outgoing_calls:    null,
          overview:         'get_symbols_overview',
        },
        warmup: { tool: 'get_symbols_overview', note: '...' },
      },
    };

Canonical kit MCP config candidate list (``detect-lsp-provider.js:99-105``):

    const candidates = [
      path.join(HOME, '.claude.json'),
      path.join(HOME, '.claude', 'settings.json'),
      path.join(HOME, '.claude', 'mcp.json'),
      path.join(HOME, '.mcp.json'),
      path.join(process.cwd(), '.mcp.json'),
    ];

Stricter/looser/different than canonical
----------------------------------------
- DIFFERENT registry: the kit ships ``cclsp`` (TypeScript LSP MCP server) and
  ``serena``. ADR-062 Section 9 binds this port to ``serena`` plus a
  ``native_lsp`` tier (the Claude built-in ``LSP`` tool / Copilot auto-LSP).
  ``cclsp`` is dropped (not used in this repo); ``native_lsp`` is added as the
  tier-2 fallback the kit's single-provider model lacked.
- DIFFERENT serena ``implementation`` mapping: the kit maps
  ``implementation -> find_symbol`` (Serena has no direct equivalent). This
  repo exposes ``mcp__serena__find_implementations``, so this port maps
  ``implementation -> find_implementations`` and ``diagnostics ->
  get_diagnostics_for_file`` (both real tools here), where the kit had ``null``.
- STRICTER capability binding (the load-bearing ADR-062 rule, Section 2 vs 3):
  the kit blocks grep on any code symbol regardless of file type. This port
  splits two capabilities. ``symbol_navigation`` (go-to-definition /
  find-references) qualifies ONLY for programming languages
  (python/typescript/bash/powershell), so the symbol-grep guards never fire on
  markdown/json/yaml/toml. ``symbols_overview`` (Serena ``get_symbols_overview``)
  qualifies for ALL 8 configured Serena languages, so the Read gate ramps on
  every configured type. The kit has no such capability split.
- DIFFERENT availability source: the kit reads only user-level Claude MCP config
  JSON. This port additionally reads ``.serena/project.yml`` ``languages`` (the
  ADR-062 source of truth for which languages receive LSP treatment) and maps
  file extension -> serena language. ``native_lsp`` availability comes from a
  fixed programming-language extension set (no config dependency).
- DIFFERENT API surface: the kit's suggestion/structured-block builders
  (``buildSuggestion``, ``buildStructuredBlockResponse``, etc.) are message
  formatting and live in the thin guards, not in this pure detection module.
  This module exposes ``detect_providers``, ``is_code_target``, and the registry.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# --- Provider registry (adapted per the divergence section above) ----------
# Each provider maps abstract navigation intents to concrete tool names, and
# declares which capabilities it offers. ``None`` means the provider does not
# offer that intent.
PROVIDERS: dict[str, dict] = {
    "serena": {
        "label": "Serena",
        "prefix": "mcp__serena__",
        "match_token": "serena",
        "tools": {
            "definition": "find_symbol",
            "references": "find_referencing_symbols",
            "symbol_search": "find_symbol",
            "overview": "get_symbols_overview",
            "implementation": "find_implementations",
            "diagnostics": "get_diagnostics_for_file",
        },
        "warmup": {
            "tool": "get_symbols_overview",
            "note": "Serena's 'first tool to understand a file'",
        },
    },
    "native_lsp": {
        "label": "native LSP",
        "prefix": "",
        "match_token": "LSP",
        "tools": {
            "definition": "goToDefinition",
            "references": "findReferences",
            "symbol_search": "workspaceSymbol",
            "overview": "documentSymbol",
            "hover": "hover",
            "diagnostics": "diagnostics",
            "implementation": "goToImplementation",
        },
        "warmup": {
            "tool": "documentSymbol",
            "note": "Claude built-in LSP tool overview",
        },
    },
}

# Capabilities the guards request. ``symbol_navigation`` is go-to-definition /
# find-references; ``symbols_overview`` is get_symbols_overview.
SYMBOL_NAVIGATION = "symbol_navigation"
SYMBOLS_OVERVIEW = "symbols_overview"
_VALID_CAPABILITIES = (SYMBOL_NAVIGATION, SYMBOLS_OVERVIEW)

# File extension -> serena language name. The serena languages list in
# .serena/project.yml is the source of truth for which languages receive LSP
# treatment (ADR-062 Context).
EXTENSION_TO_SERENA_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".sh": "bash",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}

# Serena languages that are programming languages (have symbol navigation).
# markdown/json/yaml/toml are configured for symbols_overview but have no
# symbol search that replaces grep, so they are excluded here (ADR-062 Sec 2).
PROGRAMMING_SERENA_LANGUAGES: frozenset[str] = frozenset(
    {"python", "typescript", "bash", "powershell"}
)

# Native LSP availability comes from a fixed programming-language extension set
# (the Claude built-in LSP tool / Copilot auto-LSP handle these without config).
NATIVE_LSP_CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".py",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".swift",
        ".vue",
        ".svelte",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".sh",
        ".ps1",
        ".psm1",
    }
)


def _read_json_silent(file_path: Path) -> dict | None:
    """Read and parse a JSON file, returning None on any failure.

    Mirrors the kit's ``readJsonSilent`` (``detect-lsp-provider.js:88-95``):
    missing file or parse error returns None, never raises.
    """
    try:
        if not file_path.is_file():
            return None
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _serena_extension_language(file_path: str) -> str | None:
    """Map a file path's extension to a serena language name, or None."""
    suffix = Path(file_path).suffix.lower()
    return EXTENSION_TO_SERENA_LANGUAGE.get(suffix)


def _read_serena_languages(project_dir: str) -> set[str]:
    """Read the configured serena languages from .serena/project.yml.

    Pure config read. Uses a minimal line parser for the ``languages:`` block
    so this module has no YAML dependency at the hook boundary. Unreadable or
    absent config returns an empty set (fail-open: no availability, allow).
    """
    config_path = Path(project_dir) / ".serena" / "project.yml"
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return _parse_languages_block(text)


def _parse_languages_block(text: str) -> set[str]:
    """Extract language names from a ``languages:`` YAML list block.

    Reads ``- name`` list items following a top-level ``languages:`` key and
    stops at the next non-indented key. Comment lines are ignored.
    """
    languages: set[str] = set()
    in_block = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not in_block:
            if line.strip().startswith("#"):
                continue
            if line.strip() == "languages:" or line.strip() == "languages: []":
                in_block = True
            continue
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.startswith("- "):
            languages.add(stripped[2:].strip().lower())
            continue
        # A non-list, non-blank line ends the languages block.
        break
    return languages


def _mcp_config_candidates(project_dir: str) -> list[Path]:
    """Return MCP config file candidates (kit ``candidates`` list, adapted).

    Kit reads ~/.claude.json, ~/.claude/settings.json, ~/.claude/mcp.json,
    ~/.mcp.json, and cwd/.mcp.json. This port reads the project .mcp.json,
    ~/.mcp.json, and ~/.claude.json (the forms used in this repo).
    """
    home = Path.home()
    return [
        Path(project_dir) / ".mcp.json",
        home / ".mcp.json",
        home / ".claude.json",
    ]


def _serena_mcp_configured(project_dir: str) -> bool:
    """True if any MCP config registers a server containing 'serena'.

    Mirrors the kit's ``collectMcpServerNames`` + ``mcpNames.has('serena')``
    (``detect-lsp-provider.js:97-118, 141-143``), case-insensitive.
    """
    for candidate in _mcp_config_candidates(project_dir):
        data = _read_json_silent(candidate)
        if not isinstance(data, dict):
            continue
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            continue
        for name in servers:
            if "serena" in str(name).lower():
                return True
    return False


def _serena_available(file_path: str, capability: str, project_dir: str) -> bool:
    """True if Serena offers ``capability`` for ``file_path`` per config.

    Availability requires: (1) the file extension maps to a configured serena
    language, (2) the serena MCP server is configured, and (3) the capability
    binding holds for that language.
    """
    language = _serena_extension_language(file_path)
    if language is None:
        return False
    configured = _read_serena_languages(project_dir)
    if language not in configured:
        return False
    if not _serena_mcp_configured(project_dir):
        return False
    return _language_offers_capability(language, capability)


def _language_offers_capability(language: str, capability: str) -> bool:
    """Apply the ADR-062 capability binding to a serena language.

    symbol_navigation: programming languages only. symbols_overview: all
    configured serena languages.
    """
    if capability == SYMBOL_NAVIGATION:
        return language in PROGRAMMING_SERENA_LANGUAGES
    if capability == SYMBOLS_OVERVIEW:
        return True
    return False


def _native_lsp_available(file_path: str, capability: str) -> bool:
    """True if the native LSP tier offers ``capability`` for ``file_path``.

    Native LSP only covers programming-language extensions, so it offers both
    symbol_navigation and symbols_overview for files in that set and nothing
    for non-code extensions (markdown/json/yaml/toml).
    """
    if capability not in _VALID_CAPABILITIES:
        return False
    suffix = Path(file_path).suffix.lower()
    return suffix in NATIVE_LSP_CODE_EXTENSIONS


def detect_providers(
    file_path: str,
    capability: str,
    project_dir: str | None = None,
) -> list[str]:
    """Return ordered available providers offering ``capability`` for the file.

    Order is the three-tier navigation preference (ADR-062 Section 1): Serena
    first, then native LSP. Pure configuration check, no live probe.

    Args:
        file_path: target file path; its extension selects the language.
        capability: ``symbol_navigation`` or ``symbols_overview``.
        project_dir: repo root for config reads. Defaults to the CWD.

    Returns:
        Ordered list of provider keys (subset of ``['serena', 'native_lsp']``).
        Empty when no provider offers the capability for the file type, which
        the guards treat as fail-open (allow the raw tool).
    """
    if not file_path or capability not in _VALID_CAPABILITIES:
        return []
    resolved_dir = project_dir if project_dir is not None else os.getcwd()
    providers: list[str] = []
    if _serena_available(file_path, capability, resolved_dir):
        providers.append("serena")
    if _native_lsp_available(file_path, capability):
        providers.append("native_lsp")
    return providers


def is_code_target(target: str, capability: str) -> bool:
    """True if ``target`` is a file the given capability can navigate.

    A thin predicate over the extension-to-capability binding, independent of
    whether a provider happens to be configured. ``symbol_navigation`` is true
    only for programming-language extensions; ``symbols_overview`` is true for
    any of the 8 configured serena extensions plus native LSP code extensions.
    """
    if not target or capability not in _VALID_CAPABILITIES:
        return False
    suffix = Path(target).suffix.lower()
    if capability == SYMBOL_NAVIGATION:
        language = EXTENSION_TO_SERENA_LANGUAGE.get(suffix)
        if language in PROGRAMMING_SERENA_LANGUAGES:
            return True
        return suffix in NATIVE_LSP_CODE_EXTENSIONS
    # symbols_overview
    if suffix in EXTENSION_TO_SERENA_LANGUAGE:
        return True
    return suffix in NATIVE_LSP_CODE_EXTENSIONS
