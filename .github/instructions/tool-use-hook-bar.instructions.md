---
applyTo: .claude/hooks/**,.claude/settings.json,.agents/architecture/**
---

# The Tool-Use Hook Bar

Operative rule for ADR-084 rule 6. The ADR carries the decision and its
evidence; this file is what to do at the authoring seam.

**Scope: every per-call event, vendored or repo-local.** That is `PreToolUse`,
`PostToolUse`, `PermissionRequest`, and `PostToolUseFailure`, matching ADR-084
rule 6. Naming fewer would leave the bar evadable by event choice: a guard
refused on `PostToolUse` could re-register on `PostToolUseFailure`, pay the same
spawn, and match every tool.

`PostToolUseFailure` deserves the most scrutiny, not the least.
`build/scripts/generate_dispatcher.py:517` omits it from `_MATCHER_EVENTS`, so
it cannot be tool-scoped at all: any registration on it fires on every failed
tool call. It is the one per-call event with no narrowing available. Nothing is
registered on it today (ADR-096), so this is a warning about what re-adding one
would cost, not a description of a live hook.

A tool-use hook runs on the caller's hot path on every matching call, for the
life of the install. Its cost scales with how hard the agent is working, which
the session-boundary events do not.

## The cost is a blast radius, not a stopwatch

Lead with this, because the millisecond framing understates the risk by orders
of magnitude.

Issue #5013, recorded at `.agents/architecture/ADR-085-...asymmetry.md:428-431`:
the `push_pr_script_identity_guard` was registered on a bare `Bash` matcher, and
combined with the Copilot dispatcher's timed child-process deny (#4706) it
**denied 127 unrelated Bash commands over more than 21 minutes** before the
owner contained it. That is the real failure mode: a wrong deny on a hot tool
takes out unrelated work. Per-spawn latency is the smaller half.

Three mechanisms make a tool-use matcher wider than it looks. None is visible
from `.claude/`, which is where hooks are authored.

**1. Copilot matches on tool name only.** Its matcher targets are `toolName` for
`preToolUse` and `postToolUse` (see
`.claude/skills/agent-harness-reference/references/official-hook-contracts.md`,
"Matchers"). There is no argument-scoped form. Claude accepts `Bash(git push*)`;
`build/scripts/generate_dispatcher.py` strips the argument constraint via
`_COMMAND_SCOPED_RE`, so it degrades to bare `Bash` and the interpreter starts on
every Bash call, filtering in-process after the spawn.

**2. One dispatcher entry per event makes the matcher a union.** This is OUR
invariant, not a host limitation: issue #2342 collapses each event to a single
entry. It was pinned by
`tests/build_scripts/test_copilot_dispatcher_artifact.py::test_every_event_is_one_dispatcher_entry`,
which ADR-096 deleted along with the generated dispatcher it asserted against.
The invariant still lives in `build/scripts/generate_dispatcher.py`; nothing
currently pins it, because there is no generated dispatcher to pin. The
generator already emits multiple entries per event for
`_DIRECT_HOST_MERGE_EVENTS`. So adding a hook widens the union for every hook
already on that event, and the first hook re-added must restore that pin. Do
not restate this as a Copilot property; if the consolidation is ever revisited,
this cost changes with it.

**3. One unreducible matcher deletes the matcher for the whole event.** This is
the ceiling, and it is worse than widening. `event_matcher_union`
(`build/scripts/generate_dispatcher.py:556`) returns `None` when ANY registered
matcher fails to reduce to a known tool name, and its own docstring states the
consequence: "emit no matcher; the dispatcher fires on every call and filters
in-process". An MCP tool name is exactly the unreducible case. No such matcher
is registered today, because none is: ADR-096 retired the two Serena guards
whose `mcp__serena__*` matchers had collapsed the entire `PreToolUse` union,
making the Copilot dispatcher spawn on every tool call rather than on Serena
calls. That collapse is the single strongest measured cost ADR-096 removed, and
it is what this mechanism will do again to the first MCP-matched hook someone
re-adds.

## MUST

1. **Justify against the blast radius, not only the latency.** A new
   `PreToolUse`, `PostToolUse`, `PermissionRequest`, or `PostToolUseFailure`
   registration needs an outcome that outweighs both the per-call cost AND the
   cost of a wrong deny on that tool: a costly mistake, an irrecoverable loss, or a
   security property enforced by denial at agent time. "Enforces a convention"
   and "keeps formatting tidy" do not clear it.

2. **Rule out every placement that would work CORRECTLY.** In order: a
   host-native declarative surface, then a Git hook or lefthook job, then CI,
   then a server-side gate. A check that runs CORRECTLY at commit, push, or
   merge time MUST run there. "Correctly" is load-bearing: it excludes a check
   whose subject never reaches a commit (an executed command, a sub-agent
   spawn, a tool argument) and one whose value is prevention where the later
   surface only detects.

   Two limits on this list. The declarative option is Claude-side and unproven
   on Copilot (the contract records DOCS SILENT on a repo-committed permissions
   surface), so do not treat it as ruled out for a Copilot consumer without
   evidence. And for a VENDORED hook with consumer-facing value, none of the
   other three is a valid alternative at all: a consumer installs this
   repository's Git hooks, lefthook, and CI not at all. Re-homing there does not
   move consumer coverage, it removes it, and that MUST be recorded per ADR-085
   Decision 10.

3. **State the Copilot-side matcher, computed not guessed.** Name the union the
   registration produces by running `event_matcher_union` from
   `build/scripts/generate_dispatcher.py:556`, and say how often it fires. A
   proposal quoting only the Claude argument-scoped matcher has understated its
   cost by construction.

4. **A matcher that does not reduce to a known tool name is disqualifying for a
   vendored tool-use hook.** It deletes the matcher for every hook on the event
   (mechanism 3).

5. **Prefer the event that fires least.** If the work can happen at
   `SessionStart`, `SessionEnd`, or `PreCompact`, it goes there.

## MUST NOT

1. MUST NOT add a tool-use hook to a hot tool (`Bash`, `Read`, `Write`, `Edit`)
   for anything short of MUST 1. #5013 is what that costs when it misfires.
2. MUST NOT justify a tool-use hook on the shorter feedback loop alone.

## What ships today: nothing

**Zero tool-use hooks are registered, on either harness.** ADR-096 retired all
five (`require_subagent_model`, `serena_memory_scope_guard`,
`serena_worktree_scope_guard`, `observation_sync`, `memory_capture`) and the
generated Copilot dispatcher with them. `.claude/hooks/hooks.json` and
`src/copilot-cli/hooks/hooks.json` both carry `"hooks": {}`; no `_dispatch.py`
ships. `tests/hooks/test_zero_tool_use_hooks.py` is the ratchet that keeps it
that way, and failing it is the signal that you are proposing the first one.

So this file has no live example to reason from. That is deliberate and it
changes how you use the bar: every MUST below applies to a proposal, not to an
existing registration you can point at for precedent.

Three things a proposer must not inherit from the retired set:

1. **"It widens no union" is a property of being first, not of the hook.** The
   retired `require_subagent_model` cleared mechanisms 2 and 3 only because
   `Agent|Task` reduces natively AND it was the only registration on its event.
   The next hook on a populated event does not get that.
2. **"The spawn is cheap relative to the work it guards" is amortization, which
   MUST 1 does not accept.** MUST 1 weighs outcome against cost, not cost
   against cost. That argument was recorded against `require_subagent_model` and
   was already flagged as not-precedent before the hook was retired.
3. **Clearing this bar is necessary, not sufficient.** ADR-096 retired
   `require_subagent_model` even though it was the marginal pass: with the other
   four gone, keeping it would have cost the entire generated Copilot
   dispatcher, its manifest, its bootstrap, and roughly 20 hardening tests for
   one registration. Price the machinery, not just the hook.

What a first re-add owes, beyond MUST 1 through 5:

- Restore the one-entry-per-event pin (mechanism 2), which had no subject to
  guard after ADR-096 and was deleted.
- Rebuild the dispatcher hardening bar ADR-096 retired: fail-open on a corrupt
  manifest, partial-upgrade degradation, JSON-bomb rejection on oversized stdin,
  and a #5013-style regression pin proving a broad matcher cannot deny unrelated
  work. The generator can rebuild the dispatcher code; these tests do not come
  back with it.
- Restore ADR-084 rule 5's `Customer value:` presence check. Its two tests were
  deleted on their own instruction once the vendored surface emptied, so nothing
  currently enforces that a vendored hook states what it does for a consumer.
- Write a fresh runtime contract in ADR-071. The matcher, fail-open, and
  fail-closed contracts recorded there describe deleted code and are marked
  retired; do not read them as a contract a new hook inherits.

## References

- ADR-084 rule 6 and the carve-out under "What this ADR does NOT do".
- ADR-085 Decisions 8, 9, 10, and the #5013 incident record.
- ADR-068 (consolidated dispatcher), which owns the one-entry-per-event
  invariant this bar's cost model depends on. Its live registration counts are
  retired; read its 2026-08-19 Status amendment first.
- ADR-096 (zero tool-use hooks), which retired all five registrations and the
  generated Copilot dispatcher. It is the reason this file has no live example,
  and its "Re-evaluation Triggers" section is what a re-add must clear.
- ADR-071 Decision item 1 (plugin-root anchoring) still binds every hook on
  every event. Its per-gate runtime contracts are retired.
- `tests/hooks/test_zero_tool_use_hooks.py`, the re-accretion ratchet.
