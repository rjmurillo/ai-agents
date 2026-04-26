# Error Patterns Catalog

Comprehensive catalog of pipeline failure patterns, diagnosis rules, and automated fix actions for the pipeline-validator skill.

---

## Pattern Categories

### 1. Build Compilation Errors

**Match:** `error CS\d+`, `error MSB\d+`, `Build FAILED`, `error NU\d+`

**Diagnosis:** Read the error message to identify the file, line number, and error code.

**Action:** Open the file and fix the compilation error at the reported location.

**Common sub-patterns:**

| Error Code | Meaning | Typical Fix |
|-----------|---------|-------------|
| CS0246 | Type or namespace not found | Add missing `using` or package reference |
| CS0234 | Namespace does not contain type | Package version changed API surface |
| CS1061 | Type does not contain member | API was renamed or removed in new version |
| CS0029 | Cannot implicitly convert type | Type changed in updated package |
| MSB3270 | Processor architecture mismatch | Update platform target |
| MSB4019 | Imported project not found | Fix SDK or props file path |

---

### 2. TreatWarningsAsErrors

**Match:** `warning treated as error`, `TreatWarningsAsErrors`, `WarningsAsErrors`

**Diagnosis:** The build has `TreatWarningsAsErrors` enabled and a warning is being promoted to an error.

**Action Options (in preference order):**

3. **Set `TreatWarningsAsErrors` to `false`** in the pipeline YAML or `.csproj` (last resort)

**Discovery:**

Get-ChildItem -Recurse -Filter "*.csproj" | Select-String -Pattern "TreatWarningsAsErrors" -SimpleMatch

# Find in Directory.Build.props

Select-String -Path "Directory.Build.props" -Pattern "TreatWarningsAsErrors" -SimpleMatch

```



**Common new warnings in .NET 10:**

| Warning | Description | Recommended Fix |
|---------|-------------|-----------------|
| CA1873 | Logging argument evaluation | Suppress in code analysis props |
| CA2263 | Prefer generic overload | Use generic `.Be<T>()` syntax |
| IDE0044 | Make field readonly | Add `readonly` modifier |
| ASPDEPR008 | IWebHost/WebHost obsolete | Suppress for now, address in follow-up |
| SYSLIB0057 | X509Certificate2(byte[]) obsolete | Suppress for now, use X509CertificateLoader later |

---

### 3. NuGet Package Errors

**Match:** `NU1101`, `Unable to find package`, `Package restore failed`, `NU1605`, `NU1608`, `NU1510`

**Sub-patterns:**

| Error | Meaning | Fix |
|-------|---------|-----|
| NU1101 | Package not found | Check NuGet.config feeds, verify package name |
| NU1605 | Package downgrade detected | Bump the conflicting package to the required version |
| NU1608 | Version outside dependency constraint | Bump package to latest compatible version |
| NU1510 | Package pruning conflict (.NET 10) | Remove explicit PackageReference for auto-pruned packages |
| NU1202 | Package not compatible with TFM | Find an updated version or alternative package |

**NU1510 Auto-pruned packages (.NET 10):**

- System.Security.Cryptography.X509Certificates
- System.Net.Security
- Microsoft.Extensions.DependencyInjection.Abstractions

**Exception:** Non-web class libraries may still need explicit references for some of these.

---

### 4. File Not Found / Path Reference Errors

**Match:** `File not found`, `not a valid path`, `does not exist`, `Could not find file`

**Diagnosis:** A YAML pipeline, config, or code file references a path that doesn't exist.



1. Identify the referenced file from the error message

```powershell
Get-ChildItem -Recurse -Filter "*RolloutSpec*" | Select-Object FullName
Get-ChildItem -Recurse -Filter "*StageMap*" | Select-Object FullName
```

---

### 5. Assembly Loading Errors

**Match:** `FileNotFoundException: Could not load file or assembly`, `AssemblyLoadContext`, `Could not load type`

**Diagnosis:** Assembly name, namespace, or DLL reference is incorrect. Often caused by a mismatch in a `topologyName` or incorrect project reference after a package bump.

**Match:** `403`, `Access denied`, `authorization`, `permission`, `unauthorized`
**Action:** ❌ **Cannot auto-fix.** Report to the user immediately with:

- The resource that was denied
- Suggested action (e.g., "Request pipeline trigger permissions for this repo")

---

**Action:** Re-trigger the same pipeline without code changes. This counts toward the retry limit.

---

### 11. Helm / Deployment Errors

1. Check if the `Deployment/` folder has any changes in the current PR

2. If NO changes to Deployment → Pre-existing issue, document and report to user
3. If YES changes → Investigate the helm values files and fix

---

- COPY paths changed

- Multi-stage build reference errors

2. Verify COPY source paths exist

---

    │

    ├─ Error contains "error CS" or "Build FAILED"?

    │   └─ YES → Pattern 1: Build Compilation Error
    │   └─ YES → Pattern 2: TreatWarningsAsErrors

    │
    ├─ Error contains "NU" (NuGet error)?
    │   └─ YES → Pattern 3: NuGet Package Error
    │
    ├─ Error contains "not found" or "does not exist"?
    │   └─ YES → Pattern 4: File Not Found
    │
    ├─ Error contains "Test Run Failed" or "Failed!"?
    │   └─ YES → Pattern 6: Test Failure
    │
    ├─ Error contains "subscription" or "backfill"?
    │   └─ YES → Pattern 7: Subscription Key Conflict
    │
    ├─ Error contains "YAML" or "pipeline is not valid"?
    │   └─ YES → Pattern 8: YAML Syntax Error
    │
    ├─ Error contains "403" or "permission" or "denied"?
    │   └─ YES → Pattern 9: Permission Error (STOP)
    │
    ├─ Error contains "timeout" or "503" or "agent was lost"?
    │   └─ YES → Pattern 10: Transient Error (retry)
    │
    ├─ Error contains "helm" or "chart"?
    │   └─ YES → Pattern 11: Helm Error
    │
    ├─ Error contains "docker" or "Dockerfile"?
    │   └─ YES → Pattern 12: Docker Error
    │
    └─ None of the above?
        └─ Report full error to user for manual diagnosis

```
