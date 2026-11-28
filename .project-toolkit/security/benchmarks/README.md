# Security Agent Benchmark Suite

> **Purpose**: Validate security agent's ability to REVIEW and INTERPRET security findings.
> **Source**: Issue #756 (Security Agent Detection Gaps Remediation)
> **Language**: Python only (per ADR-042)

## Overview

This benchmark suite tests the security agent's **interpretation capabilities**, not detection.

### Division of Labor

| Component | Responsibility | How |
|-----------|----------------|-----|
| **CodeQL** | Detection | Automated static analysis via GitHub Actions |
| **PSScriptAnalyzer** | Detection (PowerShell) | Automated static analysis |
| **Security Agent** | Interpretation | Reviews findings in project context, recommends mitigations |
| **Benchmarks** | Validation | Tests agent's review quality against known vulnerable code |

### What Benchmarks Test

**[CORRECT]** Security agent's ability to:

- Review CodeQL findings and provide business context
- Assess severity based on deployment context (CLI tool vs API service)
- Recommend specific mitigations with rationale
- Identify false positives that automated tools flag incorrectly

**[INCORRECT]** Benchmarks do NOT test:

- Agent's ability to detect vulnerabilities (that is CodeQL's job)
- Automated scanning capabilities (use CodeQL workflow)
- Detection coverage metrics (measure via GitHub Security tab)

### How It Works

```text
1. CodeQL detects vulnerability (automated)
   |
   v
2. Benchmark presents vulnerable code to agent
   |
   v
3. Agent REVIEWS code (as if CodeQL flagged it)
   |
   v
4. Agent produces interpretation:
   - Business impact assessment
   - Severity calibration for deployment context
   - Specific remediation recommendations
   |
   v
5. Benchmark validates agent's review quality
```

## Structure

```text
.project-toolkit/security/benchmarks/
    README.md                           # This file
    conftest.py                         # pytest configuration
    test_cwe22_path_traversal.py        # CWE-22 test cases
    test_cwe77_command_injection.py     # CWE-77 test cases
    vulnerable_samples/                 # Raw vulnerable code for agent review
        cwe22_path_traversal.py         # Path traversal vulnerabilities
        cwe77_command_injection.py      # Command injection vulnerabilities
```

## Running Benchmarks

### Manual Agent Review

Run security agent on benchmark files to verify interpretation quality:

```bash
# Using Task tool (Claude Code)
# Agent reviews vulnerable code as if CodeQL already flagged it
Task(subagent_type='security', prompt='Review .project-toolkit/security/benchmarks/vulnerable_samples/')
```

### Automated Testing

Run pytest to verify the benchmark infrastructure:

```bash
cd /path/to/ai-agents
uv run pytest .project-toolkit/security/benchmarks/ -v
```

### CodeQL Integration

The security agent workflow now fetches CodeQL alerts before manual review:

```bash
# Set these from the PR's base repository, never from the fork's origin.
# Example: base_owner=rjmurillo base_repo=ai-agents pull_request=7762
# Set review_base_ref to a fetched local base ref, for example upstream/main.
if [ -z "${base_owner:-}" ] || [ -z "${base_repo:-}" ] ||
   [ -z "${pull_request:-}" ] || [ -z "${review_base_ref:-}" ]; then
  echo "Set base_owner, base_repo, pull_request, and review_base_ref explicitly." >&2
  exit 2
fi
# Use an operator-approved, installed plugin root outside the reviewed checkout.
trusted_plugin_root="${CLAUDE_PLUGIN_ROOT:-${COPILOT_PLUGIN_ROOT:-}}"
case "$review_base_ref" in
  -*) echo "Invalid review_base_ref: option-shaped value." >&2; exit 2 ;;
esac
base_sha="$(git rev-parse --verify --end-of-options "$review_base_ref^{commit}")" || exit 2
head_sha="$(git rev-parse HEAD)" || exit 2

# ADR-041: guard scanner inputs and collect decoded paths before reading results.
changed_files="$(python3 -I -X utf8 - "$trusted_plugin_root" "$base_sha" <<'PYTHON'
import pathlib
import subprocess
import sys

root = pathlib.Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True).strip()).resolve()
plugin = pathlib.Path(sys.argv[1])
required = (
    "lib/ptk_run.py",
    "skills/github/scripts/pr/get_pr_code_scanning_alerts.py",
    "skills/github/scripts/pr/code_scanning_sarif.py",
    "skills/review/scripts/codeql_scanner_guard.py",
)
if not plugin.is_absolute() or plugin.resolve().is_relative_to(root) or any(
    not (plugin / name).is_file()
    or not (plugin / name).resolve().is_relative_to(plugin.resolve())
    for name in required
):
    sys.exit("CodeQL: SKIPPED (trusted plugin installation unavailable)")
sys.path.insert(0, str(plugin / "skills/review/scripts"))
import codeql_scanner_guard as guard

try:
    files = guard.changed_files(root, sys.argv[2])
    links = guard.changed_symlinks(root, sys.argv[2])
except guard.GitError:
    sys.exit("CodeQL: SKIPPED (diff could not be computed)")
if guard.guarded_paths(files, links):
    sys.exit("CodeQL: SKIPPED (scanner inputs modified)")
sys.path.insert(0, str(plugin / "skills/github/scripts/pr"))
from code_scanning_sarif import normalize_repo_path

if any(normalize_repo_path(path) != path or path.splitlines() != [path] for path in files):
    sys.exit("CodeQL: SKIPPED (changed paths cannot be represented losslessly)")
print("\n".join(files))
PYTHON
)" || exit 2
tree_state=dirty
status="$(git status --porcelain --untracked-files=all)" || exit 2
if [ -z "$status" ]; then
  tree_state=clean
fi

# The GitHub skill reads every open alert and verifies PR merge-ref freshness.
# The C locale selects Python UTF-8 mode through the launcher and reader.
printf '%s\n' "$changed_files" |
  LC_ALL=C python3 -I "$trusted_plugin_root/lib/ptk_run.py" skills/github/scripts/pr/get_pr_code_scanning_alerts.py \
    --owner "$base_owner" --repo "$base_repo" --pull-request "$pull_request" \
    --head-sha "$head_sha" --tree-state "$tree_state" \
    --changed-files-from - --output-format json
```

Use the `github` skill's transport preflight from the same trusted installation before running this block. Do not fall back to checkout scripts.
PR scans require explicit base-repository parameters, including in detached checkouts.
Use an absolute `CLAUDE_PLUGIN_ROOT` or `COPILOT_PLUGIN_ROOT` from an operator-approved installation; never select one from the reviewed checkout.
If the guard refuses the scan, report `SKIPPED` without reading alerts.
Source: [ADR-041](../../architecture/ADR-041-codeql-integration.md), amendment 2026-11-09.
Exit 0 alone is not a clean scan; inspect `Data.outcome`.
Only `CURRENT` carries alerts, including counts for findings outside the diff.
Report `STALE`, `NOT ANALYZED`, and `SKIPPED` without claiming a clean scan.
For a branch without a PR, use `codeql-scan` for a local scan.
The PR reader does not support branch refs.
Keep any branch-repository inference scoped to origin, not PR base selection.

## Test Case Format

Each test case follows this annotation format in Python:

```python
# VULNERABLE: CWE-XX [Brief description]
# EXPECTED: [SEVERITY] - [What agent should detect]
# SOURCE: PR #NNN or "Synthetic"
vulnerable_code_here
```

## Benchmark Categories

### CWE-22: Path Traversal (6 test cases)

| ID | Pattern | Source | Expected |
|----|---------|--------|----------|
| PT-001 | startswith without normalization | PR #752 | CRITICAL |
| PT-002 | os.path.join with absolute path | Synthetic | HIGH |
| PT-003 | Symlink bypass (TOCTOU) | Synthetic | HIGH |
| PT-004 | Null byte injection | Synthetic | CRITICAL |
| PT-005 | False positive (safe pattern) | GitHubCore.psm1 | PASS |
| PT-006 | Path object without validation | Synthetic | HIGH |

### CWE-77: Command Injection (7 test cases)

| ID | Pattern | Source | Expected |
|----|---------|--------|----------|
| CI-001 | shell=True with user input | PR #752 | CRITICAL |
| CI-002 | Dynamic code with user input | Synthetic | CRITICAL |
| CI-003 | Dynamic code with config | Synthetic | HIGH |
| CI-004 | Shell metacharacters in git | Synthetic | CRITICAL |
| CI-005 | False positive (list args) | Safe pattern | PASS |
| CI-006 | False positive (predefined commands) | Safe pattern | PASS |
| CI-007 | Unsafe deserialization | Synthetic | CRITICAL |

## Verification Procedure

1. Read CodeQL alerts through the GitHub skill and record analysis freshness.
2. Run security agent on `vulnerable_samples/` directory (interpretation)
3. Collect agent review in `.project-toolkit/security/SR-benchmark-*.md`
4. Evaluate interpretation quality:
   - Did agent correctly assess business impact?
   - Did agent provide specific, actionable remediation?
   - Did agent calibrate severity for deployment context?
5. Document interpretation gaps for improvement

## Success Criteria

**Detection** (CodeQL responsibility):

| Metric | Target | Measured By |
|--------|--------|-------------|
| CWE coverage | security-extended suite | GitHub Security tab |
| Automated blocking | Critical findings | CI/CD workflow |

**Interpretation** (Agent responsibility):

| Metric | Target | Current |
|--------|--------|---------|
| Review completeness | 100% findings reviewed | Pending |
| Mitigation specificity | Actionable recommendations | Pending |
| Context calibration | Severity adjusted for deployment | Pending |
| False positive identification | Correct acceptance rationale | Pending |

## Adding New Test Cases

1. Add vulnerable Python code to `vulnerable_samples/` with annotations
2. Add pytest case to appropriate `test_cwe*.py` file
3. Document in this README under appropriate category
4. Update expected detection count

## Python-Only Policy

Per ADR-042 (Python-first), all vulnerable samples are written in Python.
This ensures:

- Consistent testing across the AI/ML ecosystem
- No dual PowerShell/Python maintenance burden
- Alignment with bandit and pip-audit tooling

## References

- [Security Agent Prompt](../../../src/claude/security.md)
- [Severity Criteria](../../../.agents/governance/SECURITY-SEVERITY-CRITERIA.md)
- [CWE-699 Framework](https://cwe.mitre.org/data/definitions/699.html)
- [Issue #755 Security Agent Failure](https://github.com/rjmurillo/ai-agents/issues/755)
- [Issue #756 Detection Gaps Remediation](https://github.com/rjmurillo/ai-agents/issues/756)
- [ADR-042 Python-First](../../architecture/ADR-042-python-first.md)
