---
applyTo: "**"
priority: critical
---

# Search Before Building

Before building anything unfamiliar, **search first.** Operational rule. Pairs with [`builder-ethos.md`](./builder-ethos.md) section 2, which explains the philosophy. This file says what to do.

## When To Apply

Trigger this rule when any of the following is true:

- The task uses a runtime feature, library, framework, or platform you have not touched in this codebase before.
- The task asks for a pattern (retry, idempotency key, circuit breaker, queue topology, schema migration) that has a known canonical shape.
- The task is in a domain you do not have a memory or ADR for.
- You catch yourself starting from a blank file with no reference open.

If the task is a routine edit in code you already understand, skip the search. Search has a cost. Do not search for the sake of searching.

## The Three Layers

| Layer | Source | Action |
|-------|--------|--------|
| 1. Tried and true | Standard patterns, runtime built-ins, this codebase's existing solutions | Do not reinvent. Find the existing shape and use it. |
| 2. New and popular | Blog posts, ecosystem trends, fresh libraries | Scrutinize. Crowd can be wrong. Inputs to thinking, not answers. |
| 3. First principles | Reasoning from the specific problem | Prize above the other two. Where the leverage lives. |

## Where To Search

Use the cheapest source that answers the question. In order:

1. **This codebase.** `serena` symbol search, `grep`, ADRs in `.agents/architecture/`, existing skills in `.claude/skills/`. The pattern often already exists here.
2. **Serena memories.** `mcp__serena__find_symbol`, `mcp__serena__read_memory`. Past sessions logged what worked and what failed.
3. **Library docs.** `Context7` (`mcp__context7__resolve-library-id` then `get-library-docs`) for framework, SDK, and API questions. Beats web search on freshness for well-known libraries.
4. **DeepWiki.** `mcp__deepwiki__ask_question` for repo-level questions about a specific GitHub project.
5. **Web search.** WebSearch / Perplexity for novel or recent things not in the above.

Time-box the search. If you have not learned anything useful after 10 minutes, switch to first-principles reasoning and document what you tried.

## The Contradiction Log

When first-principles reasoning contradicts conventional wisdom on a question that matters, log it.

**What counts as contradiction worth logging:**

- Layer 1 says X (the textbook answer, the runtime built-in, the canonical pattern) and the problem in front of you makes Y correct instead.
- Layer 2 says X (the popular new approach) and analysis of the specific constraint shows X is wrong here.
- An ADR or memory says X and the current evidence shows the recorded position no longer holds.

**What does not need logging:**

- Routine style preferences.
- "I would have named it differently."
- Cases where the conventional answer is right and you confirmed it.

**Log format.** Write to Serena memory via `mcp__serena__write_memory` with name `decision-<short-slug>`. Body covers:

1. **Question**: one sentence on the decision.
2. **Conventional answer**: what Layer 1 or Layer 2 says, with a citation (ADR number, doc link, blog URL, codebase path).
3. **First-principles position**: what you concluded and the reasoning.
4. **Evidence**: file paths, benchmarks, real numbers, the specific constraint that breaks the conventional answer.
5. **Decision**: what was actually done and where it lives in the code.

Why log: the next reader (you in three months, or another agent next session) will hit the same fork and want the reasoning. Without the log they will either repeat the analysis or revert to the conventional answer and undo your work. The log compounds.

## Quick Self-Review

Before writing the first line of code on an unfamiliar task:

- Did you check this codebase for an existing solution?
- Did you check Serena memories and ADRs?
- For library or framework questions, did you check Context7 instead of guessing?
- If your design contradicts the conventional answer, did you log the reasoning to Serena memory before merging?

If any answer is "no" or "not sure," go back and search before you build.
