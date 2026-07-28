# ADR-088 Debate Log

| Field | Value |
|-------|-------|
| Artifact | `.agents/architecture/ADR-088-remove-causal-memory-tier.md` |
| Protocol | adr-review, 6-agent debate |
| Date | 2026-07-27 |
| Trigger | New ADR staged alongside its implementation |
| Rounds | 2 |
| Outcome | Accept, after 4 of 6 agents blocked the first round |

## Decision under review

Remove Tier 3 causal memory: the derived graph at
`.agents/memory/causality/causal-graph.json`, its writer, its custom merge
driver, its merge-driver registrar, its ID-repair script, its schema, its
lefthook jobs, and its tests. Keep Tier 2 episodes and the intra-episode
`caused_by` and `leads_to` links.

## Final votes

| Agent | Round 1 | Round 2 | Position |
|-------|---------|---------|----------|
| architect | Block | Accept | Removal is sound; the ADR's consumer table was false |
| independent-thinker | Block | Accept | Removal is sound; the Tier 2 boundary argument was false |
| critic | Block | Accept on correction | Numbers and the staged contract were internally contradictory |
| analyst | Block | Accept on correction | Same numeric defects, plus a misread of ADR-063 |
| security | Accept | Accept | Net security improvement; removes a merge-time execution path |
| high-level-advisor | Accept | Accept | Merge now; conflict cost compounds while 14 PRs are open |

Consensus reached: the removal was never in dispute. Every Block was against the
document's evidence, not against the decision. All five blocking findings were
corrected in the ADR before this log was written; none was waived.

## What the debate changed

This is recorded in detail because the first draft would have shipped five
false claims, and three of them were claims this ADR used to justify itself.

### 1. The three-consumer table was fabricated (architect, P0)

The draft claimed Tier 2 survived because `rework_warning.py`,
`validate_investigation_claims.py`, and `git_hook_policy.py` read episodes. The
architect checked all three and refuted all three: the first excludes the
episode path prefix from a churn signal, the second allowlists that prefix, and
the third generates and stages episodes. None reads episode content, and the
third is exactly the maintenance tooling this ADR disqualifies as evidence when
it applies the same test to the graph.

Resolution: table deleted.

### 2. The replacement argument was also false (independent-thinker, P1)

The rewrite claimed the episode read path was `search_memory.py`, named in 33
agent and skill files. That script contains no episode reference at all; it
searches Serena markdown and Forgetful, and is a Tier 1 tool.

Verified independently:

```
git grep -n "get_episodes\|get_episode(\|get_decision_sequence" -- '*.py' \
  | grep -v "memory_core/\|/tests/\|test_"
```

returns nothing.

Resolution: the Scope section now states the finding instead of hiding it.
Episodes are write-only too. On the "who reads it" axis, episodes and the
deleted graph are symmetric, and the ADR now justifies stopping at the graph on
derivation distance and cost rather than on readership. Filed as issue 3630,
which is the largest finding of this review.

### 3. Numeric errors (critic and analyst, independently, P0 and P1)

| Claim as drafted | Measured | Fix |
|---|---|---|
| `--rebuild` flag | `--reset-graph` | Corrected |
| 3 patterns with `trigger == action` | 2 | Corrected |
| "rewrote it on every commit" | Guarded no-op write, issue #3351 | Corrected; 5.7% is what survived the guard |
| "worst merge-conflict source" | 3rd most-touched at 103; the two plugin manifests are 303 each | Reframed as most conflict-prone by severity, with the ranking shown |
| 104 graph-touching commits | 103 | Corrected |
| ADR-063 "decomposed along those tiers" | ADR-063 says "split by operation, not by tier" | Corrected |

The critic also found that 46 of 79 edges and 5 of 6 patterns carry
`contributions` keyed by a synthetic `\x00legacy:N` placeholder rather than an
episode id, with 4 edges carrying no contribution map at all. Those keys name no
episode, so that state cannot be regenerated from anything on disk. This
strengthens Finding 1 and further weakens the already-retracted "destroys no
information" claim. Added to the ADR.

### 4. "Nothing reads it" was too strong (critic, P0)

No executable caller existed. But the memory-gate and memory-reflexion skills
carried prose instructing agents to escalate to Tier 3 and consult its patterns,
which is a real consumer class, and this change had to edit those instructions
rather than only delete code. Finding 2 is retitled and now claims "no
executable caller," noting that the prescribed read path pointed at cmdlets that
are not defined anywhere in the repository in any language.

### 5. The removal had no regression guard (critic, P0)

Six canonical test files and their per-skill mirrors were deleted with no
inverse tests. Every surviving test asserts positive keys, so reintroducing the
tier by a bad merge, a revert, or a stale generator template would have passed
unnoticed. This violates TESTING-RIGOR, which requires positive, negative, and
edge coverage.

Resolution: added `tests/test_causal_tier_removed.py`, 21 tests covering the
deleted artifacts, both skill trees, the `memory_core` exports, the
`.gitattributes` driver declaration, the lefthook jobs, and the hook
subcommand. One edge-case test asserts the intra-episode `caused_by` and
`leads_to` links are still present, so a future "delete everything matching
causal" sweep fails instead of silently stripping them.

Negative-controlled rather than assumed: reintroducing the graph file, the
`merge=causal-graph` attribute, and the `update-causal-graph` lefthook job made
exactly the 3 corresponding tests fail, and removing them again made all 21
pass.

### 6. Finding 5 blamed the wrong thing (analyst, P1)

The draft called the ADR-063 kill-gate eval circular. The analyst showed the
harness measures documentation knowledge transfer correctly and that 15 other
skills passed the same run. The defect is in the use, not the instrument:
ADR-063 read a knowledge-transfer score as a behavior gate.

Resolution: Finding 5 retitled and rewritten. Filed as issue 3631.

## One P0 withdrawn on challenge

The independent-thinker's opening P0 claimed nine sharding commits had already
landed on main and that this ADR contradicted them. The evidence was
`.git/logs/HEAD` reflog entries, which are local state from a cancelled agent's
deleted branch, not repository state. Refuted with
`git ls-tree -r origin/main --name-only | grep -c "causality/shard"` returning 0
and `git branch -a --list '*shard*'` returning empty. The agent withdrew it.

Recorded because the failure mode generalizes: reflog is not repository state,
and a review that cites it is citing the reviewer's own machine.

## Evidence verified during the debate

Independently re-measured by at least two agents and confirmed:

| Measure | Value |
|---|---|
| Graph size | 1,074,565 bytes |
| Nodes / edges | 2,515 / 79 |
| Nodes touched by an edge | 99, 3.94% |
| Edge types | 1, all `causes` |
| Patterns / test fixtures among them | 6 / 2 |
| Anti-pattern success rate | 0.0 across 267 occurrences |
| Episode files | 277 |
| Historical drift | 41 of 242 episodes with no node, 16.94% |
| Graph-touching commits | 103 of 1,834, 5.67% |
| Eval scores | 6 prompts, 1.17 baseline to 4.83 enhanced |
| Executable callers of the causal API | 0 |
| Executable callers of the episode API | 0 |
| Live causal orphans after removal | 0 |

## Strategic review

| Lens | Assessment | Basis |
|---|---|---|
| Chesterton's Fence | PASS | ADR-038's original goals are named and the ADR states plainly that they are being abandoned unserved. It records this as a bet, not a proof. |
| Path Dependence | PASS | Reversibility is stated honestly: the artifact is readable in git history, the integration is restorable with rework, not by one command. |
| Core vs Context | PASS | The graph was neither; it was a derived cache with no consumer. |
| Second-System Effect | PASS | Nothing is being built to replace it. The ADR explicitly declines to extend the decision to Tier 2. |

## Deferred defects

Each is filed, so none depends on this document being read.

| Issue | Defect | Priority |
|---|---|---|
| 3630 | Memory Tier 2 is write-only; no code reads the episode store | P1 |
| 3631 | ADR-063 kill gate reads knowledge transfer as downstream utility | P2 |
| 3623 | Four PowerShell cmdlets documented, zero defined | P1 |
| 3624 | Tier taxonomy attributed to ADR-007, which does not contain it | P1 |
| 3625 | `merge=ours` names no real driver; `merge=handoff-aggregate` unimplemented | P1 |
| 3628 | Episode extractor manufactures low-signal decision records | P1 |

Issues 3625 and 3628 were confirmed as pre-existing and unaffected by this
change: the deleted registrar only ever registered one driver, named
`causal-graph`, and the extractor feeds the retained episodes, so fixing it is
necessary either way and is not an alternative to this removal.

## Status

ADR-088 remains `proposed`. Acceptance is the user's call, not this debate's.
