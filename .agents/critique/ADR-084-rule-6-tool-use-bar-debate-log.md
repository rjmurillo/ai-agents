# adr-review debate log: ADR-084 rule 6 (tool-use hook bar)

**Subject**: 2026-08-18 amendment adding rule 6 to ADR-084, plus the operative
rule at `.claude/rules/tool-use-hook-bar.md`.
**Trigger**: owner policy statement that a `PreToolUse` or `PostToolUse` hook
requires exceptional justification outweighing its cost, achievable no other way.
**Rounds**: 1 (six lenses), followed by an author revision pass.

## Round 1 votes

| Lens | Vote | Head finding |
|---|---|---|
| architect | BLOCK | P0-1: MUST 2's alternative placements are all upstream, so applying them to a vendored consumer-facing hook inverts ADR-084 rule 1. |
| security | BLOCK | P0-001: the amendment moved the security carve-out and orphaned every line-number citation to it. |
| critic | BLOCK | P0-2: `PostToolUseFailure` is per-call, unmatchable, and was outside the bar, leaving it evadable by event choice. |
| analyst | Disagree-and-Commit | Claim that the two tool-use events are the only per-call events is REFUTED. |
| independent-thinker | Disagree-and-Commit | The union invariant is ours (#2342), not a Copilot property, and the millisecond exhibit is the weakest available evidence. |
| high-level-advisor | Accept (conditional) | Prose without a gate repeats rule 5, which is measurably unbuilt after 29 days. |

## Findings resolved in the revision

**Citations (security P0-001, architect P1-2).** Verified independently: the
carve-out moved from line 145 to line 169, and 11 live citations pointed at
`145-148` across ADR-068 (2), ADR-071 (3), ADR-085 (6, of which 3 prose-form).
All 11 now cite the durable section anchor "What this ADR does NOT do" instead
of a line range that the next amendment would shift again. The round-1 counts
disagreed (security said 11, architect said 5); the measured figure is 11.

**Upstream placements (architect P0-1, security P1-002).** Rule 6 now states
that for a vendored hook with consumer-facing value, none of the Git-hook,
lefthook, CI, or server-side options is a valid alternative, because a consumer
installs none of them; re-homing removes coverage rather than moving it, and
must be recorded per ADR-085 Decision 10. A placement catching the outcome
rather than the execution does not count as ruling out a security control.

**Event scope (critic P0-2, analyst claim 7).** Verified from source:
`.claude/settings.json` registers `PostToolUseFailure` with no matcher, and
`build/scripts/generate_dispatcher.py:517` omits that event from
`_MATCHER_EVENTS`, so it cannot be tool-scoped. The bar now covers every
per-call event (`PreToolUse`, `PostToolUse`, `PermissionRequest`,
`PostToolUseFailure`), stated in MUST 1's subject rather than framing prose
(critic P0-3). The refuted claim that the two tool-use events are the only
per-call events is removed from both documents.

**Union attribution (independent-thinker P0-1, architect P1-3).** Corrected. The
one-entry-per-event collapse is issue #2342, pinned by
`tests/build_scripts/test_copilot_dispatcher_artifact.py::test_every_event_is_one_dispatcher_entry`,
not a Copilot platform property; the generator already emits multiple entries
for `_DIRECT_HOST_MERGE_EVENTS`. Both documents now attribute it to ADR-068.

**Evidence re-founding (independent-thinker P0-2, P1-1).** The millisecond table
was the weakest exhibit and the 498 ms figure cannot be a spawn cost: it is 4.9x
the bare-`Bash` figure for a strictly narrower matcher, so it measures the
guard's own work. The rule now leads with issue #5013, verified at ADR-085:428:
a bare `Bash` matcher plus the timed child-process deny denied 127 unrelated
Bash commands over more than 21 minutes. Blast radius, not latency.

**Matcher deletion (independent-thinker P1-5).** Verified from source:
`event_matcher_union` (`generate_dispatcher.py:556`) returns `None` when any
matcher fails to reduce, and its docstring states the dispatcher then "fires on
every call". Added as mechanism 3 and as MUST 4, with the live
`mcp__serena__write_memory` case named.

**Incumbent grandfathering (critic P0-4).** All four MUST 2 alternatives are now
discharged on the record for `invoke_require_subagent_model.py`, including the
`scripts/validation/check_model_pins.py` CI option the critic named. The honest
verdict is recorded: CI covers the definition-file arm, the hook covers the
call-time arm only. The amortization and no-union-widening arguments are
explicitly marked as non-precedent.

**Windows figure (analyst claim 6).** Owner-recalled and measured nowhere in
this repository. Both documents now say so and name the disagreeing ADR-068:150
figure (246 ms cold start of the older per-shim launcher, a different basis).
The amendment does not rest on it.

**Scenario coverage (critic P1-9, security P2-005).** The original five
scenarios all tested refusal, so a rule refusing every tool-use hook would have
scored 5/5. Added S6 (positive arm: an agent-time prevention control no later
surface can observe), S7 (evasion via `PostToolUseFailure`), S8 (widening an
existing matcher), S9 (unreducible MCP matcher).

**Dead vendored mirror (advisor, critic P1-7).** The rule's `applyTo` named
paths no consumer repository has, reproducing the self-neutering shape rule 4
bans. Scope is now internal-only, so `generate_rules.py` skips the plugin
mirror; `.agents/architecture/**` was added so the rule loads at proposal time.
Plugin instruction files return to 23 against 28 in `.github/instructions`.

## Open, not resolved here

**No mechanical gate ships (advisor, critic P1-5).** Both lenses observe that
ADR-084 rule 5's planned CI presence check is still unbuilt 29 days after
acceptance, measured as zero occurrences of `Customer value:` anywhere in
`scripts/`, `build/`, or `.github/workflows/`. Prose has a 0-for-1 record here.
The proposed gate is a ratchet over the registration surfaces, or an assertion
in `tests/hooks/test_dispatch_groups_parity.py` requiring a per-call
registration's ledger entry to name its ruled-out alternatives. Not built in
this change; carried to the owner as an explicit decision rather than silently
deferred.

**Ambiguity of "far outweighs" (critic P1-8).** The cost has units and the
benefit does not. Mitigated but not closed: MUST 2's rule-outs and the worked
example are checkable, the threshold itself is not.
