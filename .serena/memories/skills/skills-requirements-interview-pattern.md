# Skill: requirements-interview (grill-me pattern)

**Status:** Active in `/spec` step 2 as of PR #1812 (feat/1798-autonomous).
**Issue:** #1798 (Option C — skill + /spec wiring + spec-generator handoff).
**Source:** Matt Pocock's grill-me skill (https://github.com/mattpocock/skills),
adapted from Brooks' "design tree" concept in *The Design of Design*.

## What it does

Adversarial requirements interview that walks the design tree before any code or
design work. Invoked first thing in `/spec`. Grills the user on user stories,
data model, integrations, failure modes, security, observability, and scope
boundaries. Question discipline:

- For every question, the skill proposes a recommended answer with cited evidence.
- If the codebase can answer it (grep first), the skill answers without asking.
- One decision per question. No bundling.
- Walks branches depth-first; resolves dependencies before siblings (a storage
  decision constrains the consistency model, so the storage question fires first).
- Stops when the design tree has no unresolved leaves.

## Why it exists

Pre-skill, generation-without-alignment was the dominant failure mode. JetBrains
ICSE 2026 measured 50%+ of dev time in review/edit of AI output. Faros 2026
showed +200% review time and +242% incidents per PR when alignment was skipped.
The skill is the alignment forcing function.

## End-to-end flow inside /spec

1. Clarify problem
2. **requirements-interview skill emits structured PRD** (Problem, User stories,
   Data model, Integrations, Failure modes, Security, Observability, Acceptance
   criteria, Out of scope, Deferred, Open questions)
3-5. PRD carries through complexity classification, codebase search, CVA
6. **spec-generator agent formalizes** PRD into REQ-NNN/DESIGN-NNN/TASK-NNN
   files in `.agents/specs/`
7-9. analyst, decision-critic, critic pre-mortem run against the durable artifacts

## Files

- Skill: `.claude/skills/requirements-interview/SKILL.md`
- Tests: `.claude/skills/requirements-interview/tests/test_skill_contract.py`
- Wiring: `.claude/commands/spec.md` step 2 + step 6
- Handoff target: `.claude/agents/spec-generator.md`

## Hard-won lessons from PR #1812

- **SkillForge validator (`.claude/skills/SkillForge/scripts/validate-skill.py`)
  is enforced by `.githooks/pre-commit`.** Three constraints bit late:
  1. Frontmatter `triggers:` field is NOT in `ALLOWED_PROPERTIES`. Use the
     `## Triggers` markdown section; the validator's `validate_triggers` regex
     parses backtick-quoted phrases inline.
  2. Required section heading: `## Process` (not `## Method`) or `### Phase N`.
  3. Required section heading: `## Verification` / `## Success Criteria` /
     `## Checklist` (not `## Quality Gates`). Concrete checkboxes preferred.
- **Test contract (`tests/test_skill_contract.py`) must mirror `REQUIRED_SECTIONS`
  in SKILL.md.** Renaming sections without updating tests breaks 10/10 → fail.
- **`/spec` step 6 used to drop the PRD schema.** CodeRabbit caught it on
  PR #1812. Refactor commit `f036ad54` carries every PRD section forward.
  Feature commit `d6284f80` then hands the PRD to spec-generator.
- **Two-commit discipline (refactor then feat) per `.claude/rules/refactoring.md`
  was preserved** even when the bot's original commit shipped both at once.
  Bisectability is worth the extra commit.

## Known gaps (deferred)

- **Analyst agent integration** (Issue #1798 Option C narrow read): the
  `analyst` agent prompt is NOT updated to invoke this skill in its default
  flow. `/spec` wiring is sufficient for the alignment-before-generation goal,
  but a dedicated follow-up issue should add analyst-agent invocation if
  analyst is ever called outside `/spec`.
- **Test refactor** (Gemini comments on PR #1812): test duplicates
  `VALID_MODEL_ALIASES`, `_NAME_PATTERN`, `_XML_TAG_PATTERN` from
  `scripts/validation/skill_frontmatter.py`. Promoting the validator's private
  constants to public exports and refactoring the test to import them is
  out-of-scope for #1812 (touches the shared validator). Track separately.

## Related

- [skills-index](../skills-index.md)
