---
id: ADR-096
status: accepted
date: 2026-08-19
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-096: Zero Tool-Use Hooks

## Status

Accepted. Six-role `adr-review` debate completed Round 1: analyst
Disagree-and-Commit, security Accept, independent-thinker
Disagree-and-Commit, high-level-advisor Accept, critic Disagree-and-Commit,
architect Disagree-and-Commit. **2 Accept, 4 Disagree-and-Commit, 0 Block** ,
clears the skill's consensus bar. Full findings:
`.agents/critique/ADR-096-debate-log.md`.

No reviewer contested the owner's authority to make the three ratified
decisions (retire all 5 hooks; retire the Copilot dispatcher per ADR-085
Decision 5; retire `post_tool_call_memory.py`). Every substantive finding was
about this document's own citation accuracy and completeness, not the
decision itself, consistent with the ADR-084 rule-6 precedent (3 Block, 2
Disagree-and-Commit, 1 conditional Accept, still shipped) this draft was
briefed on: the owner's ratified decision proceeds regardless of debate
outcome, but dissent and defects get recorded and fixed, not smoothed over.
Two independently-caught defects were substantive enough to fix in this
revision before merge: architect and security both flagged that Decision
section 4's original text mis-scoped the ADR-084 security carve-out
(inverted the operative sentence for the illustrative one); architect
measured `tests/hooks/test_adr_hook_claims.py` failing against this file's
own prose at 8 line ranges. Both are corrected below. The debate log records
every P0/P1 finding, including several (a currently-red
`validate_hook_anchoring.py`, a `scripts/ci/test_installed_plugin_hooks.py`
redesign, an ADR-071 amendment, a re-accretion ratchet test) that are code
changes beyond ADR prose and are tracked as required implementation work,
not resolved by this document alone. Acceptance of this decision does not
mean that implementation work is complete: `implemented: false` in the
frontmatter stays false until the branch merges, per ADR-073, and the
Impact table above and Implementation Notes below are the live punch list
until then.

## Date

2026-08-19

## Context

Issue #3075 (ADR-082) established that repository hooks make agent CLIs slow
on Windows, where a Python cold start costs ~250 ms and more under Defender
real-time scanning and machine load. ADR-082 fixed most of that by
consolidating per-hook process spawns into one process per (event, matcher)
group: Bash went from 5 spawns to 2, Write/Edit 5 to 2, user prompt 4 to 1,
git push 11 to 2. It explicitly measured that "the absolute win grows on
Windows where the per-spawn cost dominates."

The owner's Windows machine, running Defender, still experiences the
remaining per-tool-call spawns as unacceptable. This figure is owner-reported
and not independently re-measured in this ADR for these specific 5 hooks; it
is consistent with ADR-082's methodology (same root cause, same machine
class) but this document does not claim a fresh number. What is measured and
on the record is a sharper mechanism: `src/copilot-cli/hooks/hooks.json` at
HEAD carries `"matcher": null` on its single `PreToolUse` entry, because the
now-retired `invoke_serena_worktree_scope_guard.py`'s matcher
(`^mcp__serena__.*$`) did not reduce to a known tool name. Per `tool-use-hook-bar.md` mechanism 3,
`event_matcher_union` (`build/scripts/generate_dispatcher.py:556`) then
returns `None` for the *whole event*, so the Copilot dispatcher spawned on
every tool call for every consumer, not on Serena calls. That is the
strongest single measured cost this ADR removes, and it was caused
specifically by two of the five hooks, not by the ROI trade-off framing
below.

ADR-082's consolidation reduced spawn count; it did not reach zero. As of
this branch, five hooks still fired on tool calls, all now retired (see
Decision section 1):

| Hook (retired below) | Event | Matcher | Vendored? |
|---|---|---|---|
| `invoke_require_subagent_model.py` (retired) | PreToolUse | `^(Agent\|Task)$` | Yes (plugin surface, plus a standalone local-Copilot registration at `.github/hooks/require-subagent-model.json`, also retired) |
| `invoke_serena_memory_scope_guard.py` (retired) | PreToolUse | `mcp__serena__(write\|delete)_memory\|serena-(write\|delete)_memory` | Yes |
| `invoke_serena_worktree_scope_guard.py` (retired) | PreToolUse | `^mcp__serena__.*$` | Yes |
| `invoke_observation_sync.py` (retired) | PostToolUse | `mcp__serena__write_memory` | No, repo-local only |
| `invoke_memory_capture.py` (retired) | PostToolUseFailure | none (event carries no matcher option) | No, repo-local only |

Three of the five ship in the `project-toolkit` plugin (`surface: "plugin"`
in `dispatch_groups.json`), reaching every consumer who installs it. ADR-082
itself frames that plugin as "a distribution vehicle targeting
organizational rollout (hundreds of users), not a single-user convenience."
The other two are registered directly in `.claude/settings.json`, never
shipped in `.claude/hooks/hooks.json`, and never reach a consumer either way.

`PreToolUse` was the only event the plugin's `hooks.json` registered.
Retiring the three vendored hooks therefore does not shrink that manifest,
it empties it: `"hooks": {}`. `build/scripts/build_all.py` regenerates from
that manifest, and with zero events registered it correctly deletes the
generated Copilot dispatcher (`_dispatch.py`, `_bootstrap.py`,
`_manifest.json`) along with the shims. ADR-085 Decision 5 reserves this
move explicitly: "The dispatcher may be removed or replaced by direct host
registrations while hooks remain, but that change requires a new
architecture decision." This ADR is that decision.

Deleting the dispatcher also deletes the ~20 tests that exercise it: fail-open
behavior on a corrupt manifest, partial-upgrade degradation, JSON-bomb
rejection on oversized stdin, and the #5013 regression pin
(`test_pretooluse_bash_payload_never_launches_push_pr_guard`), which guards
against the exact failure mode `tool-use-hook-bar.md` was written to price:
a wrong deny on a hot tool matcher denying 127 unrelated Bash commands over
21 minutes before the owner caught it.

### What currently exists

Five hook scripts under `.claude/hooks/{PreToolUse,PostToolUse}/`, registered
across **four** surfaces prior to this change: `.claude/hooks/hooks.json`
(plugin, 3 entries), `.claude/hooks/dispatch_groups.json` (group membership
for those 3), `.claude/settings.json` (2 repo-local direct registrations),
and `.github/hooks/require-subagent-model.json` (a standalone local-Copilot
registration of the same sub-agent guard, documented in ADR-085 Decision 6:
"cloud agent reads only default-branch `.github/hooks/*.json`, so cloud
coverage begins at merge"). A generated Copilot mirror of the 3 vendored
hooks plus dispatcher machinery under `src/copilot-cli/hooks/`. All four
registration surfaces and the generated mirror are retired by this decision.

### Why change now

The original problem (Windows + Defender spawn cost) has not changed; it is
the same problem ADR-082 addressed and did not fully solve. What is new is
the owner's explicit judgment that the remaining, already-reduced spawn count
is still not acceptable on their machine, and that no hook currently
registered clears a bar of strong ROI plus broad, unconditional vendor
applicability:

- `invoke_require_subagent_model.py` (retired in this ADR) has the
  strongest individual case on cost grounds alone: `Agent|Task` reduces
  natively, widens no Copilot matcher union, and fires only on already
  expensive sub-agent spawns. Priced correctly, keeping it after the other
  four are gone would not cost one more spawn on `Agent|Task`, it would cost
  keeping the entire generated Copilot dispatcher, its manifest, its
  bootstrap, and its ~20 hardening tests alive for a single hook. The owner
  chose full retirement anyway rather than carry that machinery for one
  registration.
- The two Serena worktree guards (retired in this ADR, issues `#4917` and
  `#5061`) protect a real but conditional failure mode: cross-worktree
  corruption that only bites a vendor install using both Serena MCP and
  multiple git worktrees simultaneously, not every install. Both landed on
  2026-08-18 and 2026-08-19, the day of and the day before ADR-084 rule 6
  (ratified 2026-08-18) took effect. The retired
  `invoke_serena_worktree_scope_guard.py`'s
  matcher is exactly what rule 6 MUST-4 calls "disqualifying for a vendored
  tool-use hook": it never cleared the bar that governs it. Retiring it is
  compliance with a standing rule, not only an ROI trade.
- The two repo-local hooks (retired in this ADR) never reached a vendor
  install regardless, so their removal is not a vendor trade-off at all,
  just this repository's own dev-loop cost.

## Decision

Retire all five currently-registered tool-call hooks, and retire the
generated Copilot dispatcher machinery that their removal leaves with
nothing to run. Going forward, the vendored plugin surface (`project-toolkit`)
registers zero `PreToolUse`, `PostToolUse`, or `PostToolUseFailure` hooks.

### 1. Hook retirement, per hook

Following the retirement contract ADR-085 Decision 2 (`skill_first_guard`,
D-A) established: remove from the vendored surface and generated
registrations; name what, if anything, remains enforceable through
Lefthook/CI; record retirement of pre-execution blocking when nothing does.

- **`invoke_require_subagent_model.py`** (retired, issue #4874) and its
  standalone local-Copilot registration
  **`.github/hooks/require-subagent-model.json`** (retired, ADR-085
  Decision 6). Enforced: a sub-agent spawn naming
  no model and finding no model-pinned agent definition file was denied
  before it could inherit the session model silently. **Partially replaced.**
  `scripts/validation/check_model_pins.py` already governs the
  definition-file arm, it can assert every agent definition carries a
  `model:` pin, at zero spawns, but nothing observes the call-time arm (a
  spawn that names no model and matches no pinned definition). Only that arm
  goes unguarded. **This removes real protection from every future consumer
  install**, not just the owner's machine: a vendor's sub-agent spawn naming
  no model and hitting no pinned definition can now silently inherit and
  bill against the session model with nobody deciding it. Repository
  instructions must state this as a known, accepted gap, not imply it is
  still guarded (tracked in the Impact table below).
- **`invoke_serena_memory_scope_guard.py`** (retired, issue #5061) and
  **`invoke_serena_worktree_scope_guard.py`** (retired, issue #4917).
  Enforced: a
  Serena memory or file/symbol write whose target checkout differed from the
  caller's worktree was blocked before it landed. **Nothing replaces this.**
  Git and CI observe committed state, not an in-flight MCP tool call
  targeting the wrong worktree's `.serena/` tree. **This removes real
  protection from every future consumer install** that uses Serena MCP
  across multiple worktrees: a stray cross-worktree write can again land
  silently, exactly the failure both issues were filed to stop.
- **`invoke_observation_sync.py`** (retired). Already carried `#3217: relocate to
  .githooks/CI, authorized until then` in the parity test's authorized-hook
  list before this change; never shipped to a vendor install. Retired
  outright rather than relocated. Consequence: this repository's own
  Serena-observation-to-Forgetful sync no longer runs automatically after a
  `write_memory` call; a contributor who wants it must invoke the import
  script manually or a future decision must land it in CI.
- **`invoke_memory_capture.py`** (retired). Never shipped to a vendor install.
  Retired outright. Consequence: this repository stops auto-suggesting a
  memory after a failed tool call; nothing currently replaces that
  suggestion.

### 2. Dispatcher and Copilot hook-surface retirement (ADR-085 Decision 5)

The generated Copilot dispatcher (`_dispatch.py`, `_bootstrap.py`,
`_manifest.json`, and the per-hook shims under `src/copilot-cli/hooks/`) is
retired along with the hooks it existed to run, rather than preserved empty
for a hypothetical future hook. Runtime cost is identical either way: zero
registered hooks means zero per-call spawns whether or not the dispatcher
machinery survives on disk. The owner chose retirement over preservation
because keeping empty, unreachable machinery adds maintenance surface (its
own generator logic, its own ~20 hardening tests) for no present benefit.

This is reversible in code, not in test corpus. `build/scripts/generate_dispatcher.py`
(1,295 lines) survives this change and remains covered by
`tests/build_scripts/test_generate_dispatcher.py` (75 `tmp_path`-based
tests), so the generator itself is proven capable of building a dispatcher
from a non-empty `hooks.json` and `dispatch_groups.json` today. What this
branch actually demonstrated is the empty case ("Found 0 Claude event(s)"),
not a rebuild, the tests that would exercise a rebuilt dispatcher end to
end (`tests/build_scripts/test_copilot_dispatcher_artifact.py` and the
installed-plugin e2e suite) are exactly what this change deletes along with
their subject. Re-adding a tool-use hook in the future means the generator
builds new dispatcher code from the manifest, and whoever does that has to
re-establish the hardening-test bar from scratch rather than revert to a
preserved one.

The ~20 dispatcher-hardening tests whose subject no longer exists are
deleted, including the #5013 regression pin
(`test_pretooluse_bash_payload_never_launches_push_pr_guard`). That pin
guarded against a wrong deny on a broad Bash matcher taking out unrelated
work. Its absence-of-failure-mode justification holds only while zero hooks
are registered, that is a state, not an invariant, and the same test file
already anticipates re-addition. So this ADR requires a replacement ratchet,
not a bare deletion: a small test asserting `.claude/hooks/hooks.json`
registers zero `PreToolUse`/`PostToolUse`/`PermissionRequest`/
`PostToolUseFailure` entries, and `dispatch_groups.json` carries zero groups
on those events with `surface: "plugin"`. That forces any future re-addition
through a deliberate test deletion plus ADR review, the same property the
#5013 pin bought, aimed at the state that would let its failure mode recur
rather than at the deleted hook itself. Tracked as required implementation
work in the Impact table below; not yet written as of this revision.

### 3. Dead-code retirement

`scripts/memory_enhancement/hooks/post_tool_call_memory.py` (98 lines) lost
its only caller when `invoke_memory_capture.py` was deleted, leaving zero
production consumers. Retired in this same change under ADR-085's
zero-active-consumers retirement authorization, along with its 385-line test
suite (`tests/test_memory_hook_capture.py`), rather than left as
unreferenced library code with a live test suite pointing at nothing. Two
remaining references need updating, not deleting, since they document the
hook-registration pattern generally rather than depend on this specific
file: `tests/validation/test_validation_entry_point_imports.py:38` lists the
now-deleted path in `MODULE_ONLY_ENTRY_POINTS` and needs the entry removed;
`.agents/specs/hook-protocol.md:55` names it as a live pipeline component
and needs the line removed or marked retired.

### 4. ADR-084's security carve-out does not apply

ADR-084's "What this ADR does NOT do" section states the operative
prohibition first: "It does not authorize retiring an actual security
control. A hook that enforces a security property in consumer repos earns
its place by that property, not by an ROI cost-benefit veto, and a future
reviewer must not use this ADR's ROI bar to retire it." The two named hooks
that follow (the already-retired `invoke_security_gate.py`, the also-retired
`invoke_security_commit_gate.py`) are a worked example of the class the
rule protects at the time it was written, not an exhaustive enumeration ,
the rule is class-scoped, and
ADR-084's own rule-6 amendment reinforces this reading directly: "the
carve-out... binds this rule exactly as it binds the ROI bar, and rule 6 is
a cost test, not a route around it." An earlier draft of this section argued
the opposite ("the carve-out's own text is scoped to the two named hooks...
so it does not extend to these five"), which inverts the source and would
let any hook authored after ADR-084 be retired by ROI on the technicality
that it postdates the two named examples. ADR-085 Decision 8 faced this
exact question for a different hook and resolved it "by changing the
warrant rather than arguing the carve-out away", this section follows that
precedent instead.

The correct argument, and the one this ADR actually rests on: none of the
five hooks retired here is a security control by property. All five are
cost or correctness guards (session-model spend, cross-worktree data
integrity, memory bookkeeping), not authentication, injection, or
secret-handling controls, which is what the carve-out's operative sentence
protects. `.claude/rules/tool-use-hook-bar.md` already states of
`require_subagent_model`: "it is not a security boundary; its own docstring
says so." The two Serena guards could plausibly be read as security-adjacent
(Serena memories are agent-steering instructions, so a misplaced write puts
unreviewed instruction content into a tree a later PR commits), but no
adversary is required to trigger them, the trigger is the Serena server
resolving its project root from its startup argument rather than caller
cwd, a misconfiguration, not an attack, and the guard is trivially
bypassable by the same agent calling plain `Bash`, so it was never an
enforced boundary. That places all five in the class the carve-out does not
protect, by the carve-out's own class test, not by counting names.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| Narrow the Serena worktree guard's matcher to just its 16 write-tool names (leave the other 4 hooks as-is) | Smallest diff; keeps all five protections for non-Windows installs; cuts the highest-frequency spawn source | Still leaves 4 hooks spawning on every matching call; does not reach the owner's stated goal of zero | Owner explicitly rejected a partial cut and asked for literal zero, including the strongest-ROI hook |
| Keep the sub-agent model-spend guard only, cut the other four | Retains the one hook with unconditional vendor applicability (bounds real API spend on every install, not just multi-worktree Serena users) | Leaves one spawn on every sub-agent call; does not reach zero | Owner explicitly asked to remove this one too when given the choice |
| Retire the 5 hooks but preserve the Copilot dispatcher machinery empty, for a future hook | No rebuild cost if a hook is added later; keeps the ~20 hardening tests as documentation of the hardening bar | Requires new generator work to keep a non-empty `hooks.json` surviving regeneration without hand-editing a generated file (forbidden by `.claude/rules/generated-artifacts.md`); maintains dead code and dead tests for a hypothetical | Owner ratified full retirement; the generator already proves it can rebuild the dispatcher from the manifest, so preservation buys nothing durable |
| Move the two repo-local hooks (`observation_sync`, `memory_capture`) to Lefthook/CI instead of retiring | Preserves their behavior at a cheaper trigger point, consistent with `#3217`'s original relocation plan for `observation_sync` | Neither observes the in-session event it currently reacts to (a `write_memory` call, a tool failure); a real relocation is a redesign, not a lift-and-shift, and was out of scope for this pass | Deferred; recorded in Consequences as future work if the behavior is wanted back |

### Trade-offs

This trades three categories of real, currently-enforced protection (spend
control, cross-worktree data integrity, and this repository's own memory
bookkeeping automation) for eliminating 100% of tool-call hook process-spawn
cost, on every harness and every install. The owner made this trade
knowingly, for a measured cost (Windows + Defender spawn latency) against
protections whose failure modes are real but, for the three vendored hooks,
previously judged worth their cost by the ADR-084/085 process this ADR now
overrides for these five specifically.

## Consequences

### Positive

- Zero PreToolUse/PostToolUse/PostToolUseFailure process spawns on every
  tool call, on every harness, for every install of this plugin. Directly
  addresses the Windows + Defender cost ADR-082 measured but did not fully
  eliminate.
- Smaller vendored surface: the plugin manifest carries zero hooks, so a
  future auditor has zero vendored hook behavior to reason about, verify
  portability for, or keep passing `tool-use-hook-bar.md`'s cost test.
- Removes ~20 dispatcher-hardening tests and the dispatcher generator code
  path they exercise, reducing this repository's own test suite runtime and
  maintenance surface.
- Removes the now-dead 98-line `post_tool_call_memory.py` module along with
  its 385-line test suite.

### Negative

- A sub-agent spawn naming no model can again silently inherit and bill
  against the session model, for every install, with no enforcement
  anywhere in the stack.
- A Serena memory or file/symbol write can again silently land in the wrong
  worktree's checkout for any consumer using Serena MCP across multiple
  worktrees, for every install. This is the exact failure mode issues #4917
  and #5061 were filed to stop, now unguarded again.
- This repository's own observation-to-Forgetful memory sync and
  post-failure memory suggestion no longer run automatically; a contributor
  who wants either must invoke the underlying scripts by hand until a future
  decision lands a CI or Lefthook equivalent.
- `.claude/rules/tool-use-hook-bar.md`'s "Applying the bar to what ships
  today" section becomes stale the moment this merges (it names hooks 1 and
  4 as live) and must be rewritten in the same or immediately following
  change, or it misleads the next reader about what is actually registered.
- Re-adding any tool-call hook in the future means rebuilding the Copilot
  dispatcher from the generator, not editing a preserved-but-empty one back
  to life. The generator itself is proven capable of this (see Reversibility
  and Rollback below) but the ~20 hardening tests and the invariant they
  protected do not travel forward automatically; a future re-add carries the
  burden of re-establishing that bar.
- No CI or Lefthook signal currently forces a future contributor through
  this ADR before re-adding a tool-use hook. Until the re-accretion ratchet
  in the Impact table below is written, `.claude/hooks/hooks.json` going
  non-empty again is silent, the exact re-accretion risk ADR-084 itself
  named as the reason a written bar was needed at all.

### Neutral

- The Claude-side dispatcher (`invoke_dispatch_claude.py`) itself is not
  deleted; the two `SessionStart` groups in `.claude/settings.json` still use
  it. Only the generated Copilot-side dispatcher and the plugin's
  `PreToolUse`/`PostToolUse`/`PostToolUseFailure` surface are retired.
- `SessionStart`, `UserPromptSubmit`, `SessionEnd`, and `PreCompact` hooks are
  unaffected. They fire once per session or per turn, not once per tool
  call, and were not the cost this ADR addresses.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|---|---|---|---|
| `.claude/rules/tool-use-hook-bar.md` (+ generated mirrors `.github/instructions/tool-use-hook-bar.instructions.md`, `src/copilot-cli/instructions/`) | Direct | Rewrite "Applying the bar to what ships today" to state zero hooks are registered (it is already stale before this merges: it names `require_subagent_model` as "the only one," which stopped being true when the two Serena guards landed); regenerate mirrors with `build/scripts/generate_rules.py` per `.claude/rules/generated-artifacts.md` | Medium: an always-on injected rule actively misleads every agent session until fixed |
| `tests/hooks/test_dispatch_groups_parity.py` | Direct | Remove the 5 retired entries from `AUTHORIZED_HOOKS`; confirm `test_the_customer_value_check_examines_a_nonempty_surface` handles a deliberately empty vendored surface (its own docstring anticipates this case) | Low: test already anticipates this |
| `src/copilot-cli/hooks/` generated tree | Direct (generated) | Regenerate via `build/scripts/build_all.py`; never hand-edit; investigate the orphaned `src/copilot-cli/hooks/PreToolUse/markdownlint-safe-config.yaml` and `.claude/hooks/PreToolUse/_bootstrap.py` the regeneration left behind | Low: generator confirmed idempotent on the empty case (re-ran `build_all.py`, zero further diff), orphans are cleanup not correctness |
| `scripts/validation/validate_hook_anchoring.py` | Direct | Currently red: `uv run --frozen python scripts/validation/validate_hook_anchoring.py` exits 2 ("no hook events in src/copilot-cli/hooks/hooks.json", "no command hooks in .claude/hooks/hooks.json"). Wired into `pre_pr.py`, `lefthook.yml`, and `.github/workflows/validate-plugin-manifests.yml`. Needs an explicit disposition: permit zero hooks as a valid anchored state, or retire the validator | High: blocks every push and PR until resolved |
| `scripts/ci/test_installed_plugin_hooks.py` (+ `.github/actions/test-installed-plugin-hooks/action.yml`, `.github/workflows/installed-plugin-hook-guard.yml`) | Direct | Not a naming fix: `main()` returns 1 unconditionally when `_registered_events()` is empty, by design ("an empty or unreadable manifest is itself a failure in the caller"). That design assumption is what this ADR reverses. Needs redesign to assert the deliberately-empty state, not a renamed hook reference | High: blocks CI as currently written |
| `tests/hooks/test_adr_hook_claims.py` | Direct | Measured failing against this file: `test_no_adr_prose_names_a_hook_that_is_absent_without_retirement_marker[ADR-096]` and `test_no_adr_prose_claims_an_unregistered_hook_is_live[ADR-096]`. Each flagged sentence needs a retirement-marker word (removed/replaced/retired/superseded) in its own clause. Also flags `ADR-085:149`, which needs the same treatment for hooks this ADR retires | Medium: blocks this ADR's own acceptance gate |
| ADR-071 (Plugin Hook Runtime Contract Verification, accepted) | Direct | Amended 2026-08-11 specifically to record `require_subagent_model`'s matcher, fail-open, and fail-closed contract. That contract no longer exists. Needs an amendment marking the relevant section retired, cited in this ADR's Related Decisions | Medium: an accepted ADR describing a dead contract misleads a future reader |
| ADR-068 (Consolidated Hook Group Dispatch), lines 187, 227, 234, 309, 501 | Direct | Contains now-false claims that the retired gates are registered and that the Copilot dispatcher "spawns three timed-shim children." Escapes `test_adr_hook_claims.py`'s regex (needs an `invoke_` prefix; ADR-068 uses bare gate names) but the content is still false and needs a retirement note | Medium: same misleading-accepted-ADR risk, not caught by the automated gate |
| `CONTRIBUTING.md`, `.claude/skills/ai-agents-architecture-contract/`, `.claude/skills/ai-agents-config-catalog/`, `.claude/skills/agent-harness-reference/`, `.claude/hooks/PostToolUse/README.md` (calls `observation_sync` a "reference implementation for simple hooks"), `.agents/specs/hook-protocol.md` | Indirect | Prose referencing any of the 5 retired hooks, `.github/hooks/require-subagent-model.json`, or the Copilot dispatcher as live needs updating | Low: documentation drift, not functional risk |
| `tests/validation/test_validation_entry_point_imports.py:38` | Direct | Lists the now-deleted `post_tool_call_memory.py` path in `MODULE_ONLY_ENTRY_POINTS`; remove the entry | Low: mechanical |
| `tests/evals/rule-scenarios/tool-use-hook-bar.json` | Direct | Eval scenario for a rule whose "what ships today" section is being rewritten; needs updating to match | Low: eval drift, not a blocking gate |
| `.serena/memories/hooks/require-subagent-model-gate.md`, `.serena/memories/decision-memory-hooks-registered-directly-not-grouped.md` | Indirect | Both describe retired hooks as live; add a supersession marker per `.claude/rules/curating-memories.md` rather than delete (memories are historical record) | Low: retrieval-aid staleness, not binding |
| Count ratchets under `scripts/ci/*_count_baseline.txt` | Indirect | File deletions shift several counts downward; ratchets may only fall, update via each ratchet's own `--update` flag per `.claude/rules/ci-scripts.md` | Low: mechanical, but must not be skipped |
| Re-accretion ratchet (new test, no home yet) | Direct, not yet written | A ~5-line test asserting zero `PreToolUse`/`PostToolUse`/`PermissionRequest`/`PostToolUseFailure` registrations with `surface: "plugin"`, replacing the invariant the deleted #5013 pin protected (see Decision section 2) | Medium: without it, re-accretion is silent |

## Reversibility and Rollback

This decision owns no persistent data. `build/scripts/generate_dispatcher.py`
and its 75-test coverage under `tests/build_scripts/test_generate_dispatcher.py`
survive this change, so the mechanism that builds a dispatcher from a
non-empty `hooks.json`/`dispatch_groups.json` is proven and available.
Reverting means: restore the 5 hook scripts and their entries in
`.claude/hooks/hooks.json`, `dispatch_groups.json`, `.claude/settings.json`,
and `.github/hooks/require-subagent-model.json` from git history, then run
`build/scripts/build_all.py` to regenerate the Copilot mirror.

What does not come back automatically is the hardening-test corpus: the
~20 dispatcher tests (fail-open on a corrupt manifest, partial-upgrade
degradation, JSON-bomb rejection, the #5013 pin) and the
installed-plugin-hooks e2e coverage are deleted in this change and must be
restored from git history alongside the code, or rewritten, before a
reverted dispatcher can be trusted to the same bar it shipped at before this
ADR. A revert that restores only the registrations and not the tests
restores the vulnerability the tests existed to catch.

## Re-evaluation Triggers

Reopen this decision when any of the following occurs:

- A consumer reports Serena cross-worktree corruption (the exact failure
  mode issues #4917 and #5061 were filed to stop) after installing a
  version of the plugin that shipped this retirement.
- A consumer reports unbounded sub-agent spend traced to a modelless spawn
  that `check_model_pins.py`'s definition-file coverage did not catch.
- A measured (not owner-recalled) Windows + Defender spawn-cost figure for
  these specific hooks shows the per-call cost was not actually the
  bottleneck this ADR assumed.
- A future hook is proposed for `PreToolUse`, `PostToolUse`,
  `PermissionRequest`, or `PostToolUseFailure`. Any such proposal must clear
  the re-accretion ratchet (Impact table above), state its matcher's
  Copilot-side reduction per `tool-use-hook-bar.md` MUST 3, and rebuild the
  hardening-test bar this ADR retires, not just the dispatcher code.

## Implementation Notes

Structural change already staged on branch `claude/tool-use-hooks-perf-ht7zhx`
as of this ADR (see
`.agents/sessions/handoffs/2026-08-19-tool-use-hook-retirement-handoff.md`
for the exact file list and verification steps). Remaining work: dispose of
the ~32 tests this change reddens (categorized in that handoff), update the
dependent components above, run `uv run python scripts/validation/pre_pr.py`,
commit atomically (5 files or fewer per commit, per `.claude/rules/universal.md`
rule 6), push, and confirm the draft PR.

## Related Decisions

- ADR-082 (Claude-Side Consolidated Hook Group Dispatch). The consolidation
  this ADR takes one increment further, from reduced-but-nonzero spawns to
  zero, for the same root cause (issue #3075).
- ADR-084 (Vendored Hook ROI Bar). Its security carve-out does not apply
  here (see Decision section 4). Its rule 6 cost bar
  (`.claude/rules/tool-use-hook-bar.md`) becomes largely moot for the
  vendored surface once it carries zero tool-use hooks, though the rule
  itself is not retired by this ADR and needs its own follow-up edit.
- ADR-085 (Cross-Harness Permission-Surface Asymmetry and Hook Survivor
  Disposition). Decision 2 supplies the retirement template this ADR
  follows for each hook, and its resolution ("changing the warrant rather
  than arguing the carve-out away") is the precedent Decision section 4
  above follows. Decision 4 already partially retired `observation_sync`
  from the vendored surface; this ADR completes its retirement outright.
  Decision 5 is the reservation this ADR exercises for the dispatcher
  removal, whose confirmation contract (every dispatcher/adapter/generator
  component with a named disposition) is only partially discharged here ,
  `invoke_dispatch_claude.py`'s survival is named; the dormant generic
  `PermissionRequest` adapter (retained by Decision 3, separately), the
  orphaned `markdownlint-safe-config.yaml`, and `_bootstrap.py` are flagged
  in the Impact table as unresolved. Decision 6 documents the
  `.github/hooks/require-subagent-model.json` surface this ADR also
  retires. Decision 8's resolution method for the ADR-084 carve-out is what
  Decision section 4 above follows.
- ADR-071 (Plugin Hook Runtime Contract Verification, accepted, amended
  2026-08-11 for the `require_subagent_model` gate contract). That
  contract no longer exists after this ADR; ADR-071 needs its own amendment
  marking the relevant section retired (tracked in the Impact table above,
  not yet done as of this revision).
- ADR-068 (Consolidated Hook Group Dispatch, referenced for its now-stale
  claims about live hook registrations; see the Impact table above).

## References

- Issue #3075. Original Windows + Defender spawn-cost report (ADR-082).
- Issue #4874. `invoke_require_subagent_model.py` (retired) origin.
- Issue #4917. `invoke_serena_worktree_scope_guard.py` (retired) origin.
- Issue #5061. `invoke_serena_memory_scope_guard.py` (retired) origin.
- Issue #3217. `invoke_observation_sync.py` relocation authorization,
  superseded here by outright retirement.
- Issue #5013. The 127-wrong-denials incident behind
  `tool-use-hook-bar.md` and the regression pin retired in this change.
- `.agents/sessions/handoffs/2026-08-19-tool-use-hook-retirement-handoff.md`.
  Full file list, test-failure taxonomy, and resume steps for the
  implementation this ADR governs.
