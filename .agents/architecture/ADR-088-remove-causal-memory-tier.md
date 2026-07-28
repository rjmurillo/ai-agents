---
id: ADR-088
status: proposed
date: 2026-07-27
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-088: Remove the Tier 3 Causal Memory Graph

## Status

Proposed. The removal is implemented in the same change that files this ADR, so
the document records a decision already carried out rather than one awaiting
execution. On reversal, see the Consequences section: the historical artifact is
readable in git history, and the integration is restorable with rework rather
than by one command.

## Date

2026-07-27

## Context

ADR-038 defined a four-tier reflexion memory architecture and deferred the
router and agent integration for the causal tier to a Phase 3 that never ran.
ADR-063 later decomposed the memory skill, explicitly "split by operation, not
by tier," and carried the graph updates forward without ever adding the query
integration. The API was built; its behavioral consumer was not.

Tier 3, the causal graph, shipped as a
single file at `.agents/memory/causality/causal-graph.json`, written by
`update_causal_graph.py`, merged by a custom git merge driver at
`scripts/validation/merge_causal_graph.py`, and refreshed by an
`update-causal-graph` lefthook job that ran on every commit.

The question that produced this ADR was not "how do we make the graph faster."
It was "what reads it." That question had not been asked since the tier was
built.

### Finding 1: it is a derived cache, and a drifted one

`update_causal_graph.py` shipped a `--reset-graph` flag whose help text read
"Discard the existing graph and rebuild from the episodes on disk." The graph
was designed as a pure function of the committed episode files under
`.agents/memory/episodes/`.

It had not stayed one. The writer only ever processed staged episode paths and
returned immediately when none were staged, so it was incremental and never
reconciled. Session 3345 measured the result: 41 of 242 episodes on disk had no
node in the committed graph, and a from-scratch rebuild did not reproduce the
committed file, partly because node timestamps were stamped from wall clock at
write time.

A second class of unique content is worse, and the adr-review debate found it:
provenance was anonymized. 46 of 79 edges and 5 of 6 patterns carry
`contributions` keyed by a synthetic `\x00legacy:N` placeholder rather than by
an episode id, and 4 edges carry no contribution map at all. Those keys name no
episode, so nothing on disk can regenerate them. Evidence:
`.agents/memory/episodes/episode-2026-07-25-session-3345-causal-graph-merge-driver.json`.

So the precise claim is not "deleting it destroys zero bytes that exist nowhere
else." It is narrower and still sufficient: everything the graph held that was
derivable is derivable again from the episodes, which are kept, and the only
content unique to the committed file is the drift itself, 17 percent of
episodes missing plus per-node wall-clock timestamps. That is a defect record,
not a capability. No decision anywhere depended on it, as Finding 2 shows.

This nuance came out of the adr-review debate. An earlier draft claimed the
graph destroyed no information at all, which overstated the case by treating a
design intent as an observed property.

### Finding 2: no code reads it, and the prose that told agents to were the only readers

A full-repository reference sweep found the graph's only executable consumers
were its own maintenance tooling: the writer script, the merge driver, an
ID-repair script, a re-export in `memory_core/__init__.py`, and the lefthook job
that invoked the writer. No hook, workflow, or validator queried it to make a
decision. The read path documented in the memory skills (`Get-CausalPath`,
`Get-Patterns`, `Get-AntiPatterns`) had no caller outside its own documentation
and tests, and three of those four cmdlet names are not defined anywhere in the
repository in any language.

The precise claim is "no executable caller," not "nothing at all consumed it."
The memory-gate and memory-reflexion skills did carry prose instructing agents
to escalate to Tier 3 and consult its patterns. That is a real consumer class,
and this change had to edit those instructions rather than merely delete code.
It is also the weakest possible one: an instruction to query an interface whose
documented cmdlets do not exist, producing no artifact, no gate, and no
observed successful invocation anywhere in the repository's history.

### Finding 3: the output is noise

After 277 sessions the graph held 6 patterns. Two of them are literal test
fixtures that leaked in from the test suite. Two have a `trigger` field
identical to their `action` field, which carries no information: the condition
and the response are the same string. One anti-pattern records a `success_rate`
of 0.0 across 267 occurrences, which describes the extractor's default rather
than an observed failure rate. The flagship query ADR-038 advertised returns
five of these six.

Structurally the graph is 2515 nodes and 79 edges. Only 99 nodes, 3.9 percent,
are touched by any edge. All 79 edges are the same type, `causes`. A graph in
which 96 percent of nodes are isolated and every edge has one label is a list
with extra syntax.

Two honest limits on this finding. Six patterns is a small sample, and it does
not prove that every one of the 2515 nodes is worthless; the nodes are mostly
faithful copies of episode text. And sparsity is a statement about topology, not
about semantics. What the finding does establish is that the layer's own
advertised output, the patterns and the causal paths that were the entire reason
to derive a graph rather than read the episodes, is degenerate: half fixtures,
a third tautological, and one aggregate reporting an extractor default as a
measured rate.

### Finding 4: it is the repository's most conflict-prone file

The file is 1,074,565 bytes in a single JSON blob and was touched by 103 of
1834 commits, 5.7 percent. That is the third-highest touch count in the
repository, behind only the two plugin manifests at 303 each. The manifests are
one-line version bumps that resolve trivially; this was a megabyte of rewritten
JSON, so it is the most conflict-prone file by severity rather than by
frequency, and it is the only one of the top three where a conflict is
expensive.

The job ran on every commit, but it did not rewrite the file on every commit:
issue #3351 added a guard that skips the write when the rendered content matches
what is on disk. The 5.7 percent figure is what survived that guard. The custom
merge
driver at `scripts/validation/merge_causal_graph.py` existed only to paper over
that. Registering the driver on CI runners cannot help: GitHub computes
`refs/pull/N/merge` server-side and never executes repository code, so no
runner-side driver can change a pull request's `mergeStateStatus`.

### Finding 5: the evidence that justified keeping it did not measure what it was used for

`evals/reports/adr-063-kill-gate-20260708/memory-reflexion.json` scored the
skill 1.17 baseline against 4.83 enhanced and passed the kill gate. All six
prompts ask the model questions about the skill's own documentation, then
measure whether loading that documentation improves the answers. It does.

The harness is not broken. It measures documentation knowledge transfer and it
measures it correctly; fifteen other skills passed the same run on the same
basis. The defect is in the use, not the instrument: ADR-063 read a
knowledge-transfer score as a behavior gate and concluded the tier earned its
keep. Nothing in that run tested whether the artifact the skill produces is
read by anything downstream, which is the question that would have caught this
tier four months earlier.

This is a governance defect, it is not specific to this tier, and it outlives
the removal. Issue 3631.

## Decision

Delete the Tier 3 causal graph and all machinery that exists only to maintain
it:

- `.agents/memory/causality/causal-graph.json`
- `update_causal_graph.py`, `backfill_episode_provenance.py`, and the
  `causal-graph.schema.json` resource, in both the Claude and Copilot CLI skill
  trees
- `scripts/validation/merge_causal_graph.py`,
  `scripts/maintenance/repair_causal_graph_ids.py`, and
  `scripts/maintenance/install_merge_drivers.py`
- the `update-causal-graph` and `install-merge-drivers` lefthook jobs
- the `.gitattributes` merge-driver registration block
- the causal and pattern functions in `memory_core/reflexion_memory.py`
  (`add_causal_node`, `add_causal_edge`, `get_causal_path`, `add_pattern`,
  `get_patterns`, `get_anti_patterns`) and their re-exports
- the tests that exercised only the above

## Scope: what this does NOT remove

Tier 2 episodic memory stays. A future reader must not extend this decision to
the episodes on the strength of this one.

The reason is not that episodes have readers. They do not, and the adr-review
debate is what established that. Two earlier drafts of this section claimed
otherwise and both were wrong:

- The first named `rework_warning.py`, `validate_investigation_claims.py`, and
  `git_hook_policy.py` as episode consumers. The first excludes episode paths
  from a churn signal, the second allowlists the episode path prefix, and the
  third generates and stages episodes. None reads episode content, and the
  third is exactly the maintenance tooling this ADR disqualifies as evidence
  when it applies the same test to the graph.
- The second claimed the read path was `search_memory.py`, named in 33 agent
  and skill definitions. That script does not touch episodes at all. It
  searches Serena markdown and Forgetful. It is a Tier 1 tool.

The verifiable position, which is less comfortable and more useful:

```
git grep -n "get_episodes\|get_episode(\|get_decision_sequence" -- '*.py' \
  | grep -v "memory_core/\|/tests/\|test_"
```

returns nothing. Outside its own module, its tests, and documentation examples,
no code calls the episode query API. **Episodes are write-only today, and so
was the causal graph.** On the "who reads it" axis the two are symmetric, and
any argument that kills the graph on that axis alone would kill the episodes
too. This is filed as issue 3630 rather than buried here, because it is a
finding about the memory system as a whole and it is larger than this change.

The distinction that actually justifies cutting here and stopping is derivation
distance and cost, not readership:

| | Episodes | Causal graph |
|---|---|---|
| Position in the chain | session logs to episodes | episodes to graph, one step further out |
| Recoverable by re-derivation | Only from session logs | From the retained episodes |
| On-disk shape | 275 files, 1.5 MB total | 1 file, 1.0 MB |
| Merge behavior | Small files, rarely collide | Single rewritten blob, top conflict source |
| Content quality | Primary record of what happened | Six patterns, half of them degenerate |

The graph is the last link in the chain, the cheapest to re-derive, the most
expensive to carry, and the only one whose content was measured and found
empty. That makes it the correct first cut. It does not make the episodes
proven, and this ADR does not claim they are. Whether the episodes earn their
keep is a real open question that deserves its own evidence and its own ADR,
and it should not be settled as a side effect of this one.

The per-event `caused_by` and `leads_to` links inside an episode file also stay.
Those order the events within one session and are part of the ADR-038 episode
format that 275 committed files already use. They are not the deleted graph;
they never left the episode.

## Consequences

### Positive

- Removes the repository's most conflict-prone file. Three of the author's open
  pull requests were `CONFLICTING` on it alone.
- Removes a per-commit hook job, shortening every commit.
- Removes about 1 MB from the working tree and roughly 3,000 lines of code,
  tests, and documentation that described a read path nobody walked.
- Removes a custom git merge driver, and with it a class of supply-chain risk:
  a merge driver named by `.gitattributes` executes repository-relative code
  during a merge, and pull-request automation runs merges in steps that export
  a bot token.

### Negative

- A capability is being abandoned unserved, and this ADR should say so plainly
  rather than imply the need went away. ADR-038 set out to support
  decision-to-outcome traversal (`Get-CausalPath`), counterfactual queries
  (`Get-WhatIf`), and similarity retrieval (`Get-SimilarDecisions`). Nothing in
  this repository serves those needs today, and nothing in this change starts
  to. They were never wired to a caller in the roughly six months the tier
  existed. The judgment here is that an unserved need with no demand signal
  after 277 sessions is cheaper to re-derive later from the retained episodes
  than to keep carrying a 1 MB conflict source that answers it badly. That is a
  bet, not a proof, and a future maintainer is entitled to revisit it.
- Rebuilding the capability is not free. `git revert` restores the files, but
  the surrounding code will have moved, and the drift described in Finding 1
  means the reverted artifact is not a trustworthy starting state. The honest
  statement is that the historical artifact is readable in git history and the
  integration is restorable with rework, not that recovery is a one-command
  operation.
- ADR-038 and ADR-063 now describe a tier that does not exist. Both are
  point-in-time records and are not rewritten; this ADR amends them.

- Existing clones keep a stale `merge.causal-graph` section in their local
  `.git/config`. The deleted installer only ever wrote configuration, and this
  change cannot reach a config file it does not track. The section is inert
  once no `.gitattributes` entry names the driver, and the deleted driver
  script it points at no longer exists, so a merge that somehow reached it
  would fail loudly rather than run stale code. Contributors can remove it with
  `git config --remove-section merge.causal-graph`.

### Neutral

- The episodes, which are the raw material, are unchanged and still committed.
  Any future rebuild starts from the same place the deleted writer did.
- The removal is guarded by inverse tests at `tests/test_causal_tier_removed.py`
  rather than by the absence of tests. Deleting six test files and their mirrors
  would otherwise leave the reintroduction of the tier undetectable, because
  every surviving test asserts positive keys. The guard covers the deleted
  artifacts, both skill trees, the `memory_core` exports, the `.gitattributes`
  driver declaration, the lefthook jobs, and the hook subcommand, and it
  asserts that the intra-episode `caused_by` and `leads_to` links are still
  present so that a later "delete everything matching causal" sweep fails
  instead of silently stripping them. Bringing the tier back means superseding
  this ADR and deleting that file in the same change.

## Related defects found and NOT fixed here

Recorded so the next reader does not have to rediscover them. Each is filed, so
none of them depends on this document being read.

1. **The tier taxonomy is a fabricated citation** (issue 3624). The "Tier 1
   Semantic / Tier 2 Episodic / Tier 3 Causal, per ADR-007" framing appears
   across the memory skills, `tests/evals/skills/triage-prompts.json`, and the
   memory skill specification. ADR-007 defines no such taxonomy. Its only tier
   language is a four-tier storage-backend list (AgentDB, ReasoningBank,
   SQLite, JSON fallback) and a Tier 1 through Tier 4 memory-index hierarchy.
   Neither is the semantic/episodic/causal model. Where this change touched
   those documents it removed Tier 3 without re-asserting the attribution; it
   did not repair the attribution repository-wide.
2. **The kill gate reads a knowledge-transfer score as evidence of downstream
   utility** (issue 3631), per Finding 5. The harness is sound and measures what
   it claims; ADR-063 drew the wrong inference from it. The defect outlives the
   deletion and can certify the next capability just as wrongly.
3. **Memory reference docs document PowerShell cmdlets that do not exist**
   (issue 3623): `Get-Episode`, `New-Episode`, `Get-DecisionSequence`,
   `Get-ReflexionMemoryStatus`. No `.ps1` or `.psm1` in the repository defines
   them. The Python equivalents in `reflexion_memory.py` do exist. This change
   corrected the one fabricated CLI flag it kept tripping over
   (`--session-log-path`, which the extractor takes positionally) but did not
   convert the PowerShell surface.
4. **`.gitattributes` still names `merge=ours`** (issue 3625), which is not a
   git built-in driver and therefore conflicts rather than resolving, and
   `merge=handoff-aggregate`, which is declared but has no implementation. The
   registrar deleted by this change only ever registered one driver, named
   `causal-graph`, so this removal leaves both exactly as broken as it found
   them rather than causing the defect.
5. **The episode extractor manufactures low-signal decision records** (issue
   3628). It duplicates decision context into the action field, defaults
   success rather than measuring it, and derives causal links from lifecycle
   order. This is the producer of the noise that Finding 3 measures in the
   aggregate. It is deliberately out of scope here because the extractor also
   feeds the episodes, which are kept, so fixing it is necessary either way and
   is not an alternative to this removal. Raised as a P1 during the adr-review
   debate.

6. **Tier 2 has no reader either** (issue 3630). No code calls the episode
   query API outside its own module, its tests, and documentation examples. The
   memory system's read path is documentation-only end to end, not just at the
   layer this change removes. Two drafts of this ADR claimed otherwise and the
   review refuted both; see the Scope section. This is the largest finding of
   the review and it is deliberately not resolved here, because the answer for
   episodes is probably to wire a reader rather than to delete, and that needs
   its own evidence.

## Alternatives Considered

**Shard the graph into per-session files.** The original plan, and the reason
this investigation started. It would have fixed the merge conflicts and left
every other finding standing: still no reader, still noise, still a maintenance
surface. Sharding an artifact nobody reads optimizes the wrong axis.

**Keep the graph, drop the per-commit hook.** Halves the conflict rate and
leaves a stale artifact that still has no reader. A cache nothing reads and
nothing refreshes is strictly worse than no cache.

**Keep it as raw material for a future consumer.** The episodes are the raw
material. The graph is a lossy projection of them. A future consumer is better
served by the episodes.

## References

- ADR-007: Memory-First Architecture
- ADR-038: Reflexion Memory Schema (defines the four tiers; Tier 3 removed here)
- ADR-063: Memory Skill Decomposition (built the tier split; Tier 3 removed here)
- Issue #3345: causal graph merge conflicts
- Issue #3502: pull request mergeability and merge-driver investigation
- PR #3504: closed unmerged. Attempted a runner-side merge-driver fix; the
  premise did not survive review, per Finding 4.
