# Install Scripts CVA Analysis

**Date**: 2025-12-15
**Branch**: feat/install-script
**Document**: `.agents/planning/cva-install-scripts.md`

## Key Findings

### Duplication Rate

- 46.6% of code is duplicated across 6 scripts (358/768 lines)
- 9 distinct patterns identified for extraction

### Extracted Patterns

1. Parameter Declaration
2. Source Directory Resolution
3. Source Validation
4. Destination Directory Creation
5. Agent File Discovery
6. File Copy Loop (largest - 90 lines duplicated)
7. Git Repository Validation
8. .agents Directory Creation
9. Instructions File Handling (append logic)

### Proposed Architecture

```text
scripts/
  install.ps1                    # Unified entry point
  lib/
    Install-Common.psm1          # Shared functions
    Config.psd1                  # Environment configurations
```

### Environment Matrix

| Environment | Source Dir | File Pattern | Global Dest |
|-------------|-----------|--------------|-------------|
| Claude | src/claude | *.md | ~/.claude/agents |
| Copilot | src/copilot-cli | *.agent.md | ~/.copilot/agents |
| VSCode | src/vs-code-agents | *.agent.md | %APPDATA%/Code/User/prompts |

### Remote Execution Strategy

- Detect context via `$MyInvocation.MyCommand.Path`
- Bootstrap by downloading module files to temp
- Interactive mode when parameters not provided

### Migration Phases

1. Create common module (non-breaking)
2. Create unified entry point (additive)
3. Refactor legacy scripts (optional)
4. Remote execution support

### Expected Impact

- Lines: 768 -> ~350 (54% reduction)
- Duplication: 46.6% -> <10%
- Files: 6 -> 3
