# Build System Agents

This document describes the automated actors in the build system that generate, validate, and monitor AI agent definitions.

## Overview

The `build/` directory contains scripts that automate agent generation, drift detection, and quality validation. These scripts ensure consistency across platforms and prevent regression.

## Architecture

```mermaid
flowchart TD
    subgraph Sources["Source Files"]
        T[templates/agents/*.shared.md]
        C[src/claude/*.md]
        V[src/vs-code-agents/*.agent.md]
    end

    subgraph Build["Build Agents"]
        GEN[Generate-Agents.ps1]
        DFT[Detect-AgentDrift.ps1]
        VPA[Validate-PlanningArtifacts.ps1]
        VPN[Validate-PathNormalization.ps1]
        IPT[Invoke-PesterTests.ps1]
    end

    subgraph Outputs["Outputs"]
        OUT[Generated Agent Files]
        REP[Drift Reports]
        VAL[Validation Results]
        TST[Test Results]
    end

    T --> GEN
    GEN --> OUT
    OUT --> V

    C --> DFT
    V --> DFT
    DFT --> REP

    T --> VPA
    VPA --> VAL

    OUT --> VPN
    VPN --> VAL

    Build --> IPT
    IPT --> TST

    style Sources fill:#e1f5fe
    style Build fill:#fff3e0
    style Outputs fill:#e8f5e9
```

## Critical Workflow Rules

### Rule 1: Always Regenerate After Template Changes

After modifying ANY file in `templates/`:

```powershell
# Regenerate platform-specific files
pwsh build/Generate-Agents.ps1

# Verify generation succeeded
pwsh build/Generate-Agents.ps1 -Validate

# Commit ALL affected files together
git add templates/ src/vs-code-agents/ src/copilot-cli/
git commit -m "feat(agents): update template and regenerate"
```

### Rule 2: Claude-to-Template Synchronization

When `src/claude/` agents receive **universal changes**:

```text
1. Edit src/claude/{agent}.md (Claude-specific source)
2. Duplicate changes to templates/agents/{agent}.shared.md
3. Run: pwsh build/Generate-Agents.ps1
4. Commit all files atomically
```

See: [src/claude/AGENTS.md](../src/claude/AGENTS.md) for full rules.

### Rule 3: Never Edit Generated Files

Files in `src/vs-code-agents/` and `src/copilot-cli/` are **generated**:

```text
WRONG: Edit src/vs-code-agents/analyst.agent.md
RIGHT: Edit templates/agents/analyst.shared.md, then regenerate
```

### Rule 4: CI Validation

Two automated checks enforce these rules:

| Workflow | Purpose | Failure Action |
|----------|---------|----------------|
| `validate-generated-agents.yml` | Verify generated files match templates | Must regenerate |
| `drift-detection.yml` | Check Claude/VS Code consistency | Review and sync |

#### Staleness deferrals (issue #2770)

`build_all.py --check` is a "commit all generator output" gate. SkillForge is a
"block a broken skill" gate. When a generator mirrors an upstream-broken skill,
the two deadlock: the clean mirror cannot be committed, so `--check` cannot pass.
The historical fix was an ad-hoc `STALENESS_DEFERRALS` constant exempting the
broken mirror. It got orphaned: after the skill was fixed nobody removed the
exemption, and it hid stale mirrors until caught by hand (#2780).

Sanctioned protocol for a NEW upstream-broken skill you genuinely cannot mirror:

1. Open a tracking issue for the upstream breakage. Keep it OPEN until fixed.
2. Add a deferral entry in `build_all.py` that cites that OPEN issue as
   `#<number>` plus a one-line reason.
3. When the skill is fixed, regenerate the mirror, commit it, remove the
   deferral, and close the tracking issue.

`scripts/validation/validate_no_orphaned_build_deferrals.py` auto-polices step 3:
it scans `build_all.py` for any deferral-style exemption, reads each cited issue
state, and FAILS the gate when a deferral references a CLOSED issue. A closed
tracking issue is the orphan signature, so you cannot leave a dead exemption
behind. There are zero deferrals today; the gate passes until someone adds one.

---

## Agent Catalog

### Generate-Agents.ps1

**Role**: Platform-specific agent file generator

| Attribute | Value |
|-----------|-------|
| **Input** | `templates/agents/*.shared.md`, `templates/platforms/*.yaml` |
| **Output** | `src/vs-code-agents/*.agent.md`, `src/copilot-cli/agents/*.agent.md` |
| **Trigger** | Manual, CI validation |
| **Dependencies** | `Generate-Agents.Common.psm1`, PowerShell 7.5.4+ |

**Transformations Applied**:

- YAML frontmatter generation (model, name, tools)
- Handoff syntax transformation (`#runSubagent` vs `/agent`)
- Platform-specific tool array selection

**Invocation**:

```powershell
# Generate all agents
pwsh build/Generate-Agents.ps1

# Preview changes (dry run)
pwsh build/Generate-Agents.ps1 -WhatIf

# CI validation mode
pwsh build/Generate-Agents.ps1 -Validate
```

**Exit Codes**:

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Generation failed or validation mismatch |

---

### detect_agent_drift.py

**Role**: Semantic drift detector across agent copies. (The legacy
`Detect-AgentDrift.ps1` was expunged per ADR-042; this Python port replaces it.)

| Attribute | Value |
|-----------|-------|
| **Input** | `src/claude/*.md`, `src/vs-code-agents/*.agent.md`, `.claude/agents/*.md`, `.github/agents/*.agent.md`, `templates/agents/*.shared.md` |
| **Output** | Drift report (Text, JSON, or Markdown) |
| **Trigger** | `scripts/validation/pre_pr.py` (Agent Drift gate), weekly `drift-detection.yml`, manual |
| **Dependencies** | Python 3.10+ |

**Two comparisons** (Issue #2267):

1. **Vendored** (blocking): `src/claude/*.md` vs `src/vs-code-agents/*.agent.md`.
   The Claude self-host source vs the generated VS Code agent.
2. **Install** (advisory): `.claude/agents/*.md` vs `.github/agents/*.agent.md`,
   scoped to shared-template agents (those with
   `templates/agents/{name}.shared.md`). Freestanding Claude-only or
   GitHub-only agents are skipped.

**What It Compares** (ignoring platform-specific differences):

- Core Identity / Core Mission sections
- Key Responsibilities
- Constraints
- Review criteria / checklists
- Templates and output formats

**What It Ignores**:

- YAML frontmatter format differences
- Tool invocation syntax (`mcp__*` vs path notation)
- Claude Code Tools section
- Platform-specific tool references

**Invocation**:

```bash
# Both comparisons, 80% threshold (install drift advisory)
python3 build/scripts/detect_agent_drift.py

# Vendored comparison only
python3 build/scripts/detect_agent_drift.py --skip-install-comparison

# Promote install drift to blocking (after the install copies are reconciled)
python3 build/scripts/detect_agent_drift.py --fail-on-install-drift

# Strict threshold, JSON or Markdown output
python3 build/scripts/detect_agent_drift.py --similarity-threshold 90
python3 build/scripts/detect_agent_drift.py --output-format json
python3 build/scripts/detect_agent_drift.py --output-format markdown
```

**Exit Codes** (per ADR-035):

| Code | Meaning |
|------|---------|
| 0 | No blocking drift |
| 1 | Blocking drift detected (vendored, or install when `--fail-on-install-drift`) |
| 2 | Execution error (a required path is missing) |

The install comparison is advisory by default because the two self-host copies
carry large pre-existing structural differences. It reports drift but does not
flip the exit code, so it does not block PRs on day one. Promote it with
`--fail-on-install-drift` once the install copies are reconciled.

---

## Hand-Maintained Agent Copies

Three agent trees are **hand-maintained**: no generator writes them.

| Tree | Loaded by | Why not generated |
|------|-----------|-------------------|
| `.claude/agents/*.md` | Claude Code (this repo's self-host) | REQ-003-010 forbids generators from writing under `.claude/`; `build_all.py` asserts no `.claude/` writes |
| `.github/agents/*.agent.md` | GitHub Copilot (this repo's self-host) | Hand-maintained self-host copy; not a generator target |
| `src/claude/*.md` | Vendored Claude install source | Edited directly, then propagated to the generated `src/copilot-cli/` and `src/vs-code-agents/` copies |

Only `src/copilot-cli/agents/*.agent.md` and `src/vs-code-agents/*.agent.md` are
generated from `templates/agents/*.shared.md` by `build/generate_agents.py`.

Two gates keep the hand-maintained copies honest:

- `build/scripts/validate_install_parity.py` (wired into `pre_pr.py`): when one
  member of a shared-agent group changes, every other member must change in the
  same diff. This catches a forgotten copy. It does NOT check content
  similarity.
- `build/scripts/detect_agent_drift.py` (above): adds the semantic-similarity
  check across the `.claude/agents` vs `.github/agents` install copies that
  parity enforcement omits.

When you edit a shared-template agent, update the template
(`templates/agents/{name}.shared.md`), regenerate the `src/copilot-cli` and
`src/vs-code-agents` copies (`python3 build/generate_agents.py`), and hand-edit
`.claude/agents/{name}.md`, `.github/agents/{name}.agent.md`, and
`src/claude/{name}.md` to match.

---

### Validate-PlanningArtifacts.ps1

**Role**: Planning document consistency validator

| Attribute | Value |
|-----------|-------|
| **Input** | `.agents/planning/*.md` |
| **Output** | Validation report |
| **Trigger** | CI on planning changes, manual |
| **Dependencies** | PowerShell 7.5.4+ |

**Validations Performed**:

| Check | Description |
|-------|-------------|
| Effort estimate divergence | Compares epic/PRD estimates with task breakdown totals |
| Orphan conditions | Specialist conditions without task assignments |
| Missing task coverage | PRD requirements without corresponding tasks |

**Invocation**:

```powershell
# Validate specific feature
pwsh build/scripts/Validate-PlanningArtifacts.ps1 -FeatureName "agent-consolidation"

# CI mode (exit on error)
pwsh build/scripts/Validate-PlanningArtifacts.ps1 -FailOnError

# Strict mode (warnings as errors)
pwsh build/scripts/Validate-PlanningArtifacts.ps1 -FailOnWarning
```

---

### Validate-PathNormalization.ps1

**Role**: Path format validator for documentation

| Attribute | Value |
|-----------|-------|
| **Input** | `**/*.md` (documentation files) |
| **Output** | Path validation report |
| **Trigger** | CI on PR, manual |
| **Dependencies** | PowerShell 7.5.4+ |

**Forbidden Patterns**:

| Pattern | Reason |
|---------|--------|
| `[A-Z]:\` | Windows absolute paths |
| `/Users/` | macOS home paths |
| `/home/` | Linux home paths |

**Invocation**:

```powershell
pwsh build/scripts/Validate-PathNormalization.ps1
```

---

### Invoke-PesterTests.ps1

**Role**: Reusable Pester test runner

| Attribute | Value |
|-----------|-------|
| **Input** | Test files (`**/*.Tests.ps1`) |
| **Output** | Test results (XML, console) |
| **Trigger** | CI, pre-commit, manual |
| **Dependencies** | Pester 5.7.1 (exact), PowerShell 7.5.4+ |

**Invocation**:

```powershell
# Local development (detailed output)
pwsh build/scripts/Invoke-PesterTests.ps1

# CI mode (exit on failure)
pwsh build/scripts/Invoke-PesterTests.ps1 -CI

# Specific test file
pwsh build/scripts/Invoke-PesterTests.ps1 -TestPath "./scripts/tests/Install-Common.Tests.ps1"

# Maximum verbosity
pwsh build/scripts/Invoke-PesterTests.ps1 -Verbosity Diagnostic
```

---

## Data Flow

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant Gen as Generate-Agents.ps1
    participant Drift as Detect-AgentDrift.ps1
    participant CI as GitHub Actions

    Dev->>Gen: Edit template
    Gen->>Gen: Read templates + configs
    Gen->>Gen: Transform content
    Gen-->>Dev: Generated files

    Dev->>CI: Push changes
    CI->>Gen: Validate (--Validate)
    alt Files match
        Gen-->>CI: Exit 0
    else Files differ
        Gen-->>CI: Exit 1 (fail)
    end

    CI->>Drift: Weekly check
    Drift->>Drift: Compare Claude vs VS Code
    alt Similarity >= 80%
        Drift-->>CI: Exit 0
    else Similarity < 80%
        Drift-->>CI: Exit 1 (create issue)
    end
```

## Error Handling

| Agent | Error Scenario | Behavior |
|-------|---------------|----------|
| Generate-Agents.ps1 | Missing template | Exit 1 with path info |
| Generate-Agents.ps1 | Invalid YAML | Parse error with line number |
| Detect-AgentDrift.ps1 | Missing agent | Report as "NO COUNTERPART" |
| Validate-PlanningArtifacts.ps1 | Missing artifacts | Warning (not error) |
| Invoke-PesterTests.ps1 | Test failure | Report details, exit 1 in CI |

## Security Considerations

| Agent | Security Control |
|-------|-----------------|
| Generate-Agents.ps1 | Output path validation (no traversal) |
| All scripts | No external input (static file sources) |
| All scripts | No network access required |
| All scripts | Code review required for changes |

## Monitoring

| Agent | CI Workflow | Schedule |
|-------|------------|----------|
| Generate-Agents.ps1 | `validate-generated-agents.yml` | On PR |
| Detect-AgentDrift.ps1 | `drift-detection.yml` | Monday 9 AM UTC |
| Validate-PlanningArtifacts.ps1 | `validate-planning-artifacts.yml` | On PR |
| Validate-PathNormalization.ps1 | `validate-paths.yml` | On PR |
| Invoke-PesterTests.ps1 | `pester-tests.yml` | On PR |

## Related Documentation

- [templates/AGENTS.md](../templates/AGENTS.md) - Template system agents
- [templates/README.md](../templates/README.md) - Template usage guide
- [.github/AGENTS.md](../.github/AGENTS.md) - GitHub Actions agents
