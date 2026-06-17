#!/usr/bin/env python3
"""Block delegating an implementation subagent without pre-resolved LSP context.

Claude Code PreToolUse hook (matcher: Agent and Task) for ADR-062 conditional
LSP-first enforcement. When the orchestrator delegates to an ENFORCED subagent
(an implementation/code-navigation role) and the prompt lacks a pre-resolved
"## LSP CONTEXT" section, the agent will re-search the codebase with grep/Read,
spending tokens the orchestrator could have resolved once with an LSP query. This
guard requires that context to be in the prompt before the delegation fires.

This is the highest false-positive-risk guard in the ADR-062 set. It is
deliberately conservative: a SMALL, documented enforced set, fail-open on every
uncertainty, and behind the SKIP_LSP_GATE kill switch. When the repo agent
taxonomy is unclear, the default is ALLOW.

Hook Type: PreToolUse
Exit Codes (Claude Hook Semantics, exempt from ADR-035; see ADR-062 Section
"Implementation Notes" and precedent invoke_skill_first_guard.py):
    0 = Allow (not an Agent/Task call, exempt subagent, LSP context present,
        no provider available, fail-open, or LSP_GATE_MODE=warn)
    2 = Block (enforced subagent, no LSP context, provider available, block mode)

Mode (ADR-062 Section 6):
    LSP_GATE_MODE=warn  -> never exit 2; emit the same guidance as an exit-0
                           systemMessage on stdout instead.
    LSP_GATE_MODE=block -> default; blocks with exit 2.

Kill switch (ADR-062 Section 6): SKIP_LSP_GATE=true bypasses the guard entirely.

------------------------------------------------------------------------------
Canonical source mirror (canonical-source-mirror.md, BINDING)
------------------------------------------------------------------------------
Ported from: /tmp kit hooks/lsp-pre-delegation.js
  (github.com/nesaminua/claude-code-lsp-enforcement-kit, MIT, v2.3.2).

The kit's LSP-context detection contract, quoted CHARACTER-FOR-CHARACTER from
kit hooks/lsp-pre-delegation.js lines 85-91:

    const hasLspContext =
      /\\bLSP CONTEXT\\b/i.test(prompt) ||
      /\\bSymbol Map\\b/i.test(prompt) ||
      /\\bdefined\\s+at\\s+[\\w\\-\\/]+\\.\\w{2,4}:\\d+/i.test(prompt) ||
      /\\bcalled\\s+from\\s+[\\w\\-\\/]+\\.\\w{2,4}:\\d+/i.test(prompt) ||
      /\\bused\\s+in\\s+[\\w\\-\\/]+\\.\\w{2,4}:\\d+/i.test(prompt) ||
      /\\bimported\\s+(?:in|by)\\s+[\\w\\-\\/]+\\.\\w{2,4}:\\d+/i.test(prompt);

The kit's gate triggers only above a prompt-length floor, quoted from line 43:

    if (prompt.length < 200) process.exit(0);

The kit's "Agent" tool-name guard, quoted from line 27:

    if (data.tool_name !== 'Agent') process.exit(0);

Stricter/looser/different than canonical:
  - Tool-name set: STRICTER coverage. Kit gates only tool_name 'Agent'. This
    repo also delegates via 'Task' (Claude Code's subagent tool), so both
    'Agent' and 'Task' are gated. Anything else is allowed.
  - Agent taxonomy: DIFFERENT. The kit hardcodes a JS/TS product's agent names
    (backend-explorer, EXEMPT_AGENTS reviewers, etc.). Those names do not exist
    here. This port REMAPS to this repo's taxonomy (templates/agents/,
    .claude/agents/): the enforced set is the implementation/code-navigation
    role only (implementer). The context-retrieval agent was folded into the
    exploring-knowledge-graph skill (Issue #2103), so it is no longer a
    delegable subagent and was dropped from the set. Every other role
    (architect, analyst, qa, security, critic, planners, advisors, roadmap,
    devops, reviewers, memory, retrospective, etc.) is EXEMPT. The enforced set
    is intentionally SMALL per the ADR-062 high-false-positive caveat. Unknown
    subagent types are EXEMPT (fail-open).
  - LSP-context regex: SAME contract, character-for-character (Python re with
    the same patterns and the re.IGNORECASE flag mirroring JS /i).
  - Prompt-length floor: SAME value (200), applied identically.
  - Block-vs-warn decision: DIFFERENT mechanism. The kit chose block-vs-warn
    per call by inspecting isolation/worktree task state on disk. ADR-062 owns
    the per-call decision through LSP_GATE_MODE (env) instead: 'block' (default)
    or 'warn'. No .task directory probe, no two-hour mtime window, no worktree
    sniffing. The kit's task-phase machinery (lines 45-83) is DROPPED; ADR-062
    conditions on subagent type + provider availability, not phase-on-disk.
  - Provider conditioning: STRICTER gate, LOOSER block. ADR-062 Section 2/3
    requires an LSP tier be available before any block. This port checks
    detect_providers for the symbols-overview capability on a repository code
    target; an empty provider list degrades to ALLOW (fail-open). The kit had
    no such conditioning (it blocked regardless of provider availability).
  - State: NONE. This guard is stateless. It only READs subagent_type + prompt.
    It does not touch gate_state (that is the Read gate's tracker, ADR-062
    Section 4).
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
    print(f"Plugin lib directory not found: {_lib_dir} (CLAUDE_PLUGIN_ROOT={_plugin_root!r})", file=sys.stderr)
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
    SYMBOLS_OVERVIEW,
    configured_languages,
    detect_providers,
    representative_extension_for_language,
)

# Tools that delegate to a subagent. Kit gated only 'Agent'; this repo also
# uses 'Task'. STRICTER coverage; see module docstring divergence section.
DELEGATION_TOOLS = frozenset({"Agent", "Task"})

# ENFORCED subagent types: the implementation/code-navigation roles whose
# prompts benefit from pre-resolved LSP context. REMAP of the kit taxonomy to
# this repo (templates/agents/, .claude/agents/). Kept SMALL per the ADR-062
# high-false-positive caveat. Everything not in this set is EXEMPT.
ENFORCED_SUBAGENTS = frozenset({"implementer"})

# Prompt-length floor, quoted from kit line 43: prompts under 200 chars carry
# no real navigation surface; allow them unconditionally.
PROMPT_LENGTH_FLOOR = 200

# LSP-context detection. Faithful Python port of the kit's hasLspContext
# (kit lines 85-91), re.IGNORECASE mirrors JS /i. Order preserved. The path
# character class is broadened from the kit's ``[\w\-\/]`` to also accept
# backslash (``\\``) and the colon used in Windows drive prefixes so paths
# like ``C:\src\foo.py:42`` are recognized on Windows. The forward-slash
# branch is unchanged, so POSIX paths still match exactly as before.
_PATH_CHARS = r"[\w\-\/\\:]"
_LSP_CONTEXT_PATTERNS = (
    re.compile(r"\bLSP CONTEXT\b", re.IGNORECASE),
    re.compile(r"\bSymbol Map\b", re.IGNORECASE),
    re.compile(rf"\bdefined\s+at\s+{_PATH_CHARS}+\.\w{{2,4}}:\d+", re.IGNORECASE),
    re.compile(rf"\bcalled\s+from\s+{_PATH_CHARS}+\.\w{{2,4}}:\d+", re.IGNORECASE),
    re.compile(rf"\bused\s+in\s+{_PATH_CHARS}+\.\w{{2,4}}:\d+", re.IGNORECASE),
    re.compile(rf"\bimported\s+(?:in|by)\s+{_PATH_CHARS}+\.\w{{2,4}}:\d+", re.IGNORECASE),
)

# Default probe target used only as a last-resort fallback when the repo has
# no ``.serena/project.yml`` languages we can iterate over. Kept Python-shaped
# so existing Python-only repos still resolve the same provider tier as before.
_PROVIDER_PROBE_TARGET = "lsp_probe.py"


def is_enforced_subagent(subagent_type: str) -> bool:
    """Return True when the subagent type is in the enforced (implementation) set.

    Case-insensitive exact match. Kit used exact case-insensitive matching after
    a substring-bypass fix (kit lines 36-40); this mirrors that decision.
    """
    return subagent_type.strip().lower() in ENFORCED_SUBAGENTS


def has_lsp_context(prompt: str) -> bool:
    """Return True when the prompt already carries pre-resolved LSP context.

    Faithful port of the kit hasLspContext disjunction (kit lines 85-91).
    """
    return any(pattern.search(prompt) for pattern in _LSP_CONTEXT_PATTERNS)


def provider_available(project_dir: str) -> bool:
    """Return True when an overview-capable LSP tier exists for any configured language.

    Pure configuration check (ADR-062 Section 8): no live probe. Iterates the
    languages declared in ``.serena/project.yml`` and asks the provider
    registry whether an overview-capable LSP exists for a representative file
    of each language. This makes the gate fire correctly on TypeScript-only,
    Go-only, or other non-Python repos where the kit's single hardcoded
    Python probe target produced a silent fail-open.

    Fallback path: if no languages are configured (no ``.serena/project.yml``
    or empty list), fall back to the historic Python probe target so existing
    Python-only repos resolve providers identically to the pre-#2199 behavior.
    An empty provider list means there is no LSP whose result the orchestrator
    could have pre-resolved, so the guard must fail-open (ALLOW).
    """
    languages = configured_languages(project_dir)
    for language in languages:
        ext = representative_extension_for_language(language)
        if not ext:
            continue
        probe_target = f"lsp_probe{ext}"
        if detect_providers(probe_target, SYMBOLS_OVERVIEW, project_dir):
            return True

    # Fall back to the historic Python probe when no configured language has an
    # overview-capable provider or no languages are configured.
    providers = detect_providers(_PROVIDER_PROBE_TARGET, SYMBOLS_OVERVIEW, project_dir)
    return bool(providers)


def build_guidance(subagent_type: str) -> str:
    """Build the LSP-context guidance message (block reason or warn systemMessage)."""
    return (
        "\n## BLOCKED: Subagent Delegation Without Pre-Resolved LSP Context\n\n"
        f"**Delegating to `{subagent_type}` without a `## LSP CONTEXT` section.**\n\n"
        "Implementation subagents re-search the codebase with grep and full-file "
        "Read when the prompt does not hand them resolved symbol locations. Resolve "
        "the context once, then paste it into the prompt.\n\n"
        "### Do this now (then retry the delegation)\n"
        "1. `get_symbols_overview` on the target file(s) to prime the LSP.\n"
        "2. `find_symbol` / `find_referencing_symbols` for the symbols in scope.\n"
        "3. Add to the subagent prompt:\n\n"
        "   ## LSP CONTEXT (pre-resolved; do NOT re-search)\n"
        "   - symbolName: defined at path/to/file.py:42, called from path/to/other.py:15\n\n"
        "Re-launch the same delegation with `## LSP CONTEXT` included.\n\n"
        "Bypass: set `SKIP_LSP_GATE=true`, or `LSP_GATE_MODE=warn` for advisory mode.\n"
    )


def emit_warn(subagent_type: str) -> None:
    """Emit the guidance as an advisory exit-0 systemMessage (LSP_GATE_MODE=warn)."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "systemMessage": build_guidance(subagent_type),
        }
    }
    print(json.dumps(payload))
    print(
        f"LSP pre-delegation guard: warn mode, missing LSP context for {subagent_type}",
        file=sys.stderr,
    )


def emit_block(subagent_type: str) -> None:
    """Emit the guidance as a block response (exit 2)."""
    print(build_guidance(subagent_type))
    print(
        f"LSP pre-delegation guard: blocked delegation to {subagent_type} without LSP context",
        file=sys.stderr,
    )


def main() -> int:
    """Main hook entry point. Returns exit code (0 = allow, 2 = block)."""
    # Kill switch (ADR-062 Section 6); mirrors SKIP_QA_GATE/SKIP_ADR_GATE.
    # Normalized check for consistent behavior with other ADR-062 guards.
    if os.environ.get("SKIP_LSP_GATE", "").strip().lower() == "true":
        return 0

    if skip_if_consumer_repo("lsp-pre-delegation-guard"):
        return 0

    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)

        if hook_input.get("tool_name") not in DELEGATION_TOOLS:
            return 0

        tool_input = hook_input.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0

        # String coercion mirrors the kit (lines 31-32): non-string fields would
        # raise on subsequent string methods; coerce defensively.
        subagent_type = str(tool_input.get("subagent_type") or "")
        prompt = str(tool_input.get("prompt") or "")

        if not is_enforced_subagent(subagent_type):
            return 0

        if len(prompt) < PROMPT_LENGTH_FLOOR:
            return 0

        if has_lsp_context(prompt):
            return 0

        # Conditional gate (ADR-062 Section 2/3): only block when an LSP tier
        # is actually available; otherwise nothing was pre-resolvable.
        project_dir = get_project_directory()
        if not provider_available(project_dir):
            print(
                "LSP pre-delegation guard: no provider available, allowing",
                file=sys.stderr,
            )
            return 0

        # Runtime fail-open (issue #2622): provider_available is config-only, so
        # it still reports a provider when the language server timed out at
        # startup (ADR-062 Section 8, "configured != active"). With the LSP down,
        # the orchestrator cannot pre-resolve symbol context, so blocking the
        # delegation just wedges the turn. Allow it with a one-time warning
        # (ADR-062 Section 5, release-it.md graceful degradation).
        if lsp_runtime_down():
            warn_once_lsp_down("lsp-pre-delegation-guard", project_dir)
            return 0

        # Mode (ADR-062 Section 6): warn never blocks.
        if os.environ.get("LSP_GATE_MODE") == "warn":
            emit_warn(subagent_type)
            return 0

        emit_block(subagent_type)
        return 2

    except Exception as exc:
        # Fail-open on errors (mirror invoke_skill_first_guard.py).
        print(
            f"LSP pre-delegation guard error: {type(exc).__name__} - {exc}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
