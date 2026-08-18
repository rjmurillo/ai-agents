---
applyTo: .claude/hooks/**,.claude/settings.json,.agents/architecture/**
---

# The Tool-Use Hook Bar

Operative rule for ADR-084 rule 6. The ADR carries the decision and its
evidence; this file is what to do at the authoring seam.

**Scope: every per-call event, vendored or repo-local.** That is `PreToolUse`,
`PostToolUse`, `PermissionRequest`, and `PostToolUseFailure`. Naming only the
two tool-use events would leave the bar evadable by event choice: a guard
refused on `PostToolUse` could re-register on `PostToolUseFailure`, pay the same
spawn, and match every tool.

`PostToolUseFailure` deserves the most scrutiny, not the least.
`build/scripts/generate_dispatcher.py:517` omits it from `_MATCHER_EVENTS`, so
it cannot be tool-scoped at all, and the live registration in
`.claude/settings.json` carries no matcher and fires on every failed tool call.
It is the one per-call event with no narrowing available.

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
entry, pinned by
`tests/build_scripts/test_copilot_dispatcher_artifact.py::test_every_event_is_one_dispatcher_entry`.
The generator already emits multiple entries per event for
`_DIRECT_HOST_MERGE_EVENTS`. So adding a hook widens the union for every hook
already on that event. Do not restate this as a Copilot property; if the
consolidation is ever revisited, this cost changes with it.

**3. One unreducible matcher deletes the matcher for the whole event.** This is
the ceiling, and it is worse than widening. `event_matcher_union`
(`build/scripts/generate_dispatcher.py:556`) returns `None` when ANY registered
matcher fails to reduce to a known tool name, and its own docstring states the
consequence: "emit no matcher; the dispatcher fires on every call and filters
in-process". An MCP tool name is exactly the unreducible case, and a live one is
registered today (`.claude/settings.json`, `mcp__serena__write_memory`).

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

## Applying the bar to what ships today

Two tool-use registrations run, and the distinction matters.

**Vendored:** `invoke_require_subagent_model.py` on `^(Agent|Task)$`, the only
one in `.claude/hooks/hooks.json`. It is the marginal case, not a comfortable
pass. It fires only on a sub-agent spawn, which already costs far more than the
hook. Copilot expresses `Agent|Task` natively as tool names, so it widens no
union and cannot trigger mechanism 3. It bounds model spend, which is MUST 1's
costly-mistake arm. And no declarative surface can read
`tool_input.subagent_type`.

MUST 2 requires all four alternatives on the record, so here they are rather
than the one the first draft gave. **Declarative surface:** unavailable, no
declaration reads `tool_input.subagent_type`. **Git hook and lefthook:**
unavailable, a sub-agent spawn is not a Git event and never reaches a commit.
**CI:** partially available and NOT fully ruled out. `scripts/validation/check_model_pins.py`
already governs `model:` pins in agent definition files and could assert every
definition carries one, which covers the definition-file arm with zero spawns.
What CI cannot cover is a spawn whose model is chosen at call time rather than
in a definition, which is the case the hook exists for. **Server-side gate:**
unavailable, no server observes a local sub-agent spawn.

So the honest verdict is that CI covers part of this and the hook covers the
remainder. If the call-time arm is ever removed, the CI check subsumes it and
the hook stops clearing MUST 2.

Two further caveats a future proposer must not read as precedent. Its cost is
low partly because it is the ONLY registration on its event, so "widens no
union" is a property of being first, not of the hook. And "the spawn is cheap
relative to a sub-agent" is an amortization argument, which MUST 1 does not
accept: MUST 1 weighs outcome against cost, not cost against cost. Note also it
is not a security boundary; its own docstring says so.

**Repo-local:** `invoke_observation_sync.py` on `PostToolUse` matching
`mcp__serena__write_memory` (`.claude/settings.json`). It does not ship, so the
vendored half of MUST 2 does not apply. `tests/hooks/test_dispatch_groups_parity.py`
records it as authorized pending relocation to Git hooks or CI, which is exactly
what MUST 2 asks for. Its MCP matcher is also the live mechanism-3 case.

## References

- ADR-084 rule 6 and the carve-out under "What this ADR does NOT do".
- ADR-085 Decisions 8, 9, 10, and the #5013 incident record.
- ADR-068 (consolidated dispatcher), which owns the one-entry-per-event
  invariant this bar's cost model depends on.
