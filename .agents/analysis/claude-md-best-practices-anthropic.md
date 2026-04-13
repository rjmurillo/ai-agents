# Analysis: Claude.md Best Practices from Anthropic

> **Research Date**: 2025-01-04
> **Source**: <https://www.claude.com/blog/using-claude-md-files>
> **Additional Sources**: Anthropic Engineering Blog, Community Best Practices

## Executive Summary

Anthropic's official guidance on CLAUDE.md files reveals several alignment points and improvement opportunities for the ai-agents project. Our current minimal CLAUDE.md approach (66 lines pointing to AGENTS.md) aligns with the "keep it concise" principle, but we underutilize advanced features like `@imports`, the `.claude/rules/` directory, and hierarchical file placement. This analysis identifies 8 specific improvements that could reduce context window waste and improve Claude's performance in our codebase.

## 1. Anthropic's Core Guidance

### 1.1 What is CLAUDE.md?

Anthropic describes CLAUDE.md as "a configuration file that Claude automatically incorporates into every conversation, ensuring it always knows your project structure, coding standards, and preferred workflows."

Key characteristics:

- **Always loaded**: CLAUDE.md content is part of every Claude Code session
- **Hierarchical**: Files at different locations merge in a specific order
- **Human-readable**: Should be documentation that both humans and Claude understand

### 1.2 File Location Hierarchy

CLAUDE.md files are loaded in this order (later files can override earlier ones):

| Location | Scope | Use Case |
|----------|-------|----------|
| `~/.claude/CLAUDE.md` | All sessions, all projects | Personal preferences, global constraints |
| Project root `CLAUDE.md` | All work in repository | Team conventions, architecture |
| Subdirectory `CLAUDE.md` | On-demand when working in directory | Module-specific guidance |
| Parent directory `CLAUDE.md` | Monorepo scenarios | Shared conventions across packages |

### 1.3 Recommended File Size

**Anthropic's recommendation**: 100-200 lines maximum.

**Rationale**: CLAUDE.md is added to context every session. Large files waste tokens on every interaction. If you exceed 200 lines, move details into per-folder files or use `@imports`.

### 1.4 Content Categories

Effective CLAUDE.md documentation should cover:

| Category | Content |
|----------|---------|
| **WHAT** | Tech stack, project structure, dependencies |
| **WHY** | Purpose, goals, what the repository is for |
| **HOW** | Workflows, commands, conventions |

Anthropic explicitly recommends including:

- Common bash commands for development
- Core utilities and helper functions
- Code style guidelines (with caveats)
- Testing instructions and frameworks
- Repository conventions
- Developer environment setup
- Project-specific warnings or constraints

## 2. Advanced Features

### 2.1 @imports for File Inclusion

CLAUDE.md supports importing additional files:

```markdown
@path/to/additional-context.md
@.claude/rules/security.md
```

Features:

- Recursive imports (max depth: 5 hops)
- Can import from home directory for personal instructions not in repo
- Allows modular organization of guidance

### 2.2 .claude/rules/ Directory

For larger projects, Anthropic recommends the `.claude/rules/` directory:

- Teams can maintain focused, well-organized rule files
- Avoids one monolithic CLAUDE.md
- Files are loaded alongside CLAUDE.md

### 2.3 Custom Commands

Repetitive prompts can be stored as markdown files in `.claude/commands/`:

- Commands support arguments via `$ARGUMENTS` or numbered placeholders
- Example: `/performance-optimization` command for code analysis
- Reduces repetition and ensures consistency

### 2.4 /init Command

The `/init` command automates CLAUDE.md creation:

- Analyzes package files, documentation, configuration, and code structure
- Generates tailored configuration reflecting detected patterns
- Serves as a starting point, not a finished product
- Can be run on existing projects to suggest improvements

## 3. Anti-Patterns to Avoid

### 3.1 Linting and Style Guidelines

**Anthropic's Warning**: "Never send an LLM to do a linter's job."

Reasons:

- LLMs are comparably expensive and slow
- Code style guidelines add instructions that degrade performance
- Use actual linters (ESLint, Prettier, markdownlint, etc.) instead

**Implication for ai-agents**: Our AGENTS.md includes style guidance. This should be enforced by tooling (we already use markdownlint-cli2) rather than in prompts.

### 3.2 Excessive Content Without Iteration

"CLAUDE.md files become part of Claude's prompts, so they should be refined like any frequently used prompt; a common mistake is adding extensive content without iterating on its effectiveness."

### 3.3 Not Using /clear Between Tasks

Anthropic recommends using `/clear` between distinct tasks to reset context while preserving CLAUDE.md. Without this, accumulated history reduces signal-to-noise ratio.

### 3.4 Monolithic Files

Large CLAUDE.md files waste tokens. Break into:

- Hierarchical CLAUDE.md files (per directory)
- `.claude/rules/` directory
- `@imports` for modular content

## 4. Current State Analysis: ai-agents Project

### 4.1 Our Current Architecture

| File | Lines | Purpose |
|------|-------|---------|
| `CLAUDE.md` | 66 | Minimal pointer to AGENTS.md |
| `AGENTS.md` | 1,532 | Comprehensive agent instructions |
| `.agents/SESSION-PROTOCOL.md` | ~300 | Session requirements |
| `.agents/governance/PROJECT-CONSTRAINTS.md` | 149 | Hard constraints |

### 4.2 Alignment with Anthropic Guidance

| Aspect | Anthropic Guidance | Our Implementation | Status |
|--------|-------------------|-------------------|--------|
| File size | 100-200 lines | CLAUDE.md: 66 lines | ALIGNED |
| Concise format | Human-readable, minimal | Pointer pattern | ALIGNED |
| Critical constraints | Quick reference | Table format | ALIGNED |
| Hierarchical files | Use subdirectory CLAUDE.md | Not used | GAP |
| @imports | Use for modular content | Not used | GAP |
| .claude/rules/ | For larger projects | Not used | GAP |
| Custom commands | .claude/commands/ | Extensive (40+ commands) | ALIGNED |
| /init command | Generate or validate | Not documented | GAP |
| Linting in prompts | Avoid | Style in AGENTS.md | PARTIAL GAP |
| Workflows | Define in CLAUDE.md | In AGENTS.md | ALIGNED |

### 4.3 Token Efficiency Analysis

Our current approach requires Claude to:

1. Load CLAUDE.md (66 lines, ~500 tokens)
2. Read AGENTS.md (1,532 lines, ~12,000 tokens) - **manual read required**
3. Read SESSION-PROTOCOL.md (~300 lines, ~2,400 tokens) - **manual read required**

**Problem**: The manual reads happen every session. If we used @imports, Claude would automatically receive the most critical content without tool calls.

However, our memory-token-efficiency memory documents the trade-off: loading everything upfront vs. on-demand retrieval. Our current approach favors on-demand (read when needed) to avoid context bloat.

## 5. Gap Analysis and Recommendations

### 5.1 Gap: No @imports Usage

**Current**: CLAUDE.md tells Claude to "Read AGENTS.md FIRST"

**Anthropic Pattern**:

```markdown
# CLAUDE.md
@.agents/CRITICAL-CONTEXT.md
```

**Recommendation**: Create a minimal `CRITICAL-CONTEXT.md` with only the most essential constraints (~50 lines) and import it. Keep detailed docs (AGENTS.md, SESSION-PROTOCOL.md) as on-demand reads.

**Trade-off Analysis**:

| Approach | Tokens/Session | Context Quality |
|----------|---------------|-----------------|
| Current (manual reads) | ~15,000 (when all read) | High (full context) |
| Import everything | ~15,000 (auto-loaded) | High but bloated |
| Import critical subset | ~1,500 (auto) + on-demand | Balanced |

**Decision**: Import only blocking gates and critical constraints (~50 lines). Keep detailed docs as on-demand.

### 5.2 Gap: No .claude/rules/ Directory

We have `.claude/commands/` (40+ files) but no `.claude/rules/`.

**Recommendation**: Evaluate whether our agent-specific rules belong in `.claude/rules/`:

- Session protocol rules
- Commit message rules
- Security rules

**Decision Needed**: Does `.claude/rules/` add value beyond `@imports`? Research required.

### 5.3 Gap: Hierarchical CLAUDE.md Not Used

We have no subdirectory CLAUDE.md files. For our codebase:

| Directory | Potential CLAUDE.md Content |
|-----------|-----------------------------|
| `.claude/skills/` | Skill development conventions |
| `src/claude/` | Agent authoring guidelines |
| `scripts/` | PowerShell coding standards |
| `.github/workflows/` | Workflow constraints (ADR-006) |

**Recommendation**: Add CLAUDE.md files to high-traffic directories with directory-specific guidance.

### 5.4 Gap: Linting in Prompt Instructions

AGENTS.md includes style guidance (lines 1362-1385). Anthropic says this degrades performance.

**Current State**: We already use markdownlint-cli2 for linting. The AGENTS.md content is for human readability, not Claude enforcement.

**Assessment**: This is a documentation pattern, not an anti-pattern. No change needed if we trust the linter.

### 5.5 Gap: /init Documentation

We don't document using `/init` to validate or regenerate CLAUDE.md.

**Recommendation**: Add to session start checklist: "Run `/init` periodically to identify missing patterns."

### 5.6 Opportunity: Subagent Usage Documentation

Anthropic recommends subagents for distinct work phases. Our Task tool system already does this, but it's not explicitly documented in CLAUDE.md.

**Recommendation**: Add brief subagent guidance to CLAUDE.md quick reference:

```markdown
## Default Behavior
For any non-trivial task: `Task(subagent_type="orchestrator", prompt="...")`
```

**Status**: Already implemented (line 51-53 in CLAUDE.md).

### 5.7 Opportunity: /clear Command Documentation

Anthropic recommends `/clear` between distinct tasks. Not documented in our CLAUDE.md.

**Recommendation**: Add to session management section if not already present.

### 5.8 Opportunity: Token Optimization via Critical Content Extraction

Extract the absolute minimum blocking content from AGENTS.md into a file that can be @imported:

```markdown
# CRITICAL-CONTEXT.md (~50 lines)
- PowerShell only (ADR-005)
- No raw gh when skill exists
- Verify branch before git operations
- HANDOFF.md is read-only (ADR-014)
- Session start: activate Serena, read HANDOFF, create session log
- Session end: update memory, lint, validate, commit
```

This would provide essential context automatically while keeping detailed docs on-demand.

## 6. Integration Points with Existing Governance

### 6.1 ADRs Affected

| ADR | Relationship |
|-----|--------------|
| ADR-005 (PowerShell Only) | Constraint in CLAUDE.md quick reference |
| ADR-006 (Thin Workflows) | Constraint in CLAUDE.md quick reference |
| ADR-007 (Memory First) | Session protocol documented in AGENTS.md |
| ADR-014 (HANDOFF Read-Only) | Constraint in CLAUDE.md quick reference |

### 6.2 Memory System Alignment

The `memory-token-efficiency` memory documents our atomic file approach. The @import pattern aligns with this: import only what's critical, retrieve the rest on-demand.

### 6.3 Session Protocol Alignment

SESSION-PROTOCOL.md defines blocking gates. These could be extracted into an @imported file for automatic loading.

## 7. Implementation Recommendations

### 7.1 Immediate (No Breaking Changes)

1. **Document /init usage** in AGENTS.md session management section
2. **Document /clear usage** for context management between tasks
3. **Update CLAUDE.md comment** to clarify why it's minimal (token efficiency)

### 7.2 Short-Term (Minor Enhancements)

4. **Create CRITICAL-CONTEXT.md** (~50 lines) with blocking gates
5. **Add @import** in CLAUDE.md to auto-load critical context
6. **Add subdirectory CLAUDE.md** to high-traffic directories (skills, scripts)

### 7.3 Medium-Term (Evaluation Required)

7. **Evaluate .claude/rules/** directory structure
8. **Run /init** on repository and compare against current CLAUDE.md
9. **Measure token savings** from @import approach vs. current manual reads

## 8. Quantitative Impact Assessment

| Change | Estimated Token Impact | Complexity |
|--------|----------------------|------------|
| Import CRITICAL-CONTEXT.md (~50 lines) | +400 tokens/session (auto) | Low |
| Eliminate redundant AGENTS.md reads | -12,000 tokens (when skipped) | N/A |
| Subdirectory CLAUDE.md files | +200-500 tokens (on-demand) | Medium |
| .claude/rules/ migration | Neutral (restructure only) | High |

**Net Assessment**: The @import of critical context adds ~400 tokens per session but eliminates the need for tool calls to read basic constraints. For sessions that would have read AGENTS.md anyway, no change. For quick tasks, we save the AGENTS.md read.

## 9. Conclusion

Anthropic's CLAUDE.md guidance validates our minimal approach but reveals underutilized features. The key opportunity is the @import pattern for automatic loading of blocking gates. Our extensive `.claude/commands/` system already aligns with Anthropic's custom commands recommendation.

**Primary Recommendation**: Create CRITICAL-CONTEXT.md with ~50 lines of blocking gates and @import it from CLAUDE.md. Keep AGENTS.md as comprehensive reference for on-demand reading.

**Secondary Recommendation**: Add CLAUDE.md files to high-traffic subdirectories (skills, scripts) for directory-specific guidance.

**No Action Needed**: Our file size (66 lines), custom commands system, and session protocol documentation already align with Anthropic best practices.

## Sources

- [Using CLAUDE.MD files: Customizing Claude Code for your codebase | Claude](https://claude.com/blog/using-claude-md-files)
- [Claude Code: Best practices for agentic coding | Anthropic Engineering](https://www.anthropic.com/engineering/claude-code-best-practices)
- [CLAUDE.md: Best Practices from Optimizing Claude Code | Arize](https://arize.com/blog/claude-md-best-practices-learned-from-optimizing-claude-code-with-prompt-learning/)
- [Writing a good CLAUDE.md | HumanLayer Blog](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [Notes on CLAUDE.md Structure | callmephilip](https://callmephilip.com/posts/notes-on-claude-md-structure-and-best-practices/)
- [Manage Claude's memory | Claude Code Docs](https://code.claude.com/docs/en/memory)
