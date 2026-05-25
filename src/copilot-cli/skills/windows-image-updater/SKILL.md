---
name: windows-image-updater
version: 1.0.0
description: Automates Windows container image migration for OneBranch pipelines. Bumps AdoPipelineGeneration package, regenerates pipeline configs via ConfigGen, and verifies old image reference is removed. Use for LTSC2019 to LTSC2022 migration, container image updates, OneBranch pipeline image upgrades.
license: MIT
---

# Windows Image Updater

Automates the end-to-end workflow for migrating Windows container images (e.g., LTSC2019 → LTSC2022) in OneBranch pipeline repositories. Handles package bumping, config regeneration, build validation, and PR creation.

---

## Triggers

- `update windows image` — Start the full migration workflow
- `fix ltsc2019 warning` — Triggered by OneBranch EOL warning
- `migrate onebranch image` — Alternative phrasing
- `bump AdoPipelineGeneration` — Package-specific trigger
- `windows container image update for {repo}` — Repo-specific trigger

## Quick Reference

| Input | Output | Duration |
|-------|--------|----------|
| ADO repository (URL or local path) | Draft PR with updated pipeline ymls, passing pipelines | 30-60 min |

---

## Prerequisites

### Required Knowledge

| Term | Definition |
|------|------------|
| **OneBranch** | Microsoft's CI/CD build platform used for official builds and releases |
| **ConfigGen** | Configuration Generation tool that produces pipeline YAML files from package definitions |
| **Topology project** | A .NET project in resources repos that generates pipeline configs when run |
| **LTSC** | Long-Term Servicing Channel — a Windows release model (e.g., LTSC2019, LTSC2022) |
| **Buddy build** | Pre-merge validation pipeline that builds and tests changes before merge |
| **Buddy release** | Pre-merge pipeline that validates the release process before merge |
| **CPM** | Central Package Management — NuGet feature where all versions are in Directory.Packages.props |

### Required Tools

| Tool | Purpose | Verify |
|------|---------|--------|
| **Git** | Version control | `git --version` |
| **.NET SDK** | Build and run .NET projects | `dotnet --version` |
| **ADO access** | Repository write access, PR creation rights | `az repos list` |

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| Old image pattern | `ltsc2019` | Pattern to detect in pipeline yml files |
| Expected new image | `ltsc2022` | Expected replacement (for verification) |
| Package name | `ConfigurationGeneration.AdoPipelineGeneration` | NuGet package to bump |
| Branch name | `feat/windows-image-update` | Feature branch name |
| Props file | `Directory.Packages.props` | Primary package props file (fallback: `Packages.props`) |

---

## Process

### Phase 1: Repository Setup

**Purpose:** Establish a clean working environment with baseline build metrics.

1. **Clone or navigate** to the repository

   cd <repo-name>

   ```



   dotnet test

   ```

   Common first-error fixes:

   After each single fix, rebuild. The error count should decrease significantly with each iteration.

**Verification:**

- [ ] `dotnet build` exits with code 0

- [ ] No package downgrade warnings

### Phase 3: Config Generation & Verification

**Purpose:** Regenerate pipeline files and verify the Windows container image reference is updated.

1. **Discover the ConfigGen/Topology project**

   Search for the project file:

   ```powershell
   # Look for .csproj files with Topology or ConfigurationGeneration in the name
   Get-ChildItem -Recurse -Filter "*.csproj" | Where-Object { $_.Name -match "Topology|ConfigurationGeneration" }

   ```

   **Decision guide — how to identify repo type:**

   | Repo Type | How to Identify | Project to Run |
   | **Resources** | Repo name contains `.resources` (e.g., `MyService.resources`) OR folder contains `.resources` in name | **Topology** project (e.g., `*Topology*.csproj`) |
   | **Combined** | Single repo with a folder containing `.resources` in its name alongside service code | Run both if present; check which generates `.pipelines/` output |

   This regenerates pipeline configuration files. Expect many file changes.

   ```powershell
   Set-Location <path-to-csproj>\bin\Debug\net8.0


   Check that pipeline yml files no longer reference the old image:
   Get-ChildItem -Recurse -Path .pipelines -Filter "*.yaml" | Select-String "ltsc2019"



   The `windowscontainerimage` value should now contain `ltsc2022` (or similar updated pattern).
4. **Run final validation**

- [ ] `dotnet test` exits with code 0
- [ ] No new warnings compared to baseline

**Purpose:** Create a draft PR, validate through pipelines, and attach results.

1. **Stage and commit**

   ```bash

   git add -A
   container image, resolving the LTSC2019 end-of-life warning."
   ```bash

   git push -u origin feat/windows-image-update
     ## Summary
     (end-of-life) to LTSC2022.


     ## Changes
     - Resolved package dependency conflicts (if any)


     ## Validation








     - [ ] Buddy build: [link]






    Work Items

     - AB#{work-item-id}




   After the PR is created, the **pipeline-validator** skill takes over to:
   alidate the PR description has required sections (Summary, Changes, Validation)


    Discover and trigger all associated pipelines (PR Build → Buddy Build → Buddy Release)
    Update the PR description with pipeline run links and results

   6. Report final status


- [ ] Draft PR exists targeting default branch

---

## Anti-Patterns

|-------|-----|---------|

| Manually editing pipeline yml files | They are generated by ConfigGen; manual edits will be overwritten | Always use package bump → ConfigGen workflow |
| Creating non-draft PR | Premature review notifications before pipeline validation | Always create as draft first |
| Hardcoding ltsc2022 as the target | Next migration cycle will need different target | Use parameterized image names |

After complete execution:

- [ ] `dotnet test` succeeds

- [ ] No `ltsc2019` references in `.pipelines/` yml/yaml files
- [ ] Draft PR created with description
- [ ] pipeline-validator completed — all pipelines pass (PR, buddy build, buddy release)
- [ ] PR description updated with pipeline run links

---

## Aborting / Rollback

|-----------|-----------------|
| Phase 1-2 (not pushed) | `git checkout main && git branch -D feat/windows-image-update` |
| Phase 4 (pushed, PR created) | Close the draft PR in ADO, delete the remote branch |

---

## Extension Points

1. **Image name parameters:** Change `--old-image` for future LTSC migrations (e.g., ltsc2022 → ltsc2025)
2. **Package name:** Update the target package if ConfigGen is renamed
3. **Pipeline types:** Add new pipeline validation steps as OneBranch evolves
4. **Multi-repo batch:** Extend to process multiple repositories in sequence

## References

- [Troubleshooting Guide](references/troubleshooting.md) — Common errors and fixes during the update workflow
- [Pipeline Validator Skill](../pipeline-validator/SKILL.md) — Automated pipeline discovery, triggering, and fix-retry loop (invoked in Phase 4)
