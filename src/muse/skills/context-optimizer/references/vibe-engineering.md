---
source: wiki/concepts/AI Productivity/Vibe Engineering.md
created: 2026-04-11
review-by: 2026-07-11
---

# Vibe Engineering: 7-Step Agent Interaction Protocol

Structured LLM interaction framework from Google Chrome Engineering, popularized by Addy Osmani's agent-skills repo. Applied to every LLM interaction, not just debugging.

## The 7 Steps

### 1. Clarify the Goal

What is the actual outcome? Not "fix the bug" but "make the error message actionable for a junior dev." The goal must be verifiable.

### 2. Gather Context

Relevant code paths, constraints (performance, compatibility, security), prior attempts and why they failed, assumptions that might be wrong.

Anti-pattern: skipping context causes hallucination or solutions that violate constraints.

### 3. Break It Down

Decompose into atomic, independent steps. Each step: ~5-10 minutes agent time, clear success criterion, no dependency on future steps. If a step is >30 minutes, break it down further.

### 4. Execute with Iteration

Run the step. Check the output. If it didn't work, adjust and retry within the same step before moving on. Iteration happens at the micro level (per step), not at the end.

### 5. Verify the Result

How do you know the step succeeded? Tests pass, output matches expected format, performance meets target, error case handled.

Anti-pattern: "looks good" without verification causes silent drift.

### 6. Reflect on the Process

What went well? What slowed you down? What would you do differently? This updates the agent's working model of "what works" for this codebase.

### 7. Document the Learning

Capture the pattern for reuse: code comment, wiki entry, skill file update, memory note. Step 7 is how agent-skills grows. Every interaction that produces a reusable pattern becomes a skill.

## Why "Vibe Engineering"

The agent structures human intuition ("vibes") into verifiable steps. Good vibe engineering means the agent executes on intuition without over-specification.

## Key Insight: Anti-Patterns > Examples

Showing what NOT to do is more valuable than showing correct examples. Agents (and humans) learn boundaries faster than ideal paths.

"Don't start a review with nitpicks" is more actionable than "here's a perfect review."

Every skill should have an Anti-Patterns section first.

## Context Optimization Relevance

The 7-step protocol applies at the prompt level (every message), while project workflows apply it at the project level (issues, PRs). The context-optimizer skill can use this framework to evaluate whether context placement decisions follow the clarify-gather-verify pattern.

| Vibe Engineering Step | Context Optimization Equivalent |
|---|---|
| Clarify the Goal | Define what the agent needs to know |
| Gather Context | Determine passive vs skill placement |
| Break It Down | Extract-and-index sections |
| Execute with Iteration | Compress and validate |
| Verify the Result | Compliance check (test_skill_passive_compliance.py) |
| Reflect | Measure token reduction achieved |
| Document | Update SKILL.md references |
