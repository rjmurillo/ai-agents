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

1. The relocation target `workflow-routing.md` does not exist in the tree, and
   #1769's own section table (lines 120-135) no longer lists tier coordination
   among the sections it plans to move. The plan moved on.
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
| `.agents/SESSION-PROTOCOL.md` | summarized in one sentence | not carried | yes |

`SESSION-PROTOCOL.md` is a five-line pointer, so it summarizes rather than
quotes. That is the right shape for it, but it means "quoted verbatim" is true
of the two substantive replacements and not of the pointer. An earlier revision
of this log said all three quote verbatim, which was wrong.

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

## ADR-078, corrected here, with no debate behind it

Read this section as a disclosure, not as a review record.

**What changed.** `ADR-078-autoplan-orchestrator-router-boundary.md` described
orchestrator as `metadata.tier: manager` and reasoned about a "manager-tier"
rank. This PR deletes that vocabulary, so the ADR was left describing a field
that no longer exists. Six phrases were corrected:

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
the six phrases above.

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

**No `adr-review` debate ran for this edit.** The six-agent debate that
`AGENTS.md` normally fires on an `ADR-*.md` change did not happen. Subagent
invocation was unavailable in the authoring session. This log satisfies
`check_adr_review_policy`, which requires a staged file under `.agents/critique/`
naming the ADR ID, and that check is a string-presence test: it does not verify
that anyone reviewed anything.

The repository owner was asked and chose to have the correction made here rather
than deferred to a follow-up PR carrying a real review. That is recorded so the
next reader does not mistake a passing gate for a performed review. If the
vocabulary correction above is wrong, nothing independent caught it.
