# PRD: Session Evidence Verification System

## Problem Statement

AI agents hallucinate completion of work they did not perform. PR #875 caught 11 inconsistencies between claimed outcomes and actual results. Current session logs rely on trust-based evidence that cannot be verified. Agents claim success when failures occurred, report wrong file paths, cite nonexistent sessions, and miscount changed files.

**Evidence**: PR #875 revealed 11 specific hallucination types. Current validation only checks JSON schema, not claim accuracy. No cross-reference with git history, GitHub API, or file system.

## Goals

1. Detect agent hallucinations by comparing session claims to external sources of truth
2. Prevent hallucinated session logs from merging to main branch
3. Reduce false positives to zero through comprehensive testing
4. Maintain CI time increase under 25 percent
5. Enable gradual schema migration without breaking 387 existing sessions

## Non-Goals

1. Prevent agents from making mistakes during execution (PR #859 addresses this)
2. Replace existing JSON schema validation (complementary layer)
3. Validate historical sessions created before cutoff date (2025-12-21)
4. Block legitimate edge cases (detached HEAD, squash merge, force push)
5. Require immediate migration of all existing sessions

## User Stories

### Story 1: Cross-Field Consistency Validation

**As a** reviewer evaluating a PR

**I want** automated validation to detect when episode outcome contradicts session checklist

**So that** I do not waste time catching agent hallucinations manually

**Acceptance Criteria**:

- Validator detects outcome: failure when all MUST items complete (FAIL)
- Validator detects outcome: success when MUST items incomplete (FAIL)
- Validator detects files_changed: 0 when git shows 2 files changed (FAIL)
- Validator detects decisions: null when outcomes.decisions has content (FAIL)
- Validator returns exit code 0 for consistent sessions
- Validator returns exit code 1 with specific field-level errors for inconsistent sessions

**INVEST Check**:

- Independent: No dependencies on other validators
- Negotiable: Can adjust strictness of consistency rules
- Valuable: Addresses PR #875 issues 1, 4, 5, 6, 7
- Estimable: 3-5 days with test framework
- Small: Single validator, clear scope
- Testable: Deterministic with known inputs

### Story 2: Git Evidence Validation

**As a** security engineer auditing agent sessions

**I want** validation that session claims match actual git history

**So that** agents cannot falsify commit SHAs or file changes

**Acceptance Criteria**:

- Validator confirms startingCommit exists in repository (FAIL if missing)
- Validator confirms endingCommit is descendant of startingCommit (FAIL if not)
- Validator confirms branch contains endingCommit (WARN if missing)
- Validator confirms file changes match git diff output (FAIL if mismatch)
- Validator confirms commit timestamp aligns with session date (FAIL if future)
- Validator returns structured JSON with specific failures

**INVEST Check**:

- Independent: Uses git only, no external dependencies
- Negotiable: Can adjust temporal tolerance (24h window)
- Valuable: Detects commit SHA hallucinations
- Estimable: 2-4 days with ancestry checks
- Small: Single concern (git verification)
- Testable: Can mock git responses

### Story 3: Artifact Reference Validation

**As a** developer following session handoffs

**I want** validation that referenced artifacts exist

**So that** I do not waste time searching for nonexistent files

**Acceptance Criteria**:

- Validator detects referenced session logs that do not exist (FAIL)
- Validator detects file paths with typos or wrong directories (FAIL)
- Validator detects invalid commit SHAs (FAIL)
- Validator detects nonexistent PR numbers (FAIL via API check)
- Validator provides suggestion for similar valid paths (edit distance)
- Validator skips API checks when rate limit exhausted (exit code 2)

**INVEST Check**:

- Independent: File system and git checks only
- Negotiable: Can adjust edit distance threshold for suggestions
- Valuable: Addresses PR #875 issue 8
- Estimable: 2-3 days with path matching
- Small: Reference checking only
- Testable: Can create temporary fixtures

### Story 4: API Evidence Validation

**As a** PR reviewer

**I want** validation that claimed GitHub actions match API state

**So that** agents cannot hallucinate thread resolution or CI results

**Acceptance Criteria**:

- Validator confirms PR comments exist with claimed IDs (FAIL if missing)
- Validator confirms review thread status matches claims (FAIL if mismatch)
- Validator confirms CI check results match claims (FAIL if wrong)
- Validator caches API responses to avoid rate limit issues
- Validator skips gracefully when rate limit exhausted (exit code 2, not 1)
- Validator uses BOT_PAT for higher rate limits in CI

**INVEST Check**:

- Independent: Uses GitHub API only
- Negotiable: Can adjust caching strategy
- Valuable: Detects hallucinated PR interactions
- Estimable: 3-4 days with rate limit handling
- Small: API verification only
- Testable: Can mock gh API responses

### Story 5: Schema Migration with Backward Compatibility

**As a** system maintainer

**I want** gradual schema migration from v1.0 to v2.0

**So that** 387 existing sessions remain valid during transition

**Acceptance Criteria**:

- All 387 existing v1.0 sessions validate successfully
- New v2.0 sessions with structured evidence validate successfully
- Schema v2.0 allows string OR structured evidence (oneOf union)
- Migration script converts v1.0 to v2.0 without data loss
- session-init skill generates v2.0 logs by default
- Deprecation warnings appear for string evidence (90-day window)

**INVEST Check**:

- Independent: Schema change only, no validator changes
- Negotiable: Can adjust deprecation timeline
- Valuable: Enables structured evidence without breaking existing data
- Estimable: 2-3 days with migration script
- Small: Schema file and migration tool
- Testable: Can validate all existing sessions

### Story 6: CI Integration with Parallel Execution

**As a** DevOps engineer

**I want** validators to run in parallel without timeout

**So that** CI remains fast despite additional checks

**Acceptance Criteria**:

- CI workflow runs validators in matrix strategy (parallel per session)
- Multiple sessions also run in parallel
- Total CI time increase stays under 25 percent (from 5 min to under 6.25 min)
- Validators complete within 8-minute timeout per job
- Failed validators produce structured JSON for aggregation
- Job summary shows specific field-level errors without downloading artifacts

**INVEST Check**:

- Independent: CI config only, no validator logic changes
- Negotiable: Can adjust timeout thresholds
- Valuable: Maintains developer velocity
- Estimable: 1-2 days with workflow updates
- Small: YAML orchestration changes
- Testable: Can measure CI duration

## Functional Requirements

### Validator Requirements

1. Each validator MUST return exit code 0 for valid sessions
2. Each validator MUST return exit code 1 for MUST-level violations
3. Each validator MUST return exit code 2 for skipped checks (rate limits)
4. Each validator MUST return exit code 3 for SHOULD-level warnings
5. Each validator MUST output structured JSON with specific field errors
6. Each validator MUST complete within 3 seconds per session (excluding API calls)
7. Validators MUST work with current schema v1.0 (Sprint 1)
8. Validators MUST support schema v2.0 after migration (Sprint 2)

### Evidence Structure Requirements

1. Schema v2.0 MUST support oneOf union for string OR structured evidence
2. gitEvidence MUST include: type, sha, command, output
3. apiEvidence MUST include: type, endpoint, responseId, timestamp
4. fileEvidence MUST include: type, path, sha256, exists
5. Schema MUST validate with json-schema validator (draft-07)
6. Legacy string evidence MUST generate deprecation warnings (not errors)

### Pre-commit Requirements

1. Pre-commit hook MUST run fast validators only (episode consistency, metrics)
2. Pre-commit hook MUST complete within 10 seconds
3. Pre-commit hook MUST provide human-readable output
4. Pre-commit hook MUST suggest fix commands on failure
5. Pre-commit hook MUST NOT run API validators (rate limits)

### CI Requirements

1. CI MUST run all validators on every session in PR
2. CI MUST use matrix strategy for parallel execution
3. CI MUST aggregate results into single job summary
4. CI MUST block PR merge on exit code 1 (critical failures)
5. CI MUST warn but not block on exit code 3 (SHOULD violations)
6. CI MUST collect structured JSON output from each validator

## Design Considerations

### Existing Infrastructure to Leverage

Validators MUST use these existing modules:

| Module | Location | Purpose |
|--------|----------|---------|
| `GitHubCore.psm1` | `.claude/skills/github/modules/` | GitHub API calls, rate limiting, authentication |
| `GitHelpers.psm1` | `.claude/skills/session-init/modules/` | Git operations, commit info, diff stats |
| `SchemaValidation.psm1` | `.claude/skills/memory/modules/` | JSON schema validation |
| `HookUtilities.psm1` | `.claude/hooks/Common/` | Session path resolution, git commands |

**Episode Schema**: `.claude/skills/memory/resources/schemas/episode.schema.json`

### Validation Primitives Module

Create reusable functions in `scripts/modules/ValidationPrimitives.psm1`:

- `Test-GitCommitExists`: Verify SHA exists in repository
- `Test-GitAncestor`: Verify commit ancestry
- `Get-GitFileChanges`: List files changed between commits
- `Test-GitHubAPIResponse`: Verify API node ID exists (uses GitHubCore.psm1)
- `Get-FileContentHash`: Compute SHA-256 of file
- `Get-SessionPathByNumber`: Find session file by number
- `Resolve-SessionPath`: Normalize path with traversal prevention
- `Test-FileExists`: Check file with archive fallback
- `ConvertTo-CanonicalJson`: Serialize JSON consistently for hashing

**Security**: `Resolve-SessionPath` MUST prevent path traversal attacks by validating resolved paths stay within repo root.

### Output Format Standards

#### Structured JSON (CI)

```json
{
  "validator": "Episode-Session Consistency",
  "verdict": "FAIL",
  "exitCode": 1,
  "issues": [
    {
      "severity": "MUST",
      "field": "outcomes.episode.outcome",
      "expected": "success",
      "actual": "failure",
      "reason": "All MUST items complete but outcome is failure",
      "line": 42
    }
  ],
  "warnings": [],
  "metadata": {
    "sessionPath": ".agents/sessions/2026-01-11-session-01.json",
    "timestamp": "2026-01-11T14:30:00Z",
    "duration": "150ms"
  }
}
```

#### Human-Readable (Pre-commit)

```text
[FAIL] Episode-Session Consistency

Issues:
  ✗ outcomes.episode.outcome: Expected 'success' but got 'failure'
    Reason: All MUST items complete but outcome is failure
    Line: 42

Fix these issues before committing.
Run: pwsh scripts/Validate-SessionJson.ps1 -SessionPath [file]
```

## Technical Requirements

### Language and Tools

1. All validators MUST be PowerShell (.ps1) per ADR-005
2. All validators MUST have Pester tests (.Tests.ps1) with 90 percent coverage
3. Test framework MUST use Pester with fixtures in `tests/validation/fixtures/`
4. CI integration MUST use existing workflow pattern (no logic in YAML)

### Dependencies

1. Validators depend on ValidationPrimitives.psm1 module (Sprint 0)
2. Schema v2.0 depends on Sprint 1 validators proving approach (Sprint 2)
3. Integrity chain depends on schema v2.0 with integrity section (Sprint 3)
4. CI integration depends on Sprint 1 validators being stable (Sprint 4)

### Performance Targets

| Validator | Target Time | Parallelizable |
|-----------|-------------|----------------|
| Episode-Session Consistency | 50-100ms | Yes |
| Artifact References | 100-200ms | Yes |
| Metrics Accuracy | 200-500ms | Yes |
| File Path Consistency | 100-200ms | Yes |
| Git Evidence | 500-1000ms | Yes |
| Temporal Consistency | 200-400ms | Yes |
| API Evidence | 1000-3000ms | Yes |
| Integrity Chain | 100-300ms | Partial |

**Total parallel time per session**: 1-3 seconds (dominated by API calls)

### Edge Cases

1. **Detached HEAD**: Empty branch string is valid (WARN not FAIL)
2. **Squash merge**: Validator runs pre-merge when commit exists
3. **Force push**: Detect chain break, WARN if documented in Evidence
4. **Session spans midnight**: Allow endingCommit timestamp within 24h of session date
5. **Memory file pre-exists**: Fail if lastModified timestamp before session start
6. **API rate limit**: Skip with exit code 2, not fail
7. **Schema polymorphism**: Use case-insensitive matching for Complete/complete
8. **No endingCommit**: Valid for failed sessions, skip git diff checks
9. **Metrics tolerance**: Allow ±1 file difference for edge cases (submodules, symlinks, .gitignore changes)
10. **Archived sessions**: Check both `.agents/sessions/` AND `.agents/archive/sessions/` for file references

## Success Metrics

### Sprint 0 Success (Foundation)

- Schema polymorphism documented with distribution counts
- Test framework runs via Invoke-Pester with fixture sessions
- ValidationPrimitives module exports 5+ core functions
- All functions have unit tests with 90 percent coverage

### Sprint 1 Success (Core Validators)

- All 8 validators return exit code 0 for valid sessions
- All 8 validators return exit code 1 for invalid sessions
- PR #875 issues detectable by at least one validator
- Test suite has 90 percent code coverage across all validators
- CI integration runs validators in parallel with no timeouts

### Sprint 2 Success (Schema Migration)

- Schema v2.0 validates with json-schema validator
- All 387 existing sessions validate with new schema
- Migration script converts v1.0 to v2.0 losslessly
- session-init skill generates v2.0 sessions with structured evidence

### Sprint 3 Success (Integrity Chain)

- Integrity hashes generated for new sessions
- Chain validator detects tampering (test with modified session)
- Chain validation skips gracefully for missing previous sessions
- Force push edge case handled correctly (documented break gets WARN)

### Sprint 4 Success (CI Integration)

- CI workflow blocks PR with invalid session
- Pre-commit hook prevents commit of invalid session
- Job summary shows specific field-level errors
- PR comment includes validation report with verdicts

### Overall Success (90-day)

- Zero hallucination incidents in production sessions
- Zero false positives blocking valid work
- CI time increase under 25 percent (from 5 min to under 6.25 min)
- 100 percent of new sessions use schema v2.0 with structured evidence

## Dependencies

### External Dependencies

- PowerShell 7.0+ (already required)
- Pester testing framework (already installed)
- git command line (already required)
- gh CLI with API access (already required)
- jq for JSON processing (optional, nice to have)

### Internal Dependencies

- Existing session JSON schema at `.agents/schemas/session-log.schema.json`
- Existing validation script `scripts/Validate-SessionJson.ps1`
- session-init skill at `.claude/skills/session-init/`
- CI workflow at `.github/workflows/ai-session-protocol.yml`

### Integration with PR #859

This plan implements **verification layer** (Layer 2). PR #859 implements **prevention layer** (Layer 1).

**Deployment Order**: PR #859 MUST merge before this plan. Rationale:

1. Hooks establish baseline compliance (session logs exist)
2. Validators can assume well-formed inputs
3. Reduces false positives during validator rollout
4. Hooks are faster to deploy (no CI changes)

**Shared Utilities**: Both layers use `.claude/hooks/Common/HookUtilities.psm1`. Extend module with validation primitives for code reuse.

## Risks and Mitigations

### Risk 1: False Positives Block Valid Work

**Likelihood**: Medium

**Impact**: High (developer frustration, lost productivity)

**Mitigation**:

- Deploy validators at SHOULD level first (warnings only)
- Monitor CI for false positives for 1 week
- Promote to MUST level only after zero false positives
- Provide escape hatch: `[skip-session-validation]` in commit message (requires manual review)
- Comprehensive test suite catches edge cases before deployment

### Risk 2: Performance Degrades CI

**Likelihood**: Low

**Impact**: Medium (slower PR feedback)

**Mitigation**:

- Parallel matrix execution (already in workflow)
- Timeout limits (8 minutes per job, fail fast)
- ARM runners provide 37.5 percent cost savings (can afford longer runs)
- Performance targets documented and measured
- Optimization strategies (caching, batch operations, early exit)

### Risk 3: GitHub API Rate Limits

**Likelihood**: Medium

**Impact**: Medium (skipped validations)

**Mitigation**:

- Rate limit check before validation
- Exit code 2 (skip) instead of 1 (fail) when limit hit
- Response caching across validators
- Use BOT_PAT with higher rate limit (5000/hour vs 1000/hour)
- API validator only runs in CI, not pre-commit

### Risk 4: Schema Breaking Change

**Likelihood**: Low

**Impact**: High (breaks 387 existing sessions)

**Mitigation**:

- schemaVersion field enables version detection
- Validators check version, apply appropriate rules
- Backward compatibility tests for all existing sessions
- 90-day deprecation window for string evidence
- oneOf union allows gradual migration

### Risk 5: Integrity Chain Breaks on Legitimate Operations

**Likelihood**: Medium

**Impact**: Low (noisy warnings)

**Mitigation**:

- Document legitimate breaks (force push, session deletion)
- Validator checks for documentation in Evidence field
- Manual review flag for chain breaks (not auto-fail)
- First session (no previous) handled explicitly
- Gap in session numbers (deleted session) generates WARN not FAIL

## Open Questions

### Question 1: Integrity chain requirement level

**Question**: Should integrity chain be required (MUST) or optional (SHOULD)?

**Recommendation**: Optional (SHOULD) for first 90 days, then MUST.

**Rationale**: Allows gradual adoption. Agents need time to adapt session-init skill.

### Question 2: String evidence deprecation timeline

**Question**: When should string evidence become invalid?

**Recommendation**: 90 days warn, then hard requirement.

**Rationale**: Gives agents time to migrate. Matches industry standard deprecation window.

### Question 3: Historical session validation

**Question**: Should we validate all 387 historical sessions retroactively?

**Recommendation**: No. Exempt sessions before cutoff date (2025-12-21).

**Rationale**: Historical sessions used different protocol. Retroactive enforcement adds no value.

### Question 4: Validator bug hotfix process

**Question**: How to handle validator bugs discovered in production?

**Recommendation**: Hotfix process.

1. Deploy fix to validator
2. Re-run CI on open PRs
3. Allow manual override with `[skip-validation]` + explanation in PR comment
4. Document bug in session protocol

### Question 5: Empty endingCommit handling

**Question**: How to validate sessions with no endingCommit?

**Answer**: Valid for failed/incomplete sessions. Validators skip git diff checks if endingCommit empty.

**Rationale**: Not all sessions result in commits (investigation-only sessions).

## Implementation Phases

### Sprint 0: Foundation (Week 1)

**Goal**: Enable incremental development without breaking existing sessions.

**Deliverables**:

1. Schema polymorphism analysis report
2. Validator test framework with fixtures
3. ValidationPrimitives.psm1 module with core functions
4. Unit tests for primitives (90 percent coverage)

**Exit Criteria**: Pester tests pass, all functions documented.

### Sprint 1: Core Validators (Week 2-3)

**Goal**: Detect PR #875 issues with current schema.

**Deliverables**:

1. Validate-EpisodeSessionConsistency.ps1 (addresses issues 1, 4, 5, 6, 7)
2. Validate-ArtifactReferences.ps1 (addresses issue 8)
3. Validate-MetricsAccuracy.ps1 (addresses issues 5, 6, 7)
4. Validate-FilePathConsistency.ps1 (addresses issues 2, 3)
5. Validate-GitEvidence.ps1 (git verification)
6. Validate-TemporalConsistency.ps1 (timeline verification)
7. Validate-ApiEvidence.ps1 (GitHub API verification)
8. Pester tests for all validators (90 percent coverage)

**Exit Criteria**: All PR #875 issues detectable, zero false positives.

### Sprint 2: Schema Migration (Week 4)

**Goal**: Migrate to structured evidence types.

**Deliverables**:

1. Schema v2.0 with oneOf union for evidence
2. Validate-EvidenceStructure.ps1
3. Migration script: Convert-SessionToV2.ps1
4. Backward compatibility tests
5. Migration guide document

**Exit Criteria**: All 387 sessions validate, session-init generates v2.0.

### Sprint 3: Integrity Chain (Week 5)

**Goal**: Detect post-hoc tampering.

**Deliverables**:

1. New-SessionIntegrityHash.ps1
2. Validate-IntegrityChain.ps1
3. Unit tests with tamper detection scenarios
4. Schema update with integrity section

**Exit Criteria**: Tampering detected, legitimate breaks handled gracefully.

### Sprint 4: CI Integration (Week 6)

**Goal**: Enforce validation gates in CI and pre-commit.

**Deliverables**:

1. Updated CI workflow with validator jobs
2. Pre-commit hook with fast validators
3. Result aggregation script
4. Performance measurement report

**Exit Criteria**: CI blocks invalid sessions, time increase under 25 percent.

## Files to Create

### Sprint 0

- `scripts/Test-SchemaPolymorphism.ps1`
- `tests/validation/Test-ValidationFramework.Tests.ps1`
- `scripts/modules/ValidationPrimitives.psm1`
- `.agents/planning/session-evidence-verification/schema-polymorphism-report.md`

### Sprint 1

- `scripts/validators/Validate-EpisodeSessionConsistency.ps1`
- `scripts/validators/Validate-ArtifactReferences.ps1`
- `scripts/validators/Validate-MetricsAccuracy.ps1`
- `scripts/validators/Validate-FilePathConsistency.ps1`
- `scripts/validators/Validate-GitEvidence.ps1`
- `scripts/validators/Validate-TemporalConsistency.ps1`
- `scripts/validators/Validate-ApiEvidence.ps1`
- 7 corresponding Pester test files
- `tests/validation/fixtures/` with test sessions

### Sprint 2

- `.agents/schemas/session-log.schema.v2.json`
- `scripts/validators/Validate-EvidenceStructure.ps1`
- `scripts/Convert-SessionToV2.ps1`
- `tests/validation/Test-BackwardCompatibility.Tests.ps1`
- `.agents/planning/session-evidence-verification/migration-guide.md`

### Sprint 3

- `scripts/New-SessionIntegrityHash.ps1`
- `scripts/validators/Validate-IntegrityChain.ps1`
- `tests/validation/Test-IntegrityChain.Tests.ps1`

### Sprint 4

- `.github/workflows/ai-session-protocol.yml` (modify existing)
- `.github/hooks/pre-commit-session-validation.ps1`
- `.github/scripts/Aggregate-ValidationResults.ps1`

**Total**: 25 new files, 1 modification

## Appendix: PR #875 Evidence Mapping

| Issue | Description | Validator | Sprint |
|-------|-------------|-----------|--------|
| 1 | Episode outcome "failure" when session succeeded | Validate-EpisodeSessionConsistency.ps1 | 1 |
| 2 | File location mismatch (.agents/ vs .agents/planning/) | Validate-FilePathConsistency.ps1 | 1 |
| 3 | PR description does not match actual file changes | Validate-FilePathConsistency.ps1 | 1 |
| 4 | Status "In Progress" when complete | Validate-EpisodeSessionConsistency.ps1 | 1 |
| 5 | files_changed: 0 when 2 files created | Validate-MetricsAccuracy.ps1 | 1 |
| 6 | Event type "error" for successful milestone | Validate-MetricsAccuracy.ps1 | 1 |
| 7 | decisions: null despite decisions in session log | Validate-MetricsAccuracy.ps1 | 1 |
| 8 | Referenced session log does not exist | Validate-ArtifactReferences.ps1 | 1 |

**Coverage**: 100 percent of PR #875 issues detectable by Sprint 1 validators.

## Appendix: Validator Exit Codes

| Exit Code | Meaning | CI Behavior | Pre-commit Behavior |
|-----------|---------|-------------|---------------------|
| 0 | PASS | Continue | Continue |
| 1 | FAIL (MUST violation) | Block PR | Block commit |
| 2 | SKIP (rate limit, missing data) | Warn, continue | Warn, continue |
| 3 | WARN (SHOULD violation) | Continue, log warning | Warn, continue |

## Related Documents

- Detailed plan: `/home/richard/.claude/plans/fancy-moseying-graham-agent-ac0a4f8.md`
- Session protocol: `.agents/SESSION-PROTOCOL.md`
- Session schema: `.agents/schemas/session-log.schema.json`
- Project constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`
- PR #859 (prevention layer): Related PR implementing Claude Code hooks
- PR #875 (evidence): PR that revealed 11 inconsistencies
