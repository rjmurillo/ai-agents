# Troubleshooting Guide

Common errors and their resolutions during the Windows container image update workflow.

---

## Phase 1: Repository Setup Errors

### Build fails on default branch

**Symptom:** `dotnet build` fails before any changes are made.

**Cause:** The repository has pre-existing build issues unrelated to the image update.

**Resolution:**
1. STOP the image update workflow
2. Report the build errors to the repository owner
3. Do not proceed until the default branch builds cleanly
4. If the user confirms the errors are known/expected, document them and continue at your discretion

### Tests fail on default branch

**Symptom:** `dotnet test` fails before any changes.

**Resolution:**
1. Record the failing tests as baseline
2. These tests should still fail (not be fixed or broken differently) after your changes
3. Proceed with the workflow, noting pre-existing test failures

---

## Phase 2: Package Update Errors

### NU1605: Package downgrade detected

**Symptom:**
```
error NU1605: Detected package downgrade: PackageName from X.Y.Z to A.B.C
```

**Cause:** Bumping AdoPipelineGeneration pulls in a newer transitive dependency, but another package in the solution pins an older version.

**Resolution:**
1. Find the package mentioned in the error in `Directory.Packages.props` or `Packages.props`
2. Bump that package's version to match or exceed the version required
3. Run `dotnet build` again
4. Repeat if there are cascading downgrades

**Example fix:**
```xml
<!-- Before -->
<PackageVersion Include="SomePackage" Version="1.0.0" />
<!-- After (bump to resolve downgrade) -->
<PackageVersion Include="SomePackage" Version="2.0.0" />
```

### NU1608: Detected package version outside of dependency constraint

**Symptom:**
```
warning NU1608: Detected package version outside of dependency constraint: PackageName X.Y.Z requires OtherPackage (>= A.B.C) but version D.E.F was resolved.
```

**Resolution:**
1. Update the version constraint in the props file to satisfy the dependency
2. May require bumping multiple related packages

### CS0246: Type or namespace not found

**Symptom:**
```
error CS0246: The type or namespace name 'SomeType' could not be found
```

**Cause:** A dependent package's API changed in the newer version (breaking change).

**Resolution:**
1. Check the package's release notes for API changes
2. Update the code to use the new API
3. This is rare for ConfigGen updates but possible for transitive dependencies

### NuGet restore fails

**Symptom:** `dotnet restore` fails with authentication or feed errors.

**Resolution:**
1. Ensure NuGet feed credentials are configured
2. Check `nuget.config` for correct feed URLs
3. Try: `dotnet nuget locals all --clear` then retry

---

## Phase 3: Config Generation Errors

### ConfigGen project not found

**Symptom:** No .csproj file found with Topology or ConfigurationGeneration in the name.

**Resolution:**
1. Check if the repo uses a different naming convention
2. Search more broadly: `Get-ChildItem -Recurse -Filter "*.csproj"` and examine each
3. Look for projects that reference `ConfigurationGeneration` packages
4. Ask the user for the correct project path

### ConfigGen run produces no changes

**Symptom:** `dotnet run` completes but no file changes appear in `.pipelines/`.

**Resolution:**
1. Verify you ran the correct project (Topology for resources repos, ConfigGen for service repos)
2. Check if the project requires specific arguments or environment variables
3. Check if the `.pipelines/` folder is in a different location
4. Verify the package version actually changed (diff the props file)

### Image reference still shows ltsc2019

**Symptom:** After running ConfigGen, yml files still contain ltsc2019 references.

**Resolution:**
1. Verify the AdoPipelineGeneration package version is actually the latest
2. The latest version might still use ltsc2019 — check the package release notes
3. There may be a different package or configuration that controls the image
4. Report to user — may need to escalate to the ConfigGen team

### dotnet run fails with runtime error

**Symptom:** The ConfigGen project fails during execution.

**Resolution:**
1. Read the error message carefully — it often indicates a configuration issue
2. Check if the project requires specific files or configuration that may be missing
3. Try running with `--verbosity detailed` for more information
4. Ensure all project dependencies are restored: `dotnet restore`

---

## Phase 4: PR and Pipeline Errors

### Pipeline validation fails

**Symptom:** PR validation or buddy build pipeline fails.

**Resolution:**
1. Download and examine the pipeline logs
2. Determine if the failure is related to the image update or pre-existing
3. Common causes:
   - Test failures (compare with baseline)
   - Configuration errors in generated yml files
   - Infrastructure issues (retry)
4. If related to the change, investigate the specific failure in the ConfigGen output

### Cannot create PR via CLI

**Symptom:** `az repos pr create` fails with permission or authentication errors.

**Resolution:**
1. Ensure you're authenticated: `az login`
2. Verify you have permission to create PRs in the repository
3. Try creating the PR manually through the ADO web interface
4. Check if branch policies prevent draft PR creation

### Pipeline takes too long

**Symptom:** Pipeline runs for longer than expected (>30 minutes for build).

**Resolution:**
1. Continue polling at 5-minute intervals
2. Check the pipeline UI for progress
3. Some repositories have long build times — this is normal
4. If stuck for >1 hour, check for infrastructure issues in the pipeline

---

## General Tips

1. **Always check exit codes** — Don't assume success; verify with `$LASTEXITCODE` or `$?`
2. **Save build output** — Redirect to log files for later comparison
3. **One fix at a time** — When resolving package conflicts, fix one error, rebuild, then fix the next
4. **Git stash** — If you need to temporarily revert, use `git stash` to save work in progress
5. **Ask the user** — If stuck on a non-obvious error, ask for guidance rather than guessing
