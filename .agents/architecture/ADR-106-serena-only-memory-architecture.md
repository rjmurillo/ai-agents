---
id: ADR-106
status: accepted
date: 2026-09-08
decision-makers: [rjmurillo]
supersedes: [ADR-007, ADR-037]
superseded-by: null
explainer: null
implemented: true
---

# ADR-106: Serena-Only Memory Architecture

## Status

Accepted. Supersedes ADR-007 (Memory-First Architecture) and ADR-037 (Memory
Router Architecture). Debate evidence: `.agents/critique/ADR-106-debate-log.md`,
six seats, no blocking position.

The status is pinned from both sides rather than chosen. The ADR lifecycle
ratchet rejects `proposed-cannot-supersede`, so a proposal may not retire an
accepted decision and this record retires two. The ADR-073 acceptance gate
rejects `accepted` without debate-log evidence, so the log above lands in the
same change.

The change this record describes was carried out before the record was filed,
across the pull requests listed under Context, so this document ratifies a
decision already executed rather than one awaiting execution. That ordering
follows ADR-089, which filed its removal ADR alongside the removal itself.

## Context

Two accepted ADRs decided the memory architecture this repository ran on.

ADR-007 decided two separable things in one document. The first is a principle
at its line 83: "**Memory retrieval MUST precede reasoning in all agent
workflows.**" The second is a topology, its "Dual Memory Architecture" table,
which named Serena "**Canonical**" and Forgetful "Supplementary", and a
four-step workflow whose second step reads "**Augment** with Forgetful (if
available)".

ADR-037 decided the mechanism that implemented that topology. Three of its five
Decision items name the second backend directly: "**Serena-First Routing**:
Serena as canonical layer (per ADR-007), Forgetful as augmentation" (:51),
"**Result Augmentation**: Enhance Serena results with Forgetful semantic matches
when available" (:52), and "**Cross-Platform Guarantee**: Always works via
Serena; Forgetful enhances when present" (:54). Below those it specifies a
health probe, a result-merging strategy, a deduplication algorithm, a transport,
a synchronization strategy, and a search interface carrying a `-SemanticOnly`
switch documented at :96 as "Force Forgetful-only (requires availability)".

The repository owner decided on 2026-09-05 to remove the `forgetful` MCP server
entirely, with no replacement backend. Issue #5574 records the reason: the value
sat entirely behind an MCP server, so when that server failed to connect, every
instruction naming it became a dead end for the agent reading it, with no
degraded mode. The failure was observed directly in session, as
`forgetful (CONNECT_TIMEOUT)`.

Serena's memories are plain committed markdown under `.serena/memories/`, so
they remain readable when the MCP layer is down. That asymmetry, not a
preference between vendors, is what settles the decision.

The removal shipped across nine staged pull requests under #5574: #5575
(`1fb71695f`), #5578 (`1920d57e7`), #5600 (`19f257b5b`), #5612 (`cb213941d`),
#5616 (`652d035bb`), #5617 (`1c2e6225a`), #5625 (`0194a9715`), #5629
(`35af21e88`), and #5647 (`2aa8f02d1`). #5575 is the one that removed the
server itself. On `main` today, `.mcp.json` carries no `forgetful-ai` entry,
`.forgetful/` does not exist, and the `using-forgetful-memory` skill does not
exist.

## Decision

**1. The memory-first principle survives unchanged.** ADR-007:83, quoted above,
never depended on how many backends existed. It is carried forward here without
amendment and remains binding, and citations to the memory-first principle now
resolve to this item. Superseding ADR-007 does not retire it.

ADR-007's Decision carried four numbered sub-items at :87-90, and they do not
all survive. Sub-item 1 (call `list_memories` before analysis) and sub-item 3
(detection logic documented in memory, not executable scripts) carry forward.
Sub-item 2 ("Semantic storage: New patterns stored with embeddings for future
retrieval") is withdrawn: embeddings were the retired backend's mechanism.
Sub-item 4 ("Retrieval verification: Session logs must evidence memory
retrieval") is withdrawn as written, because session-log creation is itself
discontinued; see Confirmation below.

**2. Serena is the only memory backend.** Committed markdown under
`.serena/memories/`. There is no supplementary tier and no second store to
consult, augment from, or fall back to.

**3. The two-backend router is withdrawn.** ADR-037's router had one job, to
reconcile two backends. Four of its specifications are withdrawn rather than
simplified, because each describes an operation between two stores that no
longer both exist: result augmentation, cross-backend deduplication,
availability detection and health probing, and the synchronization strategy.

What survives is the unified entry point, ADR-037 Decision item 1. It still
ships: `.claude/skills/memory/memory_core/memory_router.py:2` reads "Unified
memory access layer over Serena, the only memory backend." That interface is
governed by this ADR going forward. The episode store it also reads is governed
by ADR-038, which is untouched.

**4. The semantic-only retrieval mode is withdrawn, not degraded.** Stated
separately because the distinction is load-bearing for a reader of ADR-037.
That ADR designed for the backend being *unavailable*, and priced that as
graceful degradation. Decommissioning is a different event: `-SemanticOnly` is
not a switch that now always degrades, it is a switch with nothing to force,
and it is removed from the contract. `-LexicalOnly` is retired as a distinct
mode, because every retrieval is now lexical over Serena.

**5. Memory identity is the file path.** ADR-007's Zettelkasten table gave
"Stable memory IDs (Forgetful: auto-generated)". Identity is now the memory's
path under `.serena/memories/`: stable, greppable without an MCP server, and
versioned with the repository.

**6. ADR-007's Security Considerations are carried forward.** ADR-063:119-121
instructs every memory sub-skill to inherit them by name, and ADR-063 is
accepted and implemented, so those rules need a live home. They are restated
under Security Considerations below, minus the one row made moot by the removal.
ADR-063's inheritance pointer resolves here.

**7. Dependent records are amended by reference, not superseded.** ADR-038,
ADR-063, ADR-064, ADR-070 and ADR-086 each name a retired backend or its router
while deciding something else that survives intact. They are not superseded and
their bodies are not rewritten. This follows the precedent ADR-089 set at its
own lines 293 to 294: "ADR-038 and ADR-063 now describe a tier that does not
exist. Both are / point-in-time records and are not rewritten; this ADR amends
them."

The known limit of that mechanism, recorded rather than discovered later: an
amendment by reference leaves no trace in the amended record. `git grep
"ADR-089"` across ADR-038 and ADR-063 returns nothing six weeks after ADR-089
amended them, and the generated index renders an amended record identically to
an untouched one. The amendments above are therefore discoverable only from
this ADR. Repairing that is out of scope here and belongs to whichever change
next touches those records.

## Confirmation

ADR-007:202-206 named three mechanisms that verified the memory-first rule.
None is live. "SESSION-PROTOCOL Phase 2" no longer exists as a blocking gate,
session-log creation is discontinued per the session-logs rule, and
`scripts/Validate-SessionJson.ps1` is absent from the tree.

Enforcement today is the `memory-gate` skill at `.claude/skills/memory-gate/`,
plus ADR-070's blocking Step 0.5 gate in the spec pipeline, which is `proposed`
rather than accepted. The honest statement is that the memory-first rule
remains binding as policy while its automated confirmation is thinner than
ADR-007 described. This ADR does not close that gap and does not claim to.

## Security Considerations

Carried forward from ADR-007 unchanged except where noted. ADR-063's memory
sub-skills inherit these.

### Memory Integrity

Memories are consumed without cryptographic verification. Mitigations: git
history provides an audit trail, and memory file changes are subject to PR
review. Provenance validation (CWE-345) remains unaddressed.

Consolidating to one store removes a cross-check that the two-backend
arrangement never actually performed, but the residual risk is worth naming:
a single write into `.serena/memories/` lands in committed markdown that is
re-injected ahead of reasoning in later sessions and cannot be un-published
from git history. Review of memory writes is the control.

### Data Classification

Memory content SHOULD NOT include API keys, tokens, credentials, PII or
sensitive user data, or security vulnerabilities (use `.agents/security/`).

### Access Control

Inherited from git repository permissions. No additional ACL.

### Storage Security

Serena is git-tracked markdown and inherits repository access controls.
ADR-007's second storage row, "**Forgetful**: Local SQLite without encryption
(CWE-311)", is moot: that store no longer exists.

## Impact on Dependent Components

| Component | Impact | Action | Risk |
|---|---|---|---|
| Agent prompt tree (`templates/agents/*.shared.md` source, `.claude/agents` mirror) | Direct. 35 lines in `.claude/agents` and 9 in `templates/agents` name the withdrawn Memory Router | Repoint or remove; not done here | Medium |
| Skills binding the retired records in `metadata.adr` | Direct. 8 SKILL.md files declare ADR-007 or ADR-037; no validator checks a declared ADR against its status, so the drift is silent | Repoint; not done here | Medium |
| Live prose still naming the retired backend | Direct. Acceptance criterion 1 of #5574 matches 45 files, 10 of them under `.claude/skills/` | Tracked on #5574; AC1 rescope is an open owner decision | Medium |
| ADR-038, ADR-063, ADR-064, ADR-070, ADR-086 | Indirect. Amended by reference under Decision item 7 | None; bodies preserved | Low |
| `.agents/architecture/README.md` | Indirect. Index moves both records to Retired | Regenerated by `build_all.py` | Low |

The first three rows are unrepaired by this change. They are prose and
frontmatter edits outside the ADR bodies #5574 protects, and they belong to the
Stage 2 surface rather than to the architecture record.

## Consequences

**Positive.**

- The MCP registration, the export corpus, the skill that fronted it, its slash
  commands, and the sync plumbing are gone, so no instruction can route an agent
  to a server no harness can start.
- The store that remains is readable when the MCP layer is down, which is the
  property the retired backend never had.
- The routing question disappears, along with the decision matrix that existed
  only to answer it.
- Memory state travels with the repository by construction, so hosted platforms
  and fresh clones see the same corpus.

**Negative.**

- Semantic similarity search is gone. Retrieval is lexical over committed
  markdown. Recall of a memory whose wording differs from the query now depends
  on the index and on cross-references rather than on embeddings. Nothing here
  restores it, and no replacement backend is being introduced.
- Cross-project recall is gone. Serena memories are scoped to this repository.
- The memory-first rule's automated confirmation is thinner than ADR-007
  described. See Confirmation.

**Neutral.**

- ADR-070 cites ADR-007's fallback table. That citation is inherited here:
  ADR-070:230-233 already priced this retirement, stating the gate "continues to
  function on Serena alone with reduced traversal depth".
- ADR-063 cites ADR-037 twice, for two different things that share the word
  router. Its thin-router citation borrows ADR-037's pattern vocabulary for a
  skill-surface router that is alive and untouched. Its store-topology clause,
  "Serena remains the canonical store and Forgetful the supplementary store",
  is withdrawn by Decision item 2, not inherited. What ADR-063 actually decided
  survives whole, by its own words at :123: "Storage backends are out of scope."
- Residual prose naming the retired backend survives in 45 files measured by
  #5574 acceptance criterion 1. That criterion asks the grep to return nothing
  and it cannot, because decommission guard tests and frozen evaluation records
  must contain the token to do their job. The rescope is an open owner decision
  on #5574 and this ADR does not depend on it.
- ADR-038's four-tier schema is untouched. Its Tier 2 episode store holds 750
  episode files under `.agents/memory/episodes/`, and its Tier 3 was already
  removed by ADR-089.

## Alternatives Considered

**Amend ADR-007 and ADR-037 in place without superseding them.** This is the
ADR-089 pattern and it is lighter. Rejected because both records *decided* the
two-backend topology rather than merely mentioning it: with the backend gone,
ADR-037's Decision items 2, 3 and 5 and ADR-007's Dual Memory Architecture table
describe an arrangement that does not exist. Issue #5574 requires that "Every
superseded ADR has a successor ADR that names it", and an amendment does not
produce one.

**Write one successor per superseded ADR.** Rejected as duplication. The two
records are one decision at two levels: ADR-007 adopted the two-tier posture and
ADR-037 specified the router that implemented it. Splitting the successor would
copy the same context into two documents and spend two review cycles to say one
thing. The partial-survival problem, that ADR-007 decided a principle which
outlives its topology, is a property of supersession rather than of successor
count, and Decision item 1 pays for it directly.

**Rewrite the bodies of ADR-007 and ADR-037 to describe Serena only.** Rejected.
Both decisions were true when written, and editing them would produce a false
history in which the second backend was never adopted. Issue #5574 forbids it
explicitly: "Do not rewrite its body."

**Adopt a replacement semantic backend.** Out of scope by the owner's decision
and named as a non-goal in #5574. Recorded here so a future reader knows the
absence of a semantic tier was chosen, not overlooked.

## Related Decisions

- `ADR-007-memory-first-architecture.md`: superseded. Its memory-first principle
  is carried forward by Decision item 1 and its Security Considerations by
  item 6.
- `ADR-037-memory-router-architecture.md`: superseded. Its two-backend router is
  withdrawn by items 3 and 4; its unified entry point survives under item 3.
- `ADR-038-reflexion-memory-schema.md`: amended by reference. Its episode schema
  is live.
- `ADR-063-memory-skill-decomposition.md`: amended by reference. Its
  operation-scoped decomposition stands.
- `ADR-064-commands-to-skills-migration.md`: amended by reference.
- `ADR-070-memory-first-gate-spec-pipeline.md`: amended by reference. Its
  blocking memory-first gate stands and now has one store to check.
- `ADR-086-lefthook-local-hook-orchestration.md`: amended by reference.
- `ADR-089-remove-causal-memory-tier.md`: the precedent for amending
  point-in-time records rather than rewriting them.
