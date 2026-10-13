# Modularity Guidelines (SkillsBench)

SkillsBench (Feb 2026) ran 87 tasks across 18 model and harness configurations. Curated
skills moved average task-macro pass rate from 33.9% to 50.5%, a gain of 16.6 percentage
points. The gain varied by configuration, from +4.1 to +25.7 points.

One-shot self-generated skill packs scored 8.1 to 11.5 points *below* running with no skill
at all, across Claude Code, Codex, and Gemini CLI. On those same configurations curated
skills added 18.2 to 24.8 points. A model writing its own skill before the task is worse
than no skill, not neutral.

## What the study measured about skill shape

| Skill shape | Average change |
|---|---:|
| One skill | +18.0 pp |
| Two to three skills | +19.0 pp |
| Four or more skills | +10.1 pp |
| Compact | +19.0 pp |
| Standard length | +21.5 pp |
| Detailed | +14.5 pp |
| Exhaustive documentation | +0.7 pp |

Read the table before applying the guidelines below. It supports **focused over exhaustive**.
It does not support "shorter is always better."

- Standard length beat compact by 2.5 points. Cutting a skill to its shortest form was not
  the winning move.
- Two to three skills beat one skill by 1.0 point. That is close enough to call a tie.
- Splitting too far cost about half the gain. Four or more skills returned +10.1 pp against
  +19.0 pp for two to three.
- Exhaustive documentation cost nearly all of it. It returned +0.7 pp against +21.5 pp for
  standard length, a 97% collapse. Detailed still returned +14.5 pp, so the failure is at
  the exhaustive end, not at length generally.

## Provenance of the targets below

The study reported named buckets, not line counts. It never published a line threshold. The
numbers in the next table are this repository's convention, chosen to keep skills inside the
"standard length" and "two to three skills" range that scored best. Treat them as a proxy for
focus, not as a study finding.

| Guideline | Target | Basis |
|-----------|--------|-------|
| SKILL.md lines | <=300 ideal, 500 max | Repo convention, proxy for focus |
| Top-level sections (h2) | <=10 | Repo convention, signals single responsibility |
| Progressive disclosure | Use scripts/, references/, templates/ | Keeps the prompt focused |
| Modularity score | >=80 | Run the audit script |

The audit script's length curve is one-sided. `_score_modularity` subtracts points above 300
lines and subtracts nothing below, so a 40-line skill and a 280-line skill score identically
on length, and no check flags a skill as too short. The table above says compact returned 2.5
points less than standard length. An author who cuts toward the floor to protect the score is
optimizing away from the measured optimum, and the tool stays silent. Tracked at
<https://github.com/rjmurillo/ai-agents/issues/4327>.

## Compare against no skill before you claim the skill helps

SkillsBench adds an authoring gate that a size audit cannot replace. Compare the skill
against no skill and against the incumbent skill on representative tasks. Thirteen of the 87
tasks had negative deltas: the skill made the agent worse. A skill that reads well and lowers
terminal success is polished failure.

The self-generated result is the sharpest form of this. In the trajectory audit, 10 of 12
Codex and Gemini runs never listed, read, or mentioned the generated pack. Passes and
failures were unrelated to what the pack said. A skill on disk is not a skill in use.

## Refactoring Targets

When a skill exceeds these targets, refactor by:

1. Extract reference tables and examples to `references/`
2. Move procedural logic to `scripts/`
3. Split skills with >10 h2 sections into focused sub-skills
4. Use `templates/` for structured output formats

Stop at two to three skills. Four or more lost about half the gain.

## Audit Command

```bash
ROOT="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
python3 "$ROOT/skills/skillforge/scripts/skill_modularity_audit.py" [--json] [--ci]
```
