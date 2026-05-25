# Skillbook: Evidence-Tiered Agent Policies

**Issue**: #2030. **Branch**: agent/issue-2030-evidence-tiered-policies.
**Status**: implemented 2026-05-17 (session 1153), PR pending.

## What it is

A policy registry under `.agents/skillbook/` that grades agent behavioral
policies by a tier grounded in eval pass/fail outcomes (not regex sentiment).

## Files

- `.agents/skillbook/{policies,tensions,workflows}.json` - registry data.
- `.agents/skillbook/README.md` - the model documentation.
- `.agents/schemas/{policy,tension,workflow,evidence-entry}.schema.json` - draft-07 schemas.
- `scripts/skillbook.py` - CLI: status/confirm/contradict/promote/tension/select.
- `scripts/validation/validate_skillbook.py` - schema + integrity validator (CI calls this).
- `.agents/hooks/post-eval.py` - eval-results -> skillbook-evidence bridge (NOT a harness lifecycle hook).
- `tests/skillbook/` - pytest suite (100 tests).
- `.github/workflows/skillbook-validation.yml` - CI schema validation.

## Key invariants (do not break)

- Tiers never decrease: hypothesis -> observed -> validated. `promote_policy`
  uses `max(old_rank, eligible_rank)`.
- A validated policy whose contradict rate climbs above 10% flips
  `status: questioning`, the tier holds. Recovers to `active` if rate drops.
- Promotion gates: confirms >= 1 -> observed; confirms >= 5 AND contradict
  rate <= 10% -> validated.
- `confirms`/`contradicts`/`application_count` are a DERIVED projection of
  the `evidence` array (the system of record); recomputed on every mutation.
- Evidence weight: external 1.0, self-referential 0.25.
- `confirm`/`contradict` are idempotent on `eval_id`.

## Design decisions

- `jsonschema` library deliberately NOT added; validator carries a small
  purpose-built draft-07 subset checker, matching `validate_session_json.py`.
- Dropped the issue example's `evidence_tier` field (duplicate of `tier`).
- `.agents/skillbook/` is a policy registry, distinct from the `skillbook`
  AGENT persona (templates/agents/skillbook.shared.md).

## Deferred (out of scope v1)

In-session enforcement, auto-discovery from transcripts, cross-repo sharing,
confidence-weighted `select` ranking, wiring `select` into agent prompts.
