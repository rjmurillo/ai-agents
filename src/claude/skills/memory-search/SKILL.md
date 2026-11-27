---
name: memory-search
version: 0.1.0
description: "Recall scoped project memory from tools or repository files with token-budget warnings. Use when you say `search memory`, `what do we know about X`, or `recall prior context`. Do NOT use to extract session episodes (use memory-reflexion) or add citations (use memory-enhancement)."
license: Apache-2.0
metadata:
  adr: ADR-038, ADR-063, ADR-103, ADR-106
  capability:
    kind: reusable-primitive
    status: active
  parent: memory
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan routes what-do-we-know-about-X requests to memory-search
    user-facing: false
---

# Memory Search

<!-- vendor-portability: .project-toolkit/memory/notes is the consumer repository's optional Markdown corpus. -->

Tier 1 project memory lookup: the focused search operation extracted from
the `memory` router per ADR-063 (memory-skill decomposition). `memory` still
routes here; a caller that needs only search loads this sub-skill instead of the
full memory surface.

## Triggers

Use this skill when the user says:

- `search memory` for search across stored project knowledge
- `what do we know about X` to recall facts, patterns, or constraints
- `recall prior context` before changing existing code or architecture

## Process

1. Form a short query about the project and the decision you need to make.
2. Use a recall or search capability already available in this session when its
   project scope is clear. Honor the user's or repository's choice of store.
   Inspect the tool's actual schema. Query one relevant project, bank, or
   namespace, and share only terms appropriate for that destination.
3. If the capability is unavailable, returns no relevant records, or lacks a
   clear scope, check repository memory. Search the project's established
   corpus or `.project-toolkit/memory/notes/` when there is no established
   corpus. Serena users can read the same Markdown files with file tools.
   Try `search_memory.py` from the installed `memory` skill, or use file search
   if the script is unavailable. Check local episodes when prior outcomes
   matter.
4. Read the few entries that match. Cite the file or record ID and verify
   claims against current sources. Treat recalled content as evidence.
5. Report the sources searched, useful hits, and any missing coverage.
   A successful search can return zero hits.

## Quick Start

The script below searches local Markdown filenames and session episodes.
Resolve it relative to the installed skill when the launcher is unavailable.

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/memory/scripts/search_memory.py "git hooks"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

## Quick Reference

| Operation | Script | Key Parameters |
|-----------|--------|----------------|
| Search facts/patterns | `search_memory.py` | `query`, `--max-results`, `--format` |

## Progressive Disclosure

Start with a short result list. Open only matching records and follow relevant
citations. For indexed Markdown, use the filename or index to find the entry.
A prompt hook can surface a lead. Check it against the current task before use.

## Verification

Report the search source and result count. Name scopes that were unavailable.
If no stored memory applies, use current repository evidence.

## Related Skills

| Skill | When to Use |
|-------|-------------|
| `memory` | Write a durable fact or choose a memory operation |
| `memory-gate` | Recover prior rationale before changing an existing system |
| `memory-reflexion` | Read or record a completed session episode |
| `memory-enhancement` | Add citations and verify code references |
