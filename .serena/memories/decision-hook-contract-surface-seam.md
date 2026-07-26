# Extending a validator to a second surface: the reader is the seam

## Question

`hook_contracts.py` validated the Claude hook surface only. How do you extend it
to the Copilot CLI surface without doubling the file?

## Conventional answer

Issue #3384 proposed threading a surface descriptor, a root prefix plus a
dispatcher name, through the four functions that assume one surface:
`extract_script_path`, `parse_settings`, `_expand_dispatch_group`,
`_resolve_script_path`.

## Why that is wrong here

The surfaces differ in three ways, not one:

| | Claude | Copilot |
|---|---|---|
| Registration shape | `event -> [{matcher, hooks:[{type,command,timeout}]}]` | `event -> [{matcher, bash, powershell, type, timeoutSec}]` |
| Plugin root resolves to | `.claude` | `src/copilot-cli` |
| Shim membership | one `dispatch_groups.json`, keyed by `--group NAME` | per-event `<Event>/_manifest.json` beside `_dispatch.py` |

A root-only descriptor fixes only row 2. Fed the Copilot file, `parse_settings`
finds `group.get("hooks", [])` empty on every entry and returns zero entries
**silently**. The validator would report "All hook contracts valid" and look
like it covered both surfaces.

## First-principles position

The per-entry validators (`validate_script_exists`, `validate_exit_code_docs`,
`validate_timeout`, `validate_hook_type_known`, `validate_duplicate_entries`)
already operate on `HookEntry` carrying a **repo-relative script path**. That
type is the seam. Everything surface-specific is "turn this registration file
into `HookEntry` objects". Everything after it is already generic.

So: one reader per surface, one expander per surface, and a `root` argument on
the plugin-root substitution. **Zero validators changed.**

## Attribution without a field

The AC asked that violations name their surface. No `surface` field was added:
every `Violation` already carries a repo-relative script path, and the roots
differ (`.claude/...` vs `src/copilot-cli/...`). A field would have to be
threaded through every validator to reach the message, reintroducing exactly the
threading the seam avoided. A test pins the attribution.

## What the gate found immediately

Two real violations the moment it could see the surface: the Copilot PreToolUse
dispatcher and its shim documented no exit-code contract. Both are **generated**,
so the fix went into `build/scripts/generate_dispatcher.py` and
`generate_hooks_shim.py`, not into the artifacts. Comments, not docstrings,
because `generate_dispatcher.py` has a `_DocstringStripper` that removes
docstrings on purpose to keep comment-only canonical edits as ownership proof.

Rule to carry forward: when a gate is extended to a surface that was never
gated, expect it to fail on the live tree, and fix whatever generated the
artifact rather than the artifact.

Refs #3384, PR #3407.
