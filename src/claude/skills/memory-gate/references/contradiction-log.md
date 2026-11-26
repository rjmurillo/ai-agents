# The Contradiction Log

When first-principles reasoning or a measured result contradicts conventional wisdom on a question that affects correctness, performance, security, or architecture, log it.

**What counts as contradiction worth logging:**

- Layer 1 says X (the textbook answer, the runtime built-in, the canonical pattern) and the problem in front of you makes Y correct instead.
- Layer 2 says X (the popular new approach) and analysis of the specific constraint shows X is wrong here.
- An ADR or memory says X and the current evidence shows the recorded position no longer holds.
- A probe, A/B run, eval, benchmark, or ablation produced numbers that disagree with what a memory, ADR, skill, doc, or common guidance predicted.

**Log it when the task ends without shipping.** A "do not ship" verdict, a
reverted experiment, or a closed spike still owes the log. The finding is often
the most valuable output, and these are the tasks that lose it. A result that
lives only in a scratch file, a tool result, or a chat reply is not logged.

**What does not need logging:**

- Routine style preferences.
- "I would have named it differently."
- Cases where the conventional answer is right and you confirmed it.
- A routine bug fix, unless the bug proved a recorded position wrong.

**Log format.** Name the entry `decision-<short-slug>`, where the slug states
the finding, for example `decision-the-retrieval-instruction-beats-the-docs-file-map`.
The body covers:

1. **Question**: one sentence on the decision.
2. **Conventional answer**: what Layer 1 or Layer 2 says, with a citation (ADR number, doc link, blog URL, codebase path).
3. **First-principles position**: what you concluded and the reasoning.
4. **Evidence**: file paths, benchmarks, real numbers, the specific constraint that breaks the conventional answer. Name the commit, date, and model when they affect the result. State the limits, such as sample size or one fixture.
5. **Decision**: what was actually done and where it lives in the code.

Keep secrets, private data, and raw transcripts out of the entry.

**Where to write it.** Follow the `memory` skill's Write a Durable Project
Fact procedure. It resolves the repository store by folder: `.serena/memories/`
when that folder exists, else the repository notes folder that procedure
names (ADR-126). The
Serena MCP server is optional; file tools on the same folder work.

1. Search the store for the same finding first. Update a matching entry, and
   add a dated pointer to any older entry the new evidence supersedes.
2. Write the entry. In an indexed Serena corpus, add its row to the matching
   domain `*-index` file in the same change.
3. When the host also configures a memory service for this project, retain
   the same entry there. A service is a retrieval aid, not a replacement for
   the repository entry.
4. State in the reply where the entry landed.

> Serena writes to the checkout active at server start, not your current
> directory. In a linked git worktree, or when you cannot tell, do not call
> Serena memory mutation tools. Make the same change to this checkout's
> memory folder with file tools, or return it to the parent session
> (`universal.md` MUST NOT 11, issue #5061).

Why log: the next reader (you in three months, or another agent next session) will hit the same fork and want the reasoning. Without the log they will either repeat the analysis or revert to the conventional answer and undo your work. The log compounds.

**When no store is writable.** If the checkout is read-only or the write
fails, return the five fields to the parent session or the user with the
intended entry name. As a last resort, put a comment block with the same five
fields in the file the decision applies to. The comment is worse than a memory
entry (less searchable, no graph) but better than losing the reasoning.
