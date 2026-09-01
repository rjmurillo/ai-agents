---
id: ADR-054
status: accepted
date: 2026-07-20
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-054: Local Security Scanning

**Status**: Accepted (amended 2026-05-02)
**Date**: 2026-02-19
**Revised**: 2026-07-20
**Deciders**: Security Agent, DevOps Agent
**Context**: Pre-push security scanning to complement CI-based CodeQL

---

## Amendment 2026-05-02: CWE-22 scope narrowing for the `security-scan` skill

Scope of this amendment: the internal `security-scan` skill at `.claude/skills/security-scan/scripts/scan_vulnerabilities.py`. This is a SEPARATE tool from the Semgrep pre-push job described in the Decision and Implementation sections below. The skill is a regex-based scanner invoked manually or by Claude during code review; the Semgrep job runs through Lefthook. Both fall under the broader "local security scanning" umbrella.

Change: the skill no longer detects CWE-22 (path traversal). CWE-22 detection is delegated to CodeQL's `python-security-extended.qls` query suite, which runs on every PR via `.github/workflows/codeql-analysis.yml`. The skill remains in scope for CWE-78 (command injection).

Rationale: PR #1841 demonstrated that the regex CWE-22 patterns generated false positives on safe `Path(__file__)` derivations (seven inline suppression annotations were added across three files to silence them). A buy-vs-build analysis (issue #1843) confirmed CodeQL's taint-tracking dataflow is a strict superset of what the regex caught for CWE-22, and the regex's substring-on-variable-name heuristic missed real attacker-controlled paths anyway. Path-traversal detection is Context (table stakes), not a competitive differentiator; CodeQL is the right tool.

What this amendment does NOT change:

- The Semgrep pre-push policy is unchanged. Whatever CWE-22 patterns its `--config auto` ruleset matches continue to fire.
- ADR-054's core decision (run lightweight security scanning before push) is intact.
- The fast-feedback goal remains. Lefthook enforces a 15-minute hard limit.

Authoritative scope statement for the skill: see `.claude/skills/security-scan/SKILL.md` `## Scope`.

Refs: issue #1843, PR #1841, PR #1851, branch `agent/issue-1843`.

---

## Context and Problem Statement

PR #908 demonstrated that security findings discovered in CI (CodeQL CWE-22 path traversal) create significant overhead:

1. **Late feedback**: Findings appear after PR creation, not during development
2. **Review noise**: Security comments pollute PR threads
3. **Wasted cycles**: Reviewers spend time on issues that could be caught locally
4. **Slower iteration**: Developers must context-switch back to fix security issues

The local pre-push pipeline runs lint, type checks, tests, and governance validation. Before this decision, it lacked security scanning for code vulnerabilities.

ADR-041 established CodeQL integration with a multi-tier strategy. Tier 1 (CI/CD) provides enforcement. Tier 2 (local) and Tier 3 (automatic PostToolUse) are optional developer conveniences. Neither tier runs in the pre-push hook.

**Key Question**: Should all PRs with code changes run local security scans before push?

## Decision

Add a Lefthook pre-push job that scans changed code files.

**Tool choice**: The pinned Semgrep executable only. Bandit remains an
alternative considered, not a fallback.

**Rationale for tool selection**:
- **semgrep**: Cross-language support for Python, PowerShell, JavaScript,
  TypeScript, and YAML through one CLI
- **bandit**: Python-only but zero dependencies, well-established
- **CodeQL CLI**: Too slow for pre-push (30-60 seconds minimum), requires database build

**Scope**: Changed files only (consistent with existing pre-push patterns).

**Threshold**: Select Semgrep `ERROR` severity only. An `ERROR` finding blocks
the push. Lower severities are not selected by this local command.

**Local bypasses**: Git `--no-verify`, Lefthook disable and configuration
override mechanisms, and direct hook edits technically exist. Repository policy
forbids using them to skip required checks. A disputed finding requires a code
fix or security-owner decision. Protected CI remains the authoritative remote
backstop.

### Implementation

The `security-scan` job in `lefthook.yml` invokes
`scripts/validation/git_hook_policy.py semgrep-push`. For each pushed ref
update, the policy computes changed paths from its resolved push range. It uses
the `origin/main` merge base when available, with existing-remote or `main`
fallbacks. It materializes each pushed tree and scans supported files from that
tree, not from the working tree.

The script:

1. Resolves each pushed ref update and its changed paths
2. Filters to supported extensions: `.py`, `.ps1`, `.psm1`, `.js`, `.ts`, `.yaml`, `.yml`
3. Runs `semgrep scan --config auto --severity ERROR --json` on matched files
4. Blocks on ERROR findings and scanner execution failures
5. Rejects inline Semgrep suppressions

### Installation

The pinned development environment provides Semgrep. See
[CONTRIBUTING.md](../../CONTRIBUTING.md#security-scanning).

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Status quo (CI-only) | No local setup | PR #908 proves late feedback is costly | Delays feedback loop |
| CodeQL CLI in pre-push | Comprehensive coverage | 30-60s minimum, requires database | Too slow for pre-push |
| bandit only | Zero dependencies | Python-only, misses PowerShell | Incomplete coverage |
| semgrep + bandit | Defense in depth | Redundant for Python, slower | Diminishing returns |
| IDE-only (extensions) | No hook friction | Not enforced, inconsistent | Optional = often skipped |

### Trade-offs

**Changed Scope vs. Coverage**: Semgrep scans changed pushed files. CI retains
repository-level CodeQL scanning for defense in depth.

**Pinned Tool vs. Optional Tool**: Semgrep is required through the frozen uv
environment. A missing executable is an environment failure, not a silent skip.

**Changed Files vs. Full Repo**: Scanning only changed files trades completeness for speed. New vulnerabilities in unchanged code remain CI's responsibility.

## Consequences

### Positive

1. **Shift-left security**: Catch blocking Semgrep findings before push
2. **Cleaner PRs**: Security findings fixed before PR creation
3. **Faster iteration**: Local feedback loop
4. **Developer education**: Immediate exposure to secure coding patterns
5. **Reduced review noise**: Fewer security comments in PR threads

### Negative

1. **Tool restoration**: Requires the pinned uv development environment
   - **Mitigation**: One `uv sync --frozen --extra dev` restores all hook tools
2. **False positives**: May flag safe patterns
   - **Mitigation**: Rewrite the code or obtain a security-owner policy change
3. **Push friction**: Adds local scanning work before each applicable push
   - **Mitigation**: Scans only changed files from the pushed trees

### Neutral

1. **CI redundancy**: CodeQL continues running in CI
   - **Rationale**: Defense in depth, different rule sets
2. **Local bypass mechanisms**: `--no-verify`, Lefthook overrides, and direct
   hook edits remain technically available
   - **Policy**: Do not use them to skip required checks; protected CI remains
     the authoritative remote backstop

## Implementation Notes

### Performance Budget

| Boundary | Enforced budget |
|----------|----------------:|
| Python Semgrep child process | 840 seconds |
| Lefthook `security-scan` job | 900 seconds |

### Exit Code Handling

Per ADR-035:
- Exit 0: No findings
- Exit 1: Findings found (blocking)
- Exit 2: Configuration error (blocking)
- Exit 3: External tool error (blocking)

### Integration with ADR-041

This ADR complements ADR-041's multi-tier strategy:

| Tier | Tool | Trigger | Coverage |
|------|------|---------|----------|
| 1 (CI) | CodeQL | PR push | Repository-level |
| 2 (Local) | CodeQL CLI | Developer-initiated | Developer-selected |
| 3 (Auto) | CodeQL | PostToolUse hook | Quick queries |
| **4 (Pre-push)** | **Semgrep** | **git push** | **Changed pushed files** |

### Suppression Policy

Inline Semgrep suppressions are rejected. A disputed finding requires a code
fix or security-owner policy decision, not a justification-based bypass.

## Related Decisions

- [ADR-086: Lefthook for Local Git Hook Orchestration](./ADR-086-lefthook-local-hook-orchestration.md)
- [ADR-041: CodeQL Integration](./ADR-041-codeql-integration.md)
- [ADR-035: Exit Code Standardization](./ADR-035-exit-code-standardization.md)

## References

- [semgrep documentation](https://semgrep.dev/docs/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md`
- Issue #949

---

**Supersedes**: None (extends ADR-041)
**Amended by**: None
