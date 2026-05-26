# Method Extraction Template

Use during Phase 1 of `book-to-skill`. Fill out one of these per book. Output drives the SkillForge handoff in Phase 3.

## Book metadata

- Title:
- Author:
- Year (if known):
- Edition / chapter range covered:

## Five forcing questions

### Q1. What problem does this book solve?

One or two sentences. If you cannot name the problem, the book is a candidate for `llm-wiki` (reference), not a skill.

### Q2. What are the steps of the method, in order?

Numbered list. Concrete actions, not aphorisms. If you cannot produce at least two ordered steps, halt: the book has no extractable method.

1.
2.
3.

### Q3. What rules does the author repeat across chapters?

Short imperatives. Five or fewer is normal; more than ten is usually noise.

-
-

### Q4. What mistakes does the author warn against?

Pair each with the rule it violates (from Q3) when possible.

-
-

### Q5. What questions does the author ask the reader?

These become the diagnose-mode prompts. If the list is empty or trivial ("are you sure?"), the book is single-skill candidate, not split.

-
-

## Anti-patterns (do not extract)

- Author biography, war stories, anecdotes used as illustration only.
- Generic productivity advice not tied to the book's specific method.
- Quotes from other books the author cites.
- The author's introduction promising what the book will teach.

## Output

Save the answers as `method.json` (or YAML) in the workspace before moving to Phase 2.
