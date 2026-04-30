Fixed in commit 4d9b8b49 (rebased to current head). Source-side wording change in `.claude/skills/SkillForge/SKILL.md`:

Was (line 769): the original criterion text described scripts as if they could operate with no human oversight at all -- exact wording removed from this reply file because the autonomy heuristic flags the literal phrase even inside a quoted citation. The phrasing read as a blanket directive, which semgrep flagged.

Now: `Scripts complete cleanly without interactive prompts during scoped, user-approved invocations`. This scopes the autonomy criterion to (a) the script-level (not the agent-level), (b) within an already-user-approved skill invocation, (c) the absence of interactive prompts (a real automation property), not the absence of human oversight.

The criterion's intent stays the same — scripts should be designed to run end-to-end without per-step prompts during a single skill execution — but the wording no longer reads as a license for unsupervised execution.

Generated copy under `src/copilot-cli/skills/SkillForge/SKILL.md` regenerated via `build_all.py`.

Resolving.
