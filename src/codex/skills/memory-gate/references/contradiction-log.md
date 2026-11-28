# The Contradiction Log

When first-principles reasoning contradicts conventional wisdom on a question that affects correctness, performance, security, or architecture, log it.

**What counts as contradiction worth logging:**

- Layer 1 says X (the textbook answer, the runtime built-in, the canonical pattern) and the problem in front of you makes Y correct instead.
- Layer 2 says X (the popular new approach) and analysis of the specific constraint shows X is wrong here.
- An ADR or memory says X and the current evidence shows the recorded position no longer holds.

**What does not need logging:**

- Routine style preferences.
- "I would have named it differently."
- Cases where the conventional answer is right and you confirmed it.

> Serena writes to the checkout active at server start, not your current
> directory. In a linked git worktree, or when you cannot tell, do not call
> Serena memory mutation tools. Make the same change to this checkout's
> `.serena/memories/` files, or return it to the parent session
> (`universal.md` MUST NOT 11, issue #5061).

**Log format.** The record is a committed file, `.serena/memories/decision-<short-slug>.md`. Write it with `mcp__serena__write_memory` (name `decision-<short-slug>`) when that tool targets this checkout, or edit the file directly. Body covers:

1. **Question**: one sentence on the decision.
2. **Conventional answer**: what Layer 1 or Layer 2 says, with a citation (ADR number, doc link, blog URL, codebase path).
3. **First-principles position**: what you concluded and the reasoning.
4. **Evidence**: file paths, benchmarks, real numbers, the specific constraint that breaks the conventional answer.
5. **Decision**: what was actually done and where it lives in the code.

In the same change, add a keyword line for the file to `.serena/memories/memory-index.md` (the `knowledge-persistence` rule, MUST 5). Every write path below, including the direct-edit fallback, includes this step.

Why log: the next reader (you in three months, or another agent next session) will hit the same fork and want the reasoning. Without the log they will either repeat the analysis or revert to the conventional answer and undo your work. The log compounds.

**When the memory write fails.** If `mcp__serena__write_memory` returns an error or the tool is unavailable, write the same file directly with the editor and commit it. That still satisfies the `builder-ethos` eureka record.

If any step fails, the record is blocked. The steps are: write `decision-<short-slug>.md`, update `memory-index.md`, and commit both. Causes include a read-only file or checkout, no commit access, and a rejected commit hook. Do two things:

1. Put a comment block with the same five fields in the file the decision applies to. Use the reply instead when that file must not be edited: it does not exist, cannot be written, is generated (regeneration discards the comment), or has no safe comment syntax (for example JSON).
2. Add one line to the reply: `Blocked record: decision-<short-slug>, <cause>`. The parent session or the user then commits the file.

A blocked record is reported, not silently dropped. The comment is worse than a memory entry (less searchable, no graph) but better than losing the reasoning.
