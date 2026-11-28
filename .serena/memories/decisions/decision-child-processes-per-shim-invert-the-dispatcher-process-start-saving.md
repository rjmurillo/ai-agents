# Child processes per shim made the hook dispatcher cost more interpreter starts

**Atomicity**: 90%
**Category**: Hook contract, dispatcher cost
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E043. State checked on main at 1be533c496 (2026-11-26).

## Question

Does consolidating PreToolUse shims into one dispatcher save process starts per matched call?

## Conventional answer

ADR-068 claimed the consolidated dispatcher saves one host process start per matched call.

## First-principles position

After PR 4706 added child processes, the saving inverted. The dispatcher starts once, then starts one child per timed shim. That costs more interpreter starts than registering the shims directly.

## Evidence with limits

- On the Copilot gate path (2026-08-11), the dispatcher plus one child per timed shim makes 4 starts on a git push. Direct registration makes 2 starts on a Bash call and 1 on an Agent or Task call.
- PR 4706 introduced the child processes that reversed the saving.
- Limits: Counted from hook_dispatch.py:307-318 and the shim manifest by a six-agent review, not timed at runtime. Dated 2026-08-11.
- State on main at 1be533c496 (2026-11-26): fixed. ADR-068-consolidated-hook-dispatcher.md:169 says the dispatcher is retained, not for matched call process savings.

## Decision

Do not justify the dispatcher by process savings. Recount starts whenever shims gain child processes.

## Related

- `.serena/memories/decision-claude-hook-group-dispatch.md`
