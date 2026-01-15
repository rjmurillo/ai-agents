# Security Agent Benchmark Suite

## Purpose

Validates security agent detection capabilities across CWE categories using real-world vulnerability patterns.

## Structure

Each benchmark file contains 3-5 vulnerable code samples with annotations:

- `# VULNERABLE: [CWE-ID] [description]` - Marks vulnerable code
- `# EXPECTED: [SEVERITY] - [finding description]` - Expected security agent finding
- `# SOURCE: [PR number or reference]` - Real-world vulnerability source

## Usage

### Running Security Agent on Benchmarks

```bash
# Option 1: Via Claude Code (recommended)
# Use Task tool to invoke security subagent:
Task(
    subagent_type='security',
    prompt='Review .agents/security/benchmarks/ directory for vulnerabilities. Generate security report SR-benchmark-[timestamp].md'
)

# Option 2: Manual invocation (if security agent has standalone mode)
pwsh scripts/security/Test-SecurityAgentCapabilities.ps1
```

### Expected Output

Security agent should generate report matching EXPECTED annotations:

```markdown
# Security Report: Benchmark Suite

## Findings

### CRITICAL-001: Path Traversal via .. Sequences (CWE-22)
- **Location**: .agents/security/benchmarks/cwe-22-path-traversal.ps1:15
- **EXPECTED**: ✅ PASS - Agent detected vulnerability

### CRITICAL-002: Command Injection via Unquoted Variables (CWE-77)
- **Location**: .agents/security/benchmarks/cwe-77-command-injection.ps1:20
- **EXPECTED**: ✅ PASS - Agent detected vulnerability
```

## Benchmark Files

| File | CWE | Test Cases | Source |
|------|-----|------------|--------|
| `cwe-22-path-traversal.ps1` | CWE-22 | 5 | PR #752 |
| `cwe-77-command-injection.ps1` | CWE-77 | 5 | PR #752 |

**Total**: 10 test cases across 2 CWE categories

## Adding New Benchmarks

When security agent misses a vulnerability (false negative):

1. Run `Invoke-SecurityRetrospective.ps1 -PRNumber <PR>` (creates stub benchmark file)
2. Extract actual vulnerable code pattern from PR
3. Add `# VULNERABLE:` and `# EXPECTED:` annotations
4. Update this README with new benchmark entry
5. Re-test security agent against updated suite

## Validation Checklist

Before approving security agent prompt changes:

- [ ] Run security agent on full benchmark suite
- [ ] Verify all EXPECTED findings detected
- [ ] Document any new false negatives
- [ ] Update benchmark suite if patterns missed
- [ ] Commit benchmark updates with prompt changes

## Maintenance

- Review benchmarks quarterly for outdated patterns
- Add new test cases for recurring vulnerability classes
- Archive benchmarks when CWE no longer relevant to codebase

**Last Updated**: 2026-01-15
**Contact**: Security team for questions on benchmark interpretation
