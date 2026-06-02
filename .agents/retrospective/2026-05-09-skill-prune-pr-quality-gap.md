# Retrospective: feat/skill-eval-triage (M1 skill catalog prune): the /review vs /pr-quality gap

## Session Info

- **Date**: 2026-05-09 (continuation chain 1825 to 1826 to 1827 to 1828)
- **Branch**: feat/skill-eval-triage
- **Source PR**: M1 skill catalog prune. The PR ran the full lifecycle (`/spec`, `/plan`, `/build`, `/test`, `/review`) and each gate returned PASS or WARN-only.
- **Parent epic**: #1933 (lifecycle-gate convergence)
- **This issue**: #1940 (Child 7: capture the iteration-paradox evidence so the lesson is durable)
- **Commits to clean after `/review` PASS**: 5, across 2 adversarial rounds
- **Outcome**: Cleaned. The cost is the lesson: an ad-hoc `/pr-quality:all` run after a green `/review` surfaced a BLOCKED verdict plus 12 findings the lifecycle gates missed.

---

## The Headline Tension

The lifecycle ran clean. `/review` returned PASS or WARN-only on every axis. Then `/pr-quality:all`, the 7-agent adversarial gate that mirrors the CI prompts at `.github/prompts/pr-quality-gate-*.md`, was invoked by hand after `/review`. It returned **qa BLOCKED** plus 9 more findings across analyst, roadmap, and architect.

`/review` and `/pr-quality:all` are meant to evaluate the same change. They did not. The local gate passed; the backstop blocked. That gap is the iteration paradox documented in `2026-05-05-pr-1887-iteration-paradox.md`, recurring on a different PR through a different mechanism: divergent prompts produce divergent evaluation criteria, and the cheap local gate misses what the expensive backstop catches.

Two fix-loops and 5 commits were required to clean. Round 2 introduced 4 NEW regressions in the Round 1 fixes. The cost of the bot-found issues exceeded the cost that upfront authoring rigor would have carried at `/build` time.

---

## Failure Mode Classification

Per `.agents/governance/FAILURE-MODES.md`, this incident maps to two existing classes. No new class is required.

### Primary: FM-9 Confident-Incorrectness Recurrence

FM-9 shape: partial signal, premature conclusion, confident delivery, multi-round correction. The "imagined contract" variant is the most damaging: an artifact references entities that do not exist or carry different state than the author believed.

This PR exhibited FM-9 in two distinct forms:

1. **Imagined contract against deleted skills**. The eval fixtures, the `doc-accuracy` description, and the `ADR-040` Tier-2 enumeration all referenced skills (`workflow`, `doc-coverage`, `doc-sync`) that the same M1 prune deleted. The text asserted current-state parity with a catalog it had just changed. The author modeled the catalog from memory instead of re-reading it after the prune. This is the same root cause FM-9 names for PR #1887: design against a remembered contract rather than the canonical source.

2. **Imagined verification mechanism**. REQ-006 AC5 named a "pre-push drift detection hook" and a script (`build/scripts/detect_skill_drift.py`) that does not exist. The acceptance criterion was unenforceable as written because it pointed at an artifact the author assumed would exist.

### Contributing: FM-4 False Completion Markers

`/review` returned PASS. The change did not satisfy the acceptance criteria that `/pr-quality:all` then checked. Success was reported by the local gate before the artifact was verified against the stricter adversarial prompts. FM-4's enforcement table calls for a verifier that produces an artifact a tool can inspect; the gap here is that `/review` and the CI backstop ran different verifiers, so a PASS from one did not bind the other.

The mechanism that produced the false completion (`/review` passing on content the backstop blocks) is divergent-prompt drift, which is the structural target of epic #1933. The fix is at the convergence layer, not at the agent-narration layer.

---

## Phase 0: Data Gathering

### The 5 fix commits

All five commits live on `feat/skill-eval-triage`. SHAs and load-bearing message content:

| # | SHA | Title | What it fixed |
|---|-----|-------|---------------|
| 1 | `7993ed9f` | `test(evals): convert deleted-skill triage prompts to negative-routing fixtures` | CI QA gate (Gate 1, F1) and analyst gate (F1, F5) flagged `tests/evals/skills/triage-prompts.json`: 18 expected-answer strings recommended deleted skills (workflow, doc-coverage, doc-sync) to evaluators as if active. Rewrote all 18 plus 2 codebase-documenter cross-references to redirect callers to `doc-accuracy` or lifecycle slash commands. Refs #1932. |
| 2 | `f937a114` | `docs(doc-accuracy): clarify description as canonical replacement for deleted skills` | CI QA gate F3 and analyst gate F5 flagged stale present-tense phrasing in `doc-accuracy/SKILL.md`. Reworded to past-tense lineage referencing the 2026-05-09 M1 prune. Mirrored to `src/copilot-cli/skills/` and `docs/SKILL-AUTHORING.md` per the canonical-source-mirror rule. Also fixed pre-existing MD040 lint errors (fenced blocks missing a `text` language identifier). |
| 3 | `a3c82a66` | `docs(spec): REQ-006 AC5 verifiable mechanism + Deferred section + session 1828 log` | CI QA gate F2 flagged REQ-006-AC5 naming a non-existent hook and script (`build/scripts/detect_skill_drift.py`). Repointed AC5 at the real mechanism: round-trip idempotence of `build/scripts/generate_skills.py`. Roadmap gate flagged deferred follow-ups listed in the session log but not in REQ-006; added a Deferred section. Session 1828 log included for the session-protocol gate. |
| 4 | `adfe9f5d` | `docs(adr): ADR-040 + plugin.json + PLAN factual corrections from /pr-quality:all` | Three factual corrections (architect Important, analyst F3, roadmap WARN): ADR-040:119 listed `doc-sync` (deleted) at count 12 (44.4%), corrected to 11 skills (42.3%); `plugin.json` named literal "23 agents, 23 slash commands, 35 lifecycle hooks, 69 reusable skills", all four stale (real 25/24/30/67), so numeric assertions were dropped; PLAN Decision Log gap filled. |
| 5 | `4e077b50` | `docs(adr): Round 2 fixes - ADR-040 percentage consistency + fixture hedge` | Round 2 surfaced regressions from the Round 1 fixes: ADR-040 Tier 2 had been recalculated to 42.3% (/26 denominator) while Tier 1 (40.7%) and Tier 3 (14.8%) still used /27; rows summed to 97.8% with mixed denominators. Recalculated all three tiers to /26 (42.3% / 42.3% / 15.4%, sum 100%). Added inline caveats on historical S356 counts. Removed hedging language from an eval fixture. |

### Round 1 adversarial verdicts (after `/review` PASS)

| Gate | Verdict | Findings |
|------|---------|----------|
| qa | **BLOCKED** | 3 (eval orphans, AC5 unenforceable, doc-accuracy description tense) |
| analyst | WARN | 4 (eval orphans, ADR-040 stale enumeration, expected-answer staleness, doc-accuracy lacks tests) |
| roadmap | WARN | 3 (workflow PRUNE Decision Log gap, downstream comms, REQ-006 deferred section) |
| architect | PASS (2 low) | 2 (ADR-040 stale, plugin.json literal counts) |
| security | PASS | 0 |
| devops | PASS | 0 |
| session-protocol | PASS | 0 |

### Round 2 adversarial verdicts (after the Round 1 fixes)

| Gate | Verdict | Regressions introduced by Round 1 |
|------|---------|-----------------------------------|
| architect | WARN | ADR-040:118,120 denominator inconsistency (one tier recalculated to /26, the other two left at /27) |
| analyst | WARN (R2, R3) | ADR-040:222,229 historical S356 counts read as inconsistent with the current-state table; eval fixture carried hedging language |
| qa / roadmap / security / devops / session-protocol | PASS | None |

Round 2 surfaced 4 NEW regressions, all inside the Round 1 fixes. The denominator drift is the cleanest example: changing one cell of the ADR-040 percentage table without recomputing the other two cells broke internal consistency that had been correct before the fix.

---

## Phase 1: What Actually Happened (timeline)

1. **`/build` through `/review`**: the M1 prune deleted skills (workflow, doc-coverage, doc-sync) and authored or edited fixtures, a SKILL.md description, REQ-006, ADR-040, and plugin.json. Several of those artifacts still described the pre-prune catalog. `/review` returned PASS or WARN-only on every axis.
2. **Ad-hoc `/pr-quality:all` after `/review`**: invoked by hand as a sanity check. qa returned BLOCKED, analyst and roadmap WARN, architect PASS-with-2-low. 12 findings total. The local gate and the backstop disagreed.
3. **Round 1 fixes (`7993ed9f`, `f937a114`, `a3c82a66`, `adfe9f5d`)**: addressed the 11 findings. One fix (commit 4) recalculated one cell of the ADR-040 percentage table.
4. **`/pr-quality:all` Round 2**: caught that the single-cell recalculation had left the table internally inconsistent (mixed /26 and /27 denominators), plus a hedging-language regression in the eval fixture.
5. **Round 2 fix (`4e077b50`)**: recomputed the entire table to a single denominator and removed the hedge. Clean.

---

## Phase 2: Root Cause

### Five Whys: Why did a green `/review` ship content the backstop blocked?

1. **Why?** `/review` evaluated the change with one set of prompts; `/pr-quality:all` evaluated it with the CI prompts at `.github/prompts/pr-quality-gate-*.md`, which check stricter and partly different criteria.
2. **Why?** The two surfaces evolved from separate prompt sources, so their evaluation criteria drifted apart over time.
3. **Why?** There was no single canonical source of truth for the review axes; `/review` and the CI prompts were maintained independently.
4. **Why?** When each surface is edited in isolation, an improvement to one bypasses the other, and divergence accumulates as cruft on both.
5. **Why?** The model that local `/review` is the primary, strictly-stronger gate and CI is the backstop was the target state, not the implemented state, at the time of this PR.

**Root cause**: divergent prompts produce divergent evaluation criteria. A PASS from the cheaper gate does not bind the stricter one, so the iteration paradox tax lands at backstop time (or worse, at CI time) instead of at `/build` time. This is the exact structural problem epic #1933 exists to fix.

### Five Whys: Why did the fixtures, ADR-040, and plugin.json reference deleted skills?

1. **Why?** The author modeled the catalog from memory while editing artifacts that had to agree with the post-prune state.
2. **Why?** The prune (deleting workflow, doc-coverage, doc-sync) and the artifact edits happened in the same PR, so "current state" was a moving target the author did not re-read after each change.
3. **Why?** No artifact pinned the canonical catalog so that a stale reference would fail at write time.
4. **Why?** The orphan-reference and count-drift checks that would catch "this text names a skill that no longer exists" did not yet exist as a gate (`orphan-ref-validator` is Child 6, #1939/#1994).
5. **Why?** Net-new authoring rigor (re-read the canonical source after you change it, before you assert parity) is the FM-9 lesson from PR #1887; it had been captured as a rule but not yet enforced by a validator on this content class.

**Root cause**: FM-9 imagined contract. The author asserted parity with a catalog the same PR had just mutated, without re-reading it. The canonical-source-mirror rule names this exact anti-pattern; this PR is a fresh instance of it on skill-catalog content rather than on a regex or schema.

### Why Round 2 introduced regressions

The Round 1 ADR-040 fix changed one tier's percentage to a new denominator (/26) without recomputing the other two tiers (left at /27). The table summed to 97.8% with mixed denominators. The lesson is mechanical: when you change one cell of a table whose cells share a denominator or must sum to a constant, recompute the entire table, not the one cell that drew the finding.

---

## Phase 3: Impact

| Affected area | Severity | Impact |
|---------------|----------|--------|
| Eval harness honesty | High | 18 expected-answer strings in `triage-prompts.json` recommended deleted skills to evaluators; the eval contract scored old-name references incorrectly until `7993ed9f`. |
| ADR-040 factual accuracy | Medium | Tier enumeration and percentage table named a deleted skill and, after a partial fix, summed to 97.8% with inconsistent denominators. Two commits (`adfe9f5d`, `4e077b50`) to reach a consistent table. |
| Spec enforceability | Medium | REQ-006 AC5 named a non-existent hook and script; the acceptance criterion was unverifiable until repointed at `generate_skills.py` idempotence (`a3c82a66`). |
| Plugin manifest accuracy | Low | `plugin.json` carried four stale literal counts (23/23/35/69 vs real 25/24/30/67); numeric assertions dropped to stop future drift (`adfe9f5d`). |
| Documentation lineage | Low | `doc-accuracy/SKILL.md` and its mirrors used present tense for deleted-skill replacement; reworded to past-tense lineage (`f937a114`). |
| Iteration cost | High | 5 commits across 2 adversarial rounds, with Round 2 introducing 4 regressions, where upfront re-read at `/build` time would have carried near-zero marginal cost. |

---

## Phase 4: Lessons (high-confidence)

1. **`/review` and `/pr-quality:all` use different prompts; local can pass while CI fails.** Until the two converge on a single canonical source (epic #1933), a green `/review` is necessary but not sufficient. Run `/pr-quality:all` before relying on a PASS.
2. **The iteration paradox compounds across the lifecycle chain.** Net-new authoring is cheaper to do at `/build` time than `/review` time, which is cheaper than `/pr-quality:all` time, which is cheaper than CI bouncing the PR. Each handoff multiplies the cost of a knowable defect.
3. **Re-read the canonical source after you change it, before you assert parity.** A PR that deletes skills and then edits artifacts to agree with the catalog must re-read the post-prune catalog, not the author's memory of it. This is the FM-9 lesson from PR #1887, recurring on skill-catalog content.
4. **Deferral is valid only if the follow-up is tracked AND the source artifact is not modified by the in-flight PR.** The ADR-040 amendment was deferred from session 1827 with documented rationale, but the deferred state itself surfaced as a finding in the next round because the in-flight PR touched ADR-040.
5. **When you change one cell of a table, recompute the entire table.** Changing one of three ADR-040 percentages without recomputing the other two broke internal consistency that had been correct before the fix.

---

## Phase 5: Remediation

Every follow-up below is tracked by a child of epic #1933 or by an existing artifact. This retro authors no new code; the remediation work lives in Children 1 to 6.

| Remediation | Tracking | Status |
|-------------|----------|--------|
| Single source of truth for review prompts at `.claude/review-axes/{axis}.md`; make `/review` a strict superset of CI | #1934 (Child 1) | Shipped (PR #1965) |
| `/review` wires existing repo artifacts so it catches what the backstop catches | #1935 (Child 2) | Tracked |
| Promote review concepts to vendor-safe `.claude/` paths | #1936 (Child 3), #1937 (Child 4) | Tracked |
| `/ship` collapses to "did /review pass on this SHA?" so the strict local gate is the gate that ships | #1938 (Child 5) | Tracked |
| `orphan-ref-validator` skill: catch text that names a deleted skill or stale count at write time | #1939 (Child 6), #1994 (Child 6 PR2: `--enforce-counts`, broad script-path, `/test` Gate 5 wiring) | Tracked; skill exists at `.claude/skills/orphan-ref-validator/` |
| ADR-040 staleness was the proximate trigger for the architect and analyst findings | `.agents/architecture/ADR-040-skill-frontmatter-standardization.md` | Corrected in `adfe9f5d`, `4e077b50` |
| Eval-harness orphan detection (longer-term fix for the deleted-skill fixture problem) | #1932 (referenced by `7993ed9f`) | Tracked |

The canonical-source-mirror rule (`.claude/rules/canonical-source-mirror.md`) already encodes the FM-9 prevention pattern for "match/mirror/align" claims. The gap this PR exposed is that the rule did not yet bind skill-catalog references the way `orphan-ref-validator` (#1939) will.

---

## Closing Note

The push-guard and evidence-standards work from PRs #1887 and #1897 named confident-incorrectness as the failure mode and built rules to prevent it. This PR is a fresh instance of the same mode on a new content class: skill-catalog references asserting parity with a catalog the same PR had just mutated. The durable lesson is not "run more gates"; it is "the local gate and the backstop must run the same criteria, with local being the strict superset", which is precisely the convergence epic #1933 implements. Land that convergence and a green `/review` becomes a binding signal instead of an optimistic one.
