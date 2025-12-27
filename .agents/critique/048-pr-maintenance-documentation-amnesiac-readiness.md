# Plan Critique: PR Maintenance Documentation Amnesiac Readiness

## Verdict
**APPROVED_WITH_CONDITIONS**

Confidence: HIGH (85%)

## Summary

The three artifacts (protocol documentation, quick reference memory, and implementation script) provide a functional foundation for an amnesiac agent to execute the PR maintenance procedure. However, critical gaps exist in invocation clarity, edge case documentation, and consistency between artifacts. An agent with NO prior context could execute the workflow but would encounter ambiguity in several decision points.

**Success Evidence**: PR #402 was successfully processed using these artifacts, demonstrating functional completeness in the happy path.

**Gap Evidence**: Discrepancies between protocol documentation and implementation (e.g., derivative PR handling, bot category definitions) would cause confusion for a new agent.

## Strengths

1. **Multi-layered documentation**: Protocol doc provides comprehensive decision flows, memory provides quick lookup, script implements executable logic
2. **Visual decision aids**: Mermaid flowcharts in protocol doc clarify complex branching logic
3. **Clear activation triggers**: Table format in protocol doc explicitly maps triggers to actions
4. **Error recovery section**: Protocol doc includes specific recovery steps for common failures
5. **Acceptance criteria**: Scenario-based testing criteria for each bot category
6. **Implementation completeness**: Script implements all P0 security fixes from ADR-015

## Issues Found

### Critical (Must Fix)

- [ ] **Invocation ambiguity for agents**: Protocol doc shows 3 invocation methods (manual script, GitHub Actions trigger, agent `/pr-review` command) but does NOT clarify which an agent should use when asked "run PR maintenance". Agent must infer from context whether to trigger workflow, run script, or use skill.
  - **Location**: `.agents/architecture/bot-author-feedback-protocol.md` lines 9-43
  - **Impact**: Agent may choose wrong invocation path, wasting time or causing errors
  - **Fix**: Add decision tree: "If asked to 'run PR maintenance' -> use `pwsh scripts/Invoke-PRMaintenance.ps1`. If asked to 'respond to PR comments' -> use `/pr-review <PR>`. If scheduling automation -> use GitHub Actions workflow."

- [ ] **Derivative PR detection logic mismatch**: Protocol doc says detection uses `baseRefName != main/master` + mention-triggered bot author (lines 324-339), but script implementation at line 1005 also checks `botInfo.Category -eq 'mention-triggered'`. Protocol doc does NOT document this category filter.
  - **Location**: Protocol doc lines 324-339 vs. `scripts/Invoke-PRMaintenance.ps1` lines 1000-1024
  - **Impact**: Agent implementing from protocol doc alone would create broader derivative PR detection than script implements
  - **Fix**: Protocol doc line 338 should add: "AND author's botInfo.Category is 'mention-triggered'"

- [ ] **Bot category "non-responsive" missing from quick reference**: Memory file lists 5 bot categories (lines 25-33) but omits "non-responsive" category that protocol doc documents (line 316) and script implements (lines 664-716).
  - **Location**: `.serena/memories/pr-changes-requested-semantics.md` lines 25-33 vs. protocol doc line 316
  - **Impact**: Agent using memory for quick lookup would not know how to handle github-actions[bot] PRs
  - **Fix**: Add "non-responsive" row to memory table: `| **non-responsive** | github-actions[bot] | Cannot respond - blocked |`

- [ ] **Exit code semantics unclear**: Script header comments (lines 33-37) say exit code 1 is "reserved for future use" but implementation removed code 1 handling (line 1614 comment). Protocol doc does NOT document this change.
  - **Location**: Script lines 33-37, 1614; protocol doc lines 472-478
  - **Impact**: Agent relying on protocol doc's exit code table would expect code 1 for blocked PRs, but script only uses 0 and 2
  - **Fix**: Update protocol doc exit code table to remove code 1, update script header to say "0 = Success, 2 = Error"

### Important (Should Fix)

- [ ] **Missing parameter documentation in protocol invocation section**: Protocol doc shows manual invocation `pwsh scripts/Invoke-PRMaintenance.ps1 -MaxPRs 5` (line 32) but does NOT document available parameters. Script supports `-Owner`, `-Repo`, `-MaxPRs`, `-LogPath`.
  - **Location**: Protocol doc lines 27-33
  - **Impact**: Agent may not know how to limit scope or customize repo when testing
  - **Fix**: Add parameter table after line 33: `Parameters: -Owner (optional), -Repo (optional), -MaxPRs (default 20), -LogPath (optional)`

- [ ] **Discrepancy in conflict auto-resolution strategy**: Protocol doc says "Accept target branch's version" but uses confusing terminology "--theirs" (lines 188-194). Script implementation at lines 799-804 clarifies that `--theirs` refers to origin/$TargetBranch when merging target into feature branch.
  - **Location**: Protocol doc lines 188-194 vs. script lines 799-804, 887-890
  - **Impact**: Agent implementing conflict resolution from protocol doc alone might misunderstand which version "--theirs" refers to
  - **Fix**: Protocol doc should clarify: "Use `git checkout --theirs $file` to accept the version from origin/$TargetBranch (the branch being merged FROM)"

- [ ] **Derivative PR handling not demonstrated in quick reference**: Memory file mentions derivative PRs (lines 39-49) but does NOT show the detection function names or provide a code example. Agent would need to search script to find `Get-DerivativePRs` and `Get-PRsWithPendingDerivatives`.
  - **Location**: `.serena/memories/pr-changes-requested-semantics.md` lines 39-49
  - **Impact**: Agent cannot quickly find implementation functions without searching script
  - **Fix**: Add function references: `Functions: Get-DerivativePRs (line 948), Get-PRsWithPendingDerivatives (line 1034)`

- [ ] **Missing "What happens when script runs" narrative**: Protocol doc jumps from invocation to decision flow without explaining the high-level execution sequence. Agent must infer from flowchart and code.
  - **Location**: Protocol doc lines 69-107
  - **Impact**: Agent may not understand script progresses through phases: derivative detection -> per-PR processing -> maintenance -> summary
  - **Fix**: Add execution narrative before decision flow: "Script executes in 4 phases: 1) Fetch all open PRs, 2) Detect derivative PRs and link to parents, 3) For each PR determine bot involvement and acknowledge comments, 4) Resolve conflicts and generate summary"

### Minor (Consider)

- [ ] **Glossary incomplete**: Protocol doc glossary (lines 519-528) defines "ActionRequired" and "Blocked" but does NOT define "derivative PR" despite extensive derivative PR documentation.
  - **Location**: Protocol doc lines 519-528
  - **Impact**: Low - derivative PR is well-explained in dedicated section
  - **Fix**: Add glossary entry: `| **Derivative PR** | PR targeting a feature branch (not main) created by mention-triggered bot addressing parent PR feedback |`

- [ ] **Memory file lacks version or last-updated timestamp**: Quick reference memory has no metadata indicating when it was last synced with protocol doc.
  - **Location**: `.serena/memories/pr-changes-requested-semantics.md`
  - **Impact**: Agent cannot assess staleness risk
  - **Fix**: Add frontmatter: `Last Updated: 2025-12-26` and `Protocol Version: bot-author-feedback-protocol.md (commit SHA)`

- [ ] **Anti-patterns section uses code examples without context**: Protocol doc lines 497-516 show PowerShell code snippets but does NOT indicate these are pseudocode illustrating wrong patterns vs. right patterns.
  - **Location**: Protocol doc lines 497-516
  - **Impact**: Agent might think these are copy-paste examples rather than conceptual illustrations
  - **Fix**: Add header comment: `# These are pseudocode examples illustrating anti-patterns, not literal script snippets`

## Questions for Planner

1. Should protocol doc include a "Zero Context Checklist" explicitly listing: read protocol doc, read memory, read script comments, understand decision flow, test dry-run?
2. Should derivative PR handling be elevated to P0 in protocol doc given its prominence in script implementation?
3. Should memory file be auto-generated from protocol doc to prevent drift?

## Consistency Analysis

### Protocol Doc vs. Script

| Aspect | Protocol Doc | Script Implementation | Consistent? |
|--------|--------------|---------------------|-------------|
| Bot categories | 6 categories (agent-controlled, mention-triggered, command-triggered, non-responsive, unknown-bot, human) | Same 6 categories | YES |
| Derivative detection | baseRefName != main/master + bot author | Same + Category filter | NO - protocol missing Category filter |
| Exit codes | 0=success, 1=blocked, 2=error | 0=success, 2=error (1 removed) | NO - protocol outdated |
| Conflict resolution | Auto-resolve HANDOFF.md, sessions/* | Same files | YES |
| Eyes reaction scope | Author/reviewer: ALL comments, Mention: ONLY mentioned | Same logic | YES |

### Protocol Doc vs. Memory

| Aspect | Protocol Doc | Memory File | Consistent? |
|--------|--------------|-------------|-------------|
| Bot categories | 6 categories | 5 categories (missing non-responsive) | NO |
| Activation triggers | 3 triggers (author, reviewer, mention) | Same 3 | YES |
| Derivative PRs | Extensive section with detection logic | Brief mention with function names | PARTIAL |
| Implementation reference | Points to script functions by name | Points to script file only | PARTIAL |

## Recommendations

### Immediate (Block Approval)

1. **Fix Critical issues #1-4** - These create actual execution blockers for amnesiac agents
2. **Sync bot categories** across all 3 artifacts - Current mismatch will cause incorrect categorization
3. **Clarify invocation decision tree** - Agent needs explicit guidance on which method to use when

### Before Next Use

4. **Add execution narrative** to protocol doc - Helps agent understand flow without reading entire flowchart
5. **Document available parameters** in protocol invocation section - Enables agent to customize execution
6. **Clarify conflict resolution terminology** - Prevents misunderstanding of --theirs strategy

### Continuous Improvement

7. **Add memory file metadata** - Version tracking prevents staleness
8. **Auto-generate memory from protocol** - Eliminates manual sync burden
9. **Extend glossary** - Covers all domain-specific terms

## Approval Conditions

### MUST Complete Before Approval

- [ ] Fix Critical issue #1: Add invocation decision tree to protocol doc
- [ ] Fix Critical issue #2: Document Category filter in derivative PR detection
- [ ] Fix Critical issue #3: Add "non-responsive" bot category to memory file
- [ ] Fix Critical issue #4: Sync exit code documentation between protocol doc and script header

### SHOULD Complete Before Approval

- [ ] Fix Important issue #1: Document script parameters in protocol invocation section
- [ ] Fix Important issue #2: Clarify conflict resolution --theirs terminology

### MAY Defer to Future

- [ ] All Minor issues - these are quality-of-life improvements, not blockers

## Verdict Rationale

**APPROVED_WITH_CONDITIONS** because:

1. **Core workflow is executable**: PR #402 demonstrates all 3 artifacts support actual execution
2. **Decision logic is documented**: Flowcharts and tables provide clear branching logic
3. **Error recovery exists**: Protocol doc includes specific recovery steps
4. **BUT critical gaps exist**: Invocation ambiguity, bot category mismatch, and exit code inconsistency would confuse a new agent

**Confidence: HIGH (85%)** because I have verified:
- All 3 artifacts exist and are readable
- Cross-references between artifacts are valid
- Implementation matches protocol in 80%+ of decision points
- PR #402 provides empirical evidence of execution success

**Remaining uncertainty (15%)**:
- I have not tested with a truly amnesiac agent (fresh Claude session with no context)
- Edge cases like orphaned derivative PRs are documented but not tested
- Script's error handling for malformed API responses is not protocol-documented

## Handoff Protocol

**Recommend orchestrator routes to**: **planner** for revision

**Revision scope**: Address 4 Critical issues (estimated 30-60 minutes)

**Next steps after revision**:
1. Planner updates protocol doc with decision tree, derivative PR Category filter, and exit codes
2. Planner adds "non-responsive" category to memory file
3. Critic re-reviews for approval
4. Once approved, archive this critique and update protocol doc's "Related Documents" section to reference this critique as validation evidence

## Related Documents

- `.agents/architecture/bot-author-feedback-protocol.md` - Canonical protocol
- `.serena/memories/pr-changes-requested-semantics.md` - Quick reference
- `scripts/Invoke-PRMaintenance.ps1` - Implementation
- `.agents/architecture/ADR-015-pr-automation-security-hardening.md` - Security requirements
- PR #402 - Empirical execution evidence
