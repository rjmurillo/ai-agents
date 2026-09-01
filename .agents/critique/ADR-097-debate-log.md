# ADR-097 Debate Log: Zero Tool-Use Hooks

Six-role `adr-review` debate on `.agents/architecture/ADR-097-zero-tool-use-hooks.md`.
Round 1. All six reviews ran independently and in parallel against the same
draft; none saw the others' output before voting.

## Context

The repo owner (rjmurillo) ratified three scope decisions under User
Sovereignty before this debate ran: retire all 5 registered tool-use hooks
(including the one with the strongest unconditional ROI case), retire the
entire generated Copilot dispatcher machinery per ADR-085 Decision 5, and
retire `post_tool_call_memory.py` as dead code in the same change. Per the
ADR-084 rule-6 amendment precedent (3 Block, 2 Disagree-and-Commit, 1
conditional Accept, still shipped), this debate is record quality, not a
veto gate: the owner's decision stands regardless of outcome. All six
reviewers were briefed on this explicitly.

## Verdicts

| Role | Verdict | Core finding |
|---|---|---|
| analyst | Disagree-and-Commit | Every file/test citation checked against the real tree holds, except Decision §3 claims `post_tool_call_memory.py` is retired when it was not yet, and the Impact table understates `scripts/ci/test_installed_plugin_hooks.py` as a naming fix when it is a designed hard failure on empty registration. |
| security | Accept | Serena guards correctly classified as correctness/data-integrity controls, not security controls (no trust boundary crossed between worktrees of one repo); ADR-084's carve-out does not block this on the merits, though the ADR's own citation of *why* is a misread that sets bad precedent. Residual risk to an unaware vendor consumer is stated in prose but never converted into a required consumer-facing deliverable. |
| independent-thinker | Disagree-and-Commit | The cost claim is unmeasured for these 5 hooks and inherits ADR-082's older, larger-surface numbers. The strongest real argument for retiring the two Serena guards specifically, an unreducible Copilot matcher (`^mcp__serena__.*$`) collapsing the entire `PreToolUse` union to fire on every tool call, is never stated, and it is exactly the argument that would make a narrower cut sufficient. Two of the five hooks landed the day of or day before the ADR-084 rule-6 bar that would have disqualified them. |
| high-level-advisor | Accept | The decision is sound and, priced correctly (keeping `require_subagent_model` costs the entire dispatcher plus ~20 tests for one hook, not one hook), better justified than the ADR states. Record quality is the gap: a re-accretion ratchet is missing, and `.github/hooks/require-subagent-model.json` is deleted without being named anywhere in the document. |
| critic | Disagree-and-Commit | No softening found in the Negative section (credited explicitly). But the registration inventory is incomplete, two blocking gates (`validate_hook_anchoring.py`, `scripts/ci/test_installed_plugin_hooks.py`) go red by design and are undisclosed, an accepted ADR (ADR-071) is invalidated and never cited, and the "not a one-way door" reversibility claim is proved by the wrong experiment (the empty-case regen, not a rebuild). |
| architect | Disagree-and-Commit | The ADR-084 carve-out citation is inverted from the source: it quotes the illustrative sentence and drops the operative prohibition three lines earlier, then concludes the opposite of what ADR-085 §8 did when it faced the identical situation. `test_adr_hook_claims.py` fails against this ADR's own prose at 8 specific line ranges (measured: 3 failed). ADR-068 and ADR-071 both contain now-false claims about live hook registrations and are absent from Related Decisions. |

**Consensus reached: 2 Accept, 4 Disagree-and-Commit, 0 Block.** Clears this
skill's stated bar (all Accept or D&C). No reviewer contested the owner's
authority to make the three ratified decisions; every substantive finding is
about the ADR's own citation accuracy, completeness, and undisclosed
consequences, not about the decision itself.

## P0 findings (must fix), deduplicated across reviewers

1. **ADR-084 carve-out citation is inverted** (architect, security). Rewrite
   Decision §4 to argue from the class test (these are cost/correctness
   controls, not the auth/injection/secret class the carve-out protects),
   not from "only two named hooks." Cite ADR-085 §8's handling of the same
   situation as the correct precedent.
2. **`.github/hooks/require-subagent-model.json` deleted, never named**
   (architect, critic, security, high-level-advisor, independent-thinker ,
   five of six). Add to "What currently exists," Decision §1, and the
   Impact table.
3. **`test_adr_hook_claims.py` fails against this ADR's own prose**
   (architect). Measured: 3 failed at lines 46-50, 94, 119, 128, 129, 137,
   144, 307-309 in ADR-097, and line 149 in ADR-085. Each needs a
   retirement-marker word (removed/replaced/retired/superseded) in its own
   sentence.
4. **`validate_hook_anchoring.py` is red right now** (critic). Measured:
   exit 2, "no hook events in src/copilot-cli/hooks/hooks.json" /
   "no command hooks in .claude/hooks/hooks.json". Wired into
   `pre_pr.py`, `lefthook.yml`, and
   `.github/workflows/validate-plugin-manifests.yml`. Needs a disposition
   (permit zero as valid, or retire), not a table row.
5. **`scripts/ci/test_installed_plugin_hooks.py` needs redesign, not a
   rename** (analyst, critic). `main()` returns 1 unconditionally when
   `_registered_events()` is empty, by design ("an empty run is a failure,
   never a skip"). That design assumption is exactly what this ADR reverses.
6. **ADR-071 (accepted) is invalidated and uncited** (critic, architect).
   Amended 2026-08-11 specifically for the require-subagent-model gate
   contract this ADR retires. ADR-068 also carries now-false claims about
   live registrations. Neither is in Related Decisions.
7. **"Not a one-way door" is proved by the wrong experiment** (critic). The
   empty-case `build_all.py` run proves deletion, not rebuild; the tests
   that would prove rebuild-from-manifest are exactly what this change
   deletes. Reword to "reversible in code (the generator survives), not in
   test corpus."
8. **#5013 regression pin deleted with no replacement invariant**
   (independent-thinker, high-level-advisor). Add a small ratchet test
   asserting zero `PreToolUse`/`PostToolUse`/`PermissionRequest`/
   `PostToolUseFailure` registrations with `surface: "plugin"`, so
   re-accretion requires a deliberate test deletion plus ADR review.
9. **`post_tool_call_memory.py` claimed retired, was not yet**
   (analyst, high-level-advisor, architect). Resolved during this debate:
   the file and its test are now actually deleted. Decision §3's LOC
   attribution was also backwards (module 98 lines, test 385 lines,
   architect finding 5), fix the sentence.

## P1 findings, deduplicated

- Impact table is incomplete against the repo: `.claude/hooks/PostToolUse/README.md`,
  `.agents/specs/hook-protocol.md:55`, `tests/validation/test_validation_entry_point_imports.py:38`,
  `tests/evals/rule-scenarios/tool-use-hook-bar.json`, `.serena/memories/hooks/require-subagent-model-gate.md`,
  `.serena/memories/decision-memory-hooks-registered-directly-not-grouped.md`, generated
  rule mirrors under `.github/instructions/` and `src/copilot-cli/instructions/`
  (critic, architect, security).
- "Nothing replaces this" for `require_subagent_model` overstates the loss:
  `scripts/validation/check_model_pins.py` already covers the definition-file
  arm at zero spawns; only the call-time arm goes unguarded (independent-thinker,
  architect, high-level-advisor, three of six).
- Cost claim leans entirely on ADR-082's older, larger-surface measurement;
  state the Windows/Defender figure as owner-reported and unmeasured, and lead
  instead with the measured mechanism (Copilot's `PreToolUse` matcher union
  collapsing to fire-on-every-call because of the two Serena guards' unreducible
  matcher) (independent-thinker, high-level-advisor, critic).
- Missing Reversibility/Rollback and Re-evaluation Triggers sections, both
  present in ADR-082 (independent-thinker, high-level-advisor).
- ADR-085 Decision 5's confirmation contract not fully discharged: need to
  name every dispatcher/adapter/generator component whose last consumer is
  gone and its disposition, not just `invoke_dispatch_claude.py` (architect).
- No debate-log path named in the ADR before this document existed, which
  blocks the ADR-073 `proposed -> accepted` transition (architect).
- Alternatives table's "keep the sub-agent guard only" row reads as
  ratification rather than analysis; missing a genuine platform/env-conditional
  alternative that targets the measured Windows-specific cause directly
  (critic).

## Resolution

P0 items 1-3 and 9 resolved directly in this session (ADR rewrite + actual
file deletion). P0 items 4-8 require code changes beyond ADR prose
(validator disposition, test redesign, a new ratchet test, ADR-068/071
amendments) and are hollmarked for the implementing orchestrator with this
debate log as its punch list. No Block vote was cast; the owner's ratified
decision proceeds per User Sovereignty regardless of remaining P1 items,
consistent with the ADR-084 rule-6 precedent this debate was briefed on.

## Implementation record: P0 items 4-8 discharged

Recorded here rather than in a second debate because these are the code
changes this debate demanded, not a new decision. No reviewer's position
changed and no new architectural question was opened; the ADR-097 verdict
above (2 Accept, 4 Disagree-and-Commit, 0 Block) still stands as the
authority for all of them.

| P0 | Finding | Discharged by |
|---|---|---|
| 4 | `validate_hook_anchoring.py` red (exit 2) | Empty manifest is now a valid anchored state exiting 0 with an examined count. Missing file, unparseable JSON, and a malformed `hooks` mapping stay fail-closed, with negative controls for both manifests. |
| 5 | `scripts/ci/test_installed_plugin_hooks.py` needs redesign | Asserts agreement between what the manifest registers and what the tree ships. Zero events with zero dispatchers passes; an orphaned dispatcher or an unreadable manifest fails. The non-empty path is unchanged and proven still armed by a test driving the real process against a synthetic registering tree. |
| 6 | ADR-071 invalidated, ADR-068 carries false claims | Both amended. ADR-071 gains a dated amendment retiring every tool-use contract while preserving Decision item 1 (plugin-root anchoring). ADR-068 gains a status note naming each false claim, stated explicitly because `test_adr_hook_claims.py` cannot catch them (its regex needs an `invoke_` prefix; ADR-068 uses bare gate names). |
| 7 | "Not a one-way door" proved by the wrong experiment | Already corrected in the ADR text to "reversible in code, not in test corpus"; the commit retiring the generated tree repeats that framing. |
| 8 | #5013 pin deleted with no replacement invariant | `tests/hooks/test_zero_tool_use_hooks.py` pins zero registrations across all four per-call events on all three manifests. Verified by mutation: re-adding a `PreToolUse` entry and a plugin-surface group fails exactly two tests; restoring returns 14/14. Carries its own vacuity guard and a negative control keeping session-scoped hooks legal. |

Two findings the implementation surfaced that the debate did not, recorded
because they change what a reader should expect from the tree:

1. **The ADR-084 rule 5 customer-value tests are deleted, on their own
   instruction.** `test_the_customer_value_check_examines_a_nonempty_surface`
   says verbatim: "If the vendored surface was deliberately emptied, delete
   both tests and say so in the ADR." Both are gone. Nothing now enforces
   rule 5's `Customer value:` docstring requirement, because there is no
   vendored hook to enforce it against. A future vendored hook must restore
   it along with the hardening bar.
2. **ADR-068's dependent-components table carried a live count.** The row for
   `.claude/hooks/hooks.json` read "Three vendored plugin registrations" and is
   pinned by `test_adr_068_dependent_components_table_matches_the_registration_count`.
   It now reads zero while keeping the historical chain, and the
   `.github/hooks/require-subagent-model.json` row is marked retired.
3. **The blast radius was wider than the Impact table.** The generated
   Copilot tree, `.github/hooks/require-subagent-model.json`, and roughly 20
   dispatcher tests across seven files were all reachable only through the
   registrations. Total: 45 tests failing before disposition, against the
   ~20 the ADR estimated.

## Post-merge PR review: nine follow-up defects, none reopening the decision

Copilot's automated review on PR #5172 (rjmurillo/ai-agents) found nine
defects after the debate closed: two matching malformed-manifest bugs
(a present-but-non-list event value read as "not registered" instead of
"malformed" in both `scripts/ci/vanilla_hook_guard.py` and
`scripts/ci/test_installed_plugin_hooks.py`), a coverage gap in the
re-accretion ratchet (`.github/hooks/*.json` and the generated Copilot
manifest were unscanned, so recreating the deleted
`require-subagent-model.json` would have passed silently), and six stale
prose claims across `agent-harness-reference/SKILL.md`,
`ai-agents-architecture-contract/SKILL.md`, `ai-agents-config-catalog/SKILL.md`,
`ADR-071`, and `hook-protocol.md` that this debate's own item 6 anticipated
in kind ("ADR-071 invalidated, ADR-068 carries false claims") but did not
enumerate exhaustively. Every finding was verified against the live source
before editing, per the same evidence standard this debate applied.

None of the nine touches the ADR-097 decision itself, the six-role verdict,
or any P0 item's disposition above. They are implementation-fidelity defects
in the discharge, the same class as the two coverage gaps the QA report's
own addendum already documented (the CI-only vanilla-guard and
case-sensitivity-path gates). Recorded here, not as a new debate round,
because no reviewer's position changes and no new architectural question is
opened; this entry exists so `check_adr_review_policy`'s debate-log gate has
current staged evidence for the ADR-071 correction in the same commit.
