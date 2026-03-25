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
   ```bash
   git clone <repo-url>
   cd <repo-name>
   ```

2. **Ensure default branch** with latest changes
   ```bash
   git checkout main   # or master, depending on repo
   git pull origin main
   ```

3. **Create feature branch**
   ```bash
   git checkout -b feat/windows-image-update
   ```

4. **Run baseline build** and record warnings
   ```bash
   dotnet clean
   dotnet build 2>&1 | tee build-baseline.log
   dotnet test
   ```

5. **Capture baseline warnings** for later comparison:
   ```powershell
   dotnet build 2>&1 | Select-String "warning" | Out-File baseline-warnings.txt
   ```

**Verification:**
- [ ] On `feat/windows-image-update` branch
- [ ] `dotnet build` exits with code 0
- [ ] `dotnet test` exits with code 0
- [ ] Baseline warnings recorded

**If build fails:** STOP. The repository has pre-existing build issues. Report to user before proceeding.

---

### Phase 2: Package Update

**Purpose:** Bump the AdoPipelineGeneration package and resolve any build conflicts.

1. **Find the package props file** in the repository root
   ```bash
   ls Directory.Packages.props 2>$null || ls Packages.props
   ```

2. **Locate `ConfigurationGeneration.AdoPipelineGeneration`** in the props file
   - **If it EXISTS:** Note the current version and proceed to step 3
   - **If it does NOT exist:** You must add it. First, discover the Topology project path (see Phase 3 step 1), then:
     ```bash
     cd <path-to-topology-project-directory>
     dotnet add package ConfigurationGeneration.AdoPipelineGeneration
     cd <repo-root>
     ```
     This will add the package reference. Then add a corresponding `<PackageVersion>` entry in the props file if using Central Package Management.

3. **Check latest available version**
   ```bash
   dotnet list package --outdated
   ```
   Or check the NuGet feed directly for the latest version of `ConfigurationGeneration.AdoPipelineGeneration`.

4. **Update the version** in the props file to the latest version

5. **Build and fix errors ONE AT A TIME**
   ```bash
   dotnet clean
   dotnet build
   ```

   **CRITICAL: Incremental error resolution strategy.**
   Do NOT try to fix all errors at once. Fix one error at a time, then rebuild:

   ```
   Loop:
     1. Run dotnet build
     2. If build succeeds → done, exit loop
     3. Read the FIRST error in the output
     4. Fix ONLY that first error (bump one package, fix one reference)
     5. Go to step 1
   ```

   **Why one at a time?** Fixing the first error (e.g., bumping one conflicting package) often resolves many transitive dependency errors downstream. If you try to fix all 20 errors at once, you may introduce new conflicts.

   Common first-error fixes:

   | Error | Fix |
   |-------|-----|
   | `NU1605: Package downgrade detected` | Bump the ONE conflicting package mentioned to the required version |
   | `NU1608: Detected package version outside of dependency constraint` | Bump the ONE package mentioned in the constraint to latest version in the props file |
   | `NU1107: Version conflict detected` | Pin the conflicting package directly in the project (add `<PackageReference>`) and/or bump the constraining package |
   | `CS0246: Type or namespace not found` | A dependent package API changed; update the code reference |

   After each single fix, rebuild. The error count should decrease significantly with each iteration.

**Verification:**
- [ ] Package version updated in props file
- [ ] `dotnet build` exits with code 0
- [ ] No package downgrade warnings

See: [references/troubleshooting.md](references/troubleshooting.md) for detailed error resolution

---

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
   |-----------|-----------------|----------------|
   | **Resources** | Repo name contains `.resources` (e.g., `MyService.resources`) OR folder contains `.resources` in name | **Topology** project (e.g., `*Topology*.csproj`) |
   | **Service** | Repo name does NOT contain `.resources` (e.g., `MyService`) | **ConfigurationGeneration** project (e.g., `*ConfigurationGeneration*.csproj`) |
   | **Combined** | Single repo with a folder containing `.resources` in its name alongside service code | Run both if present; check which generates `.pipelines/` output |

2. **Run the ConfigGen project**
   ```bash
   dotnet run --project <path-to-discovered-csproj>
   ```
   This regenerates pipeline configuration files. Expect many file changes.

   **If the project targets multiple frameworks**, specify the framework:
   ```bash
   dotnet run --project <path-to-csproj> --framework net8.0
   ```

   **If Assembly.Load fails**, build first and run from the output directory:
   ```powershell
   dotnet build <path-to-csproj> --framework net8.0
   Set-Location <path-to-csproj>\bin\Debug\net8.0
   .\<ProjectName>.exe
   ```

3. **Verify the image update**

   Check that pipeline yml files no longer reference the old image:
   ```powershell
   # Should return NO results
   Get-ChildItem -Recurse -Path .pipelines -Filter "*.yml" | Select-String "ltsc2019"
   Get-ChildItem -Recurse -Path .pipelines -Filter "*.yaml" | Select-String "ltsc2019"
   ```

   The `windowscontainerimage` value should now contain `ltsc2022` (or similar updated pattern).

4. **Run final validation**
   ```bash
   dotnet clean
   dotnet build 2>&1 | tee build-final.log
   dotnet test
   ```

5. **Compare warnings** against Phase 1 baseline:
   ```powershell
   dotnet build 2>&1 | Select-String "warning" | Out-File final-warnings.txt
   Compare-Object (Get-Content baseline-warnings.txt) (Get-Content final-warnings.txt)
   ```
   Empty diff or only resolved warnings = good. Any NEW warnings must be investigated.

**Verification:**
- [ ] No `ltsc2019` references in `.pipelines/*.yml` or `.pipelines/*.yaml` files
- [ ] `dotnet build` exits with code 0
- [ ] `dotnet test` exits with code 0
- [ ] No new warnings compared to baseline

**If image didn't change:** Verify you bumped the correct package and ran the correct ConfigGen project. Re-run Phase 2 if needed.

---

### Phase 4: PR Creation & Pipeline Validation

**Purpose:** Create a draft PR, validate through pipelines, and attach results.

1. **Stage and commit**
   ```bash
   git add -A
   git commit -m "chore: update Windows container image from LTSC2019 to LTSC2022

   Bumped ConfigurationGeneration.AdoPipelineGeneration to latest version
   and regenerated pipeline configurations to use the updated Windows
   container image, resolving the LTSC2019 end-of-life warning."
   ```

2. **Push to origin**
   ```bash
   git push -u origin feat/windows-image-update
   ```

3. **Create draft PR** targeting the default branch
   - **Title:** `chore: Update Windows container image from LTSC2019 to LTSC2022`
   - **Description template:**
     ```
     ## Summary
     Updated the Windows container image used in OneBranch pipelines from LTSC2019
     (end-of-life) to LTSC2022.

     ## Changes
     - Bumped `ConfigurationGeneration.AdoPipelineGeneration` to version X.Y.Z
     - Regenerated pipeline configuration files
     - Resolved package dependency conflicts (if any)

     ## Validation
     - [x] dotnet build passes
     - [x] dotnet test passes
     - [x] Pipeline yml files verified — no ltsc2019 references
     - [ ] PR pipeline: [link]
     - [ ] Buddy build: [link]
     - [ ] Buddy release: [link]

     ## Work Items
     - AB#{work-item-id}
     ```

4. **Attach work items** (if provided by user)

5. **Invoke pipeline-validator skill** for automated pipeline validation.

   After the PR is created, the **pipeline-validator** skill takes over to:
   1. Find the PR for the current branch
   2. Validate the PR description has required sections (Summary, Changes, Validation)
   3. Discover and trigger all associated pipelines (PR Build → Buddy Build → Buddy Release)
   4. Auto-diagnose and fix any pipeline failures (up to 3 retries per pipeline)
   5. Update the PR description with pipeline run links and results
   6. Report final status

   > **Do not proceed manually.** The pipeline-validator handles all pipeline monitoring, failure diagnosis, fix-and-retry loops, and PR description updates autonomously.

**Verification:**
- [ ] Draft PR exists targeting default branch
- [ ] pipeline-validator invoked and completed
- [ ] All pipelines pass (confirmed by pipeline-validator)
- [ ] PR description updated with pipeline links

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Manually editing pipeline yml files | They are generated by ConfigGen; manual edits will be overwritten | Always use package bump → ConfigGen workflow |
| Skipping baseline build | Cannot distinguish pre-existing vs new errors | Always run Phase 1 baseline first |
| Ignoring package downgrade errors | Downstream build will fail unpredictably | Fix all NU1605/NU1608 errors before ConfigGen |
| Creating non-draft PR | Premature review notifications before pipeline validation | Always create as draft first |
| Fixing all errors at once | One fix often resolves many downstream errors | Fix FIRST error, rebuild, repeat |
| Hardcoding ltsc2022 as the target | Next migration cycle will need different target | Use parameterized image names |

---

## Verification Checklist

After complete execution:

- [ ] `dotnet build` succeeds
- [ ] `dotnet test` succeeds
- [ ] No `ltsc2019` references in `.pipelines/` yml/yaml files
- [ ] No new warnings vs baseline
- [ ] Draft PR created with description
- [ ] pipeline-validator completed — all pipelines pass (PR, buddy build, buddy release)
- [ ] PR description updated with pipeline run links

---

## Aborting / Rollback

| Failed At | Rollback Command |
|-----------|-----------------|
| Phase 1-2 (not pushed) | `git checkout main && git branch -D feat/windows-image-update` |
| Phase 3 (not pushed) | `git reset --hard origin/main` |
| Phase 4 (pushed, PR created) | Close the draft PR in ADO, delete the remote branch |

---

## Extension Points

1. **Image name parameters:** Change `--old-image` for future LTSC migrations (e.g., ltsc2022 → ltsc2025)
2. **Package name:** Update the target package if ConfigGen is renamed
3. **Pipeline types:** Add new pipeline validation steps as OneBranch evolves
4. **Multi-repo batch:** Extend to process multiple repositories in sequence

---

## References

- [Troubleshooting Guide](references/troubleshooting.md) — Common errors and fixes during the update workflow
- [Pipeline Validator Skill](../pipeline-validator/SKILL.md) — Automated pipeline discovery, triggering, and fix-retry loop (invoked in Phase 4)
