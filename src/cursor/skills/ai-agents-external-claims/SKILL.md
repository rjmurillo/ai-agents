---
name: ai-agents-external-claims
description: Verify external, vendor, and third-party claims (numbers, attributions, structure) against authoritative primary sources before they land in a repo artifact or external deliverable. Covers stake-holding sources, round-number tells, citation-chain drift, and the walk-the-gate-or-file-conservative discipline. Use when you say `verify an external claim`, `check a vendor number`, `is this stat real`, `validate a third-party citation`. Do NOT use for running an experiment (use `ai-agents-research-methodology` in the ai-agents repository) or command-injection scanning (use `security-scan`).
metadata:
  routing:
    role: conditional-adjunct
    invoker: research
    trigger: the research claim gate finds an external claim about to enter a durable artifact
    user-facing: true
---

# ai-agents External Claims

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
This repo runs verification-based governance: a claim is true when a primary source, gate, or command output says it is, not when a vendor blog, a summary, or an agent asserts it. This skill is the front-gate for one specific claim class: external, vendor, and third-party assertions that arrive from outside the repo and are about to land inside a repo artifact (an ADR, a retro, a memory, a PR description, a session log) or an external deliverable. A wrong number un-cited from a published artifact costs more than the one or two fetches that would have caught it in the same pass.

Audience: a zero-context contributor (human or model) holding an external claim and deciding whether it may enter a durable artifact.

This skill is the discipline for verifying claims that originate OUTSIDE the repo. For proving an idea that originates inside the repo (hypothesis, probe, eval baseline), use `ai-agents-research-methodology` (in the ai-agents repository). For what counts as test evidence for code, use `ai-agents-validation-and-qa` (in the ai-agents repository). This skill hardens the general-purpose gstack `claim-verification-before-ingest` pattern into the repo's own artifact-ingest path.

## Triggers

- `verify an external claim`
- `check a vendor number`
- `is this stat real`
- `validate a third-party citation`

## Scope Boundaries

| You want | Use instead |
|----------|-------------|
| Prove a repo-internal idea (probe, eval, ADR debate) | In the ai-agents repository, `ai-agents-research-methodology` |
| Decide what counts as test evidence for a code change | In the ai-agents repository, `ai-agents-validation-and-qa` |
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

The `research` skill also invokes this skill at its claim gate, before each durable write. See Adjunct Mode below.

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

Repo caution, verified in `ai-agents-research-methodology` (in the ai-agents repository): vendor docs alone are not a primary source for runtime behavior. This repo was burned twice by wrong-by-omission docs (the #2205 and #2290 retros in `.project-toolkit/retrospective/`). When the claim is about how an external tool behaves, the primary source is an empirical probe at a pinned version, not the doc. In the ai-agents repository, route that through `ai-agents-empirical-probe-toolkit`.

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
You own everything you touch and everything adjacent to it. Scope is not an excuse. If you walked past a broken thing on the way to the thing you were asked to fix, you saw it. You are on the hook for at least flagging it.

### Phase 4: Walk the gate, or file conservative

This is the load-bearing discipline. When a claim is not yet verified, you have exactly two honest moves. Naming a verification you did not run, then shipping anyway, is neither:

- **Walk the gate.** Run the verification now (the fetch is typically under two minutes), then state the claim at the confidence the primary source supports, with the source cited inline.
- **File conservative.** State only what you can defend without the unrun verification, drop the unverifiable number or attribution, and do not name the gate you skipped inside the artifact.

The anti-pattern this closes is "Reporting Without Acting": writing "would be N if X corroborates" or "likely Y pending source Z" into an artifact instead of running X or Z. That hands the reader a TODO dressed as a finding. The repo skill `avoiding-manufactured-work` names the same reward-bias root cause on the produce-a-deliverable side; this phase is its provenance-side twin. The gstack `claim-verification-before-ingest` pattern is the general form.

- [ ] Every external number, attribution, or structural claim in the artifact is either verified against its primary source with an inline citation, or removed.
- [ ] No conditional-caveat sentence ("would be X if", "likely Y pending", "could confirm with Z") names a verification path that was left unrun.

## Adjunct Mode: The Research Claim Gate

The `research` skill invokes this skill before it writes a durable artifact:
the analysis document, the Serena memory, or the issue body. That is where a
fetched page becomes a repository file, so the gate sits there, and a direct
`/research` call passes through it too.

### Activation

Activation depends on what the text claims, not on the file type. Activate when
the artifact will state any of these:

| Category | Example |
|----------|---------|
| `vendor` | A product feature, capability, or behavior |
| `api` | An external API, platform, or compatibility fact |
| `statistic` | A benchmark, market figure, percentage, or count |
| `legal` | A legal, regulatory, or standards assertion |
| `project-status` | A third-party project's maintenance, security, or performance |
| `comparative` | One external tool or service compared with another |

Skip when every fact comes from this repository, its tests, or its versioned
internal documents, and no sentence leans on an outside source. A skip still
writes a ledger, with the reason.

### The claim ledger

Write one JSON ledger per artifact, since each artifact restates its own set
of claims. Record one entry per atomic claim: one assertion, small enough that
one source can confirm or refute it.

```json
{
  "artifact": "{analysis-dir}/{topic-slug}.md",
  "activation": {"decision": "activate", "reason": "vendor and statistic claims"},
  "claims": [
    {
      "id": "C1",
      "claim": "the draft sentence, as gathered",
      "category": "statistic",
      "time_sensitive": true,
      "source": {"kind": "primary", "url": "https://...", "published": "2026-09-01",
                 "accessed": "2026-09-25", "secondary_reason": null},
      "confidence": "medium",
      "disposition": "narrowed",
      "final_wording": "As of 2026-09-25 the repository lists 987 stars",
      "gap": "The source counts stars, not users."
    }
  ]
}
```

| Field | Values |
|-------|--------|
| `source.kind` | `primary`, `secondary` (say why no primary exists), or `none` |
| `confidence` | `high`, `medium`, `low`, `none` |
| `disposition` | `verified`, `narrowed`, `qualified`, `removed` |

The source kind bounds the rest:

- `verified` needs a primary source and high or medium confidence.
- A secondary source caps confidence at medium and cannot be `verified`.
- Source kind `none` (browsing unavailable, or no authority found) allows only
  `qualified` or `removed`. The run continues; it does not halt.
- A kept time-sensitive claim says "as of" in its final wording and records
  the source's publication or update date.
- Anything short of `verified` records its gap.

A search result snippet is not a source. Fetch the page it points to.

### The gate

Write the artifact to a draft file first. Run the validator on the ledger and
the draft. Only when it exits 0, copy the draft's exact text to its final
location and run the validator again on that file. The `artifact` field names
that final location.

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/ai-agents-external-claims/scripts/claim_ledger.py" \
    --ledger "{analysis-dir}/{topic-slug}-analysis-claims.json" \
    --artifact "{analysis-dir}/{topic-slug}-analysis.draft.md"
```

| Exit | Meaning | Next move |
|------|---------|-----------|
| 0 | The ledger passed | Copy the draft to its final location and recheck it |
| 1 | Defects, listed in the JSON on stdout | Fix the ledger or the draft, then rerun |
| 2 | A file is unreadable or the ledger is not JSON | Fix the input; do not write |

With `--artifact`, the validator refuses a kept final wording that is missing
from the draft, a removed claim that is still present, and a narrowed or
qualified claim whose gathered sentence is still present. It also refuses a
`skip` decision over a draft that cites an outside URL. So the artifact carries
the checked wording, not the unreviewed draft. The JSON summary names the
ledger and the draft, so a failure log says which gate failed.

## Durable Provenance For Load-Bearing Contracts

The claim ledger guards one research write. This section covers what outlives
the write: an outside contract that future correctness depends on. Persist
provenance for those contracts. Keep ordinary research ephemeral. Reference the
source; do not copy it. Issue #5415.

### Persist or not

| Situation | Persist? |
|-----------|----------|
| A compiler, type, or test already proves the behavior | No. The lookup stays ephemeral |
| A tutorial or page taught you an API and nothing cites it as a contract | No |
| An import, schema, pinned dependency, or generated projection already carries the relationship | No. Structure is the provenance (ranks 1 to 3 in `canonical-source-mirror`) |
| Code relies on a vendor limit, a version-specific API, a standard, or a probed runtime behavior, and nothing executable represents it | Yes. One record beside the consumer |

### The record

The record lives in the file whose behavior depends on the contract. There is no
global ledger and no local ID: the source URI and the file are the identity. In
a Markdown or template file it is a fenced block whose info string is
`external-contract`. In code or config it is a comment block, a line holding the
comment marker and `external-contract:` followed by comment lines with two or
more spaces of indent.

```yaml
# Fence info string is external-contract in a real record; yaml here keeps the
# example from counting as one.
source: https://github.com/github/copilot-cli
version: GitHub Copilot CLI 1.0.57
evidence: empirical
verified: 2026-06-01
purpose: Hook cwd and plugin-root variables the launcher relies on
reverify: tests/build_scripts/test_generate_hooks_runtime_contract.py
```

That record is real: the Copilot CLI hook runtime test carries it as a comment
block, and `--source copilot-cli` finds it.

```python
# external-contract:
#   source: https://example.org/spec/v2
#   version: v2.1
#   evidence: specification
#   verified: 2026-10-11
#   purpose: Wire format the adapter must emit
```

| Field | Rule |
|-------|------|
| `source` | Required. A URI. The vendor page, the spec, or the tool's repository |
| `version` | Required. The release, API version, commit, or date the source had |
| `evidence` | Required. `documentation`, `specification`, or `empirical` |
| `verified` | Required. ISO date of the last check. Not in the future |
| `purpose` | Required. One label of at most 200 characters. Never source text |
| `reverify` | A repo path to a test, probe, or script, optionally `path::selector`. Required for `empirical`, because a runtime observation has no URL to re-read |
| `capability` | Optional. A capability a canonical artifact owns under `metadata.capability` (ADR-110). Reuses #5396 ownership |

`empirical` marks evidence that came from running the tool because the vendor
documentation was silent or wrong. It never cites the docs as the authority.

### Find the consumers of a source

Run the repository's `check_external_contracts.py` validation script from the
repository root with a query flag. Both queries print JSON with each record's file and line, so
a changed or obsolete source maps to its consumers without a grep.

| Question | Flag |
|----------|------|
| Which files depend on this source? | `--source docs.github.com` |
| Which records went unchecked since a date? | `--stale-before 2026-01-01` |

The pre-PR gate `External Contract Records` checks the shape of every record:
closed field list, a real `reverify` path, no value over 200 characters. A file
with no record never fails it.

### Why not a `docs-used.md` ledger

| Ledger cost | Record answer |
|-------------|---------------|
| One hot file every change appends to, so merge conflicts | One record per consumer file, written only when that file changes |
| Grows with every lookup | Written only for load-bearing contracts |
| Needs IDs copied into code to point back | The record sits in the file, so no pointer exists |
| A second mutable artifact to keep in sync | The consumer and its provenance change in one diff |

### How it composes

- The claim ledger verifies a claim before a write. When code will depend on the
  verified source, add the record from the ledger's `source` entry.
- `ai-agents-empirical-probe-toolkit` owns the probe. The record points at the
  probe or the durable test with `reverify`.
- The record never holds source text, so it adds no authored copy for #5399.
- The record states which source and version were used. Whether that evidence
  is independent is #5406's question, not this one's.

## Scripts

| Script | Purpose | Exit codes |
|--------|---------|------------|
| `claim_ledger.py` | Validates a claim ledger, and with `--artifact` the artifact text, before a research write. Prints a sorted JSON summary. Reads local files only. | 0 pass, 1 defects, 2 unreadable input or bad arguments |
| `check_external_contracts.py` (repository validation scripts, not shipped) | Validates every `external-contract` record, or with `--source` and `--stale-before` lists the records that match. Reads local files only. | 0 pass or query ran, 1 malformed record, 2 bad root or date |

The script ships in this skill's own script directory. The Adjunct Mode
gate above shows the plugin-root invocation.

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
- [ ] In research adjunct mode, the claim ledger passed `claim_ledger.py` against the draft before the write, and again against the written file.

## Provenance

Issue #3068 requested a stewardship and knowledge-transfer skill library for this repo. Fourteen domain knowledge-packs plus `agent-harness-reference` shipped in PR #2831 as the `ai-agents-*` skill set. This skill adds the one named domain that set did not cover: verifying external and third-party claims against authoritative primary sources before ingest. It began as a documentation knowledge-pack modeled on `ai-agents-validation-and-qa`. Issue #5388 added the research adjunct mode and its one validator script.

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
