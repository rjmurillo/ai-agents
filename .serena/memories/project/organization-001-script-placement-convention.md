# Organization: Script Placement Convention

## Skill-Organization-001: Script Placement Convention

**Statement**: A validation script lives in exactly one place. Runtime and repo-hygiene validators go in `scripts/validation/`; build and generation validators go in `build/scripts/`. Never duplicate either into `.agents/utilities/`.

**Context**: When creating new validation or utility scripts for the project

**Evidence**: Validate-Consistency.ps1 (since migrated to `scripts/validation/consistency.py`)
placed in scripts/ following the PowerShell conventions of the time; duplicate in
.agents/utilities/ removed to maintain single source of truth. Corrected 2026-07-28: the
statement previously said `scripts/` only, which was false. Six validators live under
`build/scripts/` (`validate_install_parity.py`, `validate_path_normalization.py`,
`validate_planning_artifacts.py`, `validate_plugin_manifests.py`,
`validate_plugin_version_bump.py`, `validate_templates_schema.py`) because they validate
generator output and run in the build pipeline, not at runtime.

**Atomicity**: 95%

**Tags**: organization, conventions, file-structure, DRY

**Note**: All agent references should use `scripts/validation/consistency.py` directly

**Directory Structure**:

```text
scripts/               # Runtime scripts and validators
├── validation/       # Runtime validation scripts (Python, per ADR-042)
└── *.py              # Task scripts

build/scripts/         # Build-pipeline and generator-output validators
└── validate_*.py

tests/                 # pytest suites (repo root, not under scripts/)

.agents/utilities/     # Agent-specific utilities ONLY (not duplicates)
├── fix-markdown-fences/  # Markdown repair tools
├── metrics/              # Metrics collection
└── security-detection/   # Security file detection
```

---
