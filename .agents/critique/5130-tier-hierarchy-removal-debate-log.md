# Issue #5130 debate log: remove the agent tier hierarchy

Subject: `.agents/AGENT-SYSTEM.md` section 2.5,
`docs/orchestrator-routing-algorithm.md` Phase 2.5, and the `tier:` frontmatter
on 186 agent files across six trees.

Gate at authoring time: `AGENTS.md` fired `adr-review` on any
`.agents/SESSION-PROTOCOL.md` edit. See the update below; that file and its
trigger were deleted upstream before this branch landed.
`scripts/validation/git_hook_policy.py check_adr_review_policy` requires this
log staged alongside the change.

## Review provenance (read this first)

**The debate ran on 2026-08-20. Votes and findings are in "The `adr-review`
debate" section at the end of this file.** It was run at the maintainer's
explicit direction, in a session with subagent invocation available, against
the branch at `be5d513`. Seven agents: the six `adr-review` roles plus a `qa`
pass. Result: 4 ACCEPT, 1 DISAGREE-AND-COMMIT, 2 BLOCK. Both blocks named
bounded clearing conditions; both sets of findings were real, and the two P0s
were fixed before this log was updated.

The rest of this section is the original disclosure, kept verbatim rather than
deleted, because the history of *how long this went unreviewed* is part of the
record. Read it as history, not as current state.

---

The six-agent `adr-review` debate did **not** run for this change. The session
that authored it was configured with subagent invocation disabled, so no
independent architect, critic, independent-thinker, security, analyst, or
high-level-advisor pass exists. This log is a single-author design record plus
the measurements that back it, not a consensus artifact, and it should not be
read as one. A maintainer who wants the debate the gate normally buys should
run `adr-review` against this diff before merging.

**Update, 2026-08-20, after merging `origin/main` at `ba541c21f`.** The gate
named above no longer applies to this change, and not because anything here
improved. PR #5179 deleted `.agents/SESSION-PROTOCOL.md` outright, along with
the four session-lifecycle skills and every living reference to the document.
`AGENTS.md:44` now reads "Any `ADR-*.md` edit fires adr-review"; the
SESSION-PROTOCOL trigger is gone with the file.

This branch accepted that deletion on merge rather than restoring the file, so
the edit that fired the gate no longer exists in the diff, and the diff touches
no `ADR-*.md`. The criterion is moot rather than met. Nothing in this log was
independently reviewed, and the paragraph above stands as the record of that.
Anyone reading this later should not mistake a deleted trigger for a passed
one.

What this log does carry: the prior independent review that produced issue
#5130 in the first place. PR #5127 attempted the same removal, the `critic`
agent found the cut incomplete and factually wrong, and the attempt was
reverted. Issue #5130 records five specific findings from that review. Every
one is answered below with the file it was answered in.

## The decision

**Delete the hierarchy. Repurpose `tier:` as `role:`.**

The alternative on the table was relocation, per the existing plan in
`.agents/analysis/1769-monolith-section-classification.md`. Relocation lost on
evidence:

1. The relocation target does not exist in the tree.
   `.agents/analysis/1769-monolith-section-classification.md:87` classifies
   section 2.5 as `PATH-SCOPED-RULE` with target `agent-catalog.md`, and that
   target names a rule file under `.claude/rules/` that does not exist
   (`ls .claude/rules/ | grep agent-catalog` returns nothing). The
   `docs/agent-catalog.md` in the tree is a different artifact, the generated
   agent index that `build/generate_agent_catalog.py` writes, not a
   path-scoped rule. So relocation had no destination, and shrinking the
   section in place is the only move available today.

   **Corrected 2026-08-20 by the `adr-review` debate (critic, analyst), and
   the original wording was wrong twice over.** It read: "The relocation
   target `workflow-routing.md` does not exist in the tree, and #1769's own
   section table (lines 120-135) no longer lists tier coordination among the
   sections it plans to move. The plan moved on." Both halves are false.
   #1769 never assigned section 2.5 to `workflow-routing.md`; that is the
   target for sections 3, 4, and 6 (lines 88, 89, 91). And lines 120-135 are
   the `SESSION-PROTOCOL.md` table, a different document: the AGENT-SYSTEM.md
   table is lines 84-97, where line 87 still lists this section. The plan did
   not move on, and this log said it had, citing the wrong file and the wrong
   lines to prove it.

   The correction matters more than the sentence. Issue #5130 exists because
   PR #5127 committed a replacement that asserted a state the tree
   contradicted. This log is the artifact meant to prevent that, and it had
   reproduced the defect. Noted rather than silently rewritten so the next
   reader can see the failure mode recur under the guard built for it.

   Note also that this PR edits `1769-monolith-section-classification.md:87`
   itself, so that row is not independent confirmation of anything: the
   document was made to agree with the change in the same commit. What the
   row now records is the new state (section 2.5 is 58 lines and quotes
   ADR-009), not a verdict that relocation was rejected.

2. `.agents/SESSION-PROTOCOL.md` had already been reduced to a five-line
   pointer at the `AGENT-SYSTEM.md` copy by the time this change started. The
   223-line body issue #5130 describes lives only in `AGENT-SYSTEM.md`
   section 2.5 today. There is one copy left to decide about, not two.
3. Nothing reads a rank. The hierarchy claimed that a lower tier cannot
   delegate to a higher one, that Builders cannot delegate to Builders, and
   that Integration is a leaf. No hook, validator, generator, or workflow in
   this repository enforces any of it. Documented constraints that nothing
   checks drift from behavior silently, which is what the governance-overhead
   review in `.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`
   was filed to catch.

What survives is the part that was always load-bearing: ADR-009's aggregation
strategies and escalation target. How much of the ADR each file carries differs
by what that file is for, so the provenance claim is per-file rather than
blanket. Measured by byte comparison against the ADR, not by eye:

| File | Aggregation table | Consensus protocol | Names `high-level-advisor` |
|---|---|---|---|
| `.agents/AGENT-SYSTEM.md` | verbatim | verbatim | yes |
| `docs/orchestrator-routing-algorithm.md` | verbatim | not carried, by design | yes |
| `.agents/SESSION-PROTOCOL.md` (deleted upstream, see below) | summarized in one sentence | not carried | yes |

`SESSION-PROTOCOL.md` was a five-line pointer, so it summarized rather than
quoted. That is the right shape for a pointer, but it means "quoted verbatim"
is true of the two substantive replacements and not of it. An earlier revision
of this log said all three quote verbatim, which was wrong.

That row is **history, not current state**: PR #5179 deleted
`.agents/SESSION-PROTOCOL.md` from `main`, and this branch took the deletion on
merge. The row is kept because the verbatim-provenance claim it corrects was
made about all three files, and dropping it would leave the correction looking
like it only ever concerned two. Only the first two rows describe files that
exist today, and only those two are asserted by
`test_adr_009_blocks_are_quoted_byte_for_byte`.

What matters for issue #5130 finding 3 is the escalation target, and all three
name `high-level-advisor`. None contains "escalate to the orchestrator" or the
old `"escalate_to": "manager"`, which is what PR #5127 got wrong. Reproduce:

```python
from pathlib import Path
adr = Path(".agents/architecture/ADR-009-parallel-safe-multi-agent-design.md").read_text()
table = adr[adr.index("| Strategy | Use Case | Behavior |"):
            adr.index("Route to high-level-advisor |") + len("Route to high-level-advisor |")]
proto = adr[adr.index("1. Orchestrator dispatches to N agents in parallel"):
            adr.index("4. Final decision applied") + len("4. Final decision applied")]
for f in (".agents/AGENT-SYSTEM.md", "docs/orchestrator-routing-algorithm.md"):
    s = Path(f).read_text()
    print(f, "table:", table in s, "protocol:", proto in s, "hla:", "high-level-advisor" in s)
```

`.agents/SESSION-PROTOCOL.md` was the third path in this block until PR #5179
deleted the file upstream. Running it against a deleted path raises
`FileNotFoundError`, so the check that was meant to prove the claim would
instead fail to run at all. Dropped rather than left as a broken repro. Refs
#5177 review (Copilot).

## The five findings from #5130, and where each is answered

| # | Finding from the reverted attempt | Answer in this change |
|---|---|---|
| 1 | `AGENT-SYSTEM.md` still carried a full duplicate | Section 2.5 replaced. 149 lines out, a 58-line coordination section in. |
| 2 | ~40 templates carry `tier:` pointing at a deleted definition | 186 files across six trees migrated to `role:`, in two frontmatter shapes. See "The two shapes" below. |
| 3 | Replacement prose said "escalate to the orchestrator"; ADR-009 says `high-level-advisor` | Both surviving documents name `high-level-advisor` and quote ADR-009 verbatim. Originally three: the `SESSION-PROTOCOL.md` pointer summarized rather than quoted, and that file was deleted upstream by PR #5179. See the per-file table above. |
| 4 | `detect_agent_drift.py` baselines merge-resolver at 20.7% because of tier enrichment | Re-measured. See below. |
| 5 | #1769 plans relocation, not deletion | Reconciled above. Relocation target does not exist; #1769's table no longer claims the section. |

## The two shapes, and a correction to this log

An earlier revision of this log said "136 files across six trees" and "Zero
`tier:` keys remain in any agent tree." Both were wrong when written, and the
second was wrong in the specific way issue #5130 exists to prevent: a committed
artifact asserting a completion that had not happened.

The field exists in two frontmatter shapes:

```yaml
role: executor                  # templates/agents/, .github/agents/,
                                # src/vs-code-agents/, src/copilot-cli/agents/
metadata:                       # .claude/agents/, src/claude/
  role: strategic
```

The first migration pass matched `^tier:` and caught 136 files. It left 50
nested under `metadata:` untouched, and this log was written from that pass's
numbers. The true population is 186. The install-parity gate caught the miss by
demanding the untouched Claude-side siblings of every shared agent the change
touched; no test caught it, because nothing reads `metadata.tier`.

Measure it, rather than trusting this sentence:

```bash
grep -rn '^\s*tier:' templates/agents .claude/agents .github/agents \
  src/claude src/vs-code-agents src/copilot-cli/agents | wc -l
```

That returns 0 on the complete branch and 50 on any head carrying only the
first pass.

A third consequence surfaced during review. `scripts/openclaw_bridge.py` read
only the top-level key, so every nested-shape agent resolved to the fallback
role: `.claude/agents/architect.md` declares `strategic` and exported as
`support`. That blind spot predates this change (the old code read a top-level
`tier` the same way), but it is a real defect and is fixed here, with tests
covering the nested shape and a negative control for an unmigrated
`metadata.tier` file.

## Finding 4, measured

The baseline comment claimed `src/claude/merge-resolver.md` is "the
tier-hierarchy-enriched prompt (PR #1426)". That descriptor is wrong and was
wrong before this change: `grep -n -i tier src/claude/merge-resolver.md
.claude/agents/merge-resolver.md` returns nothing. Neither merge-resolver body
has ever carried tier prose. The enrichment PR #1426 added is section
structure (Core Mission, Key Responsibilities, Execution Mindset, Handoff
Protocol, Memory Protocol), which the comment itself goes on to say.

Measured after the removal, via `uv run python build/scripts/detect_agent_drift.py`:

```
merge-resolver [.claude/agents vs .github/agents]: OK (baselined) (20.7% similar)
merge-resolver [src-claude vs src-vscode]: OK (baselined) (20.7% similar)
```

Both comparisons are unchanged at 20.7%. The floors in `KNOWN_BASELINE_DRIFT`
stay where they are; only the stale "tier-hierarchy-enriched" wording is
corrected, with the re-measurement recorded in the comment so the next reader
does not have to redo it.

## Why `role:` rather than deleting the field

Deleting `tier:` outright would have broken two live consumers and lost real
information:

- `build/generate_agent_catalog.py` requires the field and renders it as a
  column in `docs/agent-catalog.md`.
- `scripts/openclaw_bridge.py` mapped tier values into OpenClaw role names via
  `_TIER_TO_OPENCLAW_ROLE` (`expert -> strategic`, `manager -> coordinator`,
  `builder -> executor`, `integration -> support`).

The OpenClaw side already wanted a functional role, not a rank. Adopting that
vocabulary directly in frontmatter removes the indirection: the bridge now
copies `role:` through, and the mapping table is gone. The four values keep
their meaning as descriptions of what an agent does. They grant and withhold
nothing, and the coordination section says so explicitly so the rank reading
cannot creep back in.

The bridge gained `_resolve_role`, which logs and falls back to `support` on an
unrecognized value. Before, an unknown tier was exported verbatim as a new role
name into the OpenClaw manifest. A typo in frontmatter now surfaces as a
warning instead of inventing a role downstream.

## Standing dissent

Recorded so a later reader can weigh it: renaming rather than deleting keeps a
taxonomy alive that nothing enforces, and a future reader may re-derive
delegation rules from the four role values exactly as they were derived from
the four tiers. The mitigation is the explicit sentence in
`.agents/AGENT-SYSTEM.md` section 2.5 stating that delegation is decided by the
orchestrator against the task, not by comparing two agents' role values. If
that sentence is ever dropped, this dissent becomes live again.

## References

- Issue #5130. The scoped follow-up this change implements.
- Issue #1769. `.agents/analysis/1769-monolith-section-classification.md`.
- PR #5127. The reverted attempt whose critic review produced #5130.
- `.agents/architecture/ADR-009-parallel-safe-multi-agent-design.md`. Canonical
  aggregation and escalation source, quoted verbatim.
- `.claude/rules/canonical-source-mirror.md`. Why the ADR text is quoted, not
  paraphrased.

## The `adr-review` debate, 2026-08-20

Run at the maintainer's direction against the branch at `be5d513`, base
`origin/main` at `ba541c21f`. Six `adr-review` roles per
`.claude/skills/adr-review/SKILL.md`, plus a `qa` pass added because the
repository's spec validator listed `REQ-020: Obtain QA verification of test
coverage` as `NOT_COVERED` alongside the ADR, security, architect, and critic
gaps.

### Phase 1: independent votes

| Agent | Vote | The finding that drove it |
|-------|------|---------------------------|
| architect | **BLOCK** | No ADR records this decision. The change retires a documented governance contract across 186 files, rewrites the documented conflict-resolution algorithm, and withdraws a rationale clause from ADR-078, with the rationale living only in a reference document and this log. |
| critic | **BLOCK** | Two wrong citations committed to the permanent record: `"security": 2` shipped under a `per ADR-009` attribution ADR-009 does not support, and this log's finding-5 answer cited the wrong relocation target and the wrong line range. |
| independent-thinker | ACCEPT | The hierarchy was not merely unenforced but false: it opened "per ADR-009" while ADR-009 contains zero occurrences of "tier", and six of the nine agents it granted delegation authority carry "you CANNOT delegate" in their own prompt bodies. |
| security | ACCEPT | Tier never gated anything (`grep -riE "\btier\b" .claude/hooks/` returns zero on `origin/main`); the delegation containment survives independently; both new role gates fail closed toward the least-authority value. |
| analyst | DISAGREE-AND-COMMIT | Claims 1, 1a, 2, 5, 6 reproduce under independent verification. Claim 4 (the #1769 reconciliation) is overstated and partly circular. |
| high-level-advisor | ACCEPT | The migration is mechanically atomic; splitting ships a known-broken intermediate. A live 50-agent mis-export bug is fixed on the way. |
| qa | ACCEPT | 68 tests pass; changed functions measure 91 to 100 percent branch coverage; all seven negative controls it could construct fail as the PR claims. |

### Phase 2: consolidation

Consensus was not reached on the first round (the skill's bar is 6/6 Accept or
Disagree-and-Commit). Two findings were raised independently by more than one
agent, which is the signal worth recording:

- **The `security: 2` misattribution** was found by architect and critic
  separately. Verified: `.agents/architecture/ADR-009-parallel-safe-multi-agent-design.md:90`
  reads `- Soft conflicts -> weighted vote (architect > implementer)` and is
  the ADR's only weighting statement; `grep -c -i security` on the ADR returns
  0.
- **`.agents/prototypes/agents/README.md:32`** was found by architect and
  independent-thinker separately: it instructed future prototype authors to
  keep `metadata.tier` aligned with a baseline that no longer has the field.

Two agents also independently corrected the *reason* this change is right.
The debate log's own argument was "nothing enforces the hierarchy, so delete
it." independent-thinker rejected that inference as unsound in this repository,
where `.claude/rules/*.md` and `AGENTS.md` bind behavior with no validator
behind them, and found that enforcement had in fact existed:
`test_tier_compatibility.py` shipped in PR #1426 (`525490fae`) with
`TIER_HIERARCHY`, `AGENT_TIERS`, and real exit codes, and was deleted
incidentally in `5c4729345` ("M1 catalog prune"), not by a decision that ranks
should stop being checked. The conclusion survives on a stronger premise the
original argument did not make: **the hierarchy was false, not merely
unwatched.** Removing a wrong rule is not the same act as removing an
unenforced one, and this log had been claiming the weaker of the two.

### Phase 3: resolution

Fixed in this change, before the log was updated:

| Finding | Priority | Raised by | Resolution |
|---------|----------|-----------|------------|
| `"security": 2` attributed to ADR-009 | P0 | critic, architect | Removed from `CONFLICT_VOTE_WEIGHTS` in `docs/orchestrator-routing-algorithm.md`, with the reason recorded inline. Weighting any further agent is an ADR-009 amendment, not a docs edit. |
| This log's finding-5 answer cited `workflow-routing.md` and lines 120-135 | P0 | critic, analyst | Corrected in place, with the original wording quoted so the failure is visible rather than tidied away. The real target is `agent-catalog.md` at line 87; lines 120-135 are the `SESSION-PROTOCOL.md` table. |
| "There is no ranked agent hierarchy" sits 21 lines above a verbatim `architect > implementer` | P1 | architect, critic | `.agents/AGENT-SYSTEM.md` section 2.5 now says "no ranked *delegation* hierarchy" and carries a paragraph distinguishing an aggregation weight from an invocation rank. |
| The verbatim ADR-009 quote had no guard | P1 | critic, architect | `test_adr_009_blocks_are_quoted_byte_for_byte` added, extracting the blocks from ADR-009 at test time. Negative control run: a one-word paraphrase ("the high-level-advisor") fails it. |
| ADR-078 stale and its option-C rationale not vocabulary-only | P1 | architect, analyst | Corrected with a dated note at the end of ADR-078. The "breaking the manager-tier boundary" clause is **withdrawn**, not renamed, because a role that grants nothing cannot be broken. Option C is still rejected, on two grounds instead of three. |
| ADR-078:212 missing from the PR's own stale-line disclosure | P2 | analyst | Added; the correction note lists all six lines. |
| `.agents/prototypes/agents/README.md:32` mandates the deleted field | P2 | architect, independent-thinker | Updated to `metadata.role`, with the frozen-prototype exemption explained so a new prototype does not inherit it. |

Disclosed and deliberately **not** fixed here:

- **Duplicate section number `2.5`** at `.agents/AGENT-SYSTEM.md:572` (`### 2.5
  Strategy Agents`) and `:788` (`## 2.5 Agent Coordination`). Raised P2 by
  critic. Pre-existing on `origin/main`. Renumbering either one requires
  choosing a numbering convention and updating
  `.agents/analysis/1769-monolith-section-classification.md` plus the section
  tally that `test_audit_records_total_section_count` pins. That is a
  maintainer's call on convention, not a defect this change introduced.
- **Four copies of `_KNOWN_ROLES` with no equality test** (qa P1, security P2).
  qa proved it: adding `"auditor"` to the validator's copy alone leaves all six
  affected modules green.
- **No cross-tree role-agreement guard** (qa P1). qa proved it: setting
  `.claude/agents/janitor.md` to `role: strategic` against
  `templates/agents/janitor.shared.md`'s `role: support` leaves 119 tests green
  and the drift detector reporting no drift. This is the highest-probability
  regression for a six-tree sweep, and it is untested.
- **A malformed agent file in a configured tree escapes the role guard** (qa
  P1), because `_agent_definitions()` requires parseable frontmatter. The raw
  textual sweep closes this for the old `tier:` key but not for the new `role:`
  key.
- **The nested-role read elevates 25 agents in the OpenClaw export** (security
  P2, CWE-269). Correct behavior, but the downstream semantics of `role` in
  OpenClaw are outside this repository and were not verified by anyone here.

### Phase 4: convergence

`ACCEPT` from independent-thinker, security, high-level-advisor, and qa.
`DISAGREE-AND-COMMIT` from analyst, conditioned on the finding-4 correction,
which is made above.

critic's `BLOCK` named its clearing condition explicitly: "Add the
verbatim-quote test (P1-5) and the one reconciling sentence (P1-4) in the same
pass and I would move to ACCEPT." Both P0s are fixed and both P1s are done, so
that condition is met on this head. **It is met by construction, not by a
re-vote: critic was not re-run against the fixed tree.** Whoever merges should
know the difference.

architect's `BLOCK` is **not** cleared. Its P0 is that no ADR records this
decision, and this change still adds none (`git diff --name-status
origin/main...HEAD -- .agents/architecture/` shows only the ADR-078
correction). architect's position is that a critique log has no status field,
no supersession chain, and is not in the catalog a future architect greps, so
it cannot carry a decision of this size. high-level-advisor's position, given
directly on the same question, is to land the migration and file the ADR work
as a follow-up issue rather than grow this PR further.

Both are designated tie-breakers under
`.claude/skills/adr-review/SKILL.md` (architect on structural questions,
high-level-advisor on deadlock), and they disagree. Under `AGENTS.md`
Boundaries, authoring a new ADR is `Ask First` regardless. **That decision is
the maintainer's and is recorded here as open**, rather than resolved by
whichever tie-breaker is quoted last.

## ADR-078, corrected here: what changed, phrase by phrase

Read this section as the detail of the edit. The review record is the debate
section above; this one predates it and is kept for the before/after table,
with its provenance paragraph corrected at the end.

**What changed.** `ADR-078-autoplan-orchestrator-router-boundary.md` described
orchestrator as `metadata.tier: manager` and reasoned about a "manager-tier"
rank. This PR deletes that vocabulary, so the ADR was left describing a field
that no longer exists. Seven phrases were corrected:

| Line | Before | After |
|---|---|---|
| 36 | `manager-tier agent (model: opus, metadata.tier: manager)` | `coordinator-role agent (model: opus, metadata.role: coordinator)` |
| 79 | `manager-tier coordinator of the agent system` | `coordinating hub of the agent system` |
| 110 | `operate at different tiers` | `operate at different layers` |
| 111 | `orchestrator is a manager agent` | `orchestrator is a coordinator-role agent` |
| 123 | `breaking the manager-tier boundary` | `breaking the skill/agent boundary` |
| 206 | `orchestrator (manager-tier agent)` | `orchestrator (coordinator-role agent)` |
| 212 | `end-to-end at manager tier` | `end-to-end at the agent layer` |

The replacement values were read from the shipped frontmatter rather than
assumed: `.claude/agents/orchestrator.md` declares `metadata.role: coordinator`
and `templates/agents/orchestrator.shared.md` declares `role: coordinator`.

**What did not change.** The decision. ADR-078 chose explicit layering between
autoplan as front-door router and orchestrator as the routed-to multi-agent
coordinator, and that boundary is untouched by renaming the metadata field.
Nothing in the Consequences, Options, or Decision sections was rewritten beyond
the seven phrases above.

Lines 110 and 111 were added on a second pass, and the reason they were missed
is worth recording because it is the failure mode this whole PR is about. The
first pass classified line 110's "different tiers" as the skill-versus-agent
layering, a different concept, and stopped reading. The very next sentence said
"orchestrator is a manager agent", which is the deleted rank with no ambiguity
at all. Reading a word in isolation to decide whether it was in scope produced
a defensible call on that word and a wrong one on the sentence around it. The
spec validator caught it on CI, not me. `grep -c ' manager'` on the file now
returns 0, which is the check I should have run in the first place instead of
adjudicating uses one at a time.

Three other uses of the word "tier" in that document are deliberately left
alone, because they are different concepts that the tier-to-role migration does
not touch: Cynefin complexity tiers (line 37), the skill-versus-agent layering
(56, 94, 130), and the opus model tier (63, 122). "Agent-tier handoff" at 94
and 123 means the agent layer rather than an agent rank, and stays for the same
reason.

**Review provenance, corrected 2026-08-20.** An earlier revision of this
section said no `adr-review` debate ran for this edit. That was true when it was
written and is no longer true. The six-agent debate ran later the same day, at
the maintainer's direction, and the `architect` pass reviewed this ADR-078
correction specifically as a proposed change, not merely the wider migration.
Its finding is why the correction reads as it does: a straight rename of
"manager-tier boundary" to "coordinator-role boundary" was rejected, because a
role that grants nothing at runtime cannot be broken, so the clause was
re-grounded on the skill/agent boundary instead. Votes and findings are in the
section above.

Two things that remain true and should not be read away. `check_adr_review_policy`
requires only a staged file under `.agents/critique/` naming the ADR ID, and is a
string-presence test that verifies nothing about whether a review occurred, so a
green commit gate is never evidence of review. And the repository owner was asked
and chose to have this correction made here rather than deferred to a follow-up
PR; that call stands on its own merits, independently of the debate that
subsequently ran.

## The `adr-review` debate on ADR-098, 2026-08-20

The first debate's `architect` pass blocked on a P0: no ADR recorded this
decision. The maintainer directed that one be written.
`.agents/architecture/ADR-098-agent-role-metadata-replaces-tier-hierarchy.md`
is that record, and editing an ADR fires `adr-review` under `AGENTS.md:44`, so
the six roles ran again against ADR-098 itself.

**4 BLOCK-or-conditional, 2 clean: `ACCEPT` from security, `ACCEPT` (conditional)
from high-level-advisor, `DISAGREE-AND-COMMIT` from analyst, `BLOCK` from
architect, critic, and independent-thinker.**

### Phase 1: votes

| Agent | Vote | Driving finding |
|-------|------|-----------------|
| architect | **BLOCK** | The original P0 is discharged ("Yes"), but three statements in ADR-098 were false against the tree. An ADR that retires a document for being false cannot ship false claims. |
| critic | **BLOCK** | Same Context paragraph, measured three ways wrong, plus an Implementation Notes section about to become false on its own merge commit. |
| independent-thinker | **BLOCK on the record, not the decision** | "The decision survives every attack I mounted and is better supported than the ADR argues." Five spans wrong, including the exemption set understated 14x. |
| analyst | DISAGREE-AND-COMMIT | Every mechanical claim (149 lines, 186 files, four `_KNOWN_ROLES`, 17 templates, 20.7%) reproduces; Context claim 6 does not. |
| security | ACCEPT | No P0. `role` confers no runtime authority anywhere traceable, and both fallback paths degrade to `support`, the least-authority value. |
| high-level-advisor | ACCEPT (conditional) | "Architect was right. I was wrong on the ranking." |

### The finding all three blocks converged on

One paragraph, wrong three ways, and it was the evidence base for the ADR's
third force. Measured independently by architect, critic, analyst, and
independent-thinker, then re-measured before correcting:

| Claim as written | Measured |
|---|---|
| "the nine agents it ranked" | The table ranked **24** agents. Nine is the Expert plus Manager count, the agents *granted delegation authority*, which the ADR failed to say. |
| "Six of the nine ... carry an explicit 'As a subagent, you CANNOT delegate' line" | **Seven** of the nine. And `templates/agents/roadmap.shared.md:161` reads "You cannot delegate.", so the quoted uppercase string covers 9 of 17 templates, not all of them. |
| "`orchestrator` is the only agent of the nine with no such line, and it is the only one that actually delegates" | **Two** lack it: `orchestrator` and `pr-comment-responder`. The second delegates in its own body, and `templates/agents/pr-comment-responder.shared.md:217` documents delegating directly to `implementer` **bypassing orchestrator**, which is the one delegation-topology fact the retired section was the only document to carry. |

The corrected number argues *for* the decision more strongly than the wrong one
did. That is the uncomfortable part and the reason it is recorded rather than
quietly fixed: the error ran in the self-flattering direction in a document
whose whole thesis is that unchecked claims drift.

### What independent-thinker found that strengthens the decision

Sent to attack its own prior reasoning, it went looking for the charitable
reading (that the hierarchy was aspirational documentation for a system never
finished) and killed it with one commit inspection. At `525490fae`, the commit
that introduced the hierarchy, `src/claude/architect.md` carried `tier: expert`
at frontmatter line 5 and "**As a subagent, you CANNOT delegate**" at line 486.
Same file, same commit, and `test_tier_compatibility.py`'s own `AGENT_TIERS`
listed `"architect": "expert"` the day it shipped. The hierarchy did not precede
the contradiction and wait to be reconciled; it was authored on top of one. That
evidence is now in ADR-098's Context and appears in no earlier artifact.

### Phase 3: resolution

Every finding below was re-verified before acting. Corrections landed in ADR-098:

| Finding | Priority | Raised by | Resolution |
|---|---|---|---|
| Context paragraph wrong three ways | P0 | architect, critic, independent-thinker, analyst | Rewritten to 24 ranked / 9 empowered / 7 denying / 2 exempt, naming `pr-comment-responder` and its orchestrator bypass |
| Implementation Notes listed three open gaps, two already closed | P0 | architect, critic, security, independent-thinker | Gaps 1 and 2 moved to Consequences/Positive citing the tests that closed them. Gap 3 was left recorded as open here, and that became false in the same PR: `tests/test_agent_tree_discovery.py` closed it, and the round-3 `architect` pass flagged this row as the last artifact still asserting otherwise |
| The "load-bearing" mitigation sentence was pinned by nothing | P0 (hla), P1 (architect), P2 (security) | three passes | `test_the_role_inertness_sentence_survives_in_agent_system` added. Negative control: replacing the sentence fails it, restoring passes |
| Exemption set understated 14x | P1 | independent-thinker, security, architect | Negative section now names all 14 templates carrying no delegation statement, and identifies the tool grant as the real enforcement surface |
| "grants nothing at runtime" asserted globally from local evidence | P1 | security | Scoped to this repository, with the OpenClaw export boundary called out and added to Re-evaluation Triggers |
| 50-agent mis-export conflated exposure with shipped impact | P1 | critic | 50 files carried the latent bug; a default export emits 25. Both numbers now stated and kept apart |
| "repository-wide sweep" and "enforced in three consumers" overstated reach | P1 | critic, independent-thinker | Both scoped: the sweep covers six trees, and two of the three consumers scan one tree each by default |
| Opening sentence quoted with a silent truncation | P2 | critic, analyst | Quoted in full, with its actual position under `### Overview` |
| "cannot leave a stale mirror" broader than the parametrization | P2 | critic | Narrowed to what the guard actually asserts |
| #1769 circularity disclosed in the log but not the ADR | P2 | critic | Caveat carried into the ADR's References |
| No re-evaluation triggers | P2 | architect, critic | Four added, including the Standing Dissent's own trigger |
| Standing Dissent not verbatim; omitted which sentence it depends on | P2 | architect | Clause restored, with a note on why naming it matters |
| `decision-makers: []`, `implemented: false` against "Shipped in PR #5177" | P2 | architect, hla, critic | `[rjmurillo]` and `implemented: true`, matching ADR-093's shape |
| Pointer-only section 2.5 never evaluated | P2 | independent-thinker | Recorded under Trade-offs as a doc-treatment choice, rejected on the evidence that `SESSION-PROTOCOL.md` was such a pointer and had already eroded into a summary |
| Re-derivation risk stated three times | P2 | high-level-advisor | Collapsed to Standing Dissent, which the protocol requires |

### One correction to the reviewers

Two passes reported the `if front is None:` branch in the migration module as
dead code with a docstring claiming coverage it did not have. The implementer
found that wrong: the branch **is** reachable, because
`build/scripts/validate_agent_matrix_refs.py` reads with `utf-8-sig` while the
test helper reads with `utf-8`, so a byte-order mark makes one accept and the
other reject. Proven by prepending a BOM to `.claude/agents/janitor.md`. The
branch was kept and its message reworded to name the real cause. Deleting it, as
two reviewers implied, would have made that parser disagreement unreportable.

### Phase 4: convergence

architect's clearing condition was three edits, all made. critic's was the
Context paragraph plus the Implementation Notes state, both made.
independent-thinker's was five spans plus the pointer alternative plus a plan
for the unowned delegation constraint, all made. **As with the first debate,
this is met by construction and not by a re-vote: no reviewer was re-run against
the corrected ADR.** Whoever merges should know the difference between a
condition satisfied and a condition re-verified by the agent that set it.

What remains open and is not a defect of this ADR: the delegation constraint has
no normative owner and 14 of 31 templates carry no statement of it. The ADR does
not create that hole, it stops describing it falsely. Tracked with a named
acceptance criterion rather than parked in a Consequences list.

## The `adr-review` re-run on ADR-098, 2026-08-20 (round 3)

Round 2 ended on three standing BLOCK votes, and the section above says in as
many words that the clearing conditions were "met by construction and not by a
re-vote". The `adr-review` contract requires every final vote to be ACCEPT or
DISAGREE-AND-COMMIT. A Copilot review on PR #5177 made the same point against
the same lines, and it is correct: disclosing that a gate was not cleared is not
clearing it.

So the three blocking lenses were re-run against the corrected ADR-098, each
given its own recorded clearing conditions plus the three Copilot corrections
that had landed since, and each told that a BLOCK is legitimate only with a
file:line measurement behind it.

### Phase 1: votes

| Agent | Vote | Driving finding |
|-------|------|-----------------|
| architect | **ACCEPT** | All three clearing conditions discharged and independently re-measured. Two P2s, no P0. "Nothing false remains in the ADR." |
| critic | **BLOCK** | Both clearing conditions discharged, but a new P0: the export-impact number is still wrong, in the span its first BLOCK named. |
| independent-thinker | **DISAGREE-AND-COMMIT** | All five clearing conditions discharged. Two P1s, one of which is a real over-claim it declined to block on: "the escaped artifact loads in no host and grants nothing, and the fix is one sentence in a residuals list that already exists." |

### The P0, confirmed by re-measurement

`critic` held that "**50 files carried the latent bug** ... a default export run
emits **25 wrong roles**" put an exposure-shaped number in the impact slot. I
replayed the pre-fix resolver rather than take this on the reviewer's word:
`e6de14b39^:scripts/openclaw_bridge.py:116` reads `metadata.get("tier",
"integration")`, top-level only, so every nested-shape file mapped through
`_TIER_TO_OPENCLAW_ROLE["integration"]` and exported `support`.

| Quantity | Measured |
|---|---|
| Nested-shape files carrying the latent read | **50** (25 per tree) |
| Of those, files that exported a wrong role | **32** (16 per tree) |
| Files whose wrong output coincided with the right answer | **18**, having declared `integration`, which already mapped to `support` |
| Wrong roles in a default export run (`--agents-dir` defaults to `src/claude`) | **16** |

25 was the nested-shape count in `src/claude`, not a count of anything wrong.
The round-2 correction split exposure from impact and then filled the impact
slot with the exposure-shaped number, so the error survived the very edit that
was supposed to fix it. As in round 2, it ran self-flattering. Corrected in
three spans: Context, Consequences/Positive, and the affected-components table.

### The escape both critic and independent-thinker found, from opposite ends

Round 2 recorded gap 3 as closed by
`test_every_agent_file_in_a_configured_tree_is_a_readable_definition`. Both
lenses measured that the closure was one directory narrower than the claim:
`_agent_files` globs each tree non-recursively, so a malformed file inside
`.claude/agents/security/` is invisible to it, and `nested_agent_definitions`
(`build/scripts/validate_agent_matrix_refs.py`) skipped it too, because that
function gated on `is_agent_definition` and a malformed file is not a
definition. The file escaped the fail-closed corpus guard, the nested guard,
tree discovery, and all three role consumers at once.

Verified by planting `.claude/agents/probe2/zzbad.md` with unbalanced YAML and
`role: strategc`: the matrix validator exited **0** and all 27 role tests
passed. Rather than record a third residual, the hole was closed:
`nested_agent_definitions` now reports a nested file that opens a frontmatter
fence and fails to parse. Same probe after the fix exits **2** and names the
file; removing it returns exit 0. Five tests were added covering unbalanced
YAML, an unclosed fence, a scalar block, a clean-but-descriptionless sidecar
(which must stay silent, and does), and a malformed file at the top level
(another guard's corpus). 139 pass in that file, up from 134.

### One correction to the reviewers

`architect` raised as P2 that a misplaced agent in a subdirectory escapes every
role guard, on the ground that `tests/agent_metadata_helpers.py:104` uses
`glob` and not `rglob`. For a **well-formed** agent that is wrong:
`nested_agent_definitions` has covered it since issue #3601, wired at
`validate_agent_matrix_refs.py:684`. Negative control: a planted
`.claude/agents/probe/zzprobe.md` with valid frontmatter and `role: strategc`
makes the validator exit **2** with "agent definition in a subdirectory", and
exit 0 once removed. No residual was added for it. The malformed variant that
`critic` and `independent-thinker` described is a different case, it was real,
and it is the one that got fixed.

### Phase 3: resolution

| Finding | Priority | Raised by | Resolution |
|---|---|---|---|
| Export-impact number named the exposure, not the impact | P0 | critic | Three numbers now stated and kept apart: 50 exposure, 32 wrong, 16 in a default run, with the replay method named |
| Malformed nested file escapes every guard | P1 (it), P2 (critic) | critic, independent-thinker | Closed rather than documented: new branch in `nested_agent_definitions` plus five tests, negative-controlled both ways |
| `.agents/AGENT-SYSTEM.md` asserts inertness globally where ADR-098 scopes it to this repository, and the pin held the broader wording | P1 | critic | Sentence scoped to "in this repository" and the OpenClaw boundary named; `_ROLE_INERTNESS_CLAUSES` updated to the scoped form and made wrap-insensitive, since the old clause embedded a literal newline |
| "Tracked as a follow-up" cited no tracker | P1 | independent-thinker | Issue #5184 opened with acceptance criteria, and cited by number |
| Review Provenance recorded round 1 only, so a reader concludes 4-1-2 when this ADR's own review was 2-1-3 | P2 | independent-thinker | All three rounds now tabled, with the middle row called out rather than averaged away |
| Three bare line numbers into a 1900-line living document | P2 | critic | Replaced with quoted phrases. The advice proved itself within the hour: a four-line edit elsewhere in this change moved all three |
| A seventh bare-`.md` tree is called "not far-fetched" but is not a re-evaluation trigger | P2 | critic | Added as trigger 5 |
| Phase 3 table of round 2 still said the malformed-frontmatter gap remains open | P2 | architect | Row corrected in place, with the reason it went stale |
| Misplaced well-formed agent in a subdirectory escapes every guard | P2 | architect | **Refuted by negative control.** Covered since issue #3601; no change made |

### Phase 4: convergence

`critic`'s BLOCK was a single P0 with an exact edit attached. That edit is made
and the number it named was re-measured independently before changing anything,
which is the standard round 2 set. `architect` accepted. `independent-thinker`
committed on the record while declining to certify one sentence, and that
sentence has since been fixed by closing the hole rather than by rewording the
claim.

**This round did converge, and not by construction.** Every round-2 blocker was
re-run against the corrected document and returned a vote; the one BLOCK named
a P0, and the P0 is fixed with its measurement recorded above. What is not
claimed: `critic` has not been re-run a second time against the corrected
number. Its clearing condition was stated as an exact replacement text and that
text is what landed, so the gap between "condition satisfied" and "condition
re-verified" is narrower here than it was in round 2, but it is not zero, and a
reader should know which one this is.
