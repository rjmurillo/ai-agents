# ADR Debate Log: ADR-010 and ADR-018 Status Reconciliation

## Summary

- **Rounds**: 1 of 10 (independent review plus one convergence vote)
- **Outcome**: Consensus. Both roles Accept.
- **Final Status**: ADR-010 `deprecated` (implemented false). ADR-018 stays `accepted` with `implemented` flipped to true.
- **Review independence**: one model played the architect and critic roles in separate passes. This is not two independent reviews. Treat the votes as one reviewer's two lenses.
- **Panel**: reduced (architect and critic). The change touches no executable enforcement and no rule another gate reads. The lifecycle validator reads `status` and `implemented`, and Phase 0 ran it on the edited records.
- **Work item**: issue #5292. The repo owner delegated the design choices on 2026-10-11.

## Phase 0: Related Work

| Item | State | Relevance |
|---|---|---|
| #5292 | open | Seven ADRs flagged. ADR-028 was fixed by #5283. Five are `proposed` with `implemented: true`. ADR-010 and ADR-018 are `accepted` with `implemented: false`. |
| #5200 | open | Same pairing for six other ADRs. Its review notes call `proposed` with `implemented: true` deliberate per ADR-098. |
| `scripts/validation/check_adr_lifecycle.py` docstring | merged | States the pairing "is intentionally not violations here" and cites ADR-098. |
| `.project-toolkit/critique/ADR-073-phase2-backfill-debate-log.md` | merged | Says ADR-010 is the only clean "accepted and never built" record. Says ADR-018 chose a no-op on purpose and must not be triaged as unbuilt work. |
| Epic #183 | closed, not planned 2026-03-01 | ADR-010's own origin. |
| Issue #172 | closed, completed 2026-02-24 | Named by ADR-010 Phase 5 step 2. No scoring artifact shipped. |

## Evidence Gathered

- The five `proposed` records (ADR-038, 049, 059, 067, 070) still carry `implemented: true`. ADR-098's Status section says the pairing is deliberate because accepting a governance ADR is a maintainer act. No edit is owed.
- ADR-010 search: `git grep` for "evaluator-optimizer" lists only ADR text, governance docs, and indexes. A grep for the 25 percent four-criterion rubric and for "Actionability" over `templates/`, `scripts/`, and `.claude/skills/` finds no scorer. The two `score >= 70` hits (`score_atomicity.py:175`, `triage_skill_request.py:754`) are unrelated thresholds.
- ADR-010 citations: ADR-087 cites the three-iteration cap as background. `AI-REVIEW-MODEL-POLICY.md:271` leaves "Integrate with ADR-010 Quality Gates framework" unchecked. No rule file, `AGENTS.md`, or `CLAUDE.md` cites ADR-010.
- ADR-018 search: no `github-*-cache.md` under `.serena/memories/`. The one file matching `*cache*` in the GitHub topic, `.serena/memories/github/github-cli-labels-cache.md`, holds `gh label` how-to notes, not cached API data. `git grep` for `lru_cache`, `functools.cache`, and `_CACHE` over `.claude/skills/github` and `scripts/github_core` returns nothing.

## Phase 1: Independent Reviews

### architect

ADR-010 options:

| Option | Blast radius | Verdict |
|---|---|---|
| Keep `accepted`, `implemented: false` | None, but leaves a MUST nobody follows and keeps "is this binding" ambiguous for 1 record | Rejected. This is the defect the issue names. |
| Implement the loop | Orchestrator, independent-thinker, metrics, session logs | Rejected. The parent epic closed as not planned. This is an ocean. |
| Supersede | Needs a successor decision. ADR-087 bounds a different question (held-out evidence) and does not replace the rubric or the cap | Rejected. No successor exists to name. |
| Deprecate | One record, plus the generated index row | Chosen. `deprecated` is the enum value for a record that was accepted and no longer binds. |

ADR-018: `implemented` is false only because the Phase 2 derivation looks for an artifact. The decision's correct implementation is the absence of a git-tracked cache. Deprecating it would claim the decision lost force, which is false. Adding a schema value is a larger change to ADR-073 for one record. Flipping the boolean with a prose note is the narrowest correct fix.

### critic

- Does deprecation lose information? ADR-087 and ADR-023 link to ADR-010. A deprecated record stays in the tree, and the new Status section names ADR-087's use. No link breaks.
- Is `implemented: true` for ADR-018 a stretch? ADR-073 says the field flips at the first merged change. No change merged. The note in the record says the value reflects execution as written, not a merged artifact. This is a stated deviation, and the alternative leaves a false negative that the Phase 2 log already told readers to ignore.
- Is a status edit by an agent a forged approval signal? ADR-073 binds only the transition to `accepted`. Neither edit moves a record to `accepted`. The repo owner delegated both choices on #5292.
- Do the five `proposed` records need touching? No. Editing them would contradict ADR-098 and the validator docstring.

| Issue | Priority | Description |
|---|---|---|
| C1 | P2 | The ADR-018 note depends on a search scoped to the `github` skill and `scripts/github_core`. The note names that scope instead of claiming repo-wide absence. Addressed. |

## Phase 4: Convergence Vote

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Accept |

### Dissent

None recorded. The single-model caveat in the Summary applies.

## Strategic Check

- Chesterton's Fence: PASS. ADR-010's origin (Epic #183) is read, and its closure is the evidence the fence guards nothing live.
- Path Dependence: PASS. Both edits are reversible by one frontmatter line.
- Core vs Context: N/A.
- Second-System Effect: PASS. No new mechanism or schema value is added.
