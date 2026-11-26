---
id: ADR-084
status: accepted
date: 2026-11-25
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-084: Vendored-Hook ROI Bar

## Status

Accepted (repo-owner @rjmurillo, 2026-07-18). Requested by issue #3215 as part
of the issue #3197 vendored-hook ROI review. adr-review consensus recorded
(6/6 Accept, see the debate log). Blocks #3197: the hook elimination
that #3197 authorizes needs a written bar so the vendored surface does not
re-accrete.

Amended 2026-08-18 (repo-owner @rjmurillo) to add rule 6, a bar on the per-call
events. Rule 3 is unchanged. The amendment's adr-review reached round 1 with 3
Block, 2 Disagree-and-Commit, and 1 conditional Accept; the record and the
resolution of every blocking finding are at
`.project-toolkit/critique/ADR-084-rule-6-tool-use-bar-debate-log.md`. See the Amendment
Record below. The
security carve-out under "What this ADR does NOT do" is unchanged and still
binds: this amendment tightens an ROI preference, and neither it nor the
original bar authorizes retiring a genuine security control.

Amendment proposed 2026-10-31 (requested by repo-owner @rjmurillo for
REQ-048). It adds rule 2a, which separates retro enforcement from an advisory
nudge, narrows rule 2's word "retros" to "retro enforcement", and corrects
rule 5's enforcement record. Its adr-review closed by consensus, and the owner
accepted it under owner decision D26 (2026-11-04, REQ-048 TASK-006), so rule 2a, the rule 2
wording change, and the rule 5 duties now bind; frontmatter `status: accepted`
covers them too.
The debate record is
`.project-toolkit/critique/ADR-084-debate-log-2.md`. Rules 1, 3, 4, and 6 and
the security carve-out are unchanged.

Amendment proposed 2026-11-25 (requested by repo-owner @rjmurillo for
REQ-050, owner decision D10). It adds rule 2b, which covers the two `receipts`
Stop hook registrations and names the rule 2a conditions each one departs
from. Rule 2b does not bind until the owner accepts it. The debate record is
`.project-toolkit/critique/ADR-084-debate-log-3.md`. Rules 1, 2, 2a, 3, 4, 5,
and 6 and the security carve-out are unchanged.

## Date

2026-07-20; amended 2026-08-18; amendment proposed 2026-10-31, accepted 2026-11-04; rule 2b proposed 2026-11-25

## Context

The project ships two plugin surfaces to consumers: the project-toolkit plugin
(`.claude/` and its generated `src/copilot-cli/` mirror) and the claude-agents
plugin (`src/claude/`). A consumer installs the plugin into their own repository.
The plugin's hooks then run in that consumer's repo, on that consumer's tool
calls, against that consumer's git origin and paths.

The #3197 ROI review measured the vendored hook surface against that reality and
found it is almost all cost:

- 12 of 13 push and memory hooks are dead code in any consumer repo. They gate
  on the git origin being `ai-agents` (`skip_if_consumer_repo` in
  `.claude/lib/hook_utilities/guards.py`), or on repo-root paths such as
  `build/scripts/` that the plugin never vendors. In a consumer repo they load,
  spawn, check the guard, and no-op. The per-hook enumeration and the single
  survivor are recorded in the #3197 ROI review; this ADR sets the bar, it does
  not restate that census.
- The LSP-first enforcement family (retired by the ADR-062 amendment filed under
  #3214) added one true positive in 6.5 weeks against a running tally of false
  positives, while paying a per-Read process-spawn tax on the hottest tool.
- Hooks that do carry weight ship no statement of what consumer value they
  deliver, so a plugin reader cannot tell a customer-facing hook from an
  internal-protocol enforcer that leaked into the vendored tree.

The failure mode is structural, not incidental. Without a written bar, every
future "add a hook to enforce X" request re-accretes internal dev-protocol
machinery into the surface a customer pays to load. The surface trends back
toward its current state the moment the #3197 cleanup lands.

The distinction the bar must hold is between two audiences that the current
surface conflates:

- The consumer, who installs the plugin to get value in their own repo.
- This repository's own contributors, whose dev protocol (session logs, ADR
  debate, retros, install parity, plugin version bumps, generator drift, PR
  description shape) is an internal concern that a consumer neither sees nor
  benefits from.

Internal enforcement already has a home that costs the consumer nothing:
`lefthook.yml` and CI, which run only in this repository and never ship.

## Decision

A hook may ship in a vendored plugin surface only if it delivers value in a
consumer's own repository. Internal dev-protocol enforcement stays in
Lefthook and CI. Prefer host-native declarations over process-spawning
hooks. Concretely, the bar is six rules:

1. **Consumer-repo value is required.** A vendored hook MUST state the value it
   delivers in a consumer's own repo. "Enforces our protocol" is disqualifying:
   a consumer does not run this project's protocol.
2. **Internal enforcement is not vendored.** Session logs, ADR debate, retro
   enforcement, install parity, plugin version bumps, generator drift, and
   PR-description shape are internal concerns. (Accepted 2026-11-04:
   "retro enforcement" replaces the earlier word "retros".)
   They live in Lefthook and CI only, never in a vendored surface.

   **2a. One advisory nudge is not enforcement (proposed 2026-10-31,
   accepted 2026-11-04).** Rule 2 bars enforcing this repository's protocol. It does
   not bar telling a consumer, about their own session, that the shipped
   `retrospective` skill may help. Rule 2a covers one hook only: the REQ-048
   friction nudge, an extension of `invoke_reflect_nudge.py`. Any other
   advisory hook needs its own amendment. The hook may ship vendored only when
   all seven conditions hold:

   a. It only advises. It never emits a `decision` field, and it exits 0 on
      every path.
   b. It writes nothing inside any repository it can detect. Its own state
      lives in per-user storage outside every repository it can detect, and
      it refuses a state root when it or any ancestor directory holds a
      `.git` entry. Bare-repository setups that leave no `.git` entry are an
      accepted gap (REQ-048 AC-24).
   c. Its output is fixed text plus counts. It never echoes transcript,
      tool, or repository content.
   d. It runs on `Stop` only. The per-call events in rule 6 are out of reach,
      and so is every event whose output enters model context, such as
      `UserPromptSubmit` and `SessionStart`.
   e. It opens only its stdin payload, the file at that payload's
      `transcript_path`, and its own state, and it reads a closed list of
      environment variables. The condition b refusal may also `stat`
      ancestor directories. REQ-048 AC-22 names the variable list and the
      launcher's own reads.
   f. Its output goes to a user-visible channel only, never into model
      context. Its text addresses the user, not the agent, and gives the
      agent no instruction.
   g. It has a documented off switch and a bounded firing rate. One
      environment variable turns the whole hook off, and the hook reads it
      before it opens the transcript. The `Customer value:` line names the
      variable and its off values. The docstring states the firing bound.

   Conditions a, e, and f bind the whole plugin path, launcher included.
   Condition e does not count the plugin's or Python's own files. The
   launcher may read two consumer-repo plugin manifests for one name field
   and echoes nothing from them (REQ-048 AC-28). REQ-048 holds each
   condition's testable form; its condition-to-AC map is the TASK-006
   review checklist.

   Retro enforcement stays internal. That means blocking a turn until a retro
   exists, writing skeleton files, demanding a fill, or instructing the agent
   to run one. PR #3372 (issue #3349, `b862e14e9`, 2026-07-26) deleted exactly
   that hook. Rule 2a does not reopen it. A hook that fails any of a to g is
   enforcement under rule 2.

   Sunset: rule 2a lapses when REQ-048's kill criterion removes the friction
   branch, when the owner drops the friction branch under REQ-048 AC-19, or
   when the hook leaves the vendored surface. The removing PR
   records the lapse in this ADR. The removing PR also removes the plugin
   dispatch group per Rollback, unless a new amendment covers what remains.

   The hook MUST stay out of the Copilot tree. Its dispatch group sets
   `copilotExclude: true` and meets ADR-085 Decision 7's generic field
   governance. REQ-048 TASK-006 maps each of its nine items to this use. The
   field is used here for an output-contract gap, not a security judgment,
   and this amendment owns that reason. A generator test MUST show that
   `src/copilot-cli/hooks/hooks.json` carries no entry for it. The reason is in
   the Amendment Record: Copilot documents neither an advisory field nor
   `transcript_path`.

   The hook also records a fresh runtime contract in ADR-071. ADR-071's
   recorded contracts describe deleted code, and `tool-use-hook-bar.md` "What
   a first re-add owes" names that duty.

   **2b. The receipts Stop hook (proposed 2026-11-25, not yet binding).**
   Rule 2b covers one capability only: the REQ-050 `receipts` hook. It checks
   claims in the agent's final reply against that session's own tool results.
   It reads no rule of this repository and demands no artifact, so it is not
   protocol enforcement under rule 2. It has two registrations. Each meets
   every rule 2a condition except the ones named below. Rule 2a's sentence "A
   hook that fails any of a to g is enforcement under rule 2" does not reach
   these named departures. Any other departure is enforcement. Any further
   hook still needs its own amendment.

   Claude Code registration. It is advisory and meets conditions a, b, d, e,
   f, and g. It departs from condition c in two ways. Its message repeats at
   most 80 characters of claim text per stamp, taken from the agent's own
   final reply. Each receipt also names the tool, and that name must match
   `^[A-Za-z0-9_.-]{1,48}$` or it prints as `tool`. It echoes no tool output
   and reads no repository file. Its dispatch group sets
   `copilotExclude: true`, because the Claude hook's advisory output has no
   documented Copilot channel. ADR-128 owns that exclusion.

   Copilot CLI registration. It meets conditions b, d, and e, reading
   `transcriptPath` where condition e says `transcript_path`. It meets
   condition g's off switch. Its firing bound under g is one block per claim
   per session; rule 2b sets no cap on blocks per session. It departs from
   conditions a, c, and f: it emits `{"decision": "block", "reason": ...}`,
   the reason enters model context, and the reason names a tool from the
   transcript. The departure holds only inside these bounds, which ADR-128
   decides:

   - It blocks only when a tool result contradicts a claim in the final
     reply.
   - It blocks at most once per claim per session. Its own digest-only marker
     enforces that, in per-user storage under condition b. When the marker
     cannot be read or written, the hook does not block.
   - The reason is a fixed template plus the claim kind, the call index, and
     a tool name that matches `^[A-Za-z0-9_.-]{1,48}$`. It never echoes
     reply or tool-output text.
   - It registers only after ADR-128's measured gate passes. Until then a
     generator test MUST show that `src/copilot-cli/hooks/hooks.json` carries
     no entry for it.

   The PR that adds either registration MUST update the pinned tests it
   trips in `tests/hooks/test_plugin_stop_registration.py` in the same
   change, and rule 5's customer-value tests MUST cover the new hook.

   Rule 2a is unchanged. The reflect nudge stays out of the Copilot tree.
   Rule 2b does not reopen the hook PR #3372 deleted: that hook blocked until
   an artifact existed, and receipts blocks once on a contradicted statement.

   Sunset: rule 2b lapses when ADR-128 is rejected or superseded, or when
   both registrations leave the vendored surface. If ADR-128's gate is unmet
   on 2027-02-25, the Copilot half is reviewed again with ADR-128. The
   removing PR records the lapse in this ADR.
3. **Prefer zero-spawn host-native surfaces.** When the host provides a
   declarative surface that achieves the same effect without spawning a process,
   use it. `permissions.allow` and `permissions.deny` in settings and static
   rules loaded as context both cost zero spawns per tool call; a PreToolUse
   hook that spawns an interpreter on every matching call does not. When the host
   surface cannot express the required logic (runtime inspection of tool
   arguments or file content, or conditional branching a static declaration
   cannot encode), a spawning hook is the right tool and this rule does not
   apply. The preference is for the declarative surface where it achieves the
   same effect, not a ban on hooks that do work no declaration can. For the
   per-call events rule 6 names, clearing this rule is necessary but not
   sufficient; rule 6 adds a further bar.
4. **Self-neutering hooks are banned from the vendored surface.** A hook that
   no-ops in consumer repos because it gates on the git origin
   (`skip_if_consumer_repo`) or on repo-root paths the plugin does not vendor
   delivers no consumer value by construction. It does not belong in the
   vendored surface. If the logic is genuinely internal, it moves to Lefthook
   or CI per rule 2; it is not shipped dead.
5. **Every vendored hook carries a one-line customer-value justification, and a
   test asserts its presence.** The justification lives in the hook's module
   docstring as a single line a plugin reader can find, prefixed
   `Customer value:` so the check is a presence grep, not a semantic judge.

   **Enforced since 2026-08-19 by
   `tests/hooks/test_dispatch_groups_parity.py::test_every_vendored_hook_states_its_customer_value`,
   not by a standalone CI job.** The original text promised a new CI check and
   none was built; measured 29 days after acceptance, `Customer value:` appeared
   in no script under `scripts/`, `build/`, or `.github/workflows/`. The
   instrument changed on evidence: the vendored surface is one hook, and a
   dedicated workflow, script, and baseline guarding one already-compliant file
   is more machinery than the risk carries. The parity suite already resolves
   plugin-surface groups and already runs in the `python-tests` gate, so the
   enforcement costs no new job.

   **Scope is the registration, not the directory.** A hook is vendored when its
   dispatch group carries `surface: "plugin"`. `.claude/hooks/` also holds this
   repository's own dogfood hooks, which this rule never covered; scoping by
   directory would demand a consumer-value line from hooks that have no
   consumer. Measured at the time of writing: 8 hook scripts under
   `.claude/hooks/`, of which 1 is vendored, and that one complies.

   A companion test fails when the plugin surface is empty, because a zero-file
   corpus would let the presence check pass while examining nothing.

   **Correction (2026-10-31): nothing enforces rule 5 today.** The two tests
   named above, `test_every_vendored_hook_states_its_customer_value` and
   `test_the_customer_value_check_examines_a_nonempty_surface`, were deleted in
   `f79e70c01` (2026-08-19, #5172, ADR-097) when the vendored surface emptied.
   The presence test was added in `2c85d2547` (2026-08-18 18:38 -0700) and
   deleted in `f79e70c01` (2026-08-19 16:52 -0700), so it enforced rule 5 for
   about 22 hours. In -0700 local time, the "Enforced since 2026-08-19" date
   above is one day late. In UTC (`2c85d2547` is 2026-08-19T01:38Z) it is
   correct.
   Do not count the test as a working control.
   Measured at `9254b9945` (2026-10-31): the plugin root hooks.json registers
   zero hooks, and no dispatch group carries `surface: "plugin"`. The
   paragraphs above record what held before that date. Accepted with rule
   2a on 2026-11-04: each PR that makes the vendored surface non-empty
   MUST restore both tests. That PR MUST
   NOT merge until they pass. The restored tests now bind this MUST; the
   Amendment Record names them.

   What the test does NOT do is judge whether the stated value is real. That
   stays with human review at ADR and PR time, as it always did.
6. **The per-call events clear an additional bar (added 2026-08-18).** This
   rule governs `PreToolUse`, `PostToolUse`, `PermissionRequest`, AND
   `PostToolUseFailure`. For all four, inability to express the check
   declaratively is where the analysis starts, not where it ends. Their cost
   scales with how hard the agent is working, which the session-boundary events
   do not.

   **All four, not just the tool-use pair, and the scope is load-bearing.**
   Naming fewer leaves the bar evadable by event choice: a guard refused on
   `PostToolUse` could re-register on `PostToolUseFailure`, pay the same spawn,
   and match every tool. `PostToolUseFailure` deserves the most scrutiny rather
   than the least, because `build/scripts/generate_dispatcher.py:517` omits it
   from `_MATCHER_EVENTS`, so it cannot be tool-scoped at all, and the live
   registration in `.claude/settings.json` carries no matcher and fires on every
   failed tool call. `PermissionRequest` shares the per-call cost and the
   tool-name-only matcher with the tool-use pair, which is why the generator
   groups those three together.

   A registration on any of the four requires BOTH:

   a. An outcome that far outweighs the per-call spawn cost: a costly mistake,
      an irrecoverable loss, or a security property enforced by denial at agent
      time. A shorter feedback loop is not on its own a justification.

   b. No other placement that would work CORRECTLY. A Git hook, a lefthook job,
      a CI check, and a server-side gate must each be ruled out on the record.
      "Correctly" is load-bearing: a check whose subject never reaches a commit
      (an executed command, a sub-agent spawn, a tool argument), or whose value
      is prevention where the later surface only detects, is not covered by
      those surfaces merely because they exist.

   **Rule 1 constrains (b), and this limit is load-bearing.** For a VENDORED
   hook whose value is consumer-facing, none of those four placements is a valid
   alternative, because a consumer installs this repository's Lefthook, CI, and
   server-side gates not at all. Re-homing such a check there does not relocate
   consumer coverage, it removes it. Deleting a consumer-facing hook on that
   reasoning drops consumer coverage to zero and MUST be recorded as such, per
   ADR-085 Decision 10. A placement that catches the outcome rather than the
   execution, or that does not travel with the plugin, does not count as ruling
   out a security control; the carve-out under "What this ADR does NOT do"
   binds this rule exactly as it binds the ROI bar, and rule 6 is a cost test,
   not a route around it.

   The worked cost model lives in the former `tool-use-hook-bar` rule (now at `.claude/skills/skillforge/references/rule-tool-use-hook-bar.md`). Since 2026-11-24 that text loads only through the `skillforge` skill, not on hook-path edits. The
   per-event matcher union that makes the cost larger than a Claude-side matcher
   suggests is ADR-068's consolidation decision, not a host property; see
   ADR-068 "Decision" and its re-evaluation trigger on union widening.

## Consequences

### Positive

- The vendored surface trends toward customer value, not internal ceremony. A
  plugin reader can tell what each shipped hook does for them.
- (Historical, 2026-08-18.) Rule 5 is mechanically enforced when a hook is added, by a test in
  the parity suite rather than the standalone CI check first proposed. That test
  is the ratchet against re-accretion. It went 29 days unbuilt while the ADR
  described it as planned, which is the reason the rule now names the file that
  enforces it instead of an intention. Correction (2026-10-31): that test was
  deleted in `f79e70c01`, so nothing enforces rule 5 today. See the rule 5
  correction.
- Rules 3 and 4 push cost off the consumer's hot path: zero-spawn host-native
  surfaces where possible, and no dead hooks spawning per call to no-op.
- Internal enforcement does not weaken. It moves to Lefthook and CI. CI gates
  this repo's contributions unconditionally; Lefthook installs and runs the
  local Git hooks.

### Negative and risks

- Rule 5's enforcement is a presence check, not a semantic judge of whether the
  stated value is real; human review at ADR and PR time judges the value. Its
  maintenance cost is near zero because it reuses the parity suite's existing
  plugin-surface resolution and adds no job, script, or baseline. The residual
  risk it cannot cover is a hook that carries a truthful-looking line whose
  claimed consumer value is fictional.
- Moving internal enforcement out of the vendored surface means a contributor
  who relied on a vendored hook firing locally now relies on Lefthook and CI.
  The mitigation is CI, which gates every PR unconditionally; Lefthook's native
  install command closes the local-commit gap, so the enforcement point moves
  but does not disappear.
- Rules 1, 2, 3, 4, and 6 are policy, not code. They bind future additions only
  if reviewers apply them. Rule 5 is the single mechanically checkable clause. It
  was enforced for about 22 hours in 2026-08 and is not enforced today (see the
  rule 5 correction); the rest are not, and this ADR should not be read as claiming
  otherwise.

### What this ADR does NOT do

- It does not delete any hook. The elimination is the #3197 implementation work
  (#3216, #3217, #3218) that this bar governs. This ADR sets the standard those
  issues apply.
- It does not authorize retiring an actual security control. A hook that
  enforces a security property in consumer repos earns its place by that
  property, not by an ROI cost-benefit veto, and a future reviewer must not use
  this ADR's ROI bar to retire it. Of the two security gates current when this
  ADR was written, only the previously registered
  `invoke_security_gate.py` was consumer-effective: it was not
  `skip_if_consumer_repo` gated and ran on consumer Write/Edit.
  The historical `invoke_security_commit_gate.py` was `skip_if_consumer_repo` gated, so it did
  not run in consumer repos; whether it should was the #3197/#3219
  security-rebuild question, not this ROI bar. Genuine security controls remain
  subject to the bar's mechanical rules (rule 5's docstring requirement applies
  to them like any vendored hook).
- It does not change any security property. The security posture of the current
  hooks is handled by the #3197 decision to rebuild a portable auth-edit hook on
  real consumer demand (#3219); this ADR governs ROI, not security controls.
- It does not retire the LSP enforcement family. That is the ADR-062 amendment
  under #3214. This ADR is the general bar; the ADR-062 amendment is the first
  application of it.

## Amendment Record

The 2026-08-18 entry (rule 3, tool-use events) and the 2026-10-31 entry (rule 2a
and the rule 5 correction) moved verbatim on 2026-11-25 to
`.project-toolkit/critique/ADR-084-amendment-record-archive.md`. The move keeps
this record under the 500-line cap. No rule text changed.

**2026-11-25, rule 2b (proposed, owner decision D10).** REQ-050 adds
`receipts`, a Stop hook that checks claims in the agent's final reply against
tool results. Rule 2a covers one hook and says any other advisory hook needs
its own amendment. It also calls a hook that fails any of conditions a to g
enforcement. The Claude receipts hook echoes up to 80 characters of claim
text and a tool name, which condition c bars. The Copilot receipts hook emits
a block decision whose reason enters model context and names a tool, which
conditions a, c, and f bar. The first
ADR-128 review round blocked on that conflict (3 Block, 3
Disagree-and-Commit). The owner chose to amend this record over a silent
exception in ADR-128.

Why a block can sit outside rule 2. Rule 2 bars enforcing this repository's
protocol on a consumer. The deleted hook wrote files and held the turn open
until a retro existed (#3140, PR #3372). Receipts enforces no protocol. It
tells the agent once that its own tool output contradicts its own statement.
The once-per-claim marker bounds the cost at one turn per claim per session.
It does not cap blocks per session: each distinct contradicted claim can
block once.

Why the marker and not `stop_hook_active`. Measured 2026-11-25 over all
11,160 `~/.copilot/session-state/*/events.jsonl` files on the owner's
machine: 3,897 logged `agentStop` blocks, and the next stop in the same file
had the flag false 378 times of 3,889. Scope: one operator, Copilot 1.0.37 to
1.0.105, and the next-stop pairing is an inference. No block was logged on
1.0.87 or later.

What rule 2a's Copilot exclusion rested on, and what changed. Its two reasons
were no documented advisory field and no `transcript_path`. The first still
holds, so the reflect nudge stays excluded. The second changed: the same logs
show `transcriptPath` set in 10,977 of 19,518 runs, and in all 436 runs on
1.0.87 and later.

Evidence limits. The spike behind REQ-050 found zero contradicted stamps in
678 runs (draft PR #7631, 2026-11-25), so the false-block rate is unmeasured.
ADR-128 Decision 7 gates registration on 30 hand-judged contradictions with
none false, drawn by offline replay of the owner's logs. The figures show no
consumer demand, and this amendment claims none.

Alternatives considered. Stretching rule 2a to cover receipts was rejected:
rule 2a names one hook and its conditions bar a block. Deciding the exception
in ADR-128 alone was rejected: the rule and its pinned tests would then
contradict a later record. Shipping Claude-only was rejected by the owner
(REQ-050 Open questions, decisions D4 and D6).

Rollback: remove both dispatch entries and cut a release. The Copilot marker
directory stays in per-user storage until the user deletes it.

What this amendment does not change: rules 1, 2, 2a, 3, 4, 5, and 6; the
security carve-out; and the reflect nudge's Copilot exclusion.

## References

- Issue #3215 (this ADR request), issue #3197 (vendored-hook ROI review).
- Issue #5154 and ADR-085 Decisions 8, 9, 10 (the retirements rule 6 generalizes).
- Issue #5013 and ADR-085 lines 428 to 431 (127 wrong denials; rule 6's primary evidence).
- ADR-068 (consolidated dispatcher), which owns the one-entry-per-event invariant.
- `.project-toolkit/critique/ADR-084-rule-6-tool-use-bar-debate-log.md` (rule 6 debate).
- Issue #3216, issue #3217, issue #3218 (the elimination this bar governs).
- Issue #3219 (portable auth-edit hook, rebuilt on consumer demand).
- The ADR-062 amendment under issue #3214 (first application of this bar).
- `.claude/lib/hook_utilities/guards.py` (`skip_if_consumer_repo`, the
  self-neutering surface rule 4 addresses).
- The adr-review consensus for this ADR is recorded in
  `.project-toolkit/critique/ADR-084-debate-log.md`.
- REQ-048 (`.project-toolkit/specs/requirements/REQ-048-friction-triggered-retrospective-nudge.md`),
  the friction nudge that rule 2a governs.
- `.project-toolkit/critique/ADR-084-debate-log-2.md` (rule 2a and rule 5
  correction debate).
- PR #3372, issue #3349, and `b862e14e9` (the auto-retrospective hook rule
  2a keeps deleted); issue #3140 (its failure).
- ADR-097 and `f79e70c01` (#5172), which emptied the vendored surface and
  deleted rule 5's tests.
