# Documentation Link Requirements (MANDATORY)

When referencing an existing file in any documentation artifact, the reference MUST be a clickable relative link. Plain text file paths without links are prohibited.

**Scope**: All documentation under `.agents/`, `.gemini/`, `docs/`, retrospectives, session logs, plans, and any markdown artifact that references repository files.

| Pattern | Status | Example |
|---------|--------|---------|
| Linked reference | CORRECT | `[`.agents/SESSION-PROTOCOL.md`](.agents/SESSION-PROTOCOL.md)` |
| Plain text path | WRONG | `` `.agents/SESSION-PROTOCOL.md` `` |
| Inline code path (no link) | WRONG | `See .agents/SESSION-PROTOCOL.md` |

**Correct examples**:

```markdown
<!-- Linking a referenced file -->
Plan referenced test file [`.github/workflows/tests/ai-issue-triage.Tests.ps1`](.github/workflows/tests/ai-issue-triage.Tests.ps1)

<!-- Linking in a table -->
| Source | Location |
|--------|----------|
| Session protocol | [`.agents/SESSION-PROTOCOL.md`](.agents/SESSION-PROTOCOL.md) |

<!-- Linking in prose -->
See the [naming conventions](`.agents/governance/naming-conventions.md`) for details.
```

**Exceptions**:

- Code blocks (fenced with triple backticks) are exempt; paths in code samples do not require links
- Shell commands and script invocations are exempt
- Paths referencing files that do not exist in the repository (hypothetical examples) are exempt
- Informational tables listing file path patterns (not specific files) are exempt

**Rationale**: Clickable links allow readers to navigate directly to referenced files and verify their existence. Plain text paths create friction and prevent discovery. ([PR #60 review](https://github.com/rjmurillo/ai-agents/pull/60#discussion_r2633132093))
