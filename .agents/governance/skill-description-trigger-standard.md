# Skill Description and Trigger Standard

**Version**: 2.0
**Date**: 2026-01-03
**Status**: Canonical Standard
**Applies To**: All new skills, skill updates

## Purpose

Maximize skill discoverability through excellent descriptions and efficient body structure.

---

## Core Principle

**The model selects skills based on description**. Description must be excellent. Body is lazy-loaded via progressive disclosure, so keep it concise and practical.

---

## Part 1: Description (Frontmatter)

### Requirements

Per Anthropic Claude Code specification:

- **Mandatory**: `name` and `description` only
- **Description is primary trigger**: Include trigger keywords for discoverability
- **Length**: 10+ words minimum (validator enforces), 150-250 chars recommended
- **Format**: Action verb + what + when + trigger keywords + outcome
- **No angle brackets**: `<` or `>` will fail validation

### Formula

```
[ACTION VERB] + [WHAT] + [WHEN WITH TRIGGER KEYWORDS] + [OUTCOME]
```

### Excellent Examples

**Observed-error pattern** (illustrative; the skill this example was drawn
from was later removed, but the pattern still applies):

```yaml
description: Fix a validation failure in GitHub Actions. Use when a PR fails
  with "Validation failed", "MUST requirement(s) not met", "NON_COMPLIANT"
  verdict, or "Aggregate Results: FAIL".
```

- Trigger keywords: exact error messages users will see
- When: explicit failure scenarios
- Outcome: implied (passing validation)

**research-and-incorporate**:
```yaml
description: Research external topics, create comprehensive analysis, determine
  project applicability, and incorporate learnings into Serena and Forgetful
  memory systems. Transforms knowledge into searchable, actionable context.
```

- What: research, analyze, incorporate
- Outcome: "searchable, actionable context"
- Trigger keywords: implicit in workflow verbs

### Common Mistakes

| Mistake | Why It Fails | Fix |
|---------|--------------|-----|
| "Handles memory operations" | No trigger keywords, vague | "Search and manage memories across Serena and Forgetful. Use when needing past context or creating new memories." |
| "Populates Forgetful via LSP" | Too technical, no when | "Encode codebase into searchable knowledge graph. Use when onboarding to repository or refreshing project understanding." |
| "Collects metrics" | No use case | "Collect agent usage metrics from git history. Use when measuring agent adoption or system health over time." |

### SKIP Clause for Sibling Families

A sibling family is the set of skills whose directory names share the same leading hyphen-delimited token. Examples: `memory-*`, `context-*`, `session-*`, `security-*`, `adr-*`, and `ai-agents-*`. Theme-only groupings do not create an enforceable family unless this standard names them explicitly.

When a skill is in a sibling family with two or more members, its description **MUST** include a SKIP clause that names at least one real sibling skill and routes away from it.

A positive trigger alone over-triggers across the family: the router matches the shared keyword and cannot deterministically pick the right member. The remediation is a negative trigger. This is the Over-triggering remediation from the wiki `Skill Triggering Failure Modes` page: "Add negative triggers: 'Do NOT use for X (use Y skill instead).'"

**Format**:

```
Do NOT use for [sibling's job]; use [sibling-name] instead.
```

**Rules**:

- Name at least one real sibling skill that exists in the repo.
- Use one of the validator-recognized route forms: `(use sibling-skill)`, `(use sibling-a or sibling-b)`, `use sibling-skill instead`, or `; use sibling-skill`.
- Keep the sibling family's routing graph connected when edges are read without direction. Pairwise reciprocity is not required; it does not fit large families under the description budget.
- Keep the description under 1024 chars and free of angle brackets (AIP-02).

**Example** (`context-gather` vs `context-optimizer`, which both match "context" but do opposite jobs):

```yaml
description: Gather context from memory and docs before planning. Use when you say
  "gather context before planning". Do NOT use for compressing or placing skill
  text; use context-optimizer instead.
```

---

## Part 2: Body Structure (Progressive Disclosure)

Body is lazy-loaded. Keep it concise and practical.

### Required Elements

1. **Trigger table or list** (phrase → operation mapping)
2. **Decision trees** (when to use vs alternatives)
3. **Anti-patterns** (what NOT to do)
4. **Verification checklists** (how to validate success)

### Optional Elements (use references/)

- Deep implementation details
- Advanced scenarios
- Historical context

### Trigger Table Format

Map user phrases to operations:

```markdown
## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| "get PR context for #123" | Get-PRContext.ps1 |
| "respond to review comments" | Post-PRCommentReply.ps1 |
| "merge this PR" | Merge-PR.ps1 |
```

Or categorized lists:

```markdown
## Triggers

### Creation
- `create skill` - Natural language activation
- `design skill for {purpose}` - Purpose-first creation

### Improvement
- `improve {skill}` - Enter improvement mode
```

### Decision Trees

Show when to use this skill vs alternatives:

```markdown
## When to Use

Use this skill when:
- [ ] Condition A is true
- [ ] Condition B is present
- [ ] You need outcome X

Use alternative skill when:
- [ ] Condition C is true (use skill-Y instead)
```

### Anti-Patterns

Prevent common mistakes:

```markdown
## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Recreating from memory | Miss exact structure | Copy from template |
| Marking MUST as N/A | Validation fails | Provide justification |
| Placeholder evidence | Validators detect | Use real evidence text |
```

### Verification Checklist

Help users validate success:

```markdown
## Verification

After execution:
- [ ] Output file exists at expected path
- [ ] Validation script passes
- [ ] Commit includes all changes
- [ ] CI workflow triggered
```

---

## Part 3: Token Efficiency

### Progressive Disclosure Pattern

**Main SKILL.md**: Concise, practical, complete workflow

**references/ directory**: Deep dives, advanced scenarios, historical context

Example from adr-review:

```
SKILL.md (token-efficient):
- Quick Start
- Triggers table
- When to Use
- Anti-Patterns
- Verification checklist

references/:
- debate-protocol.md (detailed Phases 0-4)
- deletion-workflow.md (D1-D4 workflow)
- issue-resolution.md (P0/P1/P2 handling)
- artifacts.md (output formats)
```

### Concise Structure

| Section | Max Lines | Purpose |
|---------|-----------|---------|
| Triggers | 10-15 | Phrase mapping |
| When to Use | 5-10 | Decision criteria |
| Anti-Patterns | 5-10 | Common mistakes |
| Verification | 5-10 | Success checklist |

Deep content goes in `references/`.

---

## Part 4: Validation

### Pre-Commit Validation

The SkillForge validator (`.claude/skills/SkillForge/scripts/validate-skill.py`) checks:

1. ✅ Description exists (1-1024 chars)
2. ✅ Description has 10+ words
3. ✅ Description has no angle brackets
4. ✅ Frontmatter is valid YAML

**Note**: Validator checks WORD COUNT (10+ words), not character count. 150-250 chars is recommended for readability but not enforced.

### Security Requirements

Trigger phrases MUST use character whitelist: `[a-zA-Z0-9 \-:,.'"]`

Operation paths in trigger tables MUST:
- Be relative paths only (no `..`)
- Reference scripts in skill directory
- Not execute arbitrary commands

### Manual Review Checklist

Before marking skill complete:

- [ ] Description has action verb
- [ ] Description includes trigger keywords (how users will search)
- [ ] Description has "Use when" or equivalent
- [ ] Description mentions outcome
- [ ] Body has trigger table/list
- [ ] Body has decision tree or "when to use"
- [ ] Body has anti-patterns table
- [ ] Body has verification checklist
- [ ] Deep content moved to references/
- [ ] No changelog section in body
- [ ] No version/date metadata in body

### Independent-Distribution Validation

Every check above scores a phrase the author wrote against a rule the author
wrote. That is a closed loop, and a closed loop cannot tell you whether anyone
would ever type the phrase.

**Measured.** Trigger phrases were matched against real user prompts mined from
local Claude Code transcripts, on word boundaries, excluding slash commands and
single words.

| Corpus | Phrase set | Ever said | Share |
|---|---|---|---|
| 640 prompts, 480 transcripts (issue #3509) | documented in a `## Triggers` table | 22 of 212 | 10.4% |
| 640 prompts, 480 transcripts (issue #3509) | promoted into a description | 8 of 140 | 5.7% |
| 524 prompts, 1713 transcripts (2026-07-29) | documented in a `## Triggers` table | 5 of 211 | 2.4% |
| 524 prompts, 1713 transcripts (2026-07-29) | promoted into a description | 7 of 280 | 2.5% |

Two independent corpora agree on direction. Most documented trigger phrases have
never been typed by a real user. The phrases that do occur are short and
conversational: `do it`, `your call`, `security review`, `create a PR`,
`create session log`, `compare models`.

**What this claims.** This is evidence about provenance, not about the router.
The router is a model doing semantic matching, so a phrase nobody typed verbatim
can still route correctly. What the number establishes is that the phrases were
authored rather than observed.

**Why provenance matters.** A practitioner's skill-activation classifier scored
93 percent precision and recall on 40 prompts he wrote, then 27 percent
precision on 86 prompts mined from his own transcripts. Same classifier, same
author. The only variable was who wrote the prompts.

**Two authoring rules.**

1. Prefer an observed phrase to an invented one. The best example in this
   document already follows the rule: the observed-error pattern above
   quotes the exact CI error strings a user will paste, not phrasings its
   author imagined.
2. Never benchmark trigger phrases on prompts you wrote. A score against your
   own prompts measures your consistency, not the phrase.

**Two matching rules that are load-bearing** when you measure this yourself.

- Anchor on word boundaries. A bare substring test counted `analyze` 60 times in
  one corpus, every occurrence inside ordinary prose.
- Exclude slash commands and single words. A slash command is dispatched by name
  and never consults a description, so counting it measures the dispatcher.

**Reproducing the measurement.** No CI gate enforces this, and none should. The
transcript store is local to a developer machine and absent on a runner, so a CI
arm would be silently inert. Run it on demand instead. Collect user turns from
`~/.claude/projects/**/*.jsonl` where `type` is `user`, `isSidechain` is falsy,
and `message.content` is a string. Match each phrase with `\b<phrase>\b`,
case-insensitively, after dropping slash commands and single words.

**A caution on the corpus.** In the 2026-07-29 run only 59 of 524 prompts
carried `promptSource: typed`. The rest were `sdk`, `system`, or unlabelled,
meaning much of the corpus is agent-injected rather than human-typed. Report the
`promptSource` split alongside any realism figure.

**What this does not license.** Do not bulk-promote table phrases into
descriptions to raise a coverage score. That optimizes the closed loop and adds
permanent context cost for phrases with a 2 to 10 percent chance of ever being
typed. Promote a phrase when it names a capability the description omits, not to
make a table and a description agree.

---

## Part 5: Examples by Skill Type

### Automation Skills (metrics, security-detection)

**Description pattern**: `Collect/Detect + [data] + Use when [condition] + [outcome]`

**Body must have**:
- Trigger phrases for metric types
- Decision tree (when to use this vs manual)
- Verification checklist (validate output format)

### Workflow Skills (milestone-planner, research-and-incorporate)

**Description pattern**: `[Workflow verb] + [multi-step process] + Use when [starting condition] + [outcome]`

**Body must have**:
- Trigger table mapping phrases to workflow stages
- Decision tree (when full workflow vs shortcuts)
- Anti-patterns (common workflow mistakes)

### Diagnostic Skills (incoherence, analyze)

**Description pattern**: `Detect/Analyze + [problems] + Use when [symptoms] + [outcome]`

**Body must have**:
- Trigger phrases for symptoms
- Decision tree (what to analyze vs ignore)
- Verification checklist (validate findings)

---

## References

- [Skill Description Trigger Review](../analysis/skill-description-trigger-review.md) - 28-skill analysis
- `Skill Triggering Failure Modes` (wiki: Agent Instruction Patterns) - Over-triggering remediation backing the SKIP clause requirement
- [SkillForge Specification](../../.claude/skills/SkillForge/SKILL.md) - Skill creation framework
- [Session 372](../sessions/2026-01-03-session-372.json) - Standard creation session
- [ADR Review Debate Log](../critique/skill-description-trigger-standard-debate-log.md) - P0 issues addressed
