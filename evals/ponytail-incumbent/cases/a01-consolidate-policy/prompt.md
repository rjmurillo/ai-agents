---
name: a01-consolidate-policy
tags: [decision, ai-agents-delta, canonical-policy]
max_turns: 3
allowed_tools: []
---

Our repository serves two AI coding harnesses. The testing policy lives in two hand-edited files: `.claude/rules/testing.md` and `.github/instructions/testing.instructions.md`. They drifted: one requires 80% line coverage, the other 90%. The build already renders other rule files for both harnesses from one template under `templates/rules/`. Both harnesses accept the same markdown body; only the frontmatter differs, and the renderer already writes each harness's frontmatter.

What change do you make? Explain in at most five sentences. End your reply with one final line of the form `DECISION: <LABEL>`, where LABEL is exactly one of: CONSOLIDATE (one canonical source that the build renders to both locations), SYNC (edit both files to agree, optionally adding a check that they stay equal).
