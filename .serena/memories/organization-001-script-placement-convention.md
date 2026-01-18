# Organization: Script Placement Convention

## Skill-Organization-001: Script Placement Convention

**Statement**: Validation scripts belong ONLY in `scripts/` directory; never duplicate to `.agents/utilities/`

**Context**: When creating new validation or utility scripts for the project

**Evidence**: Validate-Consistency.ps1 placed in scripts/ following PowerShell conventions; duplicate in .agents/utilities/ removed to maintain single source of truth

**Atomicity**: 95%

**Tags**: organization, conventions, file-structure, DRY

**Note**: All agent references should use `scripts/Validate-Consistency.ps1` directly

**Directory Structure**:

```text
scripts/               # Single source of truth for all scripts
├── Validate-*.ps1    # Validation scripts
└── tests/            # Pester tests

.agents/utilities/     # Agent-specific utilities ONLY (not duplicates)
├── fix-markdown-fences/  # Markdown repair tools
├── metrics/              # Metrics collection
└── security-detection/   # Security file detection
```

---