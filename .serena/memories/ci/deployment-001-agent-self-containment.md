# Skill-Deployment-001: Agent Self-Containment

## Statement

Agent files ship as independent units - embed requirements, do not reference external files

## Context

When adding documentation, guidelines, or requirements to agent files. Agent files are copied to end-user machines (~/.claude/, ~/.copilot/, ~/.vscode/) without source tree access.

## Evidence

Commit 7d4e9d9 (2025-12-19): External reference to src/STYLE-GUIDE.md failed because agents ship independently. Fixed by embedding requirements in all 36 agent files.

## Metrics

- Atomicity: 95%
- Impact: 9/10
- Category: deployment, agent-development, self-contained
- Created: 2025-12-19
- Tag: helpful
- Validated: 1

## Related Skills

- Skill-Architecture-015 (Deployment Path Validation)
- Skill-Planning-022 (Multi-Platform Scope)

## Application Pattern

**Before**:

```markdown
**MUST READ**: Before producing any output, reference src/STYLE-GUIDE.md for:
```

**After**:

```markdown
**Communication Standards**:
- Use clear, direct language
- Avoid emojis unless explicitly requested
- Structure responses with headers
[...embedded content...]
```

## Anti-Pattern

Referencing external files from agent prompts that ship to end-user machines:

- src/STYLE-GUIDE.md
- .agents/governance/CONSTRAINTS.md
- Any file outside agent deployment directory

## Success Criteria

- Agent file contains all required content inline
- No references to paths outside deployment location
- Agent works independently when copied to ~/.claude/, ~/.copilot/, ~/.vscode/

## Update 2026-07-26: the plugin-marketplace form of this principle

The 2025-12-19 evidence above predates the plugin marketplace (ADR-045) and the
issue #2050 portability work. The principle held; the delivery model and the
tooling around it changed. Canonical rule is now
`.claude/rules/plugin-self-containment.md`. This section carries only the
retrieval context that is not in that rule.

**Three roots ship, nothing else.** `.claude/` and `src/copilot-cli/` both as
`project-toolkit`, `src/claude/` as `claude-agents`. A consumer receives one
source directory and nothing above it.

**The distinction that matters most.** A path outside the plugin root is not
automatically a defect. Three kinds:

- Bundled dependency, resolved through the plugin-root env vars: fine.
- Consumer-workspace path, for example an agent writing to `.agents/planning/`
  in the installing repo: fine, that is the plugin working.
- Upstream-only path that exists solely in `rjmurillo/ai-agents`: defect unless
  declared.

Conflating the second and third kinds is the common review error in both
directions. A grep cannot separate them.

**The declaration.** A legitimate upstream dependency is declared with a
`vendor-portability:` HTML comment, which suppresses the ratchets. 170 files
inside the plugin roots carry it.

**Every portability check is a baselined ratchet**, not a universal enforcer.
All four live in `scripts/validation/`: `check_vendor_portability.py`,
`check_skill_md_portability.py`, `check_skill_md_exec_portability.py`,
`check_skill_portability.py`. Passing
means "no new debt", never "this file is portable". Do not cite a green check
as proof of portability.

**Known gap as of this date.** The Markdown ratchet flags only `.agents/`,
`.claude/lib/`, and `.claude/review-axes/`. It does not flag
`templates/agents/` or `templates/platforms/`, which exist only upstream. Do
not widen this to a bare `templates/`: skills bundle their own `templates/`
and `assets/templates/` directories that ship correctly, and prose names
Flask's `templates/` convention. Narrow the pattern rather than declaring the
file, because the declaration suppresses every portability check for that file
and would hide a later real `.agents/` regression.

**Why it stays invisible.** The repository self-hosts its own plugins, so every
upstream path resolves during development and in most of CI.
