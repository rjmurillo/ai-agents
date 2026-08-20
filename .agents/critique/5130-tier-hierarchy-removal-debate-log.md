# Issue #5130 debate log: remove the agent tier hierarchy

Subject: `.agents/SESSION-PROTOCOL.md`, `.agents/AGENT-SYSTEM.md` section 2.5,
`docs/orchestrator-routing-algorithm.md` Phase 2.5, and the `tier:` frontmatter
on 186 agent files across six trees.

Gate: `AGENTS.md` fires `adr-review` on any `.agents/SESSION-PROTOCOL.md` edit.
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
strategies and escalation target. That is now quoted verbatim in all three
places rather than paraphrased.

## The five findings from #5130, and where each is answered

| # | Finding from the reverted attempt | Answer in this change |
|---|---|---|
| 1 | `AGENT-SYSTEM.md` still carried a full duplicate | Section 2.5 replaced. 149 lines out, a 58-line coordination section in. |
| 2 | ~40 templates carry `tier:` pointing at a deleted definition | 186 files across six trees migrated to `role:`, in two frontmatter shapes. See "The two shapes" below. |
| 3 | Replacement prose said "escalate to the orchestrator"; ADR-009 says `high-level-advisor` | Every replacement quotes ADR-009's table and consensus protocol verbatim and states the target explicitly. |
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
