# ADR-032: PowerShell Exit Code Convention

## Status

Proposed

## Date

2025-12-29

## Context

Review feedback on PR #530 identified inconsistent exit code usage across PowerShell scripts in `.claude/skills/github/scripts/`. Scripts return various exit codes without a documented convention, making it difficult for:

1. CI/CD pipelines to distinguish error types
2. Callers to handle errors appropriately
3. Developers to know what exit codes to use

Currently observed exit codes vary from 0-5 with no standardization.

## Decision

Adopt a standard exit code convention for all PowerShell scripts in the repository:

| Code | Category | Meaning | Example |
|------|----------|---------|---------|
| 0 | Success | Operation completed successfully | Script executed without errors |
| 1 | Input Error | Invalid parameters or arguments | Missing required arg, invalid format |
| 2 | Auth Error | Authentication or authorization failure | gh not authenticated, token expired |
| 3 | API Error | External API error | GitHub API returned 5xx, rate limited |
| 4 | Not Found | Resource not found | PR/Issue doesn't exist, file missing |
| 5 | Permission | Permission denied | Insufficient repo access, read-only |
| 6 | State Error | Invalid state for operation | PR already merged, issue closed |
| 7 | Conflict | Resource conflict | Merge conflict, concurrent modification |
| 8-99 | Reserved | Reserved for future standard codes | - |
| 100+ | Custom | Script-specific error codes | Documented in script header |

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Single failure code (1) | Simple, no ambiguity | No error differentiation | CI/CD can't make smart decisions |
| HTTP-style codes (200, 404, 500) | Familiar to web devs | Confusing in shell context | Shell conventions use 0-255 |
| Boolean only (0/1) | Unix-standard | No granularity | Lost debugging information |

### Trade-offs

- **Complexity vs Granularity**: More codes mean more to remember, but enable smarter error handling
- **Convention vs Flexibility**: Strict convention reduces freedom but improves consistency
- **Backwards Compatibility**: Existing scripts may need updates

## Consequences

### Positive

- CI/CD pipelines can handle errors differently based on code
- Debugging is easier with specific error categories
- New script authors have clear guidance
- Cross-script error handling becomes consistent

### Negative

- Existing scripts need audit and potential updates
- Developers must learn the convention
- Some edge cases may not fit neatly into categories

### Neutral

- Exit codes 8-99 are reserved for future expansion
- Custom codes (100+) allow script-specific needs

## Implementation Notes

1. **Script Header Documentation**: Each script should document exit codes in its header:
   ```powershell
   #>
   #   Exit Codes: 0=Success, 1=Invalid params, 3=API error, 4=Not found
   #>
   ```

2. **Helper Function**: Consider adding to `GitHubHelpers.psm1`:
   ```powershell
   function Exit-WithCode {
       param([int]$Code, [string]$Message)
       if ($Message) { Write-Error $Message }
       exit $Code
   }
   ```

3. **Audit Priority**: Focus on `.claude/skills/github/scripts/` first

## Related Decisions

- ADR-005: PowerShell-only scripting
- ADR-006: Thin workflows with testable modules

## References

- [PowerShell Exit Codes](https://docs.microsoft.com/en-us/powershell/scripting/learn/ps101/09-functions#exit-codes)
- [POSIX Exit Status](https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html#tag_18_08_02)
- GitHub Issue: #536
- PR Review: #530

---

*Created: 2025-12-29*
*Author: rjmurillo-bot*
