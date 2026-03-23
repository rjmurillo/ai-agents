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
1. **Suppress the specific warning code** in the appropriate scope (`.csproj`, `Directory.Build.props`, or inline `#pragma`)
2. **Fix the code** to eliminate the warning (if the fix is straightforward)
3. **Set `TreatWarningsAsErrors` to `false`** in the pipeline YAML or `.csproj` (last resort)

**Discovery:**
```powershell
# Find TreatWarningsAsErrors in YAML files
Select-String -Path ".pipelines\*.yml" -Pattern "TreatWarningsAsErrors" -SimpleMatch
# Find in csproj files
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
- System.Net.Http
- System.Security.Cryptography.X509Certificates
- System.Net.Security
- Microsoft.Extensions.Caching.Memory
- Microsoft.Extensions.DependencyInjection.Abstractions

**Exception:** Non-web class libraries may still need explicit references for some of these.

---

### 4. File Not Found / Path Reference Errors

**Match:** `File not found`, `not a valid path`, `does not exist`, `Could not find file`

**Diagnosis:** A YAML pipeline, config, or code file references a path that doesn't exist.

**Action:**
1. Identify the referenced file from the error message
2. Search the repo for the correct path or filename
3. Update the reference

```powershell
# Find files matching a pattern
Get-ChildItem -Recurse -Filter "*RolloutSpec*" | Select-Object FullName
Get-ChildItem -Recurse -Filter "*StageMap*" | Select-Object FullName
```

---

### 5. Assembly Loading Errors

**Match:** `FileNotFoundException: Could not load file or assembly`, `AssemblyLoadContext`, `Could not load type`

**Diagnosis:** Assembly name, namespace, or DLL reference is incorrect. Often caused by a mismatch in a `topologyName` or incorrect project reference after a package bump.

**Action:**
1. Check that assembly names match the expected convention
2. Verify project references are correct
3. Ensure namespace names haven't changed in updated packages

---

### 6. Test Failures

**Match:** `Failed! - Failed:`, `Test Run Failed`, `[xUnit.net]`, `[NUnit]`, `[MSTest]`

**Diagnosis:** Read the failing test output to determine:
- Is the test checking something affected by the current change? → Fix code or update test
- Is it a flaky/infrastructure test? → Re-trigger without code changes
- Is it pre-existing (failed before your changes)? → Document and skip

**Action:**
- **Change-related:** Fix the code or update the test assertion
- **Flaky:** Re-trigger the pipeline (counts toward retry limit)
- **Pre-existing:** Document in the PR description and proceed

---

### 7. Subscription Key Conflicts

**Match:** `Conflict while trying to declarative backfill subscription`, `subscription key already exists`

**Diagnosis:** The subscription key name is too generic and conflicts with another service.

**Action:** Rename the subscription key to something service-specific.

```powershell
# Find subscription enum files
Get-ChildItem -Recurse -Path "ConfigurationGeneration" -Filter "*.cs" | Select-String -Pattern "enum.*Subscription|AzureSubscriptionSubject" -List
```

---

### 8. YAML Schema / Pipeline Syntax Errors

**Match:** `unexpected value`, `Mapping values are not allowed`, `pipeline is not valid`, `A template expression is not allowed`

**Diagnosis:** YAML file has a syntax error or uses an invalid schema.

**Action:** Open the YAML file mentioned in the error and fix the syntax issue. Common fixes:
- Incorrect indentation
- Missing quotes around special characters
- Invalid template expression syntax

**IMPORTANT:** If the YAML is generated by ConfigGen, do NOT edit it directly. Fix the source (ConfigGen project, topology, or package) and regenerate.

---

### 9. Permission / Access Denied

**Match:** `403`, `Access denied`, `authorization`, `permission`, `unauthorized`

**Diagnosis:** The pipeline agent or user account lacks required permissions.

**Action:** ❌ **Cannot auto-fix.** Report to the user immediately with:
- The specific permission error message
- The resource that was denied
- Suggested action (e.g., "Request pipeline trigger permissions for this repo")

---

### 10. Infrastructure / Transient Errors

**Match:** `timeout`, `503`, `agent was lost`, `infrastructure failure`, `lost communication`, `Service Unavailable`

**Diagnosis:** Transient infrastructure issue — not caused by code.

**Action:** Re-trigger the same pipeline without code changes. This counts toward the retry limit.

If the same transient error occurs 3 times, it's likely a persistent infrastructure issue. Report to user.

---

### 11. Helm / Deployment Errors

**Match:** `helm upgrade`, `helm template`, `Error: read`, `Failed to render helm chart`

**Diagnosis:** Helm chart rendering or deployment failed. This is often a pre-existing issue in shared pipeline templates, not caused by the current change.

**Action:**
1. Check if the `Deployment/` folder has any changes in the current PR
2. If NO changes to Deployment → Pre-existing issue, document and report to user
3. If YES changes → Investigate the helm values files and fix

---

### 12. Docker Build Errors

**Match:** `docker build`, `COPY failed`, `FROM`, `base image`, `manifest unknown`

**Diagnosis:** Docker image build failed, often due to:
- Base image tag not available for new .NET version
- COPY paths changed
- Multi-stage build reference errors

**Action:**
1. Check Dockerfile base image tags are valid
2. Verify COPY source paths exist
3. Update base image tags to match the target .NET version

---

## Diagnosis Decision Tree

```
Pipeline Failed
    │
    ├─ Error contains "error CS" or "Build FAILED"?
    │   └─ YES → Pattern 1: Build Compilation Error
    │
    ├─ Error contains "TreatWarningsAsErrors"?
    │   └─ YES → Pattern 2: TreatWarningsAsErrors
    │
    ├─ Error contains "NU" (NuGet error)?
    │   └─ YES → Pattern 3: NuGet Package Error
    │
    ├─ Error contains "not found" or "does not exist"?
    │   └─ YES → Pattern 4: File Not Found
    │
    ├─ Error contains "assembly" or "AssemblyLoadContext"?
    │   └─ YES → Pattern 5: Assembly Loading Error
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
