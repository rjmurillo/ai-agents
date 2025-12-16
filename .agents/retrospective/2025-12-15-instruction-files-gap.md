# Retrospective: User-Facing Instruction Files Gap

**Date**: 2025-12-15
**Epic**: Agent Consolidation (epic-agent-consolidation.md)
**PRD**: prd-agent-consolidation.md
**Outcome**: Gap Identified

---

## Summary

The 2-Variant Agent Consolidation epic successfully implemented the template system for generating platform-specific agent files. However, the planning phase missed a critical component: **user-facing instruction files** that explain how to USE the installed agents.

The repository's `copilot-instructions.md` and `CLAUDE.md` are designed for contributors to the ai-agents repository, not for users who install the agents in their own projects.

---

## Gap Analysis

### What Was Missed

1. **User Instruction Files**
   - The installer copies `CLAUDE.md` and `copilot-instructions.md` to user machines
   - These files were contributor-focused (testing, development utilities, repo-specific details)
   - Users need instructions explaining how to INVOKE and USE agents, not develop them

2. **Source Directory Placement**
   - Instruction files belong in `src/{env}/` alongside agent files
   - The installer already looks for `InstructionsFile` in `SourceDir`
   - Missing files would cause silent installation failures

3. **File Pattern Collision**
   - Claude uses `*.md` file pattern
   - `CLAUDE.md` placed in `src/claude/` would be copied as an "agent file"
   - Required installer modification to exclude instruction files

### Root Cause

The planning phase focused narrowly on **agent file consolidation** without considering the **complete user installation experience**. The installer configuration referenced instruction files, but no one verified these files existed or were appropriate for end users.

**Contributing Factors:**
- No end-to-end installation testing in acceptance criteria
- PRD scope was "agent files" not "installation package"
- No explicit user journey mapping

---

## Impact

| Area | Impact Level | Description |
|------|--------------|-------------|
| User Experience | **High** | Users would receive contributor docs, not usage guides |
| Installation | **Medium** | Missing files could cause warnings/errors |
| Maintenance | **Low** | Gap discovered before release |

---

## Remediation Actions Taken

1. Created user-facing instruction files:
   - `src/claude/CLAUDE.md` - Claude Code usage instructions
   - `src/vs-code-agents/copilot-instructions.md` - VS Code usage instructions
   - `src/copilot-cli/copilot-instructions.md` - Copilot CLI usage instructions

2. Updated installer to exclude instruction files from agent copying:
   - Modified `Get-AgentFiles` to accept `ExcludeFiles` parameter
   - Updated `install.ps1` to pass instruction filename to exclusion list

3. Verified changes with existing Pester test suite (144 tests passing)

---

## Lessons Learned

### Process Improvements Needed

1. **Installation Testing in QA Gate**
   - Acceptance criteria should include "end-to-end installation test"
   - Test should verify all expected files exist and are appropriate

2. **User Journey Mapping**
   - Before implementation, map the complete user journey
   - "User downloads installer" → "User runs installer" → "User uses agents"
   - Identify all touchpoints and required artifacts

3. **Configuration Audit**
   - Any configuration that references files (`InstructionsFile`, `SourceDir`) should trigger verification
   - Add check: "Do all referenced files exist?"
   - Add check: "Are these files appropriate for the target audience?"

4. **Audience-Aware Documentation**
   - Distinguish between contributor docs and user docs
   - Contributor docs: How to develop/maintain the system
   - User docs: How to use the installed system

---

## Skill Extraction

### Skill-Install-001: Complete Package Verification

**Context**: When planning installation/distribution features

**Strategy**:
1. List all files referenced in installer configuration
2. Verify each file exists in expected location
3. Verify each file is appropriate for end users (not contributors)
4. Test complete installation flow before release

**Validation**: This gap would have been caught by steps 2-3 above.

---

### Skill-Planning-003: User vs Contributor Scope

**Context**: When creating documentation or instruction files

**Strategy**:
1. Identify target audience (user vs contributor)
2. For users: Focus on "how to use" not "how to develop"
3. For contributors: Include development details, testing, utilities
4. Never mix audiences in the same document

**Validation**: The original `CLAUDE.md` mixed user and contributor content, causing this gap.

---

## Recommended Process Change

### Proposed Addition to PRD Template

Add section: **Installation Artifacts**

```markdown
## Installation Artifacts

### Required Files for User Installation
| File | Location | Purpose | Audience |
|------|----------|---------|----------|
| [filename] | [src/env/path] | [purpose] | [User/Contributor] |

### Configuration References
| Config Key | Referenced File | Verified Exists | Verified Audience |
|------------|-----------------|-----------------|-------------------|
| InstructionsFile | [filename] | [ ] | [ ] User |
```

This ensures every referenced file is verified before implementation begins.

---

## Follow-up Actions

- [ ] Create GitHub issue for process improvement
- [ ] Update PRD template with Installation Artifacts section
- [ ] Add installation verification to QA acceptance criteria
- [ ] Document skill extractions in skillbook

---

*Generated by Retrospective Agent - 2025-12-15*
