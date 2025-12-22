# CodeRabbit AI Learnings Skills

Category: Review Bot Configuration and Conventions
Source: CodeRabbit AI learnings export (2025-12-20)
Import Method: Bulk import from CSV with atomicity validation

## Summary

- **Total Learnings Imported**: 12
- **Valid Skills Created**: 8
- **Duplicates Identified**: 4 (already in skills-linting)
- **Partial Duplicates**: 1 (incorporated into Skill-CodeRabbit-008; not counted separately)

---

## Valid Skills (Atomic, High-Impact)

### Skill-CodeRabbit-001: MCP Tool Path Case Sensitivity (95%)

- **Statement**: MCP tool path identifiers (e.g., `github/*`, `cloudmcp-manager/*`) are case-sensitive technical identifiers that must match the MCP server configuration exactly. Do not suggest capitalizing them to "GitHub" even when they appear in backticks.
- **Context**: Code review on markdown documentation containing MCP tool references
- **Evidence**: PR #15 (vs-code-agents), CodeRabbit review on `.github/copilot-code-review.md`
- **Impact**: Prevents false positive review comments on technical paths
- **Application**: When reviewing markdown, distinguish between technical path identifiers (case-sensitive, lowercase) and prose references to platforms (capitalized)

### Skill-CodeRabbit-002: Template Bracket Notation Placeholders (93%)

- **Statement**: Agent template files use bracket notation placeholders like `[List of...]` to indicate where agents should fill in context-specific content during execution. These are intentional template guidance, not incomplete documentation.
- **Context**: Code review on agent template files with placeholder syntax
- **Evidence**: PR #15 (vs-code-agents), CodeRabbit review on `copilot-cli/retrospective.agent.md`
- **Impact**: Prevents false positive comments flagging placeholders as incomplete
- **Application**: Recognize bracket patterns in `.agent.md` files as runtime placeholders

### Skill-CodeRabbit-003: Infrastructure Naming Avoids Spaces (90%)

- **Statement**: Infrastructure files (.github/workflows, .githooks, scripts) follow naming conventions that avoid spaces. Prioritize readability over handling edge cases like filenames with spaces/newlines in workflows.
- **Context**: Code review on workflow files handling file paths
- **Evidence**: PR #57 (vs-code-agents), CodeRabbit review on `.github/workflows/routing-check.yml`
- **Impact**: Prevents over-engineering defensive code for edge cases that will not occur
- **Application**: When reviewing infrastructure scripts, do not require space-handling code unless the project specifically supports filenames with spaces

### Skill-CodeRabbit-004: Expression Injection Labeling Is Intentional (95%)

- **Statement**: In security documentation, "VULNERABLE" vs "SECURE" labeling for GitHub Actions expression injection examples is intentionally strong for pedagogical purposes. Echo statements with direct GitHub expression interpolation are genuinely vulnerable to log injection attacks.
- **Context**: Security documentation review with vulnerability examples
- **Evidence**: PR #57 (vs-code-agents), CodeRabbit review on `docs/secure-infrastructure-guide.md`
- **Impact**: Prevents false positive comments softening intentional security warnings
- **Application**: When reviewing security documentation, recognize that strong vulnerability labels on echo statements with `${{ }}` interpolation are accurate, not hyperbolic

### Skill-CodeRabbit-005: MCP Tool Naming with Duplicated Segments (92%)

- **Statement**: In MCP tool naming, the pattern `mcp__[server]__[tool-id]` uses double underscores to separate the server and tool-id segments. Breaking down an example: `mcp__cloudmcp-manager__commicrosoftmicrosoft-learn-mcp-search` splits into `mcp__` (prefix) + `cloudmcp-manager` (server) + `__` (separator) + `commicrosoftmicrosoft-learn-mcp-search` (tool-id). The repeated "microsoft" segment in the tool-id portion is intentional per the MCP server's naming convention, not a formatting error.
- **Context**: Code review on agent files using MCP tool references
- **Evidence**: PR #32 (ai-agents), direct link: https://github.com/rjmurillo/ai-agents/pull/32
- **Impact**: Prevents false positive comments on MCP tool identifier formatting
- **Application**: Recognize that apparent duplication in MCP tool identifiers follows the `mcp__[server]__[tool-id]` pattern where tool-id may contain the server name again

### Skill-CodeRabbit-006: Generated Files Omit Edit Warnings (90%)

- **Statement**: Generated agent instruction files (e.g., `src/vs-code-agents/*.agent.md`, `src/copilot-cli/*.agent.md`) intentionally omit "DO NOT EDIT DIRECTLY" headers because AI agents consume these files and human-oriented warnings would add noise to their context.
- **Context**: Code review on code generation scripts
- **Evidence**: PR #43 (ai-agents), CodeRabbit review on `build/Generate-Agents.ps1`
- **Impact**: Prevents false positive comments requesting edit warnings in generated files
- **Application**: CI validation (`validate-generated-agents.yml`) is the enforcement mechanism for preventing manual edits, not file headers
- **Related**: ADR or governance document should specify this pattern

### Skill-CodeRabbit-007: Analyst vs Impact Analysis Architecture (95%)

- **Statement**: The analyst agent performs background research and saves to `.agents/analysis/`, while impact analysis consultations are orchestrated by the planner agent and involve five specialists (implementer, architect, security, devops, qa) who save to `.agents/planning/impact-analysis-[domain]-[feature].md`.
- **Context**: Code review on agent planner documentation
- **Evidence**: PR #46 (ai-agents), CodeRabbit review on `src/claude/planner.md`
- **Impact**: Prevents confusion between analyst research and impact analysis workflows
- **Application**: The analyst is NOT an impact analysis consultant. This architectural separation is intentional per the ROOT delegation model.

---

## Duplicate Learnings (Already in skills-linting)

The following learnings were identified as duplicates or subsets of existing skills:

### Learning 7-10: Markdownlint Configuration Deference

These 4 learnings (from PRs #43) all state the same pattern: defer to `.markdownlint-cli2.yaml` for MD031/MD032 formatting decisions.

**Status**: Already covered by Skill-Lint-002, Skill-Lint-005, and Skill-Lint-008 in `skills-linting` memory.

**Files Referenced**:
- `templates/agents/implementer.shared.md`
- `templates/agents/qa.shared.md`
- `src/copilot-cli/analyst.agent.md`
- `templates/agents/planner.shared.md`

### Learning 11: Nested Code Fence Backtick Count

This learning about 4-backtick outer fences for nested code blocks is partially covered.

**Status**: Related to Skill-Lint-006 (Language Identifier Selection) but adds nested fence guidance.

**Action**: Added as note to Skill-CodeRabbit-008 below as supplementary guidance.

---

## Supplementary Guidance

### Skill-CodeRabbit-008: Nested Code Fence Syntax (88%)

- **Statement**: When nesting code fences inside a code block, the outer fence must use more backticks than the inner fence. For example, an outer fence written with four backticks and the language identifier "markdown" is correct when it contains a standard three-backtick code fence inside.
- **Context**: Markdown documentation with code block examples
- **Evidence**: PR #43 (ai-agents), CodeRabbit review on `templates/agents/roadmap.shared.md`
- **Impact**: Prevents false positive comments on correct CommonMark nested fence syntax
- **Application**: This is standard CommonMark syntax, not a formatting error
- **Note**: Supplements Skill-Lint-006 from skills-linting memory

---

## Integration Notes

### For pr-comment-responder Agent

When addressing CodeRabbit review comments, check these skills:
1. MCP tool paths: case-sensitive technical identifiers (Skill-CodeRabbit-001)
2. Template placeholders: bracket notation is intentional (Skill-CodeRabbit-002)
3. Infrastructure paths: no space handling needed (Skill-CodeRabbit-003)
4. Security labels: strong labeling is intentional (Skill-CodeRabbit-004)
5. Markdownlint: defer to project config (see skills-linting)

### For Code Review Agents

These skills help reduce false positive dismissal time when CodeRabbit flags patterns that are intentional in this codebase.

---

## Metadata

- **Created**: 2025-12-20
- **Source**: CodeRabbit AI learnings export (`10d35ecf-aaef-4464-bd45-a7d353831a9c.csv`)
- **PRs Referenced**: #15, #32, #43, #46, #57
- **Repositories**: vs-code-agents (former name), ai-agents (current)
