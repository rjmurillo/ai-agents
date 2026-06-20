---
id: ADR-073
status: accepted
date: 2026-06-19
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-073: Machine-Readable ADR Lifecycle Frontmatter

## Status

Accepted (2026-06-19). Requested by issue #2583 (labels `agent-architect`, `agent-explainer`, `area-skills`, `priority:P1`, `adr-followup`).

A 6-agent adr-review debate ran on the first draft (architect, critic, independent-thinker, security, analyst, high-level-advisor; debate log at `.agents/critique/ADR-073-debate-log.md`). Consensus: DISAGREE-AND-COMMIT, no substantive blocks. This revision incorporates the P1 findings: scope is now committed only to Phase 1 (optional, unenforced fields) with backfill and the enum gate deferred and consumer-gated; `status: accepted` is bound to adr-review evidence; `explainer` is display-only and no-auto-fetch; the `yq` example was replaced with the repo's `python-frontmatter`; backfill is acknowledged as non-mechanical (triage for ADR-072, ADR-055); and the `implemented` precedent is cited precisely (adr-best-practices.md line 42).

Accepted 2026-06-19 by repo-owner authorization (rjmurillo), bound to the 6-agent adr-review consensus evidence at `.agents/critique/ADR-073-debate-log.md` (DISAGREE-AND-COMMIT, no substantive blocks) per the Phase-3 acceptance gate. Phase-1 tooling (optional, unenforced lifecycle frontmatter) ships with this acceptance under #2583.

## Date

2026-06-19

## Context

ADRs in this repository record lifecycle state as prose inside the `## Status` section. The canonical template (`.agents/architecture/ADR-TEMPLATE.md`) offers `[Proposed | Accepted | Deprecated | Superseded by ADR-XXX]`, and `adr-best-practices.md` instructs authors to "Mark the old ADR as `Superseded by ADR-NNN`". This is the stock MADR convention, and for a human-read decision log it is fine.

It is the wrong fit for an agent-operated repository. Three forces drive a decision now:

1. **No machine-readable current state.** "Which ADRs are accepted right now" cannot be answered without parsing prose. Free-text status like "Proposed. Architect design review completed (verdict: APPROVE WITH CHANGES); this ADR may exist as `Proposed` but MUST clear the five approval conditions..." (ADR-072, lines 5 to 10) is unparseable by an enum filter.

2. **Supersession and implementation have no structured field; status reconciliation is unowned.** The canonical parser `.claude/skills/adr-review/scripts/detect_adr_changes.py` (`_get_adr_status`, lines 40 to 48) already reads an optional `status:` line via `re.search(r"(?m)^status:\s*(.+)$", ...)` and defaults to `proposed`. So a single `status:` line is already consumed, but it is not the authoritative source (the human-read `## Status` prose is), the two are never reconciled, and supersession and implementation state have no machine-readable field at all. Every other consumer that wants current state re-scrapes the prose body.

3. **The `implemented` gate is already sanctioned but cannot be used yet.** `adr-best-practices.md` (line 42, shipped in PR #2586 for issue #2582) already says a project "may add optional `implemented` metadata that flips at the first merged change" to decide amend-versus-supersede, but adds: "Do not emit that field unless the project's ADR template or existing ADRs already use it." The field is authorized in principle and blocked in practice, because no template defines it. Adopting the schema is the act that unblocks it.

Research (verified 2026-06-11, recorded on #2583): no upstream spec (Nygard, MADR 4.0.0, AWS, GDS Way, arc42) defines a machine-readable `supersedes`/`superseded-by` field pair. It exists only in tooling conventions: `adr-tools` flips the prior record's status via `adr new -s`. Current-state discoverability is conventionally solved by generated views over a clean log, and those views need clean metadata to read.

## Decision

Adopt a queryable lifecycle frontmatter schema as the machine-readable source of truth for ADR state, retaining the human-readable `## Status` prose section as a secondary rendering.

Add a YAML frontmatter block to the canonical ADR template:

```yaml
id: ADR-NNN
status: proposed | accepted | rejected | deprecated | superseded   # enum, no prose
date: YYYY-MM-DD          # last updated
decision-makers: []
supersedes: []            # ADR ids this record supersedes
superseded-by: null       # ADR id that supersedes this record, or null
explainer: null           # link to a living design doc, if paired
implemented: false        # flips true at first merged change; gates amend-vs-supersede
```

The frontmatter `status` enum is authoritative for tooling. The prose `## Status` section remains for humans and may carry the nuance the enum cannot (review verdicts, conditions to reach Accepted, the conditional state ADR-072 uses today). When the two disagree, the frontmatter wins, the gate flags the drift, and the author reconciles by editing the prose to match; the gate never silently rewrites prose.

Two integrity rules bind the schema from the start, because the review of this ADR surfaced both as exploitable gaps:

- **`status: accepted` is not a self-asserted approval.** A hand-edit of frontmatter to `accepted` MUST NOT be treated as governance approval. The Phase 3 gate accepts a transition to `accepted` only when the same change carries adr-review consensus evidence (the debate-log artifact path under `.agents/critique/`). Without that binding, the enum is a forgeable approval signal.
- **`explainer` is a display-only link.** Tooling and agents MUST NOT auto-fetch the `explainer` URL (it is a poisoning and SSRF surface; CWE-918). It is metadata for human click-through, and the gate SHOULD constrain it to in-repo paths or org-internal URLs.

Scope discipline: only **Phase 1 (additive, optional fields) is committed by this decision**. The backfill (Phase 2) and the enforced enum gate (Phases 3 to 4) are explicitly deferred and are conditional on a concrete consumer existing (a stale-ADR detector, a generated current-state index, or a dependency viewer). Optional fields with no consumer are cheap; a 72-file backfill and a blocking gate with no consumer are not. This answers the "no consumer today" objection: adopt the schema so future tooling has clean metadata to read, without paying the migration cost until that tooling is real.

Roll out in phases, each independently shippable and reversible. The enum gate (the only breaking step) ships last, after every existing ADR carries valid frontmatter, and only once a consumer justifies it.

This ADR records the decision and the migration contract. It does not itself ship the template change; it is written in the current format so it does not depend on its own not-yet-accepted schema.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern being changed**: ADR lifecycle state recorded as prose in `## Status`; supersession recorded as the free-text phrase `Superseded by ADR-NNN`.
- **When introduced**: Convention inherited from the project canonical template `.agents/architecture/ADR-TEMPLATE.md`; reinforced by `adr-generator/references/adr-best-practices.md`.
- **Original author and context**: Adopted from MADR/Nygard, the widely used community conventions, when the ADR log was established.

### Historical Rationale

- **Why was it built this way?** MADR and Nygard target human-maintained logs where prose status is readable and sufficient. The repo adopted the community default rather than inventing a schema.
- **What alternatives were considered?** None recorded at adoption time; the community default was taken as-is.
- **What constraints drove the design?** Familiarity and tooling compatibility with `adr-tools` and MADR linters.

### Why Change Now

- **Has the original problem changed?** Yes. The consumer is now agents and CI tooling, not only humans. Prose status blocks enum filtering and forces body scraping.
- **Is there a better solution now?** Yes. Frontmatter is parseable by Python frontmatter tooling and by agents, with no loss of the human prose section.
- **What are the risks of change?** Backfilling 72 existing ADRs; a gate that requires the enum becomes a tripwire on any un-migrated record. Mitigated by shipping the gate last and defaulting missing frontmatter to `proposed` during migration.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep prose status (status quo) | Zero migration; matches MADR/Nygard; no tooling work | No machine-readable state; every consumer re-implements prose scraping; `implemented` stays a human judgment | Does not solve the stated problem; the forces that motivated #2583 remain |
| Generated index/view over prose bodies | No per-ADR change; one script produces a current-state table | The generator must still scrape prose, the exact brittleness we want to remove; drift between bodies and index; no per-record source of truth | Moves the parsing problem rather than removing it |
| Minimal status-only frontmatter (status enum only, defer the rest) | Delivers the queryability benefit at about 20% of the schema and author burden; no supersedes/explainer/implemented to maintain until a consumer needs them | Does not solve supersession or the `implemented` gate, the two forces #2583 and #2582 raised | Partly chosen: the chosen option ships the full schema but makes every field except `status` optional and unenforced, which collapses to this option in practice until a consumer appears |
| Adopt `adr-tools` wholesale | Battle-tested `adr new -s` supersession; community tooling | Heavy dependency; imposes its directory and numbering conventions; conflicts with this repo's `ADR-NNN-slug.md` + `check_adr_uniqueness.py` gate | Disproportionate to the need; we want one field pair, not a toolchain swap |
| Lifecycle frontmatter, gate enforced immediately | Clean enum from day one | The enum gate fails every un-backfilled ADR on the first run; breaks `main` until all 72 are migrated in one change | Rejected in favor of the same schema with a phased, consumer-gated rollout (chosen) |
| **Lifecycle frontmatter, additive first, gate consumer-gated (chosen)** | Machine-readable state; one Python frontmatter query for current state; objective `implemented`; additive and reversible; Phase 1 commits only optional fields | Backfill cost (deferred); dual representation (frontmatter + prose) to reconcile; YAML in ADRs is new to this repo | Chosen: gets the schema in place now at near-zero cost, defers the expensive enforced migration until a real consumer justifies it |

### Trade-offs

The chosen option accepts a dual representation: the frontmatter `status` enum and the prose `## Status` section both exist, and they can drift. We accept that cost because the prose section carries review nuance the enum cannot, and the gate makes drift visible rather than silent. The phased rollout trades a longer migration for never breaking `main` on an un-backfilled record.

## Consequences

### Positive

- Current state is one query, no body parsing. Using the repo's existing Python frontmatter dependency (`python-frontmatter`, per ADR-042 Python-first; `yq` is not in the toolchain):

  ```python
  import pathlib, frontmatter
  for p in pathlib.Path(".agents/architecture").glob("ADR-*.md"):
      post = frontmatter.load(p)
      if post.get("status") == "accepted":
          print(post.get("id"), p.name)
  ```

- Supersession becomes a structured frontmatter edit the generator and review skills can perform and the gate can verify, replacing free-text prose edits.
- `implemented` gives the amend-vs-supersede rule (adr-best-practices.md line 42, from issue #2582 / PR #2586) an objective, git-checkable gate, and satisfies that guidance's precondition ("do not emit unless the template uses it") by defining it in the template.
- `explainer` operationalizes the lean-ADR plus linked-design-doc split (Azure Well-Architected: "the decision must be clear and stand alone").
- Structured `status` removes the brittle body-regex path, reducing the regex-edge-case and ReDoS surface that prose scraping invites.

### Negative

- Backfill of 72 existing ADRs is required before the enum gate can be enforced, and it is not purely mechanical. Several records resist a clean prose-to-enum map: ADR-072 carries conditional status ("Proposed... MUST clear five approval conditions"), and ADR-055 uses an inline `**Status**: Accepted (supersedes ADR-024, ADR-025)` format. Expect a triage pass on roughly 10 to 20 percent of records. This is the main reason backfill is deferred, not committed, by this decision.
- Dual representation (frontmatter enum plus prose `## Status`) introduces a sync burden and a new drift class. The gate flags drift but cannot author the human nuance; reconciliation is a manual author step, and hooks can fail open (ADR-066), so drift is possible in practice.
- A hand-edited `status: accepted` is a forgeable approval signal unless the Phase 3 gate binds the transition to adr-review consensus evidence. The schema is security theater until that binding exists; this ADR makes the binding a Phase 3 precondition.
- The `explainer` URL is an injection and SSRF surface if any tool auto-fetches it. Mitigated by the display-only, no-auto-fetch invariant above, which the gate must enforce.
- Authors and agents must learn one more block; malformed YAML frontmatter can fail parsing for every downstream consumer at once. Mitigated by mandating `yaml.safe_load` and validating frontmatter in CI.

### Neutral

- ADRs gain a YAML frontmatter block, aligning their on-disk shape with skills and rules that already use frontmatter.
- The prose `## Status` section is retained, so human reading habits do not change.
- `detect_adr_changes.py` already reads an optional `status:` line, so Phase 1 changes what is authoritative, not whether a `status:` line is parsed.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `adr-generator/references/adr-template.md` and `ADR-TEMPLATE.md` | Direct | Add the frontmatter block with safe defaults (Phase 1) | Low |
| `adr-generator` SKILL (Phases G3, G5) | Direct | Emit and populate frontmatter; set `status: proposed` | Low |
| `adr-review` checklist and `detect_adr_changes.py` | Direct | Already reads `status:` (line 48); extend to read `superseded-by` and validate the enum; bind `accepted` to a debate-log artifact | Medium |
| `validate-adr` gate hooks | Direct | Switch to frontmatter-parse with `yaml.safe_load`; enforce enum and bidirectional supersession only after backfill and only once a consumer exists | High |
| Existing 72 ADRs under `.agents/architecture/` | Direct | Deferred backfill with a triage pass for conditional/inline status (ADR-072, ADR-055) | Medium |
| `src/copilot-cli/` mirrors of the adr skills | Indirect | Regenerate via `build/scripts/build_all.py` | Low |
| `scripts/sync_adr_protocol.py` | Indirect | Confirm no prose-status assumption breaks | Low |

## Implementation Notes

Phased rollout. Each phase is a separate PR.

1. **Phase 0 (this ADR).** Record the decision; run `adr-review`; obtain human approval. No tooling changes.
2. **Phase 1 (additive, reversible; the only phase this decision commits).** Extend the canonical template and `adr-generator` with the frontmatter fields. Only `status` is meaningful immediately; `supersedes`, `superseded-by`, `explainer`, `implemented` are optional with safe defaults (`null`, `false`). New ADRs get machine-readable state. Existing ADRs are untouched. Queries tolerate missing fields (default to `proposed`, matching `detect_adr_changes.py` today). No gate enforcement.
3. **Phase 2 (backfill; deferred, consumer-gated).** Add frontmatter to the 72 existing ADRs. Supersession is mostly mechanical (parse `Superseded by ADR-NNN`), but a triage pass handles conditional status (ADR-072) and inline-formatted status (ADR-055). `implemented` is derived from whether a merged change references the ADR. Do not start until a concrete consumer (below) exists.
4. **Phase 3 to 4 (enforce; deferred, consumer-gated).** Flip the `validate-adr` gate to frontmatter-parse using `yaml.safe_load`, require a valid `status` enum, enforce bidirectional supersession (`X.superseded-by: Y` implies `Y.supersedes: X`), and gate a transition to `status: accepted` on the presence of an adr-review debate-log artifact under `.agents/critique/`. Ship only after Phase 2 completes, so the enum gate is never a tripwire on an un-migrated record.

**Consumer trigger and success metric.** Phases 2 to 4 proceed only when at least one concrete consumer is built: a stale-ADR detector, a generated current-state index, or a dependency viewer. Success is measured by that consumer reading frontmatter instead of scraping prose, and by zero prose-vs-frontmatter drifts surviving a gate run. If no consumer materializes, the schema stays at Phase 1 (optional, unenforced) indefinitely, which is the intended low-cost resting state.

## Related Decisions

- ADR-072 (JTBD plugin architecture): example of the conditional prose status this schema must preserve in the `## Status` section and triage during backfill.
- ADR-066 (hook fail-open reconciliation): why a CI gate alone does not guarantee drift never occurs.
- `adr-best-practices.md` line 42 (immutability rule, issue #2582 / PR #2586): authorizes the optional `implemented` field this schema defines in the template.
- Issue #2583: origin of this proposal.

## References

- Azure Well-Architected Framework, architecture decision record guidance: <https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record>
- `adr-tools` supersede flip via `adr new -s`: <https://github.com/npryce/adr-tools>
- alphagov proposal 001, RFCs and ADRs: <https://github.com/alphagov/govuk-design-system-architecture/blob/main/proposals/001-use-rfcs-and-adrs-to-discuss-proposals-and-record-decisions.md>
- arc42 section 9, decision log vs maintained overview: <https://docs.arc42.org/section-9/>
- MADR 4.0.0: <https://adr.github.io/madr/>
