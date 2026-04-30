Acknowledged. Three real concerns flagged in the source `invoke_skill_learning.py`:

1. **Privacy default**: `SKILL_LEARNING_USE_LLM` defaults to true, sending session transcripts to Anthropic without explicit opt-in. Should flip to opt-in (default false), with documented setup for operators who want the LLM classification path.
2. **Implicit credential resolution**: `get_api_key()` silently picks up `ANTHROPIC_API_KEY` from environment or `.env` without operator awareness. Should require an explicit opt-in flag in addition to the key.
3. **No timeout on Anthropic call**: per `.claude/rules/release-it.md` (Timeouts on Every Outbound Call) and the codebase's lifecycle-hook guidance, every external call must be bounded. Today the SessionEnd hook can hang indefinitely if the API stalls.

Source-side fixes needed in `.claude/hooks/PostToolUse/invoke_skill_learning.py` (or wherever the live source is registered). Out of scope for this PR (which is the build pipeline existing); will track as a P0 follow-up because privacy defaults and unbounded blocking are both real risks. Leaving unresolved.
