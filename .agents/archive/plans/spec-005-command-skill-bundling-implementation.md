# Execution Plan: SPEC-005 Command-Skill Bundling Implementation

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-05-06 |
| **Owner** | agent (Claude Opus 4.7) |
| **Complexity** | Medium |
| **Source spec** | REQ-005 / DESIGN-005 / TASK-005 |
| **Authoring branch** | `docs/spec-005-command-skill-bundling` (commit `db9f24cb`) |
| **Implementation branches** | TBD per milestone (one branch per milestone) |

## Objectives

### M1: Test Infrastructure + Shared Registry [size: M, ~4-6h]

- [ ] T5-0: Verify all 13 unique skill directories exist under `.claude/skills/`
- [ ] Create `scripts/validation/bundle_registry.py` with 15 (file, skill) pairs
- [ ] Create `tests/test_command_bundles.py` parametrized by registry
- [ ] Add `validate_command_bundle_coverage()` to `scripts/validation/pre_pr.py`, but **gated behind `BUNDLE_CHECK_ENFORCED=1` env var** (default `0`); when disabled, the function emits an INFO-level note and returns 0 findings
- [ ] Unit tests for the new pre_pr function (all-present / one-missing / empty-registry, all run with env var both `0` and `1`)
- [ ] Verify `pytest tests/test_command_bundles.py` is **marked xfail** (or `@pytest.mark.skip` with a reason citing M2/M3 dependency); main stays GREEN throughout M1
- [ ] M3 closing commit flips the xfail / skip and sets `BUNDLE_CHECK_ENFORCED=1` as the default once all 15 registry rows pass
- [ ] **CI wire-up verification**: confirm `scripts/validation/pre_pr.py` is invoked from a CI workflow on PRs that touch `.claude/commands/**` (mitigates pre-mortem F2). If not wired, open follow-up issue or extend a workflow to call it. Acceptance: a deliberate broken-bundle test PR fails CI, not just local pre-commit.
- [ ] **CI path-anchor verification**: run pytest from a non-repo-root directory locally to confirm `Path(__file__).resolve().parent.parent / "scripts/validation"` resolves correctly regardless of CWD (mitigates pre-mortem F4).
- [ ] **CWE-78 test uses an independent regex**, NOT the bundle parser (mitigates pre-mortem F5). The CWE-78 test greps `git log -- "<` literally and asserts the quoted-path form for every git log invocation in build.md and review.md.

### M2: Simple-Binding Commands [size: M overall; per-task S]

- [ ] T5-1 [S]: Edit `spec.md` (always-bundle session-init preflight; skill owns missing-marker)
- [ ] T5-2 [S]: Edit `ship.md` (always-bundle session-end + reflect with min-delta guard)
- [ ] T5-3 [S]: Edit `plan.md` (replace inline analyst/critic prompts with pre-mortem + decision-critic skills)
- [ ] T5-7 [S]: Edit `pr-review.md` (conditional merge-resolver) and `research.md` (always context-gather)
- [ ] **M2 EXIT**: each task removes the `xfail` mark from its corresponding registry rows so those tests now expect-pass:
  - 7 rows un-xfailed: `spec.md/session-init` (always-bundle), `ship.md/session-end` (always-bundle), `ship.md/reflect` (with min-delta guard prose), `plan.md/pre-mortem`, `plan.md/decision-critic`, `pr-review.md/merge-resolver` (runtime-conditional on gh state), `research.md/context-gather`
  - 8 rows still xfail (cleared in M3): all `build.md/*` (3, includes runtime-conditional chestertons-fence), all `test.md/*` (3, includes complexity-tier-conditional threat-modeling), all `review.md/*` (2, includes runtime-conditional chestertons-fence)
  - CI stays GREEN throughout M2 because xfails count as passes

### M3: Complex-Binding Commands [size: M overall; per-task M]

- [ ] T5-4 [M]: Edit `build.md` (preflight chain: context-gather + steering-matcher + conditional chestertons-fence). Sized M (not S) because of conditional logic per R2.
- [ ] T5-5 [S]: Edit `test.md` (Gate 3 threat-modeling, Gate 6 slo-designer + observability)
- [ ] T5-6 [M]: Edit `review.md` (Axis 6 doc-accuracy, Axis 1 conditional chestertons-fence). Sized M (not S) because of conditional logic per R2.
- [ ] M3 EXIT:
  - All `xfail` marks removed from `tests/test_command_bundles.py`; full registry test passes
  - `BUNDLE_CHECK_ENFORCED` default flipped to `1` in `scripts/validation/pre_pr.py`
  - `python3 scripts/validation/pre_pr.py` (with the new default) produces 0 BLOCKING findings
  - CWE-78 path-quoting test passes (independent regex check; build.md and review.md git log calls quote paths)

## Implementer Quick-Start (minimum context to start M1)

**The 15 (file, skill) pairs to encode in `bundle_registry.py`**:

```python
BUNDLE_REGISTRY = [
    ("spec.md",      "session-init"),
    ("ship.md",      "session-end"),
    ("ship.md",      "reflect"),
    ("plan.md",      "pre-mortem"),
    ("plan.md",      "decision-critic"),
    ("build.md",     "context-gather"),
    ("build.md",     "steering-matcher"),
    ("build.md",     "chestertons-fence"),
    ("test.md",      "threat-modeling"),
    ("test.md",      "slo-designer"),
    ("test.md",      "observability"),
    ("review.md",    "doc-accuracy"),
    ("review.md",    "chestertons-fence"),
    ("pr-review.md", "merge-resolver"),
    ("research.md",  "context-gather"),
]
```

**The static-parser contract** (parser passes when ALL of these hold for each registry row):

1. The exact string `Skill(skill="<skill>")` appears in `.claude/commands/<file>`.
2. A `BUNDLE: <command-base> -> <skill>` text fragment appears within 5 lines of the `Skill(...)` call (where `<command-base>` is the file name without `.md`).

**`sys.path` snippet for `tests/test_command_bundles.py`** (anchor to repo root regardless of CWD):

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "validation"))
from bundle_registry import BUNDLE_REGISTRY  # noqa: E402
```

**AC-13 verification stance**: AC-13 (warn-and-continue on skill failure) is verified by **manual code review** at PR time, not by the static parser. The parser cannot evaluate prose semantics. The PR template's review checklist must include "AC-13: each new `Skill(...)` invocation is followed by a warn-and-continue note." This is a deliberate gap, not an oversight.

## Sequencing Reconciliation vs TASK-005

TASK-005 lists T5-1 through T5-7 as fully parallel after T5-0 (TASK-005 §Sequencing). This plan **adds** a M2/M3 split that introduces a sequencing constraint TASK-005 does not. Rationale: M2 (simple-bind) and M3 (conditional-bind) have different review difficulty; landing them as separate PRs reduces review fatigue and isolates blast radius for conditional-logic iteration. **Within** M2 and **within** M3, tasks remain fully parallel as TASK-005 documents. The plan's M2/M3 split is a PR-bundling decision, not a per-task ordering constraint. TASK-005 itself does not need amendment; the plan supersedes only the inter-task PR grouping.

## M1 Stays Green (replaces prior "Continuity Rule")

**Decision (2026-05-06, post-adversarial review)**: M1 no longer ships red. The earlier 5-business-day continuity rule was a social contract enforcing what a feature flag enforces mechanically. Replaced by:

- `BUNDLE_CHECK_ENFORCED` env var (default `0`) gates the `validate_command_bundle_coverage()` BLOCKING behavior.
- `tests/test_command_bundles.py` is marked `@pytest.mark.xfail(reason="awaits M2/M3 command edits")` for the registry rows that haven't been edited yet.
- M2 turns each row's `xfail` into expected-pass as commands are edited.
- M3 closing commit flips the env var default to `1` and removes the xfail marks.

**Why**: a CI signal that lies (red expected) is worse than no signal (`release-it.md` §"Health Check Integrity"). Contributors training themselves to ignore red CI is a smell. Mechanical enforcement beats social agreement.

## Open Questions From Adversarial Review (require user assent before action)

The independent-thinker agent challenged three premises that, if accepted, amend REQ-005 / DESIGN-005 / TASK-005 rather than just this plan. Surfaced for explicit user decision; no plan or spec edits applied.

### Q1 (C1): Bundle-via-prose vs. routing-layer hook, RESOLVED 2026-05-06

**Challenge raised**: Editing 7 markdown files is a workaround for missing skill-routing infrastructure. A SessionStart/PreToolUse hook + `commands.yaml` would replace markdown edits + parser + pre_pr check with one hook + one config file.

**Resolution: ship as-spec'd. Independent-thinker C1 was wrong on premise.** PR #1894 (`feat(agents,github-skill): reviewer-stronger asymmetry + verifiable status claims`) is the matching precedent at the agent layer: it edits `templates/agents/{implementer,qa,critic}.shared.md` to ship behavior via prose framing (Reviewer Asymmetry note, fresh-context adversarial framing, Adversarial Coverage Checklist), no skill-routing layer built, no "commands.yaml" abstraction introduced. Bundle-via-prose IS the house style for cross-cutting agent and command behavior. SPEC-005 is the same pattern at the command layer.

**Rejection rationale**: building a hook + YAML registry to do what 7 markdown edits already do would (a) duplicate the prose-driven convention used in PR #1894 and the seven existing `Skill(skill="...")` calls already in `.claude/commands/{spec,plan,test,review,ship,build}.md`, (b) require an ADR for an infrastructure layer that adds no behavioral capability, and (c) violate Chesterton's Fence on the established convention.

### Q2 (C3): External-installer presence-gate complexity, RESOLVED 2026-05-06

**Resolution**: drop the **command-layer** presence-gate for external-infrastructure markers. Skills own their own missing-marker handling internally.

**Applied to spec**:
- AC-1 rewritten: `/spec` invokes `Skill(skill="session-init")` unconditionally; the skill handles missing `.agents/SESSION-PROTOCOL.md`.
- AC-2 rewritten: `/ship` invokes `Skill(skill="session-end")` unconditionally; same skill-side handling.
- AC-12 narrowed to **runtime conditionals only** (chestertons-fence file age, merge-resolver gh state, threat-modeling complexity tier). External-infrastructure presence checks no longer appear in AC-12.
- DESIGN-005 BundleRegistry: `session-init` and `session-end` rows changed from `presence` to `always`.
- DESIGN-005 Presence-Marker Table now lists only runtime conditionals.
- TASK-005 T5-1 and T5-2 drop the conditional-logic checklist items.

**Why**: PR #1894 establishes that prose-driven bundling at the agent layer ships universal behavior; skills own preconditions. Pushing the missing-marker case into the skill matches the convention and removes 30% of the parser surface that was defending a not-yet-existent external installer. When a real installer reports breakage, the skill (not the command) gets the fix.

### Q3 (C4): Static parser, RESOLVED 2026-05-06

**Resolution**: scope T5-8 down from **BLOCKING** to **advisory WARN**, gated behind `BUNDLE_CHECK_ENFORCED` env var (default `0`). The parser is built; its findings are advisory; PR review is the enforcement layer (matches PR #1894's drift-detection + review pattern).

**Applied to spec**:
- AC-14 rewritten: pre_pr.py emits **advisory WARN** findings, not BLOCKING. A future spec MAY escalate to BLOCKING with an ADR after the registry stabilizes.
- DESIGN-005 Testing Strategy table: pre-PR layer changed from "blocks PRs" to "emits advisory WARN". Env-var gating documented.
- TASK-005 T5-8 acceptance criteria: WARN findings are expected during M1/M2; `BUNDLE_CHECK_ENFORCED=0` is the default. Unit tests cover both env-var values.

**Why**: PR #1894 ships its prose changes without a static parser asserting the framing phrases are present. SPEC-005 has the asymmetry that commands aren't generated from `templates/commands/`, so drift-detection doesn't apply directly, so the parser fills that gap. But framing it as advisory rather than BLOCKING:
1. Keeps the mechanical drift signal for ungenerated files (the asymmetry argument)
2. Avoids the system-wide-contract framing that pushed Q4 toward Tier 3
3. Matches PR 1894's enforcement model (drift surfaced, humans enforce)

**Q4 auto-resolves**: with the advisory framing, no system-wide CI gate is created, so Tier 2 holds honestly.

### Q4 (C2): Tier classification, RESOLVED 2026-05-06 (auto)

Resolved by Q3: with pre_pr.py emitting advisory WARN findings (not BLOCKING) gated behind an env var that defaults to off, no system-wide CI contract is created. Tier 2 classification holds honestly. No ADR required.

### Q5 (C6): Plan depth vs. value

**Challenge**: For a Tier 2 markdown change, ~1187 lines of REQ + DESIGN + TASK + Plan is process performing rigor rather than producing it.

**Resolution**: Acknowledged as deliberate spec-system dogfooding. Each artifact has a distinct readership (REQ for "why", DESIGN for "what", TASK for "how", PLAN for "when"). Trade-off accepted; no change needed unless the spec system itself is the target of revision.

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-05-06 | Land T5-8 first (M1) ahead of command edits | Tests fail red against unedited commands; every subsequent commit turns them green; drift detection from day one | Land T5-8 last per original TASK-005 sequence (rejected: drift undetectable until final commit) |
| 2026-05-06 | Group simple-bind commands (M2) separately from conditional-bind commands (M3) | Reduces blast radius when conditional logic in T5-4/T5-6 needs iteration | Single milestone for all command edits (rejected: too large) |
| 2026-05-06 | Place shared registry at `scripts/validation/bundle_registry.py` (not `tests/`) | `pre_pr.py` uses zero `sys.path` manipulation today; placing registry next to pre_pr.py allows one-line `sys.path.insert` from the test side | `tests/bundle_registry.py` (rejected: requires pyproject.toml pythonpath config or relative-import gymnastics) |
| 2026-05-06 | Static-parser-only verification for `BUNDLE:` markers | Markdown commands have no runtime stdout; the contract is the file text | Runtime stdout capture (rejected: no execution path; AC-11 originally misframed and fixed in spec) |
| 2026-05-06 | Reflect min-delta guard is implementer prose, not statically tested | Static parser cannot count git diff files; behavioral guard only verifiable via integration test | Add behavioral test (deferred: out of scope for T5-8) |
| 2026-05-06 | One feature branch per milestone | Milestones are independently shippable per AGENTS.md atomic-PR convention; lets review focus | Single branch for whole spec (rejected: too many commits per PR; review-fatigue risk) |
| 2026-05-06 | AC-13 (warn-and-continue) verified by code review, NOT by static parser | The parser parses tokens; AC-13 is prose semantics. A parseable token (e.g., `BUNDLE-FAIL: ...`) would add ceremony without catching real regressions because reviewers must read the prose anyway | Add a parseable warn-and-continue token (rejected: cosmetic; doesn't validate semantics) |
| 2026-05-06 | M1 must merge within 5 business days of M2 PR open, else revert and re-land bundled with M2 | Prevents red-main persistence (pre-mortem F1). Converts "independently shippable" into a binding window | Hard-couple M1 and M2 (rejected: defeats milestone independence) |
| 2026-05-06 | Plan supersedes TASK-005 only on PR bundling, not on per-task ordering | TASK-005 is correct that T5-1..T5-7 are parallel; the plan adds a PR-grouping decision (M2 vs M3) on top, not a task-order constraint | Amend TASK-005 (rejected: noise; the docs are consistent at the right level) |
| 2026-05-06 | CWE-78 test uses an independent regex grep, NOT the bundle parser | Sharing the parser between the production check and its test creates a single-defect surface (pre-mortem F5) | Reuse parser (rejected per F5) |
| 2026-05-06 | M1 ships GREEN behind feature flag (`BUNDLE_CHECK_ENFORCED=0` default) and `xfail` test marks; M3 closing commit flips both | Adversarial review C5: red main is a CI signal that lies; mechanical enforcement beats social agreement | 5-business-day continuity rule (rejected: social contract for what a flag should do) |
| 2026-05-06 | Q1-Q4 (bundle-via-prose vs. hook routing, presence-gate YAGNI, parser cost-justification, tier classification) raised as spec-amendment questions, not auto-applied | Adversarial review challenged premises in REQ/DESIGN/TASK, not just plan execution; user owns the spec, not the planner | Auto-apply spec amendments (rejected: changes scope of committed work without user assent) |
| 2026-05-06 | Q1 RESOLVED: bundle-via-prose retained as house style; PR #1894 is the matching precedent at the agent layer (template prose framing, no skill-routing layer, behavior tested via downstream code not prose presence) | User cited PR #1894 as the precedent; verified: `templates/agents/{implementer,qa,critic}.shared.md` use the same pattern. Bundle-via-prose is convention, not workaround | Build hook + commands.yaml routing layer (rejected: violates Chesterton's Fence on the existing convention; adds infrastructure without behavioral capability) |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-05-06 | Plan created. Source artifacts committed on `docs/spec-005-command-skill-bundling` (`db9f24cb`). M1/M2/M3 milestone structure ratified by milestone-planner. M1 import-path unknown resolved by task-decomposer. | Claude Opus 4.7 |
| 2026-05-06 | Pre-mortem (analyst) surfaced 5 plan-level failure modes (F1-F5). Critic review surfaced 4 more (F6-F9) and returned NEEDS_REVISION. All 9 findings folded into plan: Implementer Quick-Start, Sequencing Reconciliation, M1-to-M2 Continuity Rule, AC-13 verification stance, M2 GREEN/RED enumeration, T5-4/T5-6 resized to M, CI wire-up checklist items, CWE-78 independent-regex requirement. | Claude Opus 4.7 |
| 2026-05-06 | Adversarial review (independent-thinker) raised 6 RECONSIDER findings (C1-C6). Plan-level fixes applied: M1 stays GREEN via `BUNDLE_CHECK_ENFORCED=0` default + `xfail` test marks (replaces 5-business-day continuity rule). Spec-level challenges (C1, C3, C4, C2) surfaced as Q1-Q4 in new "Open Questions" section requiring user assent before REQ/DESIGN/TASK amendment. C6 (plan depth) acknowledged as deliberate dogfooding. | Claude Opus 4.7 |
| 2026-05-06 | Q2 + Q3 user-approved. Applied to REQ-005 (AC-1, AC-2, AC-12, AC-14 rewritten), DESIGN-005 (BundleRegistry session-init/session-end gate `always`; Presence-Marker Table runtime-only; Testing Strategy advisory framing), TASK-005 (T5-1, T5-2 drop conditional logic; T5-8 advisory WARN with env-var gating). All four open questions (Q1-Q4) now resolved. | Claude Opus 4.7 |
| 2026-05-06 | User cited PR #1894 as precedent for bundle-via-prose. Q1 closed (bundle-via-prose is house style, not a workaround). Q3 refined: PR 1894 uses drift detection + PR review + behavioral tests, no static parser on prose; SPEC-005 commands aren't generated, so the parallel argues for advisory-WARN parser, not BLOCKING. Q2 and Q4 still open. | Claude Opus 4.7 |
| 2026-05-06 | User approved Q3 (advisory WARN) and Q2 (drop command-layer presence-gate; skills own missing-marker handling). REQ-005 amended: AC-1, AC-2, AC-12, AC-14 rewritten. DESIGN-005 amended: BundleRegistry session-init/session-end gate type changed to `always`; Presence-Marker Table now lists runtime conditionals only; Testing Strategy reflects advisory framing. TASK-005 amended: T5-1 and T5-2 drop conditional logic; T5-8 acceptance criteria reflect advisory + env var gating. Q4 auto-resolved Tier 2 (no system-wide CI contract created). | Claude Opus 4.7 |

## Blockers

- None at plan-creation time.
- Watch list: M1 import resolution must work in CI (R1); chestertons-fence prose ambiguity in T5-4/T5-6 (R2).

## Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | M1 import path breaks pytest discovery on CI | Med | High | Place registry at `scripts/validation/bundle_registry.py`; tests use `sys.path.insert(0, str(Path(__file__).parent.parent / "scripts/validation"))`. Validate locally before push. |
| R2 | Conditional chestertons-fence prose ambiguity in T5-4/T5-6 | Med | Med | Parser literal contract: `Skill(...)` call + adjacent `BUNDLE:` marker. Re-read DESIGN-005 §BUNDLE Marker before each edit. |
| R3 | Reflect min-delta guard not enforced statically | High | Low | Documented as implementer-prose contract; out of scope for T5-8. |
| R4 | Skill renames between authoring and merge break invocations silently | Low | High | T5-0 prerequisite verification + CI registry test catch this on every PR. |
| R5 | External plugin installer hits unexpected presence-check failure | Was Low | Mitigated | Q2 resolution: skills own missing-marker handling. Failure mode (if any) surfaces via the skill, not the command. |
| R6 | M2 tasks merged out of order | Low | Low | M2 tasks independent by design; order does not matter. |
| F1 | M1 ships red; if M2 stalls, main stays red | Was Med | Mitigated | Replaced by `BUNDLE_CHECK_ENFORCED=0` default + `xfail` marks per adversarial review C5; M1 stays GREEN, no continuity rule needed |
| F2 | `pre_pr.py` function added but not wired to CI | Med | High | M1 checklist item: deliberate broken-bundle test PR must fail CI, not just local pre-commit |
| F3 | Fresh implementer cannot start M1 from this plan alone | Was Med | Mitigated | Implementer Quick-Start section above includes registry, parser contract, sys.path snippet |
| F4 | `sys.path.insert` breaks on CI working directory variance | Med | High | Anchor to `Path(__file__).resolve().parent.parent`; M1 checklist runs pytest from non-root locally |
| F5 | CWE-78 test reuses bundle parser and shares its defect | Low | High | M1 checklist: CWE-78 test uses independent regex grep, never the bundle parser |
| F6 | AC-13 (warn-and-continue) unverified | Was Med | Accepted | Decision Log: AC-13 is manual code review at PR time; PR template must include AC-13 check |
| F7 | "Partially GREEN" undefined in M2 | Was High | Mitigated | M2 EXIT now lists exact 7 GREEN and 8 RED test case IDs |
| F8 | Plan diverges from TASK-005 sequencing without trace | Was Med | Mitigated | Sequencing Reconciliation section + Decision Log row clarify PR-bundling vs task-order |
| F9 | T5-4 and T5-6 sized as S; conditional logic risks rework | Was Med | Mitigated | T5-4 and T5-6 resized to M; per-task sizing exposed in M2/M3 objectives |

## Sequencing

```
T5-0 (verification, no commit)
  -> M1: T5-8 (3 files, 1 commit, tests RED)
    -> M2: T5-1, T5-2, T5-3, T5-7 (5 files, 4 commits, tests partially GREEN)
      -> M3: T5-4, T5-5, T5-6 (3 files, 3 commits, tests fully GREEN)
```

Critical path: 3 milestones, all sequential. Within M2 and M3, tasks parallel for authoring.

Total: 8 commits, 11 files. Within AGENTS.md (≤5 files/commit, ≤20 commits/PR).

## Deferred Items

- `/audit` cadence command: separate spec
- Cross-command Serena context handoff (analysis §9): separate spec
- `/test` Gate 4 `pipeline-validator` bundle: deferred per REQ-005; revisit after this spec lands
- `reflect` hash-based dedupe: skill-author concern, not command-level
- Behavioral integration test for ship.md min-delta reflect guard: out of scope for T5-8

## Reversibility

Every milestone is a markdown edit (M2/M3) or a pure-additive Python module (M1). `git revert` restores prior behavior in all cases. No DB migrations, no external state, no irreversible operations.

## Related

- Source analysis: `.agents/analysis/command-skill-bundling-2026-05-03.md`
- Requirements: `.agents/specs/requirements/REQ-005-command-skill-bundling.md`
- Design: `.agents/specs/design/DESIGN-005-command-skill-bundling.md`
- Tasks: `.agents/specs/tasks/TASK-005-command-skill-bundling.md`
- Session: `.agents/sessions/2026-05-06-session-1825-author-spec-005-command-skill-bundling-req.json`
- Spec commit: `db9f24cb` on `docs/spec-005-command-skill-bundling`
- Issue: (pending, track in next-step list)
- ADR: none required (Tier 2)
