# Phase 4: Copilot Follow-Up Detection - Memory-First Pattern

**Created**: 2025-12-20 Session 42
**Purpose**: Institutional knowledge for Phase 4 Copilot follow-up PR detection
**Architecture**: Memory-driven pattern matching (NOT external scripts)

## Core Pattern Recognition

### Detection Rule: Branch Pattern Matching

Copilot follow-up PRs match EXACTLY:
- **Branch format**: `copilot/sub-pr-{original_pr_number}`
- **Target**: Original PR's base branch (typically `main`)
- **Creator**: User account or `app/copilot-swe-agent`
- **Announcement**: Issue comment from Copilot containing "opened a new pull request"

**Example**: 
- Original: PR #32 
- Follow-up: PR #33 with branch `copilot/sub-pr-32`
- Announcement: Copilot posts "I've opened a new pull request, #33, to work on those changes"

### API Query Pattern

```
Search: gh pr list --state=open --search="head:copilot/sub-pr-{PR_NUMBER}"
Expected: Returns follow-up PR(s) if pattern matches
```

### Verification Pattern

**Always verify** Copilot announcement comment exists:
```
gh api repos/OWNER/REPO/issues/{PR_NUMBER}/comments
Filter: .user.login == "app/copilot-swe-agent" AND .body contains "opened a new pull request"
```

## Intent Categorization Pattern

Once follow-up PR detected, categorize by analyzing changes:

### Category 1: DUPLICATE
**Indicator**: Follow-up PR contains NO changes OR changes already applied to original PR
**Signal**: 
- Empty diff: 100% confidence DUPLICATE
- Single file same as original: 85% confidence DUPLICATE (similar analysis)
- Original PR already fixed the issues: DUPLICATE intent

**Action**: Close with explanation linking to original commits
**Why**: Copilot created follow-up AFTER original reply, but fixes already applied

**Example**: PR #32/#33 pattern
- PR #32: Received Copilot's 5 review comments
- Fix Applied: Commit 760f1e1 addressed all 5 comments
- Copilot Follow-up: PR #33 created but duplicates already-fixed issues
- Resolution: Close PR #33 as DUPLICATE

### Category 2: SUPPLEMENTAL
**Indicator**: Follow-up PR addresses DIFFERENT or ADDITIONAL issues not in original review
**Signal**:
- Multiple files changed in follow-up
- Changes target different problem areas
- New functionality added beyond scope of original comments

**Action**: Evaluate for merge OR request changes
**Why**: Copilot identified additional work needed after analyzing original PR

### Category 3: INDEPENDENT
**Indicator**: Follow-up PR unrelated to original review comments
**Signal**:
- Branch pattern matches but content unrelated
- Different problem domain
- No correlation to original comment thread

**Action**: Close with explanation
**Why**: Likely Copilot misunderstood context

## Decision Execution Pattern

### DUPLICATE Decision Flow
```
1. Identify original commits that fixed the issues
2. Close follow-up PR with comment citing commits
3. Example: "Closing: This follow-up PR duplicates changes already applied in commit {hash}. See PR #{original} for details."
4. Delete branch after closing
```

### SUPPLEMENTAL Decision Flow
```
1. Evaluate: Are supplemental changes valid?
2. If YES and important: Merge to original PR branch
3. If YES but lower priority: Leave open for tracking
4. If NO or unclear: Request clarification from Copilot
```

### INDEPENDENT Decision Flow
```
1. Verify pattern matches but content unrelated
2. Close with note: "This PR addresses concerns already resolved in PR #{original}. No action needed."
3. Delete branch
```

## Session Tracking Pattern

When executing Phase 4, document in session log:

```markdown
## Phase 4: Copilot Follow-Up Detection

**Detection**: [Found / Not Found]
**Follow-Up PR**: [#number or None]
**Announcement Verified**: [Yes / No / N/A]
**Category**: [DUPLICATE / SUPPLEMENTAL / INDEPENDENT / N/A]
**Decision**: [CLOSED / MERGED / PENDING_REVIEW / NO_ACTION]

### Results Summary
- Follow-up PRs detected: [N]
- Closed as DUPLICATE: [X]
- Merged supplemental: [Y]
- Pending review: [Z]
```

## Memory-First Implementation Pattern

**KEY PRINCIPLE**: Agents access this memory pattern during Phase 1 (Step 0: list_memories)

### Workflow Integration
```
Phase 1 (Context): Read pr-comment-responder-skills memory (includes this pattern)
Phase 2 (Acknowledgment): Add eyes reactions to all comments
Phase 3 (Analysis): Delegate to orchestrator per skill guidance
Phase 4 (Copilot Detection): Execute pattern from THIS MEMORY
Phase 5 (Replies): Post responses following template
Phase 6 (Implementation): Implement identified tasks
Phase 7 (Thread Resolution): Resolve review threads
Phase 8 (Verification): Verify all gates cleared
```

### Detection Pseudocode (Memory-Driven)
```
// Agent reads this memory at Phase 1
// At Phase 4, agent applies pattern WITHOUT external scripts

if Phase 4 triggered {
  PR_NUMBER = context.pull_number
  
  // Query for pattern match
  follow_ups = gh pr list --search="head:copilot/sub-pr-${PR_NUMBER}"
  
  if follow_ups.length == 0 {
    log("No follow-up PRs found")
    goto Phase_5
  }
  
  // Verify announcement
  announcement = query_issue_comments(filter: contains("opened a new pull request"))
  if !announcement {
    log("WARNING: Follow-up PR found but no Copilot announcement")
  }
  
  // Categorize based on memory pattern
  for each follow_up_pr {
    diff_size = analyze_diff(follow_up_pr)
    
    if diff_size == 0 {
      category = "DUPLICATE"
    } else if diff_size > threshold {
      category = "SUPPLEMENTAL"
    } else {
      category = "INDEPENDENT"
    }
    
    // Execute decision per memory pattern
    execute_decision(category, follow_up_pr)
  }
  
  goto Phase_5
}
```

## Related Memories
- `pr-comment-responder-skills`: Full skill set including Skill-PR-Copilot-001
- `copilot-follow-up-pr-pattern`: Historical pattern documentation
- `phase2-handoff-context`: Phase 2 task definitions

## Validation Checklist

Before Phase 5 begins:
- [ ] Memory accessed at Phase 1 (Step 0: list_memories)
- [ ] Pattern query executed (gh pr list for follow-up detection)
- [ ] Announcement verified (if applicable)
- [ ] Category assigned per pattern rules
- [ ] Decision executed (CLOSE / MERGE / PENDING)
- [ ] Session log updated with results
- [ ] NO external scripts invoked (memory-driven only)

## Notes

**Architecture Principle**: This pattern replaces detect-copilot-followup.sh shell script. All detection logic is now embedded in institutional knowledge (Serena memory), not in external code files.

**Benefits**:
- Agents learn from memories, not maintain external scripts
- Pattern changes only require memory updates, not code deployment
- Institutional knowledge centralized and version-controlled
- Cross-agent pattern consistency enforced via memory

**Enforcement**: SESSION-PROTOCOL.md Phase 1 MANDATORY requires agents to execute Step 0 (list_memories). This pattern is accessed as part of pr-comment-responder-skills, ensuring memory-first workflow.
