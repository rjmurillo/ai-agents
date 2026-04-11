---
source: wiki/concepts/AI Strategy/The Bitter Lesson of Building with LLMs.md
created: 2026-04-11
review-by: 2026-07-11
---

# The Bitter Lesson of Building with LLMs

As models get dramatically smarter (step changes, not incremental), simpler works best. Humans overestimate the value of their scaffolding, complex prompts, and multi-step processes. What worked for the last model generation over-constrains the next one.

## Core Principle

The art of prompting shifts from what you put in to what you leave out. Every instruction should pass: "Is this here because the model needs it, or because I needed the model to need it?"

## Four Things That Break on Step-Change Models

### 1. Prompt Scaffolding

- Audit per-line, not per-document
- Anthropic: "Add complexity only when it demonstrably improves outcomes"
- OpenAI Codex: "Just tell it what you need without long instructions"
- 3,000-token procedural prompts have 30-50% deletable content when model intelligence jumps
- Specify what and why, not how

### 2. Retrieval Architecture

- Stop predetermining retrieval logic. Let the model decide what enters context.
- Present organized, searchable sources; say "go look"
- Not "RAG is dead." The model should handle retrieval decisions in large context windows.

### 3. Hardcoded Domain Knowledge

- Count your rules. Which can the model infer from a single example?
- House style, report format, research methodology are inferrable at high fidelity
- Anecdote: 10-line research prompt replaced with one-liner produced better results (over-constraining)

### 4. Evaluation Strategy

- Moving from 85% to 99% correct changes the verification game
- One eval gate at the end, not intermediate checkpoints
- Final eval must test everything (functional + non-functional)
- Human review doesn't scale

## Mythos-Ready System Architecture

| Layer | Description |
|-------|-------------|
| Outcome specs | "Resolve this issue using our KB, policies, account history" (not 14-category intent classification) |
| Constraints | Business rules that survive model upgrades: "never disclose financial data" |
| Tools | Well-defined tool suite; model decides call order |
| Multi-agent | Planner model spins up capability-specific agents. 2-agent hierarchy > swarm |

## Meta-Skill for 2026

Model intelligence improvement modeling: seeing a new model coming and proactively simplifying workflows before it arrives.

"How much of my role is compensating for model limitations vs. architecting and aiming AI?" Lean toward the latter. Model limitations keep shrinking.

## Implications for Build vs Buy

1. Custom scaffolding depreciates faster than expected. Each model step-change invalidates complexity.
2. Simpler integrations with better models often beat complex integrations with current models.
3. Evaluate existing solutions against next-generation model capabilities, not just current ones.
4. Over-engineered prompt chains are technical debt that model improvements make worse, not better.
