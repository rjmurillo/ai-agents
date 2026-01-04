# Skill-autonomous-execution-003: User Patch as Signal

**Statement**: Unsolicited user patch indicates agent understanding gap; pause and verify comprehension before continuing.

**Context**: When user provides code patch without requesting it, this signals the agent has not understood the problem or solution space. Pause autonomous execution and verify understanding before proceeding.

**Evidence**: PR #760 user provided patches after agent claimed fix was complete. This was a signal that agent's fix was incomplete or incorrect. User providing patch = agent knowledge gap, not additional helpful context.

**Atomicity**: 89% | **Impact**: 8/10

## Pattern

When user provides unsolicited code patch:

1. **Pause autonomous execution** - Stop making further changes
2. **Analyze patch** - What does it show about your understanding?
   - Does it reveal an issue you missed?
   - Does it show a pattern you didn't implement?
   - Does it indicate misunderstanding of requirements?
3. **Ask clarifying question** - One of:
   - "I see you provided this patch. Does my current approach miss [specific point]?"
   - "What aspect of the problem does your patch address that I may have overlooked?"
   - "Should I incorporate your patch, or was this just an example?"
4. **Resume with verified understanding** - Don't continue assuming you're correct

## Anti-Pattern

Never treat user patch as optional input. User providing patch = blocker signal:
- Don't ignore it and continue with your approach
- Don't apply it and move on without understanding
- Don't assume you're correct and user is just being helpful

User patch means agent understanding is incomplete.
