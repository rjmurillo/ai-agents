Already resolved. Commit `323da832` (`fix: remove broken reference to
deleted claude-skills.instructions.md`) removed the broken reference
from both:

- `.claude/rules/claude-agents.md` (the source rule)
- `.github/instructions/claude-agents.instructions.md` (the generated copy)

The remaining References section now points to
`.agents/steering/claude-skills.md`, which exists and is the
canonical authoring source for skill standards.
