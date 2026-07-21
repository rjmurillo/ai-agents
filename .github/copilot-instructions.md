# GitHub Copilot Instructions

> **IMPORTANT**: File minimal. Cut context bloat. Detail in AGENTS.md.

## Global Behavioral Steering

For cross-harness behavior rules, local Copilot sessions can also read
`~/.copilot/copilot-instructions.md`. AGENTS.md remains this repository's
primary reference for ai-agents-specific rules.

Copilot Cloud cannot read local dotfiles. If you have access to Richard's
dotfiles repo, use the branch-agnostic fallback link in Key Documents.

## Agent Delegation for Complex Tasks

Multi-step tasks, specialized expertise, big context → prefer delegation via `#runSubagent` rather than inline handling.

| When to Delegate | Agent | Example Prompt |
|------------------|-------|----------------|
| Multi-step coordination | `orchestrator` | "Implement OAuth 2.0 with tests and docs" |
| Codebase exploration | `analyst` | "Investigate why cache invalidation fails" |
| Architecture decisions | `architect` | "Design the event sourcing pattern for orders" |
| Implementation work | `implementer` | "Implement the UserService per approved plan" |
| Plan validation | `critic` | "Review the migration plan for gaps" |
| Security review | `security` | "Assess auth flow for vulnerabilities" |

**Why delegate:**

- Context window efficient (agent start fresh)
- Specialized prompts + constraints
- Focused results to synthesize

**Delegation pattern:**

```text
#runSubagent orchestrator "Help me implement feature X end-to-end"
```

**Keep inline:** Simple single-file edits, quick lookups. No specialized reasoning needed.

## Primary Reference

**Read AGENTS.md FIRST** for full instructions:

- Session protocol (blocking gates)
- Agent catalog + workflows
- Directory structure
- GitHub workflow requirements
- Skill system
- Memory management
- Quality gates

**Path**: `../AGENTS.md` (repo root)

Before changing hooks, hook generators, agents, skills, instructions, rules, or
runtime scripts shared by Claude Code and Copilot CLI, load
`agent-harness-reference`. Execute contract changes through
`ai-agents-portability-campaign`. Do not infer one harness from another.

## Serena MCP Initialization (BLOCKING)

Serena MCP tools available → MUST call FIRST:

1. `serena/activate_project` (with project path)
2. `serena/initial_instructions`

**Check for**: Tools prefixed `serena/` or `mcp__serena__`

**If unavailable**: Skip Serena. Reference AGENTS.md for context.

## Critical Constraints (Quick Reference)

> **Full Details**: `../.agents/governance/PROJECT-CONSTRAINTS.md`

| Constraint | Source |
|------------|--------|
| Python first (.py preferred, PowerShell grandfathered) | ADR-042 |
| No raw gh when skill exists | usage-mandatory |
| No logic in workflow YAML | ADR-006 |
| Verify branch before git operations | SESSION-PROTOCOL |
| HANDOFF.md is read-only | ADR-014 |

## Session Protocol (Quick Reference)

> **Full Details**: `../.agents/SESSION-PROTOCOL.md`

**Session Start:**

1. Init Serena (if available)
2. Read HANDOFF.md (read-only dashboard)
3. Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.json`
4. Verify branch: `git branch --show-current`

**Session End:**

1. Complete session log
2. Update Serena memory (if available)
3. Run scoped markdownlint on changed files (ADR-043, see SESSION-PROTOCOL.md Phase 2)
4. Commit all changes
5. Run `python3 scripts/validate_session_json.py [log]`

## Gotchas (non-obvious, save cycles)

These recur across PRs and are not covered by AGENTS.md.

### PR description gate

The "PR Validation" workflow's description gate (`scripts/validation/pr_description.py --ci`, shown in branch protection as `PR Validation / Validate PR`) blocks merge on:

- A file-looking path (one with a known extension) that appears in inline code, bold, a list item, or a Markdown link and is not in the diff: CRITICAL "file mentioned but not in diff". The validator extracts paths only from those Markdown shapes, not from arbitrary prose, so a path mentioned in a plain sentence does not trip it, but an inline-backtick mention (`` `app.js` ``) does. Silence a real mention the way the validator recognizes: prefix with a citation cue (`` see `path` ``), use a fenced code block, a GitHub admonition (`> [!NOTE]`), or a contextual H2 (`## References`, `## Related Files`, `## See Also`, `## Notes`, `## Background`, and other proof or reference headings such as `## Evidence`, `## Out of Scope`, `## Prior Art`; see `_CONTEXTUAL_SECTION_NAMES` and `_REFERENCE_SECTION_PREFIXES` in the validator for the full set).
- Any em-dash (U+2014) or en-dash (U+2013) in the body: CRITICAL. Byte-verify both: `python3 -c "import sys;d=open(sys.argv[1],'rb').read();print(sum(d.count(c.encode()) for c in ('\u2014','\u2013')))" body.md`.

Editing the body re-triggers the gate (`pull_request: edited`); no new commit needed. Verify bot-flagged claims at byte level before editing; false positives happen.

### Markdown tables

Never place a literal `|` inside a table cell. Escape it (`\|`) or reword. A bare pipe breaks rendering and trips bot table-format flags.

### Invoking skill and hook scripts

- Prefer `uv run python` over bare `python3` for scripts that import project or third-party deps (for example `yaml`). Those resolve only in the project venv, so bare `python3` can fail `ModuleNotFoundError`; `uv run python` selects the venv deterministically. Dependency-free scripts run fine under either.
- Reference scripts by env-var-qualified plugin root, not a bare `.claude/skills/...` path: `"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/..."`. Bare `.claude/skills` paths fail under Copilot CLI and trip `check_skill_md_exec_portability.py`.

## Key Documents

1. **AGENTS.md** - Primary reference (read first)
2. `.agents/SESSION-PROTOCOL.md` - Session requirements
3. `.agents/HANDOFF.md` - Project dashboard (read-only)
4. `.agents/governance/PROJECT-CONSTRAINTS.md` - Hard constraints
5. `.agents/AGENT-SYSTEM.md` - Full agent details
6. **Global behavioral steering**: `~/.copilot/copilot-instructions.md` (local) or [`rjmurillo/ubuntu-machine-config/app-configs/copilot/copilot-instructions.md`](https://github.com/rjmurillo/ubuntu-machine-config/blob/HEAD/app-configs/copilot/copilot-instructions.md) (Copilot Cloud; requires repo access)

---

**Full docs, workflows, examples, best practices → [AGENTS.md](../AGENTS.md).**
