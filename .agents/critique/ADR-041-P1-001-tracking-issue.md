# Issue: Add Download Integrity Verification to CodeQL CLI Installation

**Priority**: P1 (High)
**Category**: Security
**Related ADR**: [ADR-041: CodeQL Integration Multi-Tier Strategy](../.agents/architecture/ADR-041-codeql-integration.md)
**Identified By**: Multi-agent ADR review (Security Agent)
**Review Date**: 2026-01-16

---

## Problem Statement

The `Install-CodeQL.ps1` script downloads the CodeQL CLI bundle from GitHub releases without verifying checksums or signatures. This creates a supply chain security vulnerability (CWE-494: Download of Code Without Integrity Check).

**CWE**: [CWE-494 - Download of Code Without Integrity Check](https://cwe.mitre.org/data/definitions/494.html)

**CVSS Score**: 7.5/10 (High)
- **Attack Vector**: Network
- **Attack Complexity**: High (requires compromising download path)
- **Privileges Required**: None
- **User Interaction**: Required (user must run install script)
- **Impact**: High (code execution, source code exfiltration, false negatives)

---

## Current Behavior

**Location**: `.codeql/scripts/Install-CodeQL.ps1:186-191`

```powershell
# Downloads without checksum verification
$ProgressPreference = if ($CI) { 'SilentlyContinue' } else { 'Continue' }
Invoke-WebRequest -Uri $Url -OutFile $archivePath -UseBasicParsing
```

**Risk**: An attacker who compromises the download path (DNS hijacking, MITM, or GitHub release compromise) could inject a malicious binary.

**Impact**:
- Affects all developers who install CodeQL locally (Tier 2/3 users)
- A compromised CLI could:
  - Exfiltrate source code during database creation
  - Inject false negatives (hide real vulnerabilities)
  - Execute arbitrary code during analysis

---

## Expected Behavior

The installation script should verify the integrity of downloaded artifacts before extraction and execution.

**Implementation Requirements**:

1. **Download Checksum File**
   - GitHub releases typically include `.sha256` files
   - Download `codeql-bundle-{version}.tar.gz.sha256` alongside the bundle

2. **Verify SHA-256 Hash**
   - Calculate actual hash: `Get-FileHash -Path $archivePath -Algorithm SHA256`
   - Compare to expected hash from checksum file
   - Fail installation if mismatch

3. **Consider GPG Signature Verification** (Optional Enhancement)
   - GitHub CodeQL releases may be GPG-signed
   - Verify signature using official GitHub public key
   - More robust than checksums alone

---

## Proposed Solution

### Minimum Viable Fix (P1)

```powershell
function Install-CodeQL {
    # ... existing download logic ...

    # Download checksum file
    $checksumUrl = "$Url.sha256"
    $checksumPath = "$archivePath.sha256"

    try {
        Invoke-WebRequest -Uri $checksumUrl -OutFile $checksumPath -UseBasicParsing
    } catch {
        Write-Warning "Checksum file not available at $checksumUrl. Proceeding without verification."
        Write-Warning "WARNING: Unable to verify download integrity. Consider manual verification."
    }

    # Verify checksum if available
    if (Test-Path $checksumPath) {
        $expectedHash = (Get-Content $checksumPath -Raw).Trim().Split()[0]
        $actualHash = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash

        if ($actualHash -ne $expectedHash) {
            throw "Checksum verification failed. Expected: $expectedHash, Got: $actualHash. Download may be compromised."
        }

        Write-Host "✓ Checksum verification passed" -ForegroundColor Green
    }

    # ... existing extraction logic ...
}
```

### Enhanced Solution (P2 - Future)

- Add GPG signature verification
- Pin expected checksums for known versions
- Maintain checksum database in repository (`.codeql/checksums.json`)

---

## Acceptance Criteria

- [ ] Script downloads checksum file (`.sha256`) alongside bundle
- [ ] Script verifies SHA-256 hash before extraction
- [ ] Script fails with clear error message if checksum mismatch
- [ ] Script provides warning if checksum file unavailable (graceful degradation)
- [ ] Pester tests added for checksum verification logic
- [ ] Documentation updated with manual verification instructions
- [ ] ADR-041 updated to reference this fix

---

## Testing Strategy

### Unit Tests (Pester)

```powershell
Describe "Install-CodeQL Checksum Verification" {
    It "Should verify valid checksum" {
        # Mock valid download + checksum
        Mock Invoke-WebRequest { }
        Mock Get-FileHash { @{ Hash = "abc123..." } }
        Mock Get-Content { "abc123..." }

        { Install-CodeQL -Version "v2.23.9" } | Should -Not -Throw
    }

    It "Should fail on checksum mismatch" {
        # Mock invalid checksum
        Mock Invoke-WebRequest { }
        Mock Get-FileHash { @{ Hash = "actual123" } }
        Mock Get-Content { "expected456" }

        { Install-CodeQL -Version "v2.23.9" } | Should -Throw "*Checksum verification failed*"
    }

    It "Should warn if checksum unavailable" {
        # Mock missing checksum file
        Mock Invoke-WebRequest -ParameterFilter { $Uri -like "*.sha256" } { throw }
        Mock Invoke-WebRequest -ParameterFilter { $Uri -notlike "*.sha256" } { }

        Install-CodeQL -Version "v2.23.9" -WarningVariable warnings
        $warnings | Should -BeLike "*Checksum file not available*"
    }
}
```

### Integration Tests

1. **Real Download Test**: Download actual CodeQL bundle and verify checksum against published value
2. **Tampered Download Test**: Intentionally corrupt downloaded file and verify installation fails
3. **Missing Checksum Test**: Delete checksum file and verify graceful degradation

---

## Documentation Updates

### User Documentation (`docs/codeql-integration.md`)

Add section:

```markdown
## Security: Download Integrity Verification

The CodeQL CLI installation script (`Install-CodeQL.ps1`) automatically verifies the integrity of downloaded binaries using SHA-256 checksums.

**What This Protects Against**:
- Compromised download mirrors
- Man-in-the-middle attacks
- Accidental file corruption

**Manual Verification** (if automatic verification fails):

1. Download bundle: `https://github.com/github/codeql-action/releases/download/codeql-bundle-v2.23.9/codeql-bundle-linux64.tar.gz`
2. Download checksum: `https://github.com/github/codeql-action/releases/download/codeql-bundle-v2.23.9/codeql-bundle-linux64.tar.gz.sha256`
3. Verify: `sha256sum -c codeql-bundle-linux64.tar.gz.sha256`

If checksum doesn't match, **DO NOT** proceed with installation. Report to security team.
```

### ADR-041 Update

Add to "Security Considerations" section:

```markdown
5. **Download Integrity**: SHA-256 checksum verification ensures CLI bundle authenticity (implemented post-ADR per multi-agent review recommendation)
```

---

## Implementation Notes

### Checksum File Format

GitHub CodeQL releases use standard format:
```
abc123def456...  codeql-bundle-linux64.tar.gz
```

### Error Handling

- **Checksum mismatch**: FAIL (exit code 3, validation error per ADR-035)
- **Checksum unavailable**: WARN and proceed (graceful degradation)
- **Network error downloading checksum**: WARN and proceed

### Performance Impact

- Adds ~1-2 seconds to installation (checksum download + hash calculation)
- Negligible impact on developer experience
- No impact on CI/CD (one-time install)

---

## Related Issues

- None (new issue identified during ADR review)

---

## Compliance

**Standards Addressed**:
- OWASP ASVS 10.3.2: "Verify that integrity checks are in place for all downloaded components"
- CWE-494: Download of Code Without Integrity Check
- GitHub Security Best Practices: Verify third-party dependencies

**Status After Fix**:
- OWASP ASVS 10.3.2: ✅ PASS
- CWE-494: ✅ MITIGATED

---

## Timeline

**Priority**: P1 (High)
**Target**: Within 7 days of ADR-041 merge
**Effort Estimate**: 4-6 hours (implementation + tests + documentation)

---

**Created By**: Multi-agent ADR review process
**Review Reference**: `.agents/critique/ADR-041-debate-log.md`
**Status**: Draft (ready to create GitHub issue)
