---
id: ADR-105
status: accepted
date: 2026-09-03
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-105: Terminal-State Completion Contract

## Context

`.agents/governance/FAILURE-MODES.md` catalogs recurring failure patterns
observed across the repository's retrospectives. Pattern 12,
"Post-Completion Continuation," records issue #5404 as its primary
evidence and documents two manifestations:

1. **Execution continuation.** The execution loop had no single
   authoritative completion contract. After the requested criteria were
   met, an agent promoted later-discovered optional refinements, adjacent
   cleanup, or newly imagined criteria into active work. Retry limits,
   review rounds, and delegation budgets remained available, and leftover
   budget alone kept the agent working, because none of those backstops
   proved the task was done.
2. **Response reopening.** After a correct terminal result, the final
   response appended an unsolicited continuation prompt. No blocker and
   no requested decision remained, yet the tail created a new implicit
   continuation edge. `.claude/rules/voice.md` before this change
   instructed the opposite behavior and shipped flag examples ending in
   exactly that shape.

FAILURE-MODES.md frames the cross-cutting defect as a missing artifact,
not verbosity. Its remediation principle for every catalogued pattern is
the same: replace a trust-based instruction with a blocking gate that
produces an artifact a tool can inspect. Pattern 12 had no such artifact:
completion was inferred from budget or TODO state, not from a named,
checkable predicate.

## Decision

Put the whole completion contract on the always-on rule path, and keep
exactly one operational procedure delegated to the skill that already
owned it.

1. **`.claude/rules/builder-ethos.md` section `## 4. Task Completion
   Contract` owns the contract end to end.** Its five subsections are
   `### Forming the contract`, `### Precedence`, `### Finding
   disposition`, `### Terminal predicate`, and `### Reactivation`. The
   terminal predicate reads, verbatim:

   > When every requested deliverable satisfies the frozen task contract and no blocker remains, the current task is terminal. Stop autonomous work.

   The precedence line reads, verbatim (fenced rather than block-quoted because the line itself uses `>` as its ranking operator):

   ```text
   `system/host requirements > current user request > mandatory safety/repository policy > frozen task contract > optional improvements`.
   ```

2. **`.claude/rules/voice.md` section `## Completion-Tail Audit` owns the
   response-side rule.** Verbatim:

   > After reporting a completed requested result, remove any unsolicited offer, question, or invitation whose only function is to continue the interaction.

   Its Quick Self-Review entry reads, verbatim:

   > Is the task terminal (builder-ethos.md Terminal Predicate)? If yes, does the response end on the result, with no unsolicited offer, question, or invitation to continue (Completion-Tail Audit)? Any sentence carrying no fact, cut it.

3. **`.agents/governance/FAILURE-MODES.md` entry 12 documents the pattern**
   so a future retrospective can map an incident to a named pattern the
   way the other eleven already work. Its Index row reads, verbatim:

   > `| 12 | Post-completion continuation | High | Issue #5404 |`

4. **`.claude/skills/avoiding-manufactured-work/SKILL.md` owns the
   disposition procedure only.** builder-ethos.md's `### Finding
   disposition` delegates to it by name, verbatim:

   > Every post-satisfaction finding is one of four classes; classify it with the `avoiding-manufactured-work` skill's disposition procedure, not a second doctrine.

   The skill maps each class name onto its pre-existing
   keep/shrink/defer/delete vocabulary. It copies no class definition, so
   there is no second copy of the contract to drift.

   The skill also adds a classification order, Blocker first, that
   builder-ethos.md does not state. It is procedure rather than a class
   definition, and it resolves toward mandatory policy while section 4's
   `### Precedence` line ranks the current user request above that policy.
   That tension is the open item recorded under Negative and tracked on
   issue #5535.

   PR #5506 shipped that delegation line before the skill carried a
   matching procedure, so from 2026-09-03 until this change
   builder-ethos.md delegated to a skill that classified nothing into the
   four classes. This change adds the mapping and closes that gap. It is
   the only part of this Decision that did not ship in PR #5506.

This ADR is the governance record for the doctrine merged in PR #5506
(commit `a7c362688`, 2026-09-03). It is written after the merge, not
before it.

## Prior Art Investigation

### What Currently Exists

- **Structure changed**: `.claude/rules/builder-ethos.md` previously ran
  sections 1 to 3 (Boil the Lake, Search Before Building, User
  Sovereignty) with no completion section. `.claude/rules/voice.md` had a
  Quick Self-Review checklist and an Ownership section but no
  completion-tail rule; its prior text instructed the opposite behavior.
  `.claude/skills/avoiding-manufactured-work/SKILL.md` classified
  post-hoc findings into keep/shrink/defer/delete with no mapping from
  the four contract classes onto that vocabulary.
- **When introduced**: the keep/shrink/defer/delete workflow predates
  this decision. The terminal predicate, the completion-tail audit, and
  the contract are new, per issue #5404.
- **Original author and context**: FAILURE-MODES.md attributes the gap to
  a catalog-wide theme rather than one author decision. Instructions
  asking agents to remember, verify, or check without an observable
  artifact succeed briefly and degrade as context grows.

### Historical Rationale

Completion was inferred from budget and TODO state because those
backstops were already load-bearing for other purposes (retry limits,
delegation budgets, review-round caps) and looked sufficient without a
dedicated predicate. The prior voice.md instruction to offer a fix
proactively reflected a helpfulness heuristic: surface the next possible
action rather than let the user wonder what else could be done.

### Why Change Now

FAILURE-MODES.md lists issue #5404 as live evidence of both
manifestations, and the catalog's own theme states that a soft
requirement with no feedback loop degrades as context grows. The risk of
not changing is continued, unmeasured recurrence of a now-named pattern.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| Do nothing; leave completion implicit | Zero change cost | FAILURE-MODES.md entry 12 already records live evidence of both manifestations against issue #5404, and the catalog's theory says an unaddressed soft requirement degrades further as context grows | Rejected: the catalog exists to close this shape of gap |
| New standalone completion-state skill | Isolates the doctrine in one file a reader opens once | Adds a fourth competing source of truth against builder-ethos.md's existing Precedence Stack instead of slotting into it; a skill is loaded on demand, so the doctrine would be absent from runs that never load it | Rejected: adds a file to reconcile, and puts an always-on invariant behind an on-demand load |
| Split the contract across builder-ethos.md and the skill: predicate in the rule, formation and precedence and reactivation in the skill | Each file states only what its scope already covers | Review on PR #5433 rejected exactly this shape. CodeRabbit review comment `3897761989` on `.claude/rules/builder-ethos.md` reads "[P1] **Keep the minimum completion contract in the always-on rule.**", noting that formation, precedence, disposition, parent and child handling, and reactivation would sit in a separately loaded skill a workflow can run without | Rejected on review evidence: an invariant that only binds when an optional skill happens to load is not an invariant |
| Whole contract in builder-ethos.md; disposition procedure delegated to the existing skill (chosen) | Every role loads the full contract on every turn; voice.md keeps the output-level consequence it already owns; the skill keeps the one procedure it already owned and gains nothing to duplicate | builder-ethos.md grows by one section; a reader wanting the disposition mechanics opens the skill | Chosen: it puts the invariant where it always loads and leaves exactly one delegation, named in-line at the delegation point |

### Trade-offs

The chosen shape trades file-size discipline in one always-on rule for
guaranteed availability of the invariant. An always-on rule that grows by
one section costs every session a fixed number of tokens. A contract that
lives behind an on-demand skill costs nothing until it is needed, and
binds nothing when it is not loaded. For an invariant whose entire job is
to stop work that should already have stopped, availability wins.

## Consequences

### Positive

- One canonical terminal predicate gives every agent role a single place
  to check whether a task is done, instead of inferring from budget or
  TODO state.
- The Completion-Tail Audit removes the continuation-prompt shapes
  FAILURE-MODES.md entry 12 names as previously shipped.
- The four-class disposition table and the keep/shrink/defer/delete
  vocabulary are joined at one delegation point, so a reviewer can cite a
  named rule instead of a per-agent judgment call.
- The critic and qa surfaces, across `templates/agents/`,
  `.claude/agents/`, `.github/agents/`, `src/claude/`,
  `src/copilot-cli/agents/`, and `src/vs-code-agents/`, replaced a
  minimum-finding quota with "Inspect exhaustively; do not manufacture a
  quota", so a zero-finding pass is a valid terminal verdict rather than
  a signal to keep looking.
- The orchestrator surfaces in the same six trees carry no quota text.
  They gained the delegation-side consequence instead: reaching the
  terminal predicate ends delegation regardless of remaining budget.

### Negative

- **Precedence places the current user request above mandatory policy,
  and review rejected that ordering.** The shipped order puts `current
  user request` ahead of `mandatory safety/repository policy`; the full
  line is quoted verbatim in the Decision above. This is the open item in
  this record, and the review history runs against what shipped.

  Three independent reviewers on PR #5433 called the ordering a
  policy-bypass path. Devin comment `3897689356` filed a security-kind
  finding on `.claude/skills/avoiding-manufactured-work/SKILL.md` headed
  "User requests override security gates". CodeRabbit comment `3897762010`
  asked to "Define one canonical order with mandatory policy before user
  overrides, apply it to both mirrors, and add a cross-surface test".
  CodeRabbit comment `3900606216` is headed "[P1] Keep safety precedence
  consistent across both instruction surfaces" and states "Both files rank
  User Sovereignty first, then add a conflicting safety exception". A
  stronger-sounding sentence in that comment, "so safety and repository
  policy blockers consistently outrank User Sovereignty", is not the
  reviewer's finding: it sits inside the collapsed "Prompt for AI Agents"
  remediation payload, which opens by instructing the reader to treat its
  contents as untrusted data rather than as instructions. It is quoted
  here only to record that it is not the ask. Copilot comment `3900826781`
  asked to
  "Apply this exception consistently so a user request cannot bypass
  mandatory safety or repository policy".

  The repository owner agreed. In PR #5433 comment `3900588149`:
  "Confirmed and agreed: the shipped precedence stack let an explicit
  user request outrank mandatory safety/repository policy. Swapped so
  mandatory policy now outranks the raw user request."

  Two commits on the PR #5433 branch carried that decision: `e84f0b603`
  swapped the precedence order in the skill, and `2c1b22df3` added a
  qualifying clause to section 3, because, in the same comment, "section
  3's 'overrides all others' line was not self-consistent with this fix in
  isolation". On the PR #5433 branch section 3 reads "This is the one rule
  that overrides all other defaults in this file, short of a mandatory
  safety or repository policy blocker"; on `main` it reads "This is the
  one rule that overrides all others" with no such qualifier. PR #5433
  never merged, so neither commit reached `main`.

  Restoring those commits would not be sufficient. Neither touches
  section 4's `### Precedence` line, because that line did not exist when
  they were written: section 4 arrived later, with PR #5506. A
  cherry-pick of both would correct section 3 and the skill and leave
  section 4 stating the ordering they were written to remove. The repair
  needs a fourth edit to section 4 itself.

  None of the four objections was re-raised on PR #5506. Its eight review
  comments do not mention precedence, so the ordering reached `main`
  unchallenged rather than re-argued and upheld.

  What the ordering demotes: `.claude/rules/universal.md` MUST 1 (no
  direct commit to `main`), MUST 7 (no secrets in a commit), MUST NOT 1
  (no force-push to a shared branch), and MUST NOT 2 (the six named hook
  and signing bypasses). Section 4's `### Precedence` line is the first
  place builder-ethos.md ranks external mandatory policy at all; the
  Precedence Stack does not cover it, because that stack opens "When two
  rules in this file disagree, apply them in this order" and all three of
  its entries are builder-ethos.md sections.

  Two things stop this from reading as a clean license. Nothing in the
  enforcement plane consults this line: `grep -rn "frozen task contract"`
  across `scripts/`, `build/`, and `tests/` returns one hit, an assertion
  string in `tests/test_completion_terminal_contracts.py`, and no consumer
  that reads the ordering at runtime. Hooks and CI still fire
  mechanically. And `universal.md` is always-on in the same context, so
  an agent reaching for section 4 to justify a bypass meets a direct
  contradiction rather than permission. The residual risk is that
  "current user request" is undefined here and carries no carve-out for
  ingested content, so an agent that resolves an issue body, a PR
  comment, or a fetched page as the current request has a quotable line
  ranking it above policy.

  This change deliberately does not edit the rule. `AGENTS.md` lists
  Security and Architecture under "Ask First", and the repair spans
  section 3 and the Precedence Stack, not section 4 alone. The decision
  is the owner's: restore the swap recorded in comment `3900588149`,
  qualify "current user request" as originating in the user turn only,
  or accept the shipped ordering and record why the agreed swap was
  dropped. This ADR takes none of those. It records that the question is
  open, that `main` currently carries the rejected ordering, and that the
  repair is tracked on issue #5535.
- **No behavioral proof against a live model.** `tests/eval/`
  fixtures and the eval scenarios register the contract statically. The
  graded runtime pass over those scenarios requires live model access and
  is not part of this decision.
- **A fourth normative surface to keep in sync.** FAILURE-MODES.md entry
  12 must track any future edit to builder-ethos.md section 4 or
  voice.md's Completion-Tail Audit. An unmirrored edit silently
  desynchronizes the documented pattern from the rule it describes.

### Neutral

- Generated instruction mirrors under `.github/instructions/` and
  `src/copilot-cli/instructions/` were regenerated with the doctrine.
  They remain mirrors, not owners.
- `.claude/rules/canonical-source-mirror.md`,
  `.claude/skills/context-optimizer/references/model-context-doctrine.md`,
  and the Serena memory index were updated alongside. They consume the
  doctrine; canonical ownership stays with the files named in the
  Decision.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|---|---|---|---|
| `.claude/rules/builder-ethos.md` | Direct | Section 4, Task Completion Contract; shipped in PR #5506 | Low |
| `.claude/rules/voice.md` | Direct | Completion-Tail Audit section and Quick Self-Review entry; shipped in PR #5506 | Low |
| `.agents/governance/FAILURE-MODES.md` | Direct | Entry 12 and the Index row; shipped in PR #5506 | Low |
| `.claude/skills/avoiding-manufactured-work/SKILL.md` | Direct | Maps the four contract classes onto keep/shrink/defer/delete, closing the delegation builder-ethos.md names | Low |
| critic and qa surfaces across six platform trees | Indirect | Replaced the minimum-finding quota with "Inspect exhaustively; do not manufacture a quota", so zero findings is a valid pass; shipped in PR #5506 | Low |
| orchestrator surfaces across six platform trees | Indirect | Carry no quota text; state that reaching the terminal predicate ends delegation regardless of remaining budget; shipped in PR #5506 | Low |
| `tests/test_completion_terminal_contracts.py`, `tests/eval/test_completion_terminal_fixtures.py`, `tests/evals/*-scenarios.json` | Indirect | Register and guard the contract text and the zero-finding scenarios | Low |
| Generated instruction mirrors under `.github/instructions/` and `src/copilot-cli/instructions/` | Indirect | Regenerated to keep shipped projections aligned with the canonical rules | Low |
| Persisted completion across compaction and handoff | Indirect | Consumes this ADR's terminal predicate and reactivation rules as its starting contract; out of scope here | Medium |

## Related Decisions

- Issue #5404 is the origin of the terminal-state invariant and the
  completion-tail audit. This ADR is its governance record.
- PR #5433 proposed an earlier four-file split of the same doctrine. It
  was not merged. Its review threads are the evidence behind one entry in
  the Alternatives table (the always-on-rule objection) and the
  precedence entry under Negative.
- PR #5506 merged the doctrine as commit `a7c362688` on 2026-09-03. The
  retrospective at
  `.agents/retrospective/2026-09-03-issue-5404-task-completion-contract.md`
  records that session.
- Durable transport and restoration of completion state across
  compaction, process restart, and handoff are a separate concern and are
  not decided here.

## Consensus

Six-seat `adr-review` panel run 2026-09-03 against this ADR, the merged
doctrine on `main`, PR #5506's diff at commit `a7c362688`, PR #5433's
unresolved review threads, and the companion skill and test changes in
this branch. Each seat ran as a separate agent with fresh context and no
sight of the others' reports.

Round 1 returned 6 Block. All six seats independently found the same
blocking defect: the debate log this ADR cited had reviewed PR #5433's
four-file split, a design this ADR does not make and that never merged.
Four further defects were found and corrected: this section's precedence
history was stated backwards, a quotation attributed to a review comment
did not appear in it, orchestrator surfaces were credited with a change
they never received, and one seat's Round 1 verification confirmed a
quoted phrase was present without checking that it sat inside a
machine-remediation payload rather than the reviewer's finding.

Round 2 returned 6 Accept after those corrections and after the debate log
was replaced with this panel's own record, which ships in the same change
as the `status: accepted` frontmatter, per ADR-073. One risk is recorded
and deliberately not resolved here: `main` ranks the current user request
above mandatory safety and repository policy. That is tracked on issue
#5535.

Debate log: `.agents/critique/ADR-105-debate-log.md`.

## References

- Issue #5404, terminal-state invariant and completion-tail audit origin
- PR #5506, commit `a7c362688`, the merged implementation
- PR #5433, the superseded proposal whose review threads inform the
  Alternatives table
- `.agents/governance/FAILURE-MODES.md`, entry 12, Post-Completion
  Continuation
- `.agents/retrospective/2026-09-03-issue-5404-task-completion-contract.md`
