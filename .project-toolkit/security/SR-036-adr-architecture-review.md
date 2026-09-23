# Security Review: ADR-036 Two-Source Agent Template Architecture

**Reviewer**: Security Agent
**Date**: 2026-01-01
**ADR**: ADR-036-two-source-agent-template-architecture.md
**Review Phase**: Phase 1 (Independent Review)

## Security Review

### Strengths

1. **Path Traversal Protection** (CWE-22)
   - `Test-PathWithinRoot` function in `Generate-Agents.Common.psm1` validates all output paths remain within repository root
   - Implements directory separator append technique to prevent prefix-matching attacks (e.g., `/repo_evil` matching `/repo`)
   - Applied at file write time, not just configuration time

2. **Symlink Attack Prevention** (TOCTOU/MEDIUM-002)
   - Pre-commit hook includes symlink checks (`-L` tests) before script execution
   - Generated file staging includes symlink rejection for both directories and files
   - Defense-in-depth: multiple checkpoints (script path, output directories, individual files)

3. **No External Dependencies in Build Pipeline**
   - Generation uses only PowerShell built-ins and custom modules
   - No network calls or external package downloads during generation
   - Reduces supply chain attack surface

4. **CI Validation Gate**
   - `validate-generated-agents.yml` regenerates all agents and compares to committed files
   - Fails CI if generated output differs from committed files
   - Prevents tampered generated files from merging

5. **Drift Detection Monitoring**
   - `drift-detection.yml` workflow monitors Claude vs template synchronization
   - Creates issues when drift detected
   - Provides visibility into desync state

### Weaknesses/Gaps

1. **No Automated Content Sync Validation Between Sources** (Risk Score: 5/10)
   - ADR explicitly acknowledges: "No automated detection of content desync between sources"
   - Shared governance/security sections must be manually updated in both `templates/agents/*.shared.md` AND `src/claude/*.md`
   - Security-critical content (validation rules, compliance sections) could diverge between Claude and Copilot platforms
   - **Impact**: Security policies in Claude agents could differ from Copilot agents, affecting 50% of deployment targets

2. **ExecutionPolicy Bypass in Pre-Commit Hook** (Risk Score: 3/10)
   - Hook uses `pwsh -NoProfile -ExecutionPolicy Bypass`
   - Acceptable for developer machines but bypasses PowerShell security policies
   - **Mitigation**: Local-only execution, no untrusted input paths

3. **Agent Generation Failure is Non-Blocking** (Risk Score: 4/10)
   - Pre-commit hook line 531-534: "Non-blocking: just warn, don't fail the commit"
   - Failed generation only produces a warning, commit proceeds
   - **Impact**: Stale generated files could persist if developer ignores warnings
   - **Mitigation**: CI validation catches this before merge

4. **No Integrity Verification of Template Files** (Risk Score: 3/10)
   - No hash verification or signing of template files
   - Compromised template could propagate malicious content to 2 platforms (36 files)
   - **Mitigation**: Git history provides audit trail; CI validates outputs

### Scope Concerns

1. **Security Policy Drift Potential**
   - If security-related agent sections (e.g., input validation rules, threat models) are added to templates but not Claude files, Claude agents miss security guidance
   - Example scenario: New CWE validation rule added to `templates/agents/implementer.shared.md` but forgotten in `src/claude/implementer.md`
   - Result: VS Code and Copilot CLI get the rule; Claude Code does not

2. **Blast Radius of Template Compromise**
   - Single template file affects: 1 Copilot CLI output + 1 VS Code output = 2 files
   - Total: 18 templates x 2 outputs = 36 files affected by template directory compromise
   - Claude files (18) remain unaffected (separate source)

### Questions

1. **Drift Detection Coverage**: Does drift detection workflow compare security-relevant sections specifically, or only overall file hashes?

2. **Manual Sync Verification**: What process ensures security-critical content (authentication rules, input validation) is synchronized between sources during code review?

3. **Template Review Process**: Are changes to `templates/agents/*.shared.md` subject to security review before merge?

4. **Claude-Only Security Content**: Is there security content in Claude agents that is intentionally NOT in shared templates? If so, how is this documented?

### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| None | - | No blocking security concerns identified |

## Risk Assessment

| Category | Risk Level | Justification |
|----------|------------|---------------|
| Supply Chain | Low | No external dependencies, local-only generation |
| Path Traversal | Low | Validated with directory separator technique |
| Symlink Attacks | Low | Defense-in-depth checks at multiple points |
| Policy Drift | Medium | Manual sync required, no automated validation |
| Template Tampering | Low | Git history + CI validation provides detection |

**Overall Security Risk**: Low to Medium

The architecture has appropriate technical controls for build pipeline security. The primary security concern is operational: ensuring security-relevant content remains synchronized between sources through process discipline rather than automation.

## Recommendations

1. **Consider Adding Security Section Diff Check** (P2)
   - Add workflow that compares specific sections (e.g., "## Security", "## Validation") between templates and Claude files
   - Alert when security-relevant sections diverge

2. **Document Security Content Sync in PR Template** (P3)
   - Add checklist item: "If editing templates/agents/*.shared.md, verify security sections synced to src/claude/"
   - Makes sync requirement explicit in review process

3. **Make Agent Generation Blocking on Failure** (P3)
   - Change pre-commit hook to fail commit if generation fails
   - Prevents stale generated files from being committed

## Verdict

[PASS] - ADR-036 has acceptable security posture for agent template architecture. Technical controls are appropriate. Process controls for content synchronization should be enhanced through documentation and optional automation.

---

*Security Review completed 2026-01-01*
