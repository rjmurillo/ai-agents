# Control-plane Subtraction Cohort 1 Ontology

Shared by REQ-024, REQ-022, and REQ-023. One `/spec` invocation covers the
first cohort of epic #5456 (three PRs); the domain vocabulary is the same
across all three, so one OntologyFragment serves all three REQ files rather
than three near-duplicates. Each REQ's `## Ontology` section cites this file
by path and lists only the entities that requirement touches.

## O1 Entities

- **CanonicalOwner**: a single behavior-owning mechanism (agent, skill, rule,
  hook, validator, workflow, lefthook job). Identity: repo-relative path or
  registered name.
- **PolicyOwner**: an authored source of governing text that can duplicate
  across mirrors (a rule file, its Copilot mirror, an ADR, a governance doc,
  a Serena memory). Identity: canonical source path.
- **AlwaysLoadedContext**: the bytes and estimated tokens a harness loads on
  every turn regardless of what file is open. Identity: (harness, file set).
- **GeneratedArtifact**: historical or derived output that is not itself a
  canonical product input (episodes, sessions, archive, generated mirrors).
  Identity: directory or generator/output pair.
- **CandidateMechanism**: anything eligible for a disposition verdict under
  the epic's KEEP/MERGE/DELETE/EXPERIMENT contract. A CandidateMechanism is
  either a CanonicalOwner or a PolicyOwner (or both, for a rule that is also
  a gate).
- **Disposition**: the verdict recorded for one CandidateMechanism: class,
  owner, consumers, evidence, and (for KEEP) the five required fields from
  the epic's Disposition contract.
- **Baseline**: the pinned-SHA measurement snapshot: commands run, numbers
  produced, exclusions with reasons, and release targets.
- **GateBudget**: declared pre-commit and pre-push worst-case latency, summed
  the way `tests/ci/test_lefthook_declared_budget.py` sums it.
- **ReleaseTarget**: a numeric or qualitative threshold a Baseline metric
  must clear before v0.7.0 ships (a release gate checkbox from the epic).

## O2 Ubiquitous language

| Canonical name | Synonyms to retire |
|---|---|
| CandidateMechanism | "control", "governance surface" (too vague; always resolve to CanonicalOwner or PolicyOwner) |
| GeneratedArtifact | "artifact" alone when the referent is historical/derived output, not a canonical input |
| Baseline | "metrics snapshot", "measurement run" |
| Disposition | "classification", "verdict" (use Disposition as the noun for the recorded row) |

## O3 Relationships

- Baseline measures-counts-of CanonicalOwner, PolicyOwner, AlwaysLoadedContext,
  GeneratedArtifact, GateBudget, for one pinned commit SHA.
- CandidateMechanism is-a CanonicalOwner or PolicyOwner (inclusive-or).
- Disposition classifies-one CandidateMechanism.
- ReleaseTarget bounds-one Baseline metric (canonical-owner count,
  always-loaded tokens, gate p95).
- GeneratedArtifact reported-apart-from CanonicalOwner (epic requires the two
  never merge into one total; REQ-024 AC enforces this).

## O4 Aggregate boundaries

- **Baseline** is the aggregate root for the measurement snapshot: it owns
  the JSON/markdown pair, the pinned SHA, the exclusion list, and the
  release targets as one unit written together.
- **Disposition** is the aggregate root for one ledger row: it owns class,
  owner, consumers, evidence, and (for KEEP) the five required fields as one
  unit; a row is never partially written.

## O5 Decision rules

- **DR1 (measurement-only)**: a script MAY only measure; it MUST NOT gate,
  ratchet, register, or evaluate. Enforced by an exit-code contract (0 on
  every metric value; nonzero only for a logic or config error). Source:
  epic "Abort if" clause 3.
- **DR2 (KEEP completeness)**: a Disposition of KEEP is invalid unless all
  five epic-required fields are present (current failure/outcome protected,
  evidence the failure still occurs, why a simpler mechanism is insufficient,
  canonical owner and consumers, cost where measurable). Source: epic
  "Disposition contract".
- **DR3 (already-fixed is KEEP, not DELETE)**: a CandidateMechanism whose
  problem is already remediated on `main` records Disposition KEEP with the
  remediation's evidence (commit, test, or code citation), never DELETE and
  never a re-proposed fix. Source: this cohort's own PR3 finding (the
  duplicate pre-push gate execution).
- **DR4 (reuse over duplication)**: a Baseline measurement for a dimension
  another script already measures MUST import or call that script rather
  than re-implement the computation. Source: epic child #5394's prohibition
  on a second context-budget authority; evidence in
  `.serena/memories/decision-the-instruction-budget-gate-already-exists.md`.

## O6 Bounded-context boundaries

This cohort's bounded context is **control-plane accounting**: counting and
classifying CandidateMechanisms and their AlwaysLoadedContext/GateBudget
cost. It stops at two seams:

1. **Mechanism implementation** (deleting or consolidating a specific
   CandidateMechanism) belongs to the child issues the epic names
   (#5394, #5395, #5396, #5420, #5421, #5436, #5241 items 5-6). This cohort
   only measures and records the Disposition; it does not execute deletions
   the disposition ledger merely classifies as DELETE-recommended-for-a-later-PR
   or EXPERIMENT.
2. **Release evaluation** (the reduced-configuration comparison against the
   full baseline, and the final release report) belongs to #5422-#5426 and
   is explicitly out of scope for this cohort (see REQ-024 Out of Scope);
   this cohort produces the Baseline those comparisons will later consume.

## O7 Open ontology questions

- Does a generated mirror that also carries policy text (for example
  `.github/instructions/*`) count as GeneratedArtifact, PolicyOwner, or
  both? Left unresolved at the ontology level; each disposition ledger row
  (REQ-022) states its own classification with a one-line reason rather than
  forcing one global rule.
- Is a lefthook job that wraps a validator a distinct CanonicalOwner from the
  validator it wraps, or the same owner counted twice? REQ-024's baseline
  script counts lefthook job names and validator files as two separate
  `canonical` dimensions on purpose (the epic's baseline bullet lists
  "agents, skills, rules, commands, hooks, validators, and workflows"
  separately from lefthook wiring), so this is a recorded design choice, not
  an unresolved question, but it is noted here because a future cohort could
  reasonably argue for de-duplication.
