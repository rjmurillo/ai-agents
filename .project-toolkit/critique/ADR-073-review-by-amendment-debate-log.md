# ADR Debate Log: ADR-073 Amendment 2026-10-13, Optional review-by Date

## Summary

- **Rounds**: 1 of 10 (Phase 1 independent review plus one convergence vote)
- **Outcome**: Consensus. Five roles Accept. One role Disagrees and Commits on a P2 residual.
- **Final Status**: accepted. Frontmatter on ADR-073 stays `status: accepted`. The amendment text stands as written.
- **Panel**: full six-role panel, because the amendment documents executable enforcement (three new checks in `scripts/validation/check_adr_lifecycle.py`) and the schema other gates read (`build/scripts/generate_adr_index.py`, `check_rule_adr_citations.py`).
- **Review independence**: one model played all six roles in separate passes. No Agent tool was available in the harness. This is not six independent reviews. Treat the votes as one reviewer's six lenses, and the repo owner's review as the check grounded outside the model.
- **Artifact reviewed**: `.project-toolkit/architecture/ADR-073-adr-lifecycle-frontmatter.md`, the new `review-by` line in the Decision schema block and the new section "Amendment 2026-10-13: optional review-by date".
- **Ground truth**: working tree of branch `fix/5193-adr-review-by-gate` against `origin/main` at `b207827d5`.
- **Owner decision under review**: issue #5193, second owner decision. Amend ADR-073 instead of filing a new ADR, and have the lifecycle validator check that a record with `review-by` also states the date in prose.

## Phase 0: Related Work

| Item | State | Relevance |
|---|---|---|
| #5193 | open | The work item. Names the past-due check, the prose-date check, and a test that fixes "now". |
| #5191 | closed | Delivered `check_adr_lifecycle.py`, the ratchet the new checks join. |
| #5273 | closed | Ratchet keyed by `(check, path)`, which is why a new check can enter with its current records baselined. |
| #5194 | closed | Precedent for adding a check after the baseline exists. `_excess` gives a check absent at the base ref no excess. |
| #5209, #5291 | merged | Landed the lifecycle gate and the status decisions for ADR-002 and ADR-039. |

## Evidence Gathered

- `uv run python scripts/validation/check_adr_lifecycle.py` after the change: `[PASS] 74 violation(s) across 118 ADR record(s), none outside the baseline`. The three new checks hold 0, 1, and 12 violations.
- `review-by-past-due` is one record: ADR-077 (due 2026-09-27, status `proposed`). Its checkpoint passed with no review outcome recorded in the prose.
- `review-by-prose-date` is twelve records: ADR-107 to ADR-118. Each sets `review-by` in frontmatter and none states the date in prose. ADR-063 sets `review-by: null` and is not counted.
- ADR-083 (due 2026-10-18, status `accepted`) states the date in its `## Review Date` section and passes today.
- Clock replay with `scan(..., today=...)` against the live corpus: on 2026-10-13 and 2026-10-18 the past-due set is ADR-077 alone. On 2026-10-19 it is ADR-077 and ADR-083. Against the committed baseline, 2026-10-19 yields excess of exactly one identity, ADR-083.
- Tests: `tests/validation/test_check_adr_lifecycle.py`, `test_check_adr_lifecycle_base_ref.py`, `test_check_adr_lifecycle_conformance.py` pass. New cases fix the clock at 2026-10-13 and cover due-today, day-after, quoted and unquoted dates, malformed values, closed statuses, a fenced date, an unparseable body, and the ratchet round trip.
- YAML probe: an unquoted `review-by: 2026-02-30` raises `ValueError` inside `frontmatter_contract.parse_frontmatter` before this gate runs. The same happens today for `date: 2026-02-30`. The amendment does not change that path.

## Phase 1: Independent Reviews

### architect

Strengths: the amendment is additive and optional with a `null` default, which matches the `explainer` and `implemented` precedent in this ADR. It lists the three check names, and they match `CHECKS`. The ADR names the clock-injection point and the reason the CLI has no flag. The Decision block and the amendment agree on the field's shape.

Weakness: none that change the text. One note. The amendment says the baseline can "only fall", which is the gate's own wording in `_BASELINE_DESCRIPTION`.

| Issue | Priority | Description |
|---|---|---|
| A1 | P2 | The amendment points to this debate log by path, so the path must stay stable. It is the name committed here. |

### critic

Does the amendment say what the code does? Checked line by line. Format applies to every status: yes, `_check_review_by` parses before it reads status. Prose-date and past-due skip closed statuses: yes, `_LIVE_STATUSES` holds `proposed` and `accepted`. Due today is on time: yes, the comparison is `due < today`. UTC: yes, `_utc_today` reads `datetime.now(UTC)`.

Gap: a malformed value stops at one finding. That is stated in the code docstring and tested, but the ADR does not say it. It is an implementation detail, not a rule, so the ADR can stay silent.

| Issue | Priority | Description |
|---|---|---|
| C1 | P2 | The ADR does not say a malformed value suppresses the other two checks. Implementation detail, covered by tests. |

### independent-thinker

Challenge 1: `review-by-past-due` is a time bomb. From 2026-10-19 every pull request fails the ratchet until someone reviews ADR-083 or moves its date, including PRs that touch no ADR. Counter: that is the stated purpose. The issue exists because a prose deadline passed unseen for seven months. A gate that warns and does not fail would reproduce that outcome. The fix at the time is cheap (move the date, or set `null`), and the failure message says so.

Challenge 2: ADR-107 to ADR-118 use `review-by` as a standalone expiry. ADR-107 line 589 calls it "An expiry, recorded as `review-by`." The prose-date check asks them to restate it. The owner's issue comment asks for this check by name, so the amendment follows the owner. The baseline absorbs the twelve records, so no ADR body is edited here. Whether those twelve authors meant a prose date is a question the owner can answer when the count falls.

| Issue | Priority | Description |
|---|---|---|
| I1 | P2 | Twelve records use the field as a standalone expiry; the prose-date rule may not match their intent. Owner to decide when clearing the baseline. |

### security

The new regexes are `\d{4}-\d{2}-\d{2}` with `fullmatch` and a lookaround around a `re.escape`d literal date. Neither has nested or overlapping quantifiers, so no backtracking blowup. The frontmatter value is parsed by `date.fromisoformat` only after the regex confirms the shape, so the wider formats Python 3.11+ accepts (`20260927`, `2026-W40-7`) never reach it. The value is never used as a path, command, or URL. The clock is a function parameter and not an environment variable or flag, so a branch cannot dodge the check by passing a date. A branch can still edit `review-by` or the baseline. The baseline cannot rise above the base ref (`_base_ref_refusal`), and editing a date is visible in the diff. No new file, network, or secret surface.

| Issue | Priority | Description |
|---|---|---|
| S1 | None | No finding. |

### analyst

Verified the claims in the issue against the tree. ADR-002 and ADR-039 are `deprecated` (PR #5291, 2026-08-25), enum-valid, with prose that records why the window lapsed. `ADR-TEMPLATE.md` and the adr-generator template already carried the field. ADR-077 and ADR-083 lacked it; both now carry it, and both already stated the date in prose, so the edits are frontmatter-only. ADR-081, ADR-058, and ADR-087 stay without a date, as the owner's correction comment says: their revisits are condition-triggered or anchored to a run record.

Feasibility: three small functions, no new dependency, no change to the ratchet arithmetic. The cost of the baseline is 13 identities that the owner can retire.

| Issue | Priority | Description |
|---|---|---|
| N1 | P2 | ADR-077's checkpoint passed with no recorded outcome. Holding that review is an owner act outside this change. |

### high-level-advisor

Priority and scope. The change closes the two defects the issue names: the stale records (done in #5291) and the missing mechanism (this change). It stays inside one idea. It does not hold the ADR-077 review, rewrite twelve ADR bodies, or fix the `ValueError` on impossible unquoted dates; each is a separate decision. The time bomb on ADR-083 is the intended forcing function and is stated in the amendment so nobody meets it by surprise.

Recommendation: accept. Flag the three residuals in the pull request body.

## Phase 2: Consolidation

No P0 or P1 findings. Four P2 notes (A1, C1, I1, N1) need no text change. I1 and N1 are owner decisions and go in the pull request body.

## Phase 3: Convergence Vote

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Accept |
| independent-thinker | Disagree and Commit. Wants the twelve standalone-expiry records reconsidered when the baseline is cleared. |
| security | Accept |
| analyst | Accept |
| high-level-advisor | Accept |

## Next Steps

- Pull request body carries the three residuals: ADR-077 overdue review, twelve records without a prose date, and the ADR-083 date of 2026-10-19.
- The repo owner reviews this log. It is one model's six lenses, not an independent panel.
