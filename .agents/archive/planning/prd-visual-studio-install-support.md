# PRD: Visual Studio 2026 Install Support

**Issue**: [#51 - feature: Add install support for (big) VS](https://github.com/rjmurillo/ai-agents/issues/51)
**Author**: AI Agent System (orchestrator → analyst → explainer pipeline)
**Status**: Draft
**Created**: 2025-12-17
**Stakeholder**: @MattKotsenas

---

## Executive Summary

This PRD defines requirements for adding Visual Studio 2026 support to the ai-agents installer. The **primary request** is for **user-level (global) installation** - a single installation that makes agents available across ALL Visual Studio workspaces without per-repository setup. Repository-level installation is a secondary nice-to-have.

Visual Studio 2022 17.14+ and Visual Studio 2026 support GitHub Copilot agent mode with custom `.agent.md` files at the repository level. However, **Microsoft's documentation does not specify a user-level (global) path** for custom agents in Visual Studio, unlike VS Code which has clear user profile support.

### Key Finding: Implementation is Partially Blocked

| Scope | Status | Blocker |
|-------|--------|---------|
| **User-level (PRIMARY ASK)** | 🔴 BLOCKED | Unknown path - requires VS team clarification |
| Repository-level (secondary) | 🟢 Ready | Can reuse VS Code's `.github/agents/` approach |

**Recommendation**: File questions with the Visual Studio team before implementing user-level support. Repository-level support can proceed immediately if interim value is desired.

---

## Problem Statement

### Current State

The ai-agents repository provides a multi-agent system for software development with installation support for:

| Platform | Global Install | Repo Install | Status |
|----------|---------------|--------------|--------|
| Claude Code | `~/.claude/agents/` | `.claude/agents/` | ✅ Supported |
| GitHub Copilot CLI | `~/.copilot/agents/` | `.github/agents/` | ✅ Supported (global has known bug) |
| VS Code / Copilot Chat | `%APPDATA%\Code\User\prompts\` | `.github/agents/` | ✅ Supported |
| **Visual Studio 2026** | ❓ Unknown | `.github/agents/` | ❌ **Not Supported** |

### Gap Analysis

**Primary Pain Point**: Users want a **single user-level installation** that makes agents available across ALL Visual Studio workspaces/repositories without requiring per-repository setup.

While repository-level installation (`.github/agents/`) technically works in VS 2022+ (shared with VS Code), this requires:
- Installing agents in every repository
- Maintaining multiple copies of agent files
- Team members each needing to pull agent changes

A **user-level (global) installation** would:
- Install once, available everywhere
- No per-repository maintenance
- Consistent agent experience across all projects

### User Impact

- **Matt Kotsenas** (and similar users) must currently install agents per-repository to use them in Visual Studio
- No "install once, use everywhere" option exists for Visual Studio users
- .NET developers who prefer Visual Studio over VS Code have a degraded experience

---

## Research Findings

### Visual Studio 2026 Agent Architecture

Based on comprehensive research of Microsoft's documentation and release notes:

#### Repository-Level Support (CONFIRMED)

Visual Studio 2026 (and VS 2022 v17.14+) **fully supports** custom agents via:

- **Location**: `.github/agents/*.agent.md`
- **Format**: Same `.agent.md` Markdown format as VS Code
- **Detection**: Automatic discovery when opening a solution/project
- **Feature Flag**: "Enable project specific .NET instructions" (auto-enabled in VS 2026)

**Source**: [Microsoft .NET Blog - Custom Agents for .NET Developers](https://devblogs.microsoft.com/dotnet/introducing-custom-agents-for-dotnet-developers-csharp-expert-winforms-expert/)

#### User-Level Support (REQUIRES INVESTIGATION)

**Current Documentation Gap**: Microsoft's documentation does not explicitly define a user-level path for custom agents in Visual Studio (unlike VS Code which has clear user profile support).

**Potential Paths** (require validation):

| Candidate Path | Likelihood | Rationale |
|----------------|------------|-----------|
| `%LOCALAPPDATA%\Microsoft\VisualStudio\17.0_<instance>\Copilot\agents\` | Medium | Follows VS extension pattern |
| `%APPDATA%\Microsoft\VisualStudio\17.0_<instance>\agents\` | Medium | Roaming profile pattern |
| `%USERPROFILE%\.github\agents\` | Low | Cross-IDE sharing |
| Shared with VS Code (`%APPDATA%\Code\User\prompts\`) | Low | Same Copilot backend |

**Related Configuration**: Visual Studio reads MCP (Model Context Protocol) server configs from `%USERPROFILE%\.mcp.json` globally, suggesting a similar pattern *may* exist for agents.

#### Instructions File Support (CONFIRMED)

Visual Studio supports custom instructions via:

- **Repository-level**: `.github/copilot-instructions.md` ✅
- **Targeted instructions**: `.github/instructions/*.instructions.md` ✅
- **User-level**: Not documented

**Source**: [Microsoft Learn - Customize Chat Responses](https://learn.microsoft.com/en-us/visualstudio/ide/copilot-chat-context?view=visualstudio)

---

## Proposed Solution

### Phase 1: Repository-Level Installation (Low Risk)

Implement repository-level installation for Visual Studio using the **same destination as VS Code** since both IDEs read from `.github/agents/`.

**Implementation**:

```powershell
# Config.psd1 addition
VisualStudio = @{
    DisplayName = "Visual Studio 2026"
    SourceDir   = "src/vs-code-agents"  # Reuse VS Code agents
    FilePattern = "*.agent.md"
    Repo        = @{
        DestDir          = '.github/agents'
        InstructionsFile = "copilot-instructions.md"
        InstructionsDest = '.github'
    }
}
```

**Note**: Since VS Code and Visual Studio share the same `.github/agents/` location for repo-level agents, this is effectively already supported via the VS Code installer. However, a distinct "VisualStudio" environment entry provides:

1. Clear user intent when running the installer
2. Visual Studio-specific completion messages and instructions
3. Future flexibility if paths diverge

### Phase 2: User-Level Installation (Requires Discovery)

Before implementing user-level (global) installation, **discovery work is required** to determine the correct path.

**Discovery Tasks**:

1. **Empirical Testing**: Install a custom agent via VS 2026 UI, observe where files are created
2. **Documentation Review**: Monitor Microsoft Learn for updated agent path documentation
3. **Community Research**: Check Visual Studio Developer Community and GitHub discussions
4. **Source Inspection**: Review VS extension APIs if accessible

**Proposed Discovery Approach**:

```powershell
# Potential discovery mechanism for install.ps1
function Find-VisualStudioAgentPath {
    $Candidates = @(
        "$env:LOCALAPPDATA\Microsoft\VisualStudio\17.0_*\Copilot\agents"
        "$env:APPDATA\Microsoft\VisualStudio\17.0_*\agents"
        "$env:USERPROFILE\.vs\agents"
    )

    foreach ($Pattern in $Candidates) {
        $Matches = Get-Item -Path $Pattern -ErrorAction SilentlyContinue
        if ($Matches) {
            return $Matches[0].FullName
        }
    }

    return $null
}
```

---

## Functional Requirements

### FR-1: Repository-Level Installation

**Priority**: P0 (Must Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1.1 | Add "VisualStudio" environment to `install.ps1` | Interactive mode shows "Visual Studio 2026" as option |
| FR-1.2 | Deploy agents to `.github/agents/` | All `*.agent.md` files copied to destination |
| FR-1.3 | Deploy instructions to `.github/` | `copilot-instructions.md` installed with content markers |
| FR-1.4 | Create `.agents/` directory structure | Standard agent output directories created |
| FR-1.5 | Support `-Force` parameter | Overwrites existing files when specified |

### FR-2: User-Level Installation

**Priority**: P1 (Should Have) - Blocked on discovery

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-2.1 | Discover VS 2026 global agent path | Path validated against VS 2026 installation |
| FR-2.2 | Add global destination to Config.psd1 | Configuration supports `$HOME` or `$env:` expansion |
| FR-2.3 | Deploy agents to user-level location | Agents available in all VS solutions |
| FR-2.4 | Display VS-specific restart instructions | User informed to restart Visual Studio |

### FR-3: Wrapper Scripts

**Priority**: P2 (Nice to Have)

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-3.1 | Create `install-visualstudio-global.ps1` | Backward-compatible wrapper script |
| FR-3.2 | Create `install-visualstudio-repo.ps1` | Backward-compatible wrapper script |

---

## Non-Functional Requirements

### NFR-1: Consistency

- Installation experience must match existing Claude/Copilot/VSCode patterns
- Output messages follow established conventions
- Error handling consistent with `Install-Common.psm1`

### NFR-2: Testability

- Unit tests in `scripts/tests/` for new configuration
- Validation via `Validate-Consistency.ps1`

### NFR-3: Documentation

- Update `AGENTS.md` with Visual Studio installation instructions
- Update `README.md` if applicable
- Add VS-specific usage examples

---

## Technical Design

### Config.psd1 Changes

```powershell
VisualStudio = @{
    DisplayName = "Visual Studio 2026"
    SourceDir   = "src/vs-code-agents"
    FilePattern = "*.agent.md"
    Global      = @{
        # Phase 2 - TBD after discovery
        DestDir          = "$env:LOCALAPPDATA\Microsoft\VisualStudio\Copilot\agents"  # Placeholder
        InstructionsFile = $null
        InstructionsDest = $null
    }
    Repo        = @{
        DestDir          = '.github/agents'
        InstructionsFile = "copilot-instructions.md"
        InstructionsDest = '.github'
    }
}
```

### install.ps1 Changes

```powershell
# Update ValidateSet
[ValidateSet("Claude", "Copilot", "VSCode", "VisualStudio")]
[string]$Environment

# Update interactive menu
Write-Host "  4. Visual Studio 2026"
```

### Write-InstallComplete Changes

```powershell
"VisualStudio" {
    Write-Host "IMPORTANT: Restart Visual Studio to load new agents." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Usage: @agent-name in Copilot Chat" -ForegroundColor Gray
    Write-Host "  Example: @orchestrator Help me implement a feature" -ForegroundColor Gray
}
```

---

## Implementation Plan

### Phase 0: Ask Blocking Questions (REQUIRED FIRST)

**Status**: 🔴 BLOCKED - Cannot proceed with user-level support without answers

| Task | Description | Owner |
|------|-------------|-------|
| 0.1 | File issue on [Visual Studio Developer Community](https://developercommunity.visualstudio.com/) asking about user-level agent paths | TBD |
| 0.2 | Alternatively, reach out to VS team contacts if available | TBD |
| 0.3 | Document response in `.agents/analysis/vs-agent-path-research.md` | TBD |

**Suggested Developer Community Post**:

> **Title**: Where does Visual Studio store user-level custom agents (.agent.md files)?
>
> **Body**:
> We're building an open-source agent installer for GitHub Copilot that supports VS Code, Claude Code, and Copilot CLI. We'd like to add Visual Studio 2022/2026 support.
>
> VS Code stores user-level agents in `%APPDATA%\Code\User\prompts\` - what is the equivalent path for Visual Studio?
>
> Specifically:
> 1. Does VS 2022+ support user-level (global) custom agents outside of `.github/agents/`?
> 2. If so, what file system path should we target?
> 3. Is there a programmatic way to discover this path (env var, registry, API)?
>
> Repository: https://github.com/rjmurillo/ai-agents
> Issue: https://github.com/rjmurillo/ai-agents/issues/51

---

### Phase 1: Repository-Level Support (CAN PROCEED NOW)

**Status**: 🟢 No blockers - can implement immediately
**Estimated Effort**: 1-2 hours
**Note**: This phase provides value but does NOT address the primary user-level request

| Task | Description |
|------|-------------|
| 1.1 | Add `VisualStudio` entry to `Config.psd1` (repo-level only) |
| 1.2 | Update `install.ps1` ValidateSet and interactive menu |
| 1.3 | Add VS-specific messages to `Write-InstallComplete` |
| 1.4 | Create wrapper scripts (`install-visualstudio-repo.ps1`) |
| 1.5 | Update `AGENTS.md` documentation |
| 1.6 | Add unit tests for new configuration |

**Outcome**: Users can install agents to individual repositories for use in Visual Studio.

---

### Phase 2: Empirical Discovery (PARALLEL TRACK)

**Status**: 🟡 Can proceed in parallel with Phase 0
**Estimated Effort**: 2-4 hours (depends on VS 2026 access)

| Task | Description |
|------|-------------|
| 2.1 | Install Visual Studio 2026 (or VS 2022 17.14+) |
| 2.2 | Use VS UI to create a custom agent (if UI exists) |
| 2.3 | Search common paths: `%LOCALAPPDATA%\Microsoft\VisualStudio\`, `%APPDATA%\Microsoft\VisualStudio\` |
| 2.4 | Use Process Monitor to observe file writes during agent creation |
| 2.5 | Document findings in `.agents/analysis/vs-agent-path-research.md` |

**Outcome**: Empirical data to validate or answer blocking questions.

---

### Phase 3: User-Level Support (BLOCKED)

**Status**: 🔴 BLOCKED on Phase 0 answers
**Estimated Effort**: 1-2 hours (once unblocked)

| Task | Description |
|------|-------------|
| 3.1 | Update `Config.psd1` with validated global path |
| 3.2 | Create `install-visualstudio-global.ps1` wrapper |
| 3.3 | Test global installation end-to-end |
| 3.4 | Update `AGENTS.md` with global installation instructions |
| 3.5 | Add unit tests |

**Outcome**: Users can install agents once and use them across all Visual Studio solutions.

---

### Decision Tree

```
Is user-level path known?
├── YES → Implement Phase 3 (user-level support)
│         └── Close Issue #51 as complete
│
└── NO → Is VS 2026 available for testing?
         ├── YES → Execute Phase 2 (empirical discovery)
         │         └── Return to decision tree with findings
         │
         └── NO → Wait for Phase 0 response
                  ├── Response received → Update PRD, proceed to Phase 3
                  └── No response after 2 weeks →
                      └── Consider Issue #51 blocked, document in issue
```

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| User-level path not documented | High | Medium | Implement repo-level first; defer global to Phase 2 |
| Path differs across VS versions | Medium | Low | Version detection in installer |
| VS Code and VS share same destination | Low | Positive | Reduces implementation complexity |
| Feature flag required in VS | Low | Low | Document in installation instructions |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Repo-level installation works | 100% of test cases pass |
| User reports issue resolved | Issue #51 closed as completed |
| Documentation updated | AGENTS.md includes VS 2026 section |
| No regressions | Existing installers continue to work |

---

## Blocking Questions for Visual Studio Team

> **⚠️ IMPLEMENTATION BLOCKER**: The following questions MUST be answered before user-level (global) installation can be implemented. Without this information, we cannot proceed with the primary feature request.

### Question 1: User-Level Agent Storage Path (CRITICAL)

**Question**: What is the file system path where Visual Studio 2022+ stores user-level custom agents that should be available across all workspaces/solutions?

**Context**:
- VS Code uses `%APPDATA%\Code\User\prompts\` for user-level agents
- Visual Studio documentation only describes repository-level agents at `.github/agents/`
- We need the equivalent user-level path for Visual Studio

**Proposed Ask to VS Team**:
> "Does Visual Studio 2022/2026 support user-level (global) custom agents stored outside of repository `.github/agents/` folders? If so, what is the recommended file system path for storing `.agent.md` files that should be available across all solutions?"

**Impact if unanswered**: Cannot implement user-level installation for Visual Studio. The feature request would be blocked.

---

### Question 2: Feature Availability

**Question**: Is user-level custom agent support available in Visual Studio 2022 17.14+, or is this a Visual Studio 2026-only feature?

**Context**:
- VS Code documentation explicitly supports user profile agents
- Visual Studio documentation is unclear on this capability
- Users on VS 2022 need to know if they can use this feature

**Proposed Ask to VS Team**:
> "Is user-level (global) custom agent storage supported in Visual Studio 2022 version 17.14+, or is this functionality only available in Visual Studio 2026?"

**Impact if unanswered**: Users may attempt installation on unsupported VS versions.

---

### Question 3: Path Discovery Mechanism

**Question**: Is there a programmatic way to discover the agent storage path (e.g., environment variable, registry key, VS settings API)?

**Context**:
- Visual Studio installations can have multiple instances with different version suffixes
- Hardcoding paths like `%LOCALAPPDATA%\Microsoft\VisualStudio\17.0_<guid>\` is fragile
- A discovery mechanism would make the installer more robust

**Proposed Ask to VS Team**:
> "Is there a recommended method for third-party tools to discover where Visual Studio stores Copilot agent files? For example, an environment variable, registry key, or Settings API endpoint?"

**Impact if unanswered**: Installer may use fragile path assumptions that break across VS versions.

---

## Recommended Next Steps

Given the blocking nature of these questions, we recommend:

1. **File a GitHub Issue or Developer Community Post** asking the Visual Studio team about user-level agent paths
2. **Empirical Testing** (parallel track): Manually create an agent via VS 2026 UI and observe where files are stored
3. **Defer User-Level Implementation** until answers are received
4. **Implement Repository-Level Only** as an interim solution (low effort, no blockers)

---

## Open Questions (Non-Blocking)

1. **Q**: Does Visual Studio share agent storage with VS Code at the user level?
   - **Hypothesis**: Likely no (different applications)
   - **Status**: Would be validated by Question 1 answer

2. **Q**: Are there VS-specific agent capabilities we should document?
   - **Example**: WinForms Expert, C# Expert agents mentioned in MS docs
   - **Status**: Nice-to-have, not blocking

---

## Appendix A: Research Sources

- [Visual Studio 2026 Release Notes](https://learn.microsoft.com/en-us/visualstudio/releases/2026/release-notes)
- [Visual Studio Agent Mode Documentation](https://learn.microsoft.com/en-us/visualstudio/ide/copilot-agent-mode?view=visualstudio)
- [Customize Chat Responses in Visual Studio](https://learn.microsoft.com/en-us/visualstudio/ide/copilot-chat-context?view=visualstudio)
- [Custom Agents for .NET Developers](https://devblogs.microsoft.com/dotnet/introducing-custom-agents-for-dotnet-developers-csharp-expert-winforms-expert/)
- [GitHub Docs - Creating Custom Agents](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-custom-agents)
- [VS Code Custom Agents Documentation](https://code.visualstudio.com/docs/copilot/customization/custom-agents)

## Appendix B: File Format Reference

### .agent.md Structure

```markdown
---
name: agent-name
description: Brief description shown in UI
tools:
  - editFiles
  - runTerminalCommand
  - codebase
model: gpt-4  # optional
target: github-copilot  # or vscode
---

# Agent Instructions

Your detailed agent instructions here in Markdown format.

## Responsibilities
- Item 1
- Item 2

## Constraints
- Do not do X
- Always do Y
```

### copilot-instructions.md Structure

```markdown
# Project Instructions

These instructions apply to all Copilot interactions in this repository.

## Code Style
- Use PascalCase for public members
- Use camelCase for private fields

## Architecture
- Follow SOLID principles
- Use dependency injection
```

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | 2025-12-17 | AI Agent (orchestrator) | Initial draft |
