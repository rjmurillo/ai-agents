# Counting fixture files overstated rule coverage because several fixtures exercised the same rules

**Atomicity**: 90%
**Category**: Eval coverage claims
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E167. State checked on main at 1be533c496 (2026-11-26).

## Question

Should rule coverage count fixture files or distinct rule paths?

## Conventional answer

The research frontier skill claimed 12 fixtures covered 12 rules, leaving 13 of 25 without a baseline (2026-08-02).

## First-principles position

Several fixture files shared the same `rule_path`. Counting distinct values showed coverage for only 4 rules on 2026-08-02. The doc had counted repeated exercises as new rule coverage.

## Evidence with limits

- The probe found 4 distinct `rule_path` values across 12 fixture files (2026-08-02).
- The deduplicated count left 21 of 25 rules without an activation baseline (2026-08-02).
- Limits: The session reran the count from issue 4167 on the fixture directory of 2026-08-02. The count is historical: `tests/evals/rule-scenarios` had 40 entries at 1be533c496 (2026-11-26).
- State on main at 1be533c496 (2026-11-26): fixed. `.claude/skills/ai-agents-research-frontier/SKILL.md:99-103` directs readers to `corpus-counts` instead of a count stored in prose.

## Decision

Measure coverage by distinct `rule_path` values. Run `corpus-counts` for the current total rather than quoting a historical count.

## Related

- `.serena/memories/adr/adr-artifact-count-verification.md`
