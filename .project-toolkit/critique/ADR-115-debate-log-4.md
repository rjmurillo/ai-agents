# ADR Debate Log: ADR-115 Cursor and Muse Skill Version and License Keys

## Summary

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log-3.md`
- **Trigger**: CodeRabbit on PR #7391 (thread `PRRT_kwDOQoWRls63xT3c`). The Cursor and Muse skill copies drop `version` and `license`, which GP-003 requires in every `SKILL.md`.
- **Owner decision, 2026-11-15**: amend ADR-115 and keep both keys in both trees.
- **Owner decision D2, 2026-11-15**: the Muse keep-list also keeps `metadata`, because four skills hold `version` there.
- **Panel**: reduced (architect and critic). The amendment changes two platform keep-lists and prose decisions. It does not touch a gate other gates read.
- **Started**: 2026-11-15

## Pre-review evidence

- On `origin/main` at `1ce1193cf` (2026-11-15), `src/cursor/skills/<name>/SKILL.md` lacked `version` and `license` for `autoplan`, `merge-resolver`, and `maintainer-review`. The Muse copies kept only `name` and `description`.
- ADR-115 Decision 3 listed `version` and `license` as deliberately dropped. The reason was that Cursor's docs are silent on unknown keys, not that Cursor rejects them.
- `scan_principles.py --rules skill-frontmatter` on the Cursor and Muse `autoplan` copies reported 0 applicable files. GP-003 was never enforced on those trees.
- Muse Code 1.4.20, no login, 2026-11-15: `muse skills validate --json` on the full Claude `autoplan` copy returned `valid: true`, `compatible`. It listed `license` as a known field and `version` as an unknown field.
- After regeneration, `RUN_CLI_E2E=1 pytest tests/e2e/test_muse_skills_validate.py` passed over all 106 Muse copies.
- `cursor-agent --help` lists no skill validate command, so no login-free Cursor check exists.

## Round 1

### Architect

Vote: Accept.

- P1: the claim that `metadata` shares Cursor's silence was false; `metadata` is a documented key.
- P1: Decision 3 still said "keeps only the keys Cursor's skill schema defines".
- P2: `muse skills validate` is a format check, not a session load.
- P2: Deferred Items had no Cursor load item. Consequences and Reversibility were unchanged.
- P2: the cited debate log 4 did not exist yet.
- P2: `test_committed_cursor_skills_carry_only_documented_keys` named keys Cursor does not document.

### Critic

Vote: Accept, conditional on the two P1 edits.

- P1: debate log 4 was cited but missing.
- P1: the unprobed Cursor load had no deferred item, against `generated-artifacts.md` MUST NOT 2. The 2026-10-13 Cursor turn loaded a Claude copy that carries both keys, which counts as inferred evidence.
- P2: same Decision 3 wording finding as the architect.
- P2: the new test docstring said the copies "failed GP-003", but no scanner checks them. The parity test passes when a source lacks both keys.
- P2: confirm the amendment date.

## Resolution

- Decision 3 now says the list keeps the documented keys plus `version` and `license`. The `metadata` clause is gone. The 2026-10-13 load is cited as inferred evidence.
- The Muse bullet now says no Muse Code session load with a login was run.
- Deferred Items adds a Cursor load and extends the personal-agent load to cover both keys.
- Consequences (Negative) and Reversibility each get a 2026-11-15 amendment.
- The test is renamed `test_committed_cursor_skills_carry_only_allowed_keys`. The new test docstring states the scanner scope and the parity limit.
- The amendment date is 2026-11-15, the local date of the work.
- This log is debate log 4.

## Outcome

Consensus: both reviewers vote Accept with every P1 resolved. Acceptance of ADR-115 remains the owner's call.

## Post-panel change

After round 1, a check found four skills that keep `version` under `metadata`: `security-scan`, `skillforge`, `style-enforcement`, `validation-authority`. GP-003's substring check accepts that placement. Cursor already kept `metadata`; Muse dropped it, so those four Muse copies still lost `version`. The owner chose to keep `metadata` in Muse (D2). With it, Muse Code 1.4.20 validated all 106 copies as compatible, and `security-scan` reported no unknown fields. The test now asserts every committed copy carries a version and a license.

## Round 2

Scope: the D2 change, keeping `metadata` in the Muse skills keep-list.

### Architect

Vote: Accept.

- P2: this log lacked round 2 votes. Resolved by this section.
- P2, outside this amendment: Hermes drops `metadata` (ADR-115 Decision 6), so the Hermes copies of `skillforge`, `style-enforcement`, and `validation-authority` keep `license` but lose `version`. Verified 2026-11-15 under `src/hermes/`. `security-scan` does not ship to Hermes. Recorded below as flagged, not changed.

### Critic

Vote: Accept.

- Confirmed the four skills carry top-level `license` and `metadata.version` in source and in the Muse copies.
- Confirmed the ADR sections agree with each other, and the Hermes nested-`metadata` rejection applies to Hermes only.
- Corrected a round 1 statement: its dash check was unverified. A Python scan in round 2 found no em or en dashes.
- P2: this log lacked round 2 votes. Resolved by this section.

## Final outcome

Consensus: both reviewers vote Accept in round 2 with no open P0 or P1. Acceptance of ADR-115 remains the owner's call.

## Out of scope, flagged

- Hermes copies of `skillforge`, `style-enforcement`, and `validation-authority` lose `metadata.version`. The task covered Cursor and Muse only. The owner decides whether Hermes keeps `version`.
- The GP-003 scanner checks only `.claude/skills/`. It never checks the `src/cursor/`, `src/muse/`, or `src/hermes/` copies.

## Pre-merge review follow-up

The `/review` run on `927396472` returned WARN from spec-compliance, security, reliability, and decision-rigor. No axis returned CRITICAL_FAIL. Follow-up edits:

- Signed-in `cursor-agent` 2026.11.11 probe, 2026-11-15. A project `.cursor/skills/` copy carrying `version`, `license`, and `metadata` registered with zero tool calls, as did a name-and-description control. A malformed-YAML control also registered, so the probe shows non-rejection only. `--plugin-dir` registered none of the three, so the plugin install path stays a deferred item, now with a failure signature and a trigger.
- Decision 3 records two rejected alternatives: exempting the generated trees from GP-003, and moving `version` under `metadata` in 102 sources.
- Consequences names Muse Code's unknown-field tolerance as a risk. Reversibility names the installed-tree lag.
- `templates/platforms/surface-parity.yaml` reasons for `skills-cursor` and `skills-muse` now list the kept keys.

## PR #7395 review follow-up

- The owner (review thread on ADR-115 Decision 3) noted that the Resolution above says the 2026-10-13 load is cited, but the `ebf475c84` rewrite dropped that citation. Decision 3 now carries the owner's suggested sentence. It cites the 2026-10-13 turn as inferred evidence for the Claude-plugin path only, not for a `src/cursor/` install.
- Cursor Bugbot noted that frontmatter `date` stayed `2026-11-11`. ADR-073 defines `date` as last updated, so it is now `2026-11-15`.
