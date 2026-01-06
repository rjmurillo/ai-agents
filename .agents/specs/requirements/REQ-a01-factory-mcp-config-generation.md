---
type: requirement
id: REQ-A01
title: Factory Droid MCP Configuration Generation Support
status: implemented
priority: P1
category: functional
created: 2026-01-05
updated: 2026-01-05
author: factory-droid[bot]
tags:
  - mcp
  - factory-droid
  - configuration
  - compatibility
related:
  - https://docs.factory.ai/cli/configuration/mcp
---

## Background

Factory Droid supports MCP (Model Context Protocol) servers for external data access. The configuration format is identical to Claude Code's `.mcp.json` (using `mcpServers` root key). VS Code also supports MCP with a different configuration format (`servers` root key).

Currently, the `Sync-McpConfig.ps1` script only generates VS Code format, requiring manual configuration for Factory Droid users.

## Problem Statement

Users who want to use Factory Droid cannot automatically generate the required `.factory/mcp.json` configuration file. This creates friction and increases operational burden for teams using both VS Code and Factory Droid, or migrating between them.

## Requirements

### Functional Requirements

#### FR-1: Factory Target Generation
**Description**: The `Sync-McpConfig.ps1` script must support generating `.factory/mcp.json` files.

**Acceptance Criteria**:
- [x] Script accepts a `-Target` parameter with values 'factory' or 'vscode' (default: 'vscode')
- [ ] When `-Target factory` is specified, script creates `.factory/mcp.json` at repository root
- [ ] Output uses `mcpServers` root key (no transformation)
- [ ] Preserves all MCP server properties types, commands, and configurations
- [ ] Does NOT modify source `.mcp.json` (read-only source of truth)

#### FR-2: Backward Compatibility
**Description**: Existing VS Code workflows must continue working without changes.

**Acceptance Criteria**:
- [x] Default target remains 'vscode' when `-Target` parameter not specified
- [ ] Script continues to generate `.vscode/mcp.json` with serena transformations (context/port)
- [ ] Existing workflows calling script without `-Target` parameter produce identical output

#### FR-3: Batch Configuration Generation
**Description**: Script must support generating both Factory and VS Code configs in a single invocation.

**Acceptance Criteria**:
- [x] Script accepts `-SyncAll` switch parameter
- [ ] When `-SyncAll` is specified, script generates both `.factory/mcp.json` AND `.vscode/mcp.json`
- [ ] Factory config maintains `mcpServers` key identity
- [ ] VS Code config applies transformation rules (serena context/port)
- [ ] `-SyncAll` and `-DestinationPath` parameters are mutually exclusive

#### FR-4: Proper Recursive Call Handling
**Description**: Recursive script calls (for `-SyncAll`) must pass parameters correctly.

**Acceptance Criteria**:
- [x] Recursive calls to sync Factory destination include `-Target factory` parameter
- [x] Recursive calls to sync VS Code destination include `-Target vscode` parameter
- [x] All recursive calls propagate `-PassThru` parameter correctly
- [x] All recursive calls propagate `-WhatIf` parameter correctly
- [ ] All recursive calls propagate `-Force` parameter correctly

#### FR-5: Hidden File Compatibility
**Description**: Script must handle hidden source/destination files correctly on all platforms.

**Acceptance Criteria**:
- [x] Script uses `Get-ChildItem -Force` instead of `Get-Item` to handle hidden files
- [ ] Script rejects symlinks for security (both source and destination)
- [ ] Script throws descriptive error when encountering symlinks
- [ ] Script works on Linux with hidden file paths

#### FR-6: Comprehensive Test Coverage
**Description**: New functionality must have complete test coverage.

**Acceptance Criteria**:
- [x] Pester tests exist for all new parameters (`-Target`, `-SyncAll`)
- [x] Tests cover parameter validation (mutually exclusive parameter combinations)
- [x] Tests cover default behavior (`vscode` default)
- [x] Tests cover Factory format generation
- [x] Tests cover VS Code format generation
- [x] Tests cover recursive/sync-all behavior
- [x] All tests passing (58/58 passing)

### Constraint Requirements

#### CR-1: No Breaking Changes
**Description**: Implementation must not break existing scripts or workflows.

**Acceptance Criteria**:
- [x] Default behavior unchanged (VS Code target, no parameters)
- [x Existing `.vscode/mcp.json` generation paths work identically
- [x] Serena transformations for VS Code unchanged
- [ ] Error messages remain consistent for existing functionality

#### CR-2: Code Quality Standards
**Description**: Implementation must follow PowerShell and project coding standards.

**Acceptance Criteria**:
- [x] Parameter validation with meaningful error messages
- [x] Proper handling of edge cases (symlinks, missing files, invalid JSON)
- [x] UTF-8 encoding without BOM for cross-platform compatibility
- [ ] PSScriptAnalyzer passes with no errors or warnings
- [ ] Code includes inline comments for complex logic

#### CR-3: Documentation
**Description**: Changes must be properly documented.

**Acceptance Criteria**:
- [x] Script help text updated with new parameters
- [x] scripts/README.md updated with usage examples
- [ ] inline comments explain key logic (recursive calls, format differences)
- [ ] External reference to Factory MCP documentation included

## Implementation Details

See PR #795 for implementation history including:
- Initial implementation (commit f9fce17)
- Review feedback fixes (commit a2b98da)
- Documentation fixes (commit 130de33)
- Test suite completions (commit 3a44b0a)
- Final test fixes achieving 100% pass rate (commit e988935)

## Verification

```bash
# Verify Factory generation
pwsh .\scripts\Sync-McpConfig.ps1 -SourcePath .\.mcp.json -Target factory

# Verify VS Code generation (default behavior)
pwsh .\scripts\Sync-McpConfig.ps1

# Verify batch generation
pwsh .\scripts\Sync-McpConfig.ps1 -SyncAll

# Verify test coverage
pwsh .\build\scripts\Invoke-PesterTests.ps1 -TestPath "scripts/tests/Sync-McpConfig.Tests.ps1"
# Expected: 58/58 tests passing
```

## References

- [Factory Droid MCP Configuration](https://docs.factory.ai/cli/configuration/mcp)
- [VS Code MCP Configuration](https://code.visualstudio.com/docs/copilot/customization/mcp-servers)
- [PR #795](https://github.comr/murillo/ai-agents/pull/795)
- [Issue #796](https://github.com/rurillo/ai-agents/issues/796)
