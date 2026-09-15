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

**Log format.** Write to Serena memory via `mcp__serena__write_memory` with name `decision-<short-slug>`. Body covers:

1. **Question**: one sentence on the decision.
2. **Conventional answer**: what Layer 1 or Layer 2 says, with a citation (ADR number, doc link, blog URL, codebase path).
3. **First-principles position**: what you concluded and the reasoning.
4. **Evidence**: file paths, benchmarks, real numbers, the specific constraint that breaks the conventional answer.
5. **Decision**: what was actually done and where it lives in the code.

Why log: the next reader (you in three months, or another agent next session) will hit the same fork and want the reasoning. Without the log they will either repeat the analysis or revert to the conventional answer and undo your work. The log compounds.

**When the memory write fails.** If `mcp__serena__write_memory` returns an error or the tool is unavailable, fall back to a code comment in the file the decision applies to. Format: a comment block with the same five fields (question, conventional answer, first-principles position, evidence, decision). The comment is worse than a memory entry (less searchable, no graph) but better than losing the reasoning.
