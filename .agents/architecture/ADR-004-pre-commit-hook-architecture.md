# ADR-004: Pre-Commit Hook as Validation Orchestration Point

## Status

Accepted

## Date

2025-12-17

## Context

As the ai-agents repository has evolved, the `.githooks/pre-commit` hook has accumulated multiple validation responsibilities:

1. **Markdown linting** (auto-fix enabled) - Since initial setup
2. **PowerShell script analysis** - PSScriptAnalyzer for syntax errors and best practices (Added 2025-12-22)
3. **Planning artifact validation** - Cross-document consistency for `.agents/planning/` files
4. **Consistency validation** - Scope alignment, requirement coverage, naming conventions
5. **Security detection** - Infrastructure and security-critical file change detection
6. **MCP configuration sync** - Transform Claude's `.mcp.json` to VS Code's `mcp.json` format
7. **Bash detection** - Enforce ADR-005 PowerShell-only scripting standard
8. **Session End validation** - Enforce Session Protocol compliance

This accumulation raises questions about:

- When to add new validations to the pre-commit hook vs. CI workflows
- How to balance developer experience (fast commits) vs. quality gates
- Whether the hook is becoming too complex or slow

## Decision

We will continue using the pre-commit hook as the primary validation orchestration point for:

1. **Fast, local validations** that provide immediate feedback
2. **Auto-fixable issues** (markdown lint, config sync) that reduce friction
3. **Non-blocking warnings** for issues that inform but don't prevent commits

Each validation in the hook follows these principles:

- **Fail-fast for critical issues** (e.g., invalid JSON, markdown syntax errors)
- **Warn-only for advisory issues** (e.g., planning inconsistencies, security recommendations)
- **Auto-fix when possible** to reduce developer friction
- **Security-hardened** (symlink rejection, path validation, TOCTOU prevention)

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| CI-only validation | Simpler hooks, faster commits | Delayed feedback, wasted CI cycles on fixable issues | Pushes easily preventable issues to remote |
| Separate hook scripts | Modular, easier to maintain | More files to manage, inconsistent execution | Current structure is manageable |
| Pre-push hook instead | Less friction, batched checks | No opportunity for auto-fix before commit | Auto-fix is a key value proposition |
| No hooks (editor-only) | Zero commit friction | Inconsistent enforcement, misses config sync | Not reliable for team workflows |

### Trade-offs

**Developer Experience vs. Quality**

- We accept slightly slower commits (1-3 seconds) for immediate feedback
- Non-blocking warnings preserve flow while raising awareness
- Auto-fix reduces the "friction budget" consumed by hooks

**Complexity vs. Centralization**

- Single hook file is easier to discover than multiple scripts
- PowerShell scripts handle complex logic, keeping bash simple
- Clear section headers document each validation's purpose

**Security vs. Speed**

- Symlink checks and path validation add minimal overhead
- We skip unavailable validators rather than failing

## Consequences

### Positive

- Developers get immediate feedback on issues before they reach CI
- Auto-fixable problems are resolved transparently
- Config files (mcp.json) stay synchronized automatically
- Security patterns are consistently applied across all validations

### Negative

- Pre-commit can feel slower than instant commits
- New developers may be surprised by auto-modifications
- Complex hook requires understanding bash + PowerShell
- Adding new validations requires careful design to avoid blocking

### Neutral

- `--no-verify` bypass remains available for exceptional cases
- CI pipelines provide redundant checks for safety

## Implementation Notes

### Current Hook Structure

```text
.githooks/pre-commit
├── Markdown Linting            # BLOCKING: Critical syntax errors
├── PowerShell Analysis         # BLOCKING: Error-level issues, WARNING: Best practices
├── Planning Validation         # WARNING: Consistency issues
├── Consistency Validation      # WARNING: Cross-document issues
├── MCP Config Sync             # AUTO-FIX: Transform and stage
├── Skill Validation            # BLOCKING: SkillForge 4.0 standards
├── Skill Frontmatter Validation # BLOCKING: YAML syntax, field constraints
├── Security Detection          # WARNING: Infrastructure changes
├── Bash Detection              # BLOCKING: ADR-005 enforcement
└── Session End Validation      # BLOCKING: Protocol compliance
```

### Guidelines for New Validations

1. **Ask**: Is this better suited for pre-commit or CI?
   - Pre-commit: Fast (<2s), local-only, auto-fixable, non-destructive
   - CI: Slow, needs network, complex analysis, security-sensitive

2. **Choose blocking level**:
   - BLOCKING: Invalid files that would break tools/builds
   - WARNING: Quality issues that should be reviewed
   - AUTO-FIX: Mechanical transformations with deterministic output

3. **Security checklist**:
   - Reject symlinks (MEDIUM-002)
   - Validate paths exist (LOW-001)
   - Quote all variables
   - Use `--` separator for arguments

4. **Add PowerShell `-NoProfile`** when invoking pwsh to avoid profile interference

### Bypass Instructions

```bash
# Skip all hooks (use sparingly)
git commit --no-verify

# Skip auto-fix only (check mode)
SKIP_AUTOFIX=1 git commit
```

### PowerShell Script Analysis Configuration

PSScriptAnalyzer settings are defined in `.PSScriptAnalyzerSettings.psd1` at repository root:

- **Default rules**: All enabled (Error, Warning, Information severity)
- **Custom rules**: PSAvoidUsingCmdletAliases, PSAvoidUsingPositionalParameters, PSAvoidUsingInvokeExpression, PSUseConsistentIndentation, PSUseConsistentWhitespace
- **Blocking behavior**: Error-level issues block commit
- **Warning behavior**: Displayed but allow commit to proceed
- **Performance**: ~1.8s for typical PowerShell file (<5s requirement)

**Rationale**: Added after Session 36 incident where variable interpolation bug (`$PullRequest:` instead of `$($PullRequest):`) was committed without detection. While PSScriptAnalyzer won't catch all syntax variations, it prevents common security issues (plaintext credentials, Invoke-Expression abuse) and enforces coding standards.

## Related Decisions

- [ADR-001: Markdown Linting](ADR-001-markdown-linting.md) - Established the auto-fix pattern
- [ADR-005: PowerShell-Only Scripting](ADR-005-powershell-only-scripting.md) - Why PowerShell is preferred
- Issue #I2, #I4: Cross-document consistency requirements

## References

- [Git Hooks Documentation](https://git-scm.com/docs/githooks)
- [PSScriptAnalyzer Documentation](https://github.com/PowerShell/PSScriptAnalyzer)
- [VS Code MCP Configuration](https://code.visualstudio.com/docs/copilot/customization/mcp-servers)
- [Claude Code MCP Configuration](https://docs.anthropic.com/claude-code/docs/mcp)
- OWASP guidelines for secure shell scripting

---

*Template Version: 1.0*
*Created: 2025-12-17*
