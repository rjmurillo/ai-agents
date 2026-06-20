# ADR-073 Machine-Readable ADR Lifecycle Frontmatter, Multi-Agent Debate Log

**ADR**: `.agents/architecture/ADR-073-adr-lifecycle-frontmatter.md`
**Triggering context**: Issue #2583 (P1, `adr-followup`); autopilot chose to author the proposed ADR to start adr-review.
**Date**: 2026-06-13
**Reviewers**: architect, critic, independent-thinker, security, analyst, high-level-advisor
**Checklist**: Zimmermann 7-question ADR review

---

## Process note

The six reviewers ran as parallel sub-agents. The agents execute in a sibling worktree and could not open the uncommitted ADR-073 file, so three (architect, critic, analyst) returned a procedural BLOCK on "file not found" while still delivering substantive observations from the proposal context, and the analyst additionally ran real evidence checks against the committed tree. The orchestrator verified the two highest-severity factual claims directly (see Resolution). The BLOCKs were procedural, not substantive rejections.

---

## Round 1, Initial Review

### architect: BLOCKED (procedural) + substantive observations

- [P1] `detect_adr_changes.py` already parses an optional `status:` line (`_get_adr_status`, lines 40 to 48) and defaults to `proposed`. Adding frontmatter does not break it; it is consumed correctly. Positive.
- [P1] Dual representation (frontmatter + prose `## Status`) is a real drift risk; the "frontmatter wins, gate flags drift" rule is sound only if the gate is blocking, not advisory.
- [P2] Canonical `ADR-TEMPLATE.md` must be updated or the convention will not propagate.
- [P2] ADR-073 staying in current format while proposing the new format is acceptable for a transition, but should state completion criteria for when ADR-073 itself adopts the schema.

### critic: BLOCK (procedural)

- [P1] ADR should document the current parser state (`detect_adr_changes.py`) as the baseline and specify what changes.
- [P2] ADR-072's conditional status ("Proposed... MUST clear five conditions") is a concrete case a single enum cannot capture; use it as a test case.

### independent-thinker: DISAGREE-AND-COMMIT (dissent)

- [P0] Claimed the named consumer `detect_adr_changes.py` does not exist (searched `scripts/` only). REFUTED by orchestrator: the file is under `.claude/skills/adr-review/scripts/`.
- [P1] The "generated index" alternative was rejected without quantifying maintenance cost; a generated index scrapes once and writes structured data.
- [P1] Dual representation has no enforcement beyond a fail-open-capable CI gate (ADR-066); define a reconciliation process or generate prose from frontmatter.
- [P1] A minimal status-only frontmatter option is missing from the alternatives table (YAGNI on supersedes/explainer/implemented until a consumer exists).
- [P2] Cost/benefit unquantified; no success metric (Zimmermann Q7).

### security: DISAGREE-AND-COMMIT (dissent)

- [P1] `status: accepted` is a forgeable approval signal: a hand-edit bypasses the debate if the gate trusts the enum (CWE-284). Bind `accepted` to consensus evidence.
- [P1] `explainer` external URL is an SSRF / context-poisoning surface (CWE-918) if tooling auto-fetches. Constrain to allowlist and mark no-auto-fetch.
- [P2] Mandate `yaml.safe_load` (CWE-502) for the 72+ file parse path.
- [P2] Enforce bidirectional supersession (`X.superseded-by: Y` implies `Y.supersedes: X`) to prevent orphan/hijack (CWE-345).
- [CREDIT] Structured frontmatter removes brittle body-regex (reduces ReDoS / regex-edge surface).

### analyst: BLOCKED (procedural) + evidence checks

1. CONFIRMED: `detect_adr_changes.py` `_get_adr_status` parses `^status:\s*(.+)$`, defaults to `proposed`.
2. PARTIAL: 72 ADRs; prose-to-enum is messy. Quoted ADR-072 (conditional) and ADR-055 (`**Status**: Accepted (supersedes ADR-024, ADR-025)`); estimates 10 to 20 percent need triage.
3. Flagged `implemented` as having "no precedent" in best practices. REFUTED by orchestrator (see Resolution): adr-best-practices.md line 42 authorizes an optional `implemented` field.
4. REFUTED the `yq` example: the toolchain uses `PyYAML` + `python-frontmatter`, not `yq` (ADR-042 Python-first).
5. PARTIAL: no machine-readable ADR index exists today (HANDOFF read-only), so the schema is not redundant.

### high-level-advisor: DISAGREE-AND-COMMIT (strong dissent)

- [P1] Stop at Phase 1 (additive optional fields). Backfilling 72 ADRs and building a CI gate is cost with no consumer today.
- [P2] Re-scope #2583 from P1 to P2; reserve heavyweight ADR governance for architecturally consequential decisions.
- Minimal valuable core: update the template with optional frontmatter, respect it in the generator, do not backfill, do not gate, until a consumer exists.

---

## Round 2, Consolidation

**Consensus (no substantive block):** the schema is sound; the defects are scope and rigor, not direction. Votes: 3 DISAGREE-AND-COMMIT (security, independent-thinker, high-level-advisor), 3 procedural BLOCK on file-not-found (architect, critic, analyst) whose substantive notes are addressable.

**Two findings required orchestrator verification before resolution:**

- `implemented` precedent (analyst P0): VERIFIED present. `adr-best-practices.md` line 42: "may add optional `implemented` metadata that flips at the first merged change... Do not emit that field unless the project's ADR template or existing ADRs already use it." The analyst's "no precedent" is wrong; the real point is to cite it precisely and note ADR-073 is the vehicle that satisfies the "template uses it" precondition.
- Phantom consumer (independent-thinker P0): REFUTED. `.claude/skills/adr-review/scripts/detect_adr_changes.py` exists and parses `status:`.

---

## Round 3, Resolution (P0/P1 incorporated into the ADR)

| # | Finding (agent) | Resolution in ADR-073 |
|---|---|---|
| 1 | Scope too large; stop at Phase 1 (advisor, independent) | Decision now commits only Phase 1; Phases 2 to 4 deferred and consumer-gated; success metric + consumer trigger added |
| 2 | `status: accepted` forgeable (security) | Decision + Negatives: Phase 3 gate binds `accepted` to an adr-review debate-log artifact under `.agents/critique/` |
| 3 | `explainer` auto-fetch risk (security) | Decision + Negatives: display-only, no-auto-fetch invariant; gate constrains to in-repo/org URLs |
| 4 | `yq` not in toolchain (analyst) | Positive consequence rewritten to a `python-frontmatter` example; ADR-042 cited |
| 5 | Backfill not mechanical (analyst, critic) | Negatives + Impact + Phase 2: triage pass for ADR-072 (conditional) and ADR-055 (inline) |
| 6 | `implemented` precedent imprecise (analyst) | Context + Related: cite adr-best-practices.md line 42 and the "template uses it" precondition |
| 7 | Minimal status-only alternative missing (independent) | Added to the alternatives table; chosen option collapses to it until a consumer appears |
| 8 | `yaml.safe_load` (security) | Phase 3 to 4 mandates `yaml.safe_load` |
| 9 | Bidirectional supersession (security) | Phase 3 to 4 enforces `X.superseded-by: Y` implies `Y.supersedes: X` |
| 10 | Drift reconciliation unowned (independent, architect) | Decision: frontmatter authoritative, gate flags, author reconciles prose; ADR-066 fail-open cited |
| 11 | Parser already reads `status:` (architect, analyst) | Context + Neutral + Impact reflect that Phase 1 changes authority, not whether a `status:` line is parsed |

P2 items (re-prioritize #2583; template completion criteria) are documented, non-blocking.

---

## Post-Review PR Thread Resolution

| Finding | Resolution in ADR-073 |
|---|---|
| Reviewer noted that the "Why Change Now" section still implied `yq` support and used a query-specific fallback syntax. | Rephrased the section to name Python frontmatter tooling and agents as the parse targets, and replaced the query-specific fallback with tool-agnostic migration behavior: default missing frontmatter to `proposed`. |

---

## Round 4, Convergence

| Agent | Final position |
|---|---|
| architect | Concerns addressable; observations incorporated (parser, template, drift). No substantive block. |
| critic | Baseline parser documented; ADR-072 conditional case captured. |
| independent-thinker | DISAGREE-AND-COMMIT conditions met: minimal alternative added, drift reconciliation defined, phantom-consumer refuted. |
| security | DISAGREE-AND-COMMIT conditions met: `accepted` binding + `explainer` no-fetch + safe_load + bidirectional supersession all added. |
| analyst | Evidence-driven fixes incorporated (yq to python-frontmatter, triage backfill, `implemented` citation). |
| high-level-advisor | Core dissent honored: scope committed to Phase 1 only; 2 to 4 consumer-gated. |

**Verdict: NEEDS-REVISION resolved to Proposed (revised).** No P0 survives. The ADR remains `Proposed` pending human acceptance; per governance, an agent cannot move an ADR to `Accepted`. The revision is recorded in the ADR Status section.

---

## Dissent captured (Disagree-and-Commit)

- high-level-advisor: still regards Phases 2 to 4 as discretionary; commits because the decision now explicitly defers them and makes the resting state Phase 1.
- security: commits on the condition that the Phase 3 gate, when built, implements the `accepted`-binding and `explainer` no-fetch rules; if those are dropped at implementation time, the gate is security theater.

---

## Post-Acceptance Metadata Alignment Review (2026-06-20)

PR #2692 updates ADR-073 metadata after shipping the Phase 1 implementation for
#2583:

- `implemented: false` to `implemented: true`
- `## Date` from `2026-06-13` to `2026-06-19`

Six reviewer positions:

| Agent | Verdict | Rationale |
|---|---|---|
| architect | ACCEPT | Phase 1 ships in PR #2692; frontmatter and prose now agree. |
| critic | ACCEPT | Metadata consistency fix; no decision, driver, or consequence change. |
| independent-thinker | ACCEPT | Factually accurate post-implementation metadata update. |
| security | ACCEPT | Non-executable metadata; no security attack surface. |
| analyst | ACCEPT | Internal consistency restored; no semantic ADR change. |
| high-level-advisor | ACCEPT | Minimal, reversible housekeeping update. |

**Verdict: ACCEPT.** No P0 or P1 blockers.
