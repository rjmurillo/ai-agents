# The repo's SkillsBench summary said short skills win, but the study ranked standard length above compact

**Atomicity**: 90%
**Category**: Skill design evidence
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E064, E065. State checked on main at 1be533c496 (2026-11-26).

## Question

What did the SkillsBench study report on skill length and on self-generated skills?

## Conventional answer

The modularity guidelines cited SkillsBench for the claim that shorter skills score higher. The audit used 300 ideal and 500 max lines (2026-08-02). The guidelines put the self-generated loss at 1.3% and the curated gain at 16.2%.

## First-principles position

The study summary ranks Standard length above Compact. The study reports named groups and sets no line counts. The 300 and 500 limits are repo conventions (2026-08-02). Self-generated packs scored 8.1 to 11.5 points below no skills. Curated skills gained 16.6 percentage points.

## Evidence with limits

- E064: the ablation table has Standard length at +21.5 pp, Compact at +19.0 pp, Detailed at +14.5 pp and Exhaustive at +0.7 pp (2026-08-02).
- E064: 2 to 3 skills scored +19.0 against +18.0 for one skill, with a cliff at 4 or more skills (+10.1).
- E064: the study reports named buckets, not line counts, so the 300 and 500 thresholds are not study results.
- E065: One-shot self-generated packs scored 8.1 to 11.5 points below no skills across Claude Code, Codex and Gemini CLI (2026-08-02).
- E065: Curated skills raised the average pass rate across 87 tasks from 33.9% to 50.5% over 18 configurations. The gain was 16.6 percentage points.
- Limits: Both checks used the same wiki summary on 2026-08-02. Neither checked the primary paper.
- State on main at 1be533c496 (2026-11-26): still wrong for E064. `src/claude/skills/skillforge/references/modularity-guidelines.md:50` and `src/claude/skills/skillforge/scripts/skill_modularity_audit.py:11` describe a curve with no penalty below 300 lines. The script sets a 100-line minimum at line 80 and penalizes shorter skills at line 134.
- State on main at 1be533c496 (2026-11-26): fixed for E065. `src/claude/skills/skillforge/references/modularity-guidelines.md:1-9` gives the gains and losses in percentage points.

## Decision

Treat the repo's line thresholds as local convention. Cite SkillsBench as favoring focused material over exhaustive coverage. Use percentage points, including the 8.1 to 11.5 point loss for self-generated skills.

The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.
