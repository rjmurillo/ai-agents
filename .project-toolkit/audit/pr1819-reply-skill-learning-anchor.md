Confirmed bug. `Path(__file__).resolve().parents[3]` was authored against the source layout `.claude/hooks/sessionEnd/invoke_skill_learning.py` (parents[3] = repo root). After the generator copies it to `src/copilot-cli/hooks/sessionEnd/invoke_skill_learning.py` (one extra `src/copilot-cli` prefix), parents[3] = `.../src` instead of the project root. Pattern loading, session lookup, and memory writes then resolve under `src/.claude`, `src/.agents`, `src/.serena` -- none of which exist.

Same structural class as comment 3162257714 (lib path resolution post-copy). The source script anchors safety to its own ancestor, which the build-time copy invalidates.

Real fix needs the runtime to anchor on the validated project root from the hook input (`hook_input["cwd"]` or `os.environ["CLAUDE_PROJECT_DIR"]`) rather than walking ancestors of `__file__`. That change goes in the source `.claude/hooks/PostToolUse/invoke_skill_learning.py` or wherever the live source actually lives, then regenerates.

Tracking as M7 follow-up alongside the lib-path fix. Leaving unresolved.
