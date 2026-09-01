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

## Round 2: post-merge validator findings

Source: the AI Spec Validator's completeness lens on PR #5156 head `ab3c122df`,
which read the shipped artifacts rather than the proposal. It returned PARTIAL
with three consistency defects in the rule 6 artifacts and one overclaim
inherited from the first scope. All four were verified against source and fixed.

**1. The decision of record was narrower than its own operative rule (the
serious one).** ADR-084 rule 6 scoped to `PreToolUse`, `PostToolUse`, and
`PermissionRequest`. `.claude/rules/tool-use-hook-bar.md` scoped to those plus
`PostToolUseFailure` and stated that naming fewer leaves the bar evadable by
event choice. A reviewer applying the ADR alone would therefore have permitted
exactly the move scenario S7 exists to refuse. This is the round 1 critic
finding (P0-2) fixed in the rule but only half-carried into the ADR. Verified
again from source before fixing: `build/scripts/generate_dispatcher.py:517`
omits `PostToolUseFailure` from `_MATCHER_EVENTS`, so it cannot be tool-scoped,
and `.claude/settings.json` registers it with no matcher. The ADR now carries
the four-event scope and says why it is load-bearing.

**2. The fixture contradicted the rule it measures.** Scenario S5's rationale
still read "The bar governs the two tool-use events only", which is the exact
claim round 1 refuted and the QA report records as corrected. A fixture that
asserts the pre-correction claim will score a regression as correct.

**3. Citation drift inside the fixture.** S4 attributed prefer-least-frequent
to MUST 4; that is MUST 5. MUST 4 is the unreducible-matcher rule, which S9
cites correctly.

**4. ADR-085 Decision 9 overstated its own residual gap.** It said a push
carrying a markdown violation reaches the remote "until the equivalent Lefthook
job is in place". `lefthook.yml` already runs `markdown-autofix` and
`markdown-check` at pre-commit over staged `**/*.md`, so the job exists. The
real gap is narrower: a violation in a file the commit did not stage, or a
commit made with `SKIP_AUTOFIX=1`. Corrected rather than left as a
worse-than-reality claim, which is the same overclaim class round 1 caught in
the millisecond exhibit.

**Method note.** Findings 1 to 3 are all the same shape: a correction applied to
one artifact and not propagated to the others that restate it. The round 1
fixes were verified against source; what went unverified was whether every
surface carrying the old claim had been swept. That is the mirror obligation
applied to documentation rather than to code, and it is worth naming because
the first three defects would each have scored as passing in isolation.

**Round 2 follow-on, same shape as findings 1 to 3.** Widening rule 6 to four
events left rule 3's appended cross-reference still reading "For `PreToolUse`
and `PostToolUse`". One more surface restating the superseded scope, found by
sweeping for the old phrasing rather than by another review round. Corrected to
name the per-call events rule 6 defines. This is the third time the same
propagation gap produced a defect in this change, which is the argument for
sweeping every surface on a claim change instead of fixing the one that was
reported.

## Round 3: rule 5, built rather than deferred

The open item both the advisor and critic lenses raised, and which round 2 left
recorded as unresolved, is now closed. Owner asked whether rule 5 was worth
building or should be amended away. The measurement decided it:

| Question | Measured |
|---|---|
| Hook scripts under `.claude/hooks/` carrying `Customer value:` | 1 of 8 |
| Of those, how many are actually vendored (`surface: "plugin"`) | 1 |
| Rule 5 compliance on the vendored surface | 1 of 1 |
| `Customer value:` occurrences in `scripts/`, `build/`, `.github/workflows/` | 0 |

The 1-of-8 figure is the trap. Rule 5 binds the vendored surface, and scope is a
property of the registration, not the directory: `.claude/hooks/` also holds this
repository's dogfood hooks, which the rule never covered. Scoping by directory
would have demanded a consumer-value line from seven hooks that have no consumer,
which is rule 1's question and rule 2's answer, not rule 5's.

**Verdict: enforce, but not as specified.** A standalone workflow, script, and
baseline guarding one already-compliant file is disproportionate, and it would
add to precisely the self-referential governance machinery this repository's
2026-08-17 retrospective measured at 94% of open issues. The parity suite already
resolves plugin-surface groups and already runs inside `python-tests`, so the
check costs no new job.

Both new tests were mutation-controlled against the real tree rather than
asserted:

| Control | Expectation | Observed |
|---|---|---|
| `Customer value:` stripped from the vendored hook | rule 5 test fails | FAILED as required |
| plugin surface emptied of all `surface: "plugin"` groups | anti-vacuity test fails | FAILED, **while the rule 5 test passed on zero files** |

The second control is why the companion test exists. It demonstrates the vacuity
rather than arguing it: with no plugin-surface groups the presence check examines
nothing and reports success, which is the shape `ci-scripts.md` MUST 12 names.

Sweeping rather than patching the reported line, per the round 2 method note:
four passages described rule 5 as planned or unbuilt (the rule itself plus three
in Consequences). All four were corrected in the same change. This is the first
time in this change that the sweep ran before a reviewer reported the second
instance.
