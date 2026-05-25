# Test Report: Evidence-Tiered Agent Policies (Skillbook) - Issue #2030

**Validator**: QA Agent
**Date**: 2026-05-17
**Branch**: agent/issue-2030-evidence-tiered-policies (uncommitted)

## Objective

Validate the skillbook feature against the 8 acceptance criteria in issue #2030,
with emphasis on the CRITICAL tier/promotion/idempotency invariants. Verify the
math is correct, not just that tests are green.

## Approach

- Ran the full pytest suite + coverage.
- Ran the validator, CLI, and post-eval hook against seed data.
- Built adversarial fixtures (missing files, malformed JSON, corrupted derived
  counts, dangling cross-refs, schema violations, empty runs).
- Independently reasoned about `eligible_tier`, `promote_policy`, `add_evidence`,
  and `aggregate_fixture_outcomes` by reading `scripts/skillbook.py`.
- Cross-checked the implementation against the canonical issue #2030 body.

## Results

### Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tests run | 98 | - | - |
| Passed | 98 | - | [PASS] |
| Failed | 0 | 0 | [PASS] |
| Line coverage (skillbook.py) | 96% | 80% | [PASS] |
| Line coverage (validate_skillbook.py) | 95% | 80% | [PASS] |
| Invariant logic coverage | ~100% (all of eligible_tier/promote_policy/add_evidence exercised) | ~100% | [PASS] |
| Execution time | 0.24s | - | [PASS] |

Uncovered lines are CLI display branches and one `tension_prefer` re-pointer
path; the tier/promotion math is fully covered.

### CRITICAL Invariants (AC #8)

| Invariant | Result | Evidence |
|-----------|--------|----------|
| Tiers never decrease | [PASS] | `promote_policy` takes `max(old_rank, eligible_rank)`. Verified: a validated policy with 0 evidence stays validated after promote. Parametrized test covers all 3 start tiers. |
| Rising contradict rate -> questioning, not demotion | [PASS] | `resolve_status` flips status to `questioning` when tier==validated and rate>10%. Tier holds. Verified directly. |
| Promotion gate: >=1 confirm -> observed | [PASS] | `eligible_tier` returns observed at `confirms >= 1.0`. |
| Promotion gate: >=5 confirms AND <=10% rate -> validated | [PASS] | `eligible_tier` checks `confirms >= 5.0 and rate <= 0.10`. Boundary test: 9c+1contra (exactly 10%) -> validated; 8c+2contra (20%) -> observed. |
| Boundary: 5 confirms -> validated; 6th contradiction -> questioning | [PASS] | `test_five_confirms_promote_then_sixth_contradiction_flips_questioning` exercises the exact sequence. Verified manually. |
| Self-referential weighted 0.25, external 1.0 | [PASS] | `CONTEXT_WEIGHTS = {external: 1.0, self-referential: 0.25}`. 5 self-ref confirms = 1.25 weighted -> only observed. 20 self-ref = 5.0 -> validated. Correct. |
| Idempotency (no double-count) | [PASS] | `add_evidence` rejects a duplicate `eval_id`. Post-eval hook re-run on the same run is a no-op. Verified end-to-end. |

### Error Handling

| Case | Result | Exit code |
|------|--------|-----------|
| Missing skillbook file | [PASS] | 2 (config) |
| Malformed JSON | [PASS] | 1 (logic) |
| Unknown policy id (confirm) | [PASS] | 1 (logic) |
| Unknown tension id | [PASS] | 1 (logic) |
| Policy not in tension pair (tension prefer) | [PASS] | 1 (logic) |
| Missing run dir / fixtures dir (post-eval) | [PASS] | 2 (config) |
| Run record missing fixture_id | [PASS] | 1 (logic) |
| Empty runs.jsonl | [PASS] | 0 (no-op) |

### Validator Adversarial Tests

| Corruption | Caught? |
|------------|---------|
| Wrong `confirms` count vs evidence | [PASS] caught |
| Evidence present but counts zeroed | [PASS] caught |
| Invalid `tier` enum value | [PASS] caught |
| Dangling `related_policies` cross-ref | [PASS] caught |
| Tension referencing unknown policy | [PASS] caught |
| Malformed policy id pattern | [PASS] caught |
| Tension resolution outside the paired policies | [PASS] caught |

### Acceptance Criteria

| AC | Status | Notes |
|----|--------|-------|
| 1. policies.json seeded, all hypothesis, 1+ per persona | [PARTIAL] | All 19 policies are `hypothesis` tier. 13 persona-owned + 5 shared + 1 skillbook. 11 of 24 persona templates have NO policy (see Concern C1). |
| 2. tensions.json exists; workflows.json 2-3 workflows | [PASS] | tensions.json has 1 tension; workflows.json has 3 workflows. AC explicitly allows an empty tensions array. |
| 3. skillbook.py status/confirm/contradict/promote/tension/select + unit tests | [PASS] | All 6 commands implemented and exercised. 98 tests. |
| 4. 4 JSON schemas + CI validation job | [PASS] | policy/tension/workflow/evidence-entry schemas exist; `skillbook-validation.yml` runs the validator. |
| 5. Post-eval hook auto-confirms/contradicts | [PASS] | `.agents/hooks/post-eval.py` works end-to-end, idempotent. |
| 6. >=1 eval tagged with policy_id | [PASS] | `evals/security-spike/fixtures/F001.json` tagged `pol-security-vuln-first`. |
| 7. README explaining model + how to add a policy | [PASS] | `.agents/skillbook/README.md` is thorough and accurate. |
| 8. Invariants tested at boundary | [PASS] | See CRITICAL Invariants table. |

## Concerns

### C1 (P2): persona coverage is partial vs AC #1 "1 policy per persona minimum"

`templates/agents/` has 24 `*.shared.md` persona templates. Only 13 have an
owning policy. Missing: backlog-generator, debug, high-level-advisor,
independent-thinker, issue-feature-review, janitor, merge-resolver,
milestone-planner, negotiation, pr-comment-responder, task-decomposer.

The AC wording is "extract 1 policy per persona minimum". The issue body's own
examples only name architect/security/qa/devops, and the design talks about
"many personas" loosely. This is a defensible scope interpretation (the 13
covered personas are the substantive decision-making agents; the 11 missing are
mostly narrow utility agents). It is not a logic defect. Flagging it because the
literal AC text was not met and the divergence is undocumented in the PR/README.
Recommend: either add stub `hypothesis` policies for the remaining personas, or
note the scope decision explicitly in the PR description.

### C2 (P3): "questioning" status only reachable at the validated tier

`resolve_status` flips to `questioning` only when `tier == "validated"`. A
`hypothesis` or `observed` policy with a 99% contradict rate (e.g. 1 confirm +
100 contradicts) stays `active`. This matches the issue text precisely ("A
validated policy with rising contradict rate flips status: questioning"), so it
is correct as specified. Noting it because an `observed` policy that is failing
almost every run is still surfaced to `select` as a plain active policy with no
warning. This is a spec-level gap, not an implementation bug. Acceptable for v1;
worth a follow-up issue.

### C3 (P3): the never-decrease assertion in `promote_policy` is structurally dead

`assert new_rank >= old_rank` where `new_rank = max(old_rank, eligible_rank)`.
By construction `max(old, x) >= old` always holds, so the assertion can never
fire. AC #8 explicitly asks for "assertion in promote()", so it satisfies the
letter of the AC and documents intent. It provides zero runtime protection
against a future refactor that changes the `max` line. The real guarantee is
the `max()` itself, which IS tested behaviorally. Acceptable, but the assertion
is a comment dressed as a check.

### C4 (P3): CI workflow push trigger does not match the working branch

`skillbook-validation.yml` triggers `on.push` for branches `main`, `feat/**`,
`fix/**`. The actual branch is `agent/issue-2030-evidence-tiered-policies`.
The `pull_request` trigger (target `main`) and `check-paths`/`skip-validate`
pass-through still make the required check run on the PR, so this is not
blocking. But the push-side validation will not fire on `agent/**` branches.
Recommend adding `agent/**` to the push branch list for parity, or confirm the
repo convention is PR-only validation for agent branches.

### C5 (P3): canonical-source-mirror citation is weak for seed policies

`policies.json` entries carry a `source` field naming the persona template
(e.g. `templates/agents/architect.shared.md`). All cited source files exist
(verified). The policy `name`/`description` are paraphrases, not verbatim
quotes from those templates. Per `.claude/rules/canonical-source-mirror.md`,
seed policies "extracted from" a source are a softer case than a contract claim
("matches"/"mirrors"), so this does not strictly trip that rule. Still, a
reviewer cannot verify the paraphrase faithfully represents the persona without
re-reading each template. Low risk; noted for completeness.

## Discussion

### What is solid

- The evidence array as system of record with derived counts is clean. The
  validator independently recomputes counts and catches drift. DRY at the
  knowledge level: counts have one writer (`recompute_counts`).
- Idempotency is real, not hoped-for: `add_evidence` keys on `eval_id`, the
  post-eval hook keys on `<run_id>::<fixture_id>`, and `run_promote` only bumps
  meta when something changed. Verified by re-running each operation.
- The math is correct. The 10% gate is `<=`, the 5-confirm gate is `>=`, the
  contradict rate is the standard weighted ratio. Boundary cases (exactly 10%,
  exactly 5 confirms, 4.99 confirms) all behave as the README documents.
- Error paths return ADR-035 exit codes consistently.
- The post-eval hook's strict-majority aggregation (`passed*2 > total`) handles
  ties correctly: a 1-1 split does not pass.

### Edge cases probed and passed

- `eligible_tier` with mixed evidence (1 confirm + 100 contradicts) -> observed.
  Correct per spec: any confirm clears the observed gate; the 99% rate only
  matters at the validated gate.
- 20 self-referential confirms (weighted 5.0) -> validated. Weighting applies
  uniformly to the promotion gate, not just display.
- `select` for a persona with no owned policy returns only shared policies.
- `tension prefer` output round-trips through schema validation cleanly.
- Empty `runs.jsonl` is a clean no-op, exit 0.

## Verdict

**Status**: PASS WITH CONCERNS
**Confidence**: High

All 8 acceptance criteria are met except AC #1, which is partially met (13 of 24
personas covered). The CRITICAL tier/promotion/idempotency invariants are
correct in the math and tested at the boundary. No logic defects found. The five
concerns are scope/spec observations (C1, C2, C5) and cosmetic robustness notes
(C3, C4); none block merge.

**Required before merge**: resolve C1 by either adding the missing persona
policies or documenting the scope decision in the PR description.

**Recommended follow-ups**: C2 (surface failing non-validated policies),
C4 (CI push trigger parity for agent/** branches).
