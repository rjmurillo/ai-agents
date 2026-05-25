---
applyTo: "**"
priority: critical
---

# Search Before Building

Before building anything unfamiliar, **search first.** Operational rule. Pairs with the sibling rule `builder-ethos.md` section 2, which explains the philosophy. This file says what to do.

Sibling reference, not link: this rule file is mirrored into multiple instruction trees under different file names (`builder-ethos.md` in `.claude/rules/`, `builder-ethos.instructions.md` in `.github/instructions/` and `src/copilot-cli/instructions/`). A relative link breaks in two of the three trees. Look the file up by name in whichever tree the reader is in.

## When To Apply

Trigger this rule when any of the following is true:

- The task uses a runtime feature, library, framework, or platform you have not touched in this codebase before.
- The task asks for a pattern (retry, idempotency key, circuit breaker, queue topology, schema migration) that has a known canonical shape.
- The task is in a domain you do not have a memory or ADR for.
- You catch yourself starting from a blank file with no reference open.

**When to skip the search.** Skip when the edit only modifies code already open in the conversation context AND introduces no new APIs, libraries, or patterns. If either condition fails, run at least Layer 1. Search has a cost; do not search for the sake of searching, but do not skip because you "feel familiar" either. Familiarity without a recent read of the file is a hallucination signal.

## The Three Layers

| Layer | Source | Action |
|-------|--------|--------|
| 1. Tried and true | Standard patterns, runtime built-ins, this codebase's existing solutions | Do not reinvent. Find the existing shape and use it. |
| 2. New and popular | Blog posts, ecosystem trends, fresh libraries | Scrutinize. Crowd can be wrong. Inputs to thinking, not answers. |
| 3. First principles | Reasoning from the specific problem | Prize above the other two. Where the leverage lives. |

**Layer interaction.** Layer 3 prizes _reasoning_ over the other two, not _skipping_ them. The order is: collect Layer 1 (what exists), check Layer 2 (what is current), then apply Layer 3 to the specific constraint. Layer 3 reasoning that contradicts Layers 1-2 is the eureka moment; log it (see Contradiction Log below). Layer 3 reasoning that bypasses Layers 1-2 because you "already know" is a hallucination shaped like confidence.

**When layers disagree.** If the codebase pattern (Layer 1) contradicts current library docs (Layer 2), prefer the current docs. The codebase pattern may be frozen against an older version of the library. Log the discrepancy as a contradiction.

**When search tools fail.** If a search tool (Serena, Context7, DeepWiki, web) is unavailable, errors, or returns empty, drop to the next source in the list and note the failure in your response so the user knows what was not searched. Do not retry a failed tool more than once per task.

## Where To Search

Use the cheapest source that answers the question. In order:

1. **This codebase.** `serena` symbol search, `grep`, ADRs in `.agents/architecture/`, existing skills in `.claude/skills/`. The pattern often already exists here.
2. **Serena memories.** `mcp__serena__find_symbol`, `mcp__serena__read_memory`. Past sessions logged what worked and what failed.
3. **Library docs.** `Context7` (`mcp__context7__resolve-library-id` then `get-library-docs`) for framework, SDK, and API questions. Beats web search on freshness for well-known libraries.
4. **DeepWiki.** `mcp__deepwiki__ask_question` for repo-level questions about a specific GitHub project.
5. **Web search.** WebSearch / Perplexity for novel or recent things not in the above.

**Bound the search.** If three tool calls have not surfaced anything useful, stop searching and switch to first-principles reasoning. Document what you tried (which tool, what query, what came back) so the user can extend the search if the answer matters more than your time budget suggests.

## The Contradiction Log

When first-principles reasoning contradicts conventional wisdom on a question that affects correctness, performance, security, or architecture, log it.

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

**When the memory write fails.** If `mcp__serena__write_memory` returns an error or the tool is unavailable, fall back to a code comment in the file the decision applies to. Format: a comment block with the same five fields (question, conventional answer, first-principles position, evidence, decision). The comment is worse than a memory entry (less searchable, no graph) but better than losing the reasoning.

## Quick Self-Review

Before writing the first line of code on an unfamiliar task:

- Did you check this codebase for an existing solution (Layer 1)?
- Did you check Serena memories and ADRs?
- For library or framework questions, did you check Context7 instead of guessing (Layer 2)?
- If your design contradicts the conventional answer, did you log the reasoning to Serena memory (or to a fallback code comment) before merging?

If any answer is "no" or "not sure," go back and search before you build.

**Layer 3 short-circuit.** The checklist does not block you from acting on first-principles reasoning when Layers 1 and 2 came back empty or stale. The checklist demands you LOOKED, not that you found anything. "No" because you skipped the search is a problem. "No" because you searched and the codebase has no precedent is a finding; record it in the contradiction log and proceed.
