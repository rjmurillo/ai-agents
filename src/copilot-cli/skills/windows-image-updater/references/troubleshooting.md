# Troubleshooting Guide

Common errors and their resolutions during the Windows container image update workflow.

---

## Phase 1: Repository Setup Errors

### Build fails on default branch

**Symptom:** `dotnet build` fails before any changes are made.

**Cause:** The repository has pre-existing build issues unrelated to the image update.

**Resolution:**

3. Do not proceed until the default branch builds cleanly
4. If the user confirms the errors are known/expected, document them and continue at your discretion

### Tests fail on default branch

**Symptom:** `dotnet test` fails before any changes.

**Resolution:**

---

## Phase 2: Package Update Errors

### NU1605: Package downgrade detected

**Symptom:**

error NU1605: Detected package downgrade: PackageName from X.Y.Z to A.B.C
**Cause:** Bumping AdoPipelineGeneration pulls in a newer transitive dependency, but another package in the solution pins an older version.

**Resolution:**
2. Bump that package's version to match or exceed the version required

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

warning NU1608: Detected package version outside of dependency constraint: PackageName X.Y.Z requires OtherPackage (>= A.B.C) but version D.E.F was resolved.

```
error CS0246: The type or namespace name 'SomeType' could not be found

```

1. Check the package's release notes for API changes

---

### Pipeline validation fails

**Resolution:**

1. Continue polling at 5-minute intervals

3. Some repositories have long build times — this is normal
4. If stuck for >1 hour, check for infrastructure issues in the pipeline

---

## General Tips

1. **Always check exit codes** — Don't assume success; verify with `$LASTEXITCODE` or `$?`
3. **One fix at a time** — When resolving package conflicts, fix one error, rebuild, then fix the next
5. **Ask the user** — If stuck on a non-obvious error, ask for guidance rather than guessing
