---
name: book-to-skill
version: 1.0.0
model: claude-sonnet-4-6
description: "Input adapter that extracts a book's method into a structured payload and hands it off to SkillForge. Use when an operator wants to turn a methodology-bearing book (The Mom Test, Make It Stick, Influence, The Pragmatic Programmer, etc.) into one or more executable skills without hand-crafting the SkillForge prompt or bypassing SkillForge's triage and review gates."
license: MIT
---

# book-to-skill

Convert a book's method into the structured input SkillForge needs, then hand off. This skill does NOT generate SKILL.md, score timelessness, triage duplicates, or run activation tests. Those are SkillForge's job.

## Triggers

| Trigger phrase | Operation |
|----------------|-----------|
| `turn this book into a skill` | Full workflow: extract method, decide split, hand off to SkillForge |
| `book-to-skill: <title>` | Same as above, with title named upfront |
| `extract method from <book title>` | Phase 1 only: produce the structured payload, do not invoke SkillForge |
| `propose diagnose/apply split for <book>` | Phase 2 only: decide single vs split, no extraction or hand-off |

## When to Use

Use this skill when:

- An operator has a book in hand and wants the method captured as one or more skills.
- The book contains a repeatable method (numbered steps, named rules, recurring questions, identified failure modes), not just narrative or argument.
- You want SkillForge's Phase 0-4 gates (triage, timelessness, multi-agent review) to decide whether the skill ships, instead of writing SKILL.md by hand.

Use a different skill when:

- The source is a transcript, voice memo, or unstructured capture. Use `panning-for-gold`.
- The goal is reference knowledge, not executable procedure. Use `llm-wiki`.
- You already know exactly what skill you want and need it produced from a goal description rather than a book. Invoke `SkillForge` directly.
- You want to compose existing skills into a slash command. Use `slashcommandcreator`.

## Out of Scope (do NOT do these)

- Source acquisition. PDFs, ePubs, Kindle decryption, paid summaries. Operator-and-legal problem.
- Producing SKILL.md. SkillForge owns this.
- Triage against existing skills (the 80% duplicate scan). SkillForge's Phase 0 owns this.
- Timelessness scoring. SkillForge's Phase 2.
- Activation tests, paraphrase tests, negative tests. SkillForge's Phase 4 multi-agent panel.
- Fiction, memoir, or pure-narrative books. Halt at Phase 1 pre-condition.

## Process

Three phases. Each has a clear input, output, and halt condition.

### Phase 1: Extract the method

Apply five forcing questions to the book content. Record answers in `method.json` (the structured payload SkillForge consumes).

1. What problem does this book solve?
2. What are the steps of the method, in order?
3. What rules does the author repeat across chapters?
4. What mistakes does the author warn against?
5. What questions does the author ask the reader?

**Pre-condition halt.** If you cannot answer Q2 with at least two ordered, concrete steps, the book has no extractable method. Stop. Report to the operator: "This book has no extractable method. Steps required for Phase 2 are absent." Suggest `llm-wiki` if the operator wants a reference page instead.

Worked template: see `references/method-extraction-template.md`.

### Phase 2: Decide diagnose/apply split

Some books carry two distinct layers:

- **Elicitation questions** (Q5 returned non-trivial questions the operator can run on their own situation): "are you doing this wrong?"
- **Transformation templates** (Q2 returned a multi-step output recipe): "here is how to do it right."

Decision rules:

- Q5 non-trivial AND Q2 multi-step → **split**. Two SkillForge invocations: `<book>-diagnose` (questions, runs on operator's situation) and `<book>-apply` (steps, produces output).
- Only one layer → **single skill**.
- Unsure → default **single**. Refactor to split later if usage shows two distinct invocation modes.

Worked example (*The Mom Test* by Rob Fitzpatrick): Q5 returns the leading-question detector, Q2 returns the Rob Fitzpatrick rewrite format. Split. Produces `momtest-diagnose` (finds leading questions in a draft interview) and `momtest-apply` (rewrites them).

Worksheet: see `references/split-decision-worksheet.md`.

### Phase 3: Hand off to SkillForge

Emit one or two SkillForge invocations using this format. Do not edit the payload after this point; SkillForge owns everything downstream.

```text
SkillForge: create skill <book-slug>[-diagnose|-apply]

Source method:
- Problem: <Phase 1 Q1>
- Steps: <Phase 1 Q2, ordered>
- Rules: <Phase 1 Q3>
- Mistakes: <Phase 1 Q4>
- Questions: <Phase 1 Q5>

Source attribution: "<book title>" by <author>, <year if known>
Diagnose/apply split decision: <single | diagnose | apply> (with one-line rationale)

Do NOT use this skill for:
- <adjacent-but-wrong task 1>
- <adjacent-but-wrong task 2>
- <adjacent-but-wrong task 3>
```

### SkillForge triage feedback loop

When SkillForge's Phase 0 returns >=80% match against an existing skill, do NOT silently proceed and do NOT second-guess the triage. Report the match to the operator with these three options:

1. Abandon. The existing skill already covers it.
2. Refine. Phase 1 extraction may have been too generic; re-run with sharper scope.
3. Override. Proceed despite the match (operator owns the decision).

## Anti-patterns

- Producing SKILL.md yourself. Hand off, do not generate.
- Skipping the pre-condition halt for fiction. The check is cheap; running Phase 1 on a novel is not.
- Forcing a split when the book only has one layer. Default single, refactor later.
- Acquiring the source for the operator. Out of scope.
- Editing the hand-off payload to flatter SkillForge's triage. The whole point is letting SkillForge decide.
- Running activation tests in this skill. SkillForge owns Phase 4.

## Relationship to other skills

| Skill | Relationship |
|-------|--------------|
| `SkillForge` | Downstream consumer. Receives the Phase 3 payload. |
| `slashcommandcreator` | Further downstream. Composes finished skills into commands. |
| `llm-wiki` | Orthogonal. Wiki = reference; skill = procedure. |
| `panning-for-gold` | Different input (transcripts) and output (thread inventory). |

## Source

- Ruben Hassid, "How to AI" infographic, r/Agent_AI 2026-05-09. Origin of the five-question template and the diagnose/apply split idea.
- The hand-off-to-SkillForge architecture (instead of duplicating SkillForge's Phase 0-4 work) is this skill's contribution.

## Acceptance verification

Run this skill on a real book before declaring it done. Suggested first run: *The Mom Test*. Expected output: two SkillForge invocations (`momtest-diagnose`, `momtest-apply`). SkillForge's own Phase 0-4 gates whether the resulting skills ship. If SkillForge rejects either skill at Phase 0 (duplicate), Phase 2 (low timelessness), or Phase 4 (failed activation tests), `book-to-skill` did its job correctly: it produced a clean input. The rejection is signal, not failure.
