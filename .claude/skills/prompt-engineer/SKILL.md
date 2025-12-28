---
name: prompt-optimizer
description: Optimize system prompts for Claude Code agents using proven prompt engineering patterns. Use when users request prompt improvement, optimization, or refinement for agent workflows, tool instructions, or system behaviors.
---

# Prompt Optimizer

Optimizes system prompts by applying research-backed prompt engineering patterns. This skill operates through human-in-the-loop phases: understand, plan, propose changes, receive approval, then integrate.

## Purpose and Success Criteria

A well-optimized prompt achieves three things:

1. **Behavioral clarity**: The agent knows exactly what to do in common cases and how to handle edge cases.
2. **Appropriate scope**: Complex tasks get systematic decomposition; simple tasks don't trigger overthinking.
3. **Grounded changes**: Every modification traces to a specific pattern with documented behavioral impact.

Optimization is complete when:

- Every change has explicit pattern attribution from the reference document
- No section contradicts another section
- The prompt matches its operating context (tool-use vs. conversational, token constraints, failure modes)
- Human has approved both section-level changes and full integration

## When to Use This Skill

Use when the user provides a prompt and wants it improved, refined, or reviewed for best practices.

Do NOT use for:

- Writing prompts from scratch (different skill)
- Prompts that are already working well and user just wants validation (say so, don't force changes)
- Non-prompt content (documentation, code, etc.)

## Required Resources

Before ANY analysis, read the appropriate pattern reference(s):

### Single-Turn Reference (Always Read)

```
references/prompt-engineering-single-turn.md
```

This contains the complete catalog of single-turn patterns, including:

- The **Technique Selection Guide** table (maps domains, trigger conditions, stacking compatibility, conflicts, and expected effects)
- The **Quick Reference: Key Principles** (numbered list of foundational techniques)
- Domain-organized technique sections with research citations and examples
- The **Anti-Patterns to Avoid** section documenting common failure modes

### Multi-Turn Reference (Conditional)

```
references/prompt-engineering-multi-turn.md
```

**Read this reference ONLY when the prompt involves:**

- **Multi-turn flows**: Scripts or systems that inject prompts accumulating on a shared context (e.g., iterative refinement loops, conversation chains where previous outputs become subsequent inputs)
- **Multi-agent / sub-agent orchestration**: Parent/child agent patterns, agent handoffs, or workflows where one agent's output feeds into another agent's prompt

**Skip this reference for:**

- Static system prompts executed in a single LLM call
- Tool instructions or one-shot prompts
- Prompts that don't involve message accumulation or agent coordination

The multi-turn document covers techniques like Self-Refine, Chain-of-Verification, Universal Self-Consistency, and Multi-Chain Reasoning—patterns that exploit deliberate self-examination across multiple passes.

---

All technique selection decisions must be grounded in these references. Do not apply patterns from memory or general knowledge—consult the appropriate reference to ensure accuracy and to surface stacking/conflict information.

---

## Phase 0: Triage

Not every prompt needs the full optimization process. Before proceeding, assess complexity.

**Simple prompts** (use lightweight process):

- Under 20 lines
- Single clear purpose (one tool, one behavior)
- No conditional logic or branching
- No inter-section dependencies

**Complex prompts** (use full process):

- Multiple sections serving different functions
- Conditional behaviors or rule hierarchies
- Tool orchestration or multi-step workflows
- Known failure modes that need addressing

### Lightweight Process (Simple Prompts)

For simple prompts, skip section decomposition. Instead:

1. Read the prompt once, identify its purpose
2. Consult the reference's Anti-Patterns section to check for obvious problems
3. Consult the Technique Selection Guide to identify 1-3 applicable patterns
4. Propose targeted changes with pattern attribution
5. Present the optimized prompt directly

Do not over-engineer simple prompts.

### Full Process (Complex Prompts)

Proceed to Phase 1.

---

## Phase 1: Understand the Prompt

Before decomposing or modifying anything, understand what the prompt is trying to accomplish and the context in which it operates. This understanding phase is essential—without it, technique selection becomes guesswork.

Answer these questions (internally, not presented to user unless clarification needed):

### 1.1 Operating Context

- **Interaction model**: Is this single-shot (tool description, one-time instruction) or conversational (back-and-forth with user)?
- **Agent type**: Tool-use agent, coding agent, analysis agent, or general assistant?
- **Token constraints**: Is brevity critical, or is thoroughness more important?
- **Failure modes**: What goes wrong when this prompt fails? What behaviors is it trying to prevent?

### 1.2 Current State Assessment

- **What's working**: Which parts of the prompt are clear and effective? (Preserve these.)
- **What's unclear**: Which instructions are ambiguous or could be misinterpreted?
- **What's missing**: Are there obvious gaps—edge cases unhandled, examples absent, priorities unclear?

### 1.3 Document Observations

Before consulting the reference, write down specific observations about problems in the prompt. Examples of observable problems:

- "Lines 12-15 use hedging language ('might want to', 'could try')"
- "No examples provided for the expected output format"
- "Multiple rules marked CRITICAL with no clear precedence"
- "Instructions say what NOT to do but don't specify what TO do"

These observations become the input to technique selection in Phase 2.

---

## Phase 2: Plan — Select Techniques from Reference

With the prompt understood and problems documented, consult the reference to devise a plan.

### 2.1 Ground Technique Selection in the Reference

For each problem identified in Phase 1.3, locate the relevant technique in the reference document and **quote the specific text** that justifies applying it. This grounding step prevents pattern-shopping and ensures accurate application.

**For each candidate technique, extract from the reference:**

```markdown
### Technique: [Name]

**Quoted trigger condition**: "[exact text from Technique Selection Guide]"

**Quoted effect**: "[exact text describing behavioral impact]"

**Stacks with**: [list from reference]
**Conflicts with**: [list from reference]

**Problem this addresses**: [your observation from Phase 1.3]

**Why this matches**: [explain how the trigger condition matches the observed problem]
```

This quote-first approach forces commitment to specific evidence before reasoning about application. If you cannot quote a trigger condition that matches your observed problem, do not apply the technique.

### 2.2 Verify Technique Selection

Before finalizing the plan, verify each selection by asking yourself open verification questions (not yes/no questions, which bias toward confirmation):

- "What specific text in the prompt matches this technique's trigger condition?"
- "What is the expected behavioral change from applying this technique?"
- "Which other techniques does this conflict with, and am I applying any of them?"
- "What does the Anti-Patterns section say about related failure modes?"

If you cannot answer these questions by pointing to specific text in the reference or the prompt, reconsider the technique selection.

### 2.3 Present the Plan for User Approval (Visual Card Layout)

Present each proposed change as a visually distinct "card" using ASCII box drawing. This format prioritizes scannability—the user should grasp scope, problem, and proposed fix at a glance before approving.

**Wait for explicit approval** before proceeding to Phase 3.

**Card Template:**

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  CHANGE N: [Short title - what this change does]                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  SCOPE                                                                       ║
║  ─────                                                                       ║
║  Prompt:      [prompt name or "multi-prompt: A → B"]                         ║
║  Section:     [which part of the prompt]                                     ║
║  Downstream:  [what depends on this output, or "none"]                       ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  PROBLEM                                                                     ║
║  ───────                                                                     ║
║  Issue:    [One sentence - what's wrong]                                     ║
║                                                                              ║
║  Evidence: "[quoted problematic text from the prompt]"                       ║
║                                                                              ║
║  Runtime:  [What the user actually sees - concrete failure behavior]         ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  TECHNIQUE                                                                   ║
║  ─────────                                                                   ║
║  Apply:    [Technique name from reference]                                   ║
║                                                                              ║
║  Trigger:  "[quoted trigger condition from reference]"                       ║
║  Effect:   "[quoted expected effect from reference]"                         ║
║  Stacks:   [compatible techniques, or "none"]                                ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  BEFORE                                                                      ║
║  ──────                                                                      ║
║  ┌────────────────────────────────────────────────────────────────────────┐  ║
║  │ [Original prompt text - exact copy]                                    │  ║
║  └────────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
║                                     ▼                                        ║
║                                                                              ║
║  AFTER                                                                       ║
║  ─────                                                                       ║
║  ┌────────────────────────────────────────────────────────────────────────┐  ║
║  │ [Modified prompt text - exact copy]                                    │  ║
║  └────────────────────────────────────────────────────────────────────────┘  ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  WHY THIS IMPROVES QUALITY                                                   ║
║  ─────────────────────────                                                   ║
║  [1-2 sentences: concrete behavioral improvement expected]                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**For multi-prompt changes**, add an INTERACTION section between TECHNIQUE and BEFORE:

```
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  INTERACTION (how prompts connect)                                           ║
║  ─────────────────────────────────                                           ║
║                                                                              ║
║  Currently:                                                                  ║
║  ┌──────────┐   free-form text   ┌──────────┐                                ║
║  │ Prompt A │ ─────────────────▶ │ Prompt B │ ──▶ [failure mode]             ║
║  └──────────┘                    └──────────┘                                ║
║                                                                              ║
║  After change:                                                               ║
║  ┌──────────┐   structured XML   ┌──────────┐                                ║
║  │ Prompt A │ ─────────────────▶ │ Prompt B │ ──▶ [success outcome]          ║
║  └──────────┘                    └──────────┘                                ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
```

**After presenting all change cards:**

```markdown
**Compatibility check**:

- [Note any stacking opportunities]
- [Note any conflicts and how to resolve]

**Anti-patterns verified**: [Confirm you checked the Anti-Patterns section]

---

Does this plan look reasonable? I'll apply these changes once you confirm.
```

Do not proceed to Phase 3 without user confirmation.

---

## Phase 3: Execute — Apply Approved Changes

With the plan approved, apply the changes to the prompt. The detailed approval happened in Phase 2; execution is straightforward.

### 3.1 Apply Changes Systematically

Work through the approved changes in logical order (typically by prompt section). For each change:

1. Locate the target text in the prompt
2. Apply the BEFORE → AFTER transformation from the approved plan
3. Verify the modification matches what was approved

No additional approval is needed per change—the plan was already approved in Phase 2.

### 3.2 Handle Conflicts During Execution

When multiple techniques could apply to the same text but suggest different approaches, present the conflict to the user:

```markdown
### Conflict: [Section Name]

**Context**:

> "[Quoted text in question]"

**Option A: [Technique Name]**

- Reference says: "[quoted justification]"
- Would change text to: [proposed modification]
- Improves: [what aspect]
- Trade-off: [what you might lose]

**Option B: [Technique Name]**

- Reference says: "[quoted justification]"
- Would change text to: [proposed modification]
- Improves: [what aspect]
- Trade-off: [what you might lose]

**My recommendation**: [Which option and why, based on the prompt's operating context]

Which approach would you prefer?
```

Wait for user decision before proceeding.

---

## Phase 4: Integrate and Verify Quality

After section-by-section changes are approved, assemble the complete prompt and verify quality holistically.

### 4.1 Integration Checks

1. **Cross-section coherence**: Do sections reference each other correctly? Are there dangling references to removed content?

2. **Terminology consistency**: Does the prompt use the same terms throughout? (e.g., don't switch between "user", "human", and "person")

3. **Priority consistency**: If multiple sections establish priorities, do they align?

4. **Emphasis audit**: Count emphasis markers (CRITICAL, IMPORTANT, NEVER, ALWAYS). Per the reference's anti-patterns section, if more than 2-3 items use highest-level emphasis, reconsider.

5. **Flow and ordering**: Does the prompt follow logical progression?

### 4.2 Quality Verification

Verify the optimized prompt by asking open verification questions about each major change:

```markdown
## Quality Verification

For each significant change, verify it achieves the intended effect:

### Change: [brief description]

- **Intended effect**: "[quoted from reference]"
- **Verification question**: "[open question to check if the change works]"
- **Assessment**: [Does the modified text actually achieve this?]
```

**Example verification questions** (use open questions, not yes/no):

- "What behavior will this instruction produce in edge cases?"
- "How would an agent interpret this instruction if it skimmed the prompt?"
- "What could go wrong with this phrasing?"

If verification reveals issues, revise before presenting the final prompt.

### 4.3 Final Anti-Pattern Check

Re-consult the reference's Anti-Patterns section. Verify the optimized prompt doesn't exhibit:

- The Hedging Spiral (accumulated uncertainty language)
- The Everything-Is-Critical Problem (overuse of emphasis)
- The Negative Instruction Trap (telling what NOT to do instead of what TO do)
- The Implicit Category Trap (examples without explicit principles)
- Any other documented anti-patterns

### 4.4 Present Final Optimization for Approval

```markdown
## Optimized Prompt

[Complete optimized prompt text]

---

## Summary of Changes

**Techniques applied** (with reference sections):

1. [Technique]: [which section, what it improved]
2. [Technique]: [which section, what it improved]
   ...

**Quality improvements**:

1. [Most significant improvement and why it matters]
2. [Second most significant]
3. [Third most significant]

**Preserved from original**: [What was already working well and kept unchanged]

**Verification completed**: [Confirm you ran quality verification on major changes]

---

Please review the complete prompt. Let me know if you'd like any adjustments.
```

---

## Completion Checkpoint

Before presenting the final prompt, verify:

- [ ] Phase 1 context assessment was completed (operating context understood)
- [ ] Phase 2 plan used visual card format showing BEFORE/AFTER for each change
- [ ] Phase 2 plan quoted specific trigger conditions from the reference for each technique
- [ ] Phase 2 plan was approved by user before proceeding to Phase 3
- [ ] No technique was applied without matching its quoted trigger condition to an observed problem
- [ ] Open verification questions were used to check each technique selection (not yes/no)
- [ ] Stacking compatibility was checked; no conflicting techniques applied together
- [ ] Pattern conflicts were presented to user and resolved with their input
- [ ] No section contradicts another section
- [ ] Anti-patterns section was consulted; no anti-patterns introduced
- [ ] Emphasis markers are used sparingly (≤3 highest-level markers)
- [ ] Quality verification was performed on major changes
- [ ] Simple prompts were not over-engineered (Phase 0 triage respected)

If any checkbox fails, address it before presenting the final prompt.

---

## Quick Reference: The Process

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. READ THE REFERENCE(S)                                        │
│    - Always: references/prompt-engineering-single-turn.md       │
│    - If multi-turn/multi-agent: also read multi-turn reference  │
├─────────────────────────────────────────────────────────────────┤
│ 2. UNDERSTAND THE PROMPT (Phase 1)                              │
│    - Operating context (single-shot? tool-use? constraints?)    │
│    - Current state (working? unclear? missing?)                 │
│    - Document specific problems with quoted prompt text         │
├─────────────────────────────────────────────────────────────────┤
│ 3. PLAN WITH VISUAL CARDS (Phase 2)                             │
│    - Present each change as a visual card with:                 │
│      SCOPE → PROBLEM → TECHNIQUE → BEFORE/AFTER                 │
│    - Quote trigger conditions from reference                    │
│    - Show exact text transformations for user approval          │
│    - ⚠️  WAIT FOR USER APPROVAL before proceeding               │
├─────────────────────────────────────────────────────────────────┤
│ 4. EXECUTE APPROVED CHANGES (Phase 3)                           │
│    - Apply the BEFORE → AFTER transformations                   │
│    - No additional approval needed (plan was approved)          │
├─────────────────────────────────────────────────────────────────┤
│ 5. INTEGRATE AND VERIFY QUALITY (Phase 4)                       │
│    - Check cross-section coherence                              │
│    - Run quality verification on major changes                  │
│    - Final anti-pattern check                                   │
│    - Present complete optimized prompt                          │
└─────────────────────────────────────────────────────────────────┘
```

## Core Quality Principles

1. **Quote before deciding**: Every technique selection must quote the reference's trigger condition. Every change must quote the problematic prompt text. This grounds decisions in evidence, not intuition.

2. **Open verification questions**: Ask "What behavior will this produce?" not "Is this correct?" Open questions surface issues; yes/no questions bias toward confirmation.

3. **Approval happens once, upfront**: The visual card format in Phase 2 shows full impact (BEFORE/AFTER) so you can approve the complete plan. Phase 3 executes without re-approval.

4. **Preserve what works**: Optimization means improving problems, not rewriting everything. Explicitly note what you're keeping unchanged and why.
