---
name: ai-agents-external-claims
version: 1.0.0
license: MIT
description: Verify external, vendor, and third-party claims (numbers, attributions, structure) against authoritative primary sources before they land in a repo artifact or external deliverable. Covers stake-holding sources, round-number tells, citation-chain drift, and the walk-the-gate-or-file-conservative discipline. Use when you say `verify an external claim`, `check a vendor number`, `is this stat real`, `validate a third-party citation`. Do NOT use for running an experiment (use `ai-agents-research-methodology`) or command-injection scanning (use `security-scan`).
---

# ai-agents External Claims

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
This repo runs verification-based governance: a claim is true when a primary source, gate, or command output says it is, not when a vendor blog, a summary, or an agent asserts it. This skill is the front-gate for one specific claim class: external, vendor, and third-party assertions that arrive from outside the repo and are about to land inside a repo artifact (an ADR, a retro, a memory, a PR description, a session log) or an external deliverable. A wrong number un-cited from a published artifact costs more than the one or two fetches that would have caught it in the same pass.

Audience: a zero-context contributor (human or model) holding an external claim and deciding whether it may enter a durable artifact.

This skill is the discipline for verifying claims that originate OUTSIDE the repo. For proving an idea that originates inside the repo (hypothesis, probe, eval baseline), use `ai-agents-research-methodology`. For what counts as test evidence for code, use `ai-agents-validation-and-qa`. This skill hardens the general-purpose gstack `claim-verification-before-ingest` pattern into the repo's own artifact-ingest path.

## Triggers

- `verify an external claim`
- `check a vendor number`
- `is this stat real`
- `validate a third-party citation`

## Scope Boundaries

| You want | Use instead |
|----------|-------------|
| Prove a repo-internal idea (probe, eval, ADR debate) | `ai-agents-research-methodology` |
| Decide what counts as test evidence for a code change | `ai-agents-validation-and-qa` |
| Scan a file for CWE-78 command injection | `security-scan` |
| Stop a deliverable that no consumer demanded | `avoiding-manufactured-work` |
| Gate work before it starts, not after it appears done | `front-gate-before-pipeline` |

## When This Skill Fires

Any of these conditions in a claim about to enter a durable artifact:

- **Numerical headline claim**: "over 1000 X", "N+ stars", "X% of teams", "$Y in spend", "Z% accuracy improvement". Round numbers ending in 100, 1000, or 10000 are usually rhetorical rounding, often inflated above the real, precise, non-round count.
- **Named-authority attribution**: "Gartner says", "an MIT study found", "Anthropic disclosed", "per the docs". The named authority is a claim about a source, not the source.
- **Stake-holding author**: vendor self-promotion, a founder pitch, an advocacy post quoting a competitor's unfavorable stat. The author benefits from the framing, so the framing is suspect until the primary source confirms it.
- **Stat-of-a-stat chain**: source A cites source B citing source C. The deeper the chain, the higher the drift risk. Follow it to the origin.
- **Downstream commitment**: the claim will land in an ADR, a retro, a Serena memory, a PR body, or an external artifact where "I will verify it later" does not survive the round trip.

If none of these fire, this skill does not apply. The front-gate has a real cost (one or two fetches); reserve it for claims where a wrong number would actually bite.

## Process

### Phase 1: Identify the claim and its primary source

Name the exact assertion in one sentence and the ONE authoritative source that could confirm or refute it. The primary source is the origin, not a summary of the origin:

| Claim type | Primary source (authoritative) | Not a primary source |
|------------|-------------------------------|----------------------|
| Star or download count | The repository host page or package registry API | A blog post citing the count |
| Benchmark or accuracy number | The paper, the dataset card, or the run artifact | A vendor landing page |
| API or version behavior | The vendor's own reference docs at a pinned version | A tutorial or a memory of the docs |
| Attribution ("X said Y") | The named party's own published statement | A third party reporting it |
| Repo-internal cross-claim | The file, ADR, or test in this tree, quoted verbatim | A retro's paraphrase of it |

Repo caution, verified in `ai-agents-research-methodology`: vendor docs alone are not a primary source for runtime behavior. This repo was burned twice by wrong-by-omission docs (the #2205 and #2290 retros in `.agents/retrospective/`). When the claim is about how an external tool behaves, the primary source is an empirical probe at a pinned version, not the doc. Route that through `ai-agents-empirical-probe-toolkit`.

### Phase 2: Fetch and compare against the primary source

- [ ] Retrieve the primary source directly (host API, registry, paper, the party's own words). Prefer the API or raw source over a rendered page.
- [ ] Compare the artifact-bound claim against the source value: exact number, exact attribution, exact scope. A claim that rounds 987 up to "over 1000" is inflated, not confirmed.
- [ ] Follow any stat-of-a-stat chain to its origin. Confirm the origin actually says what the chain claims; drift compounds at every hop.
- [ ] For a repo-internal cross-claim, open the cited file and quote the load-bearing line verbatim. Paraphrase is the failure mode `.claude/rules/canonical-source-mirror.md` exists to stop (FM-9; PR #1887 paid 7 fix commits for paraphrased contracts).

Record what you fetched, when, and the version or commit, so the next reader can re-run the same comparison.

### Phase 3: Weigh the source's stake

A source with a stake in the framing is not disqualified, but its self-favorable claims carry a lower prior until a neutral primary source confirms them:

- Vendor self-promotion and founder pitches: verify the headline number against a neutral registry or the raw artifact before it enters any repo doc.
- Advocacy quoting a competitor's unfavorable stat: find the competitor's own primary source; advocacy selects and rounds.
- A named authority invoked second-hand ("Gartner says"): the primary source is the named authority's own publication, not the party invoking it.

State the stake explicitly in the artifact when it is material, so a reader can weigh it too. This is the `.claude/rules/voice.md` "Ownership: See Something, Say Something" discipline applied to provenance: a flag with a hypothesis, not a silent pass.

### Phase 4: Walk the gate, or file conservative

This is the load-bearing discipline. When a claim is not yet verified, you have exactly two honest moves. Naming a verification you did not run, then shipping anyway, is neither:

- **Walk the gate.** Run the verification now (the fetch is typically under two minutes), then state the claim at the confidence the primary source supports, with the source cited inline.
- **File conservative.** State only what you can defend without the unrun verification, drop the unverifiable number or attribution, and do not name the gate you skipped inside the artifact.

The anti-pattern this closes is "Reporting Without Acting": writing "would be N if X corroborates" or "likely Y pending source Z" into an artifact instead of running X or Z. That hands the reader a TODO dressed as a finding. The repo skill `avoiding-manufactured-work` names the same reward-bias root cause on the produce-a-deliverable side; this phase is its provenance-side twin. The gstack `claim-verification-before-ingest` pattern is the general form.

- [ ] Every external number, attribution, or structural claim in the artifact is either verified against its primary source with an inline citation, or removed.
- [ ] No conditional-caveat sentence ("would be X if", "likely Y pending", "could confirm with Z") names a verification path that was left unrun.

## Anti-Patterns

| Anti-pattern | Why it bites | Correct move |
|--------------|--------------|--------------|
| Round-number trust ("over 1000") | Rhetorical rounding inflates above the real precise count | Fetch the exact figure from the host or registry |
| Summary as source | A summary drops scope and rounds numbers | Follow the chain to the origin and quote it |
| Vendor doc as runtime truth | Wrong-by-omission docs burned this repo twice (#2205, #2290) | Empirical probe at a pinned version |
| Paraphrased repo cross-claim | Paraphrase drifts from the contract (FM-9, PR #1887) | Quote the cited file line verbatim with its path |
| Naming a gate you did not walk | Ships a TODO disguised as a verified finding | Walk it now, or file conservative without naming it |
| Trusting a stake-holder's self-favorable stat | The author benefits from the framing | Confirm against a neutral primary source first |

## Verification

Before a claim from an external source enters a durable artifact:

- [ ] The exact assertion and its single authoritative primary source are named.
- [ ] The claim was fetched from and compared against that primary source, with version or date recorded.
- [ ] Any stat-of-a-stat chain was followed to its origin, and any repo cross-claim is quoted verbatim with its path.
- [ ] Stake-holding sources are flagged, and self-favorable claims are confirmed against a neutral source.
- [ ] Every external number and attribution is cited inline or removed; no unrun verification is named as a caveat.

## Provenance

Issue #3068 requested a stewardship and knowledge-transfer skill library for this repo. Fourteen domain knowledge-packs plus `agent-harness-reference` shipped in PR #2831 as the `ai-agents-*` skill set. This skill adds the one named domain that set did not cover: verifying external and third-party claims against authoritative primary sources before ingest. It is a documentation knowledge-pack (structure-only, no runner scripts), modeled on `ai-agents-validation-and-qa`.

Grounding sources, verified against the working tree:

| Concept | Source | Re-verify |
|---------|--------|-----------|
| Same-pass claim verification, stake-holding sources, round-number tells | gstack `claim-verification-before-ingest` skill | Read the skill's "When this skill fires" section |
| Reporting-without-acting reward-bias root cause | `.claude/skills/avoiding-manufactured-work/SKILL.md` | `grep -n -e "Reporting" -e "reward" .claude/skills/avoiding-manufactured-work/SKILL.md` |
| Flag-with-a-hypothesis provenance discipline | `.claude/rules/voice.md`, "Ownership: See Something, Say Something" | `grep -n "See Something" .claude/rules/voice.md` |
| Verbatim-quote requirement for mirrored claims (FM-9) | `.agents/governance/FAILURE-MODES.md` (enforced by `.claude/rules/canonical-source-mirror.md`) | `grep -n -e "character-for-character" -e "verbatim" .agents/governance/FAILURE-MODES.md` |
| Vendor docs are not runtime truth (#2205, #2290) | `.claude/skills/ai-agents-research-methodology/SKILL.md` | `grep -n -e "vendor docs" -e "2205" -e "2290" .claude/skills/ai-agents-research-methodology/SKILL.md` |
| Sibling set and issue | Issue #3068; PR #2831 | Repo issue and PR history |

Note on grounding: the "walk the gate, or file conservative" wording adapts a discipline the maintainer applies at the account level; the repo's own on-tree anchors for it are `avoiding-manufactured-work` and the voice.md Ownership rule cited above, not a named section in `.claude/rules/voice.md`.
