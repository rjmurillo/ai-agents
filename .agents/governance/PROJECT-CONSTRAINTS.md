# Project Constraints

> **Status**: Canonical Source of Truth
> **Last Updated**: 2026-08-04
> **RFC 2119**: This document uses RFC 2119 key words.

## Purpose

Single source of truth for project constraints. Index-style document pointing to authoritative sources.

**How to use**: Read at session start. When in doubt, click through to Source for full rationale.

---

## RETRIEVAL-LED REASONING

**IMPORTANT**: This document is the SINGLE SOURCE OF TRUTH for constraints.

When making decisions about:
- Language choice (Python vs PowerShell) → Read "Language Constraints" section, NOT pre-training
- Skill usage → Read "Skill Usage Constraints" section, NOT pre-training
- Workflow patterns → Read "Workflow Constraints" section, NOT pre-training
- Commit structure → Read "Commit Constraints" section, NOT pre-training

**Do NOT rely on pre-training for these constraints.** Pre-training may reflect outdated patterns.

**Process**:
1. Identify decision type (language, workflow, etc.)
2. Read corresponding section in THIS document
3. Follow "Source" link for full rationale if needed
4. Apply constraint, not pre-training assumption

---

## Language Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST NOT create bash scripts (.sh) | ADR-005, ADR-042 | Pre-commit hook for `.github/scripts/`; code review elsewhere |
| SHOULD prefer Python (.py) for new scripts | ADR-042 | Code review |
| MUST keep scripts Python-first; no tracked PowerShell scripts remain | ADR-042 | Code review, `git ls-files '*.ps1' '*.psm1'` |

**References**:

- [ADR-005-powershell-only-scripting.md](../architecture/ADR-005-powershell-only-scripting.md) (superseded for new development)
- [ADR-042-python-migration-strategy.md](../architecture/ADR-042-python-migration-strategy.md) (current)

**Rationale Summary**: ADR-042 establishes Python-first development due to 70-second PowerShell startup times, CodeQL support, and AI/ML ecosystem alignment. The repository no longer tracks PowerShell scripts; new scripts should use Python.

**Exceptions**: Bash scripts are still prohibited. PowerShell may appear only in historical rationale or external examples.

---

## Skill Usage Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST NOT use raw `gh` commands when skill exists | usage-mandatory | Manual helper `scripts/check_skill_exists.py`; code review |
| MUST check `.claude/skills/` before GitHub operations | usage-mandatory | Session Protocol "Phase 4: Skill Validation (BLOCKING)" |
| MUST extend skills if capability missing, not write inline | usage-mandatory | Code review |

**Reference**: Use `mcp__serena__read_memory` with `memory_file_name="usage-mandatory"`

**Rationale Summary**: Skills are tested, handle errors, have proper parameter validation, and are maintained centrally. Raw commands bypass all quality controls.

**Process**:

1. Before ANY GitHub operation, check if skill exists
2. If exists, use the skill script
3. If missing, ADD to skill (don't write inline), then use it

**Skill Location**: `.claude/skills/github/scripts/{pr,issue,reactions}/`

---

## Workflow Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST NOT put business logic in workflow YAML | ADR-006 | Code review |
| SHOULD keep workflows under 100 lines (orchestration only) | ADR-006 | Code review; no lint gate currently enforces this |
| MUST put complex logic in Python modules | ADR-006, ADR-042 | Code review |
| MUST have pytest tests for modules (80%+ coverage) | ADR-006 | Targeted pytest coverage run; code review |
| MUST add new AI-powered workflows to monitoring list | workflow-coalescing | Code review, manual validation |
| MUST run `gh act` locally before pushing workflow changes | AGENTS.md | `gh act` output in transcript |
**Reference**: [ADR-006-thin-workflows-testable-modules.md](../architecture/ADR-006-thin-workflows-testable-modules.md)

**Rationale Summary**: GitHub Actions workflows cannot be tested locally. The feedback loop (edit -> push -> wait -> check) is slow. Extracting logic to modules enables fast local testing with pytest.

**Pattern**:

- Workflow YAML: Orchestration only (calls, parameters, artifacts)
- Python modules: All business logic
- pytest tests: Fast local feedback

**New AI-Powered Workflow Checklist**:

When creating a new AI-powered workflow with concurrency control:

1. Add workflow name to monitoring list in `.github/scripts/measure_workflow_coalescing.py` (`DEFAULT_WORKFLOWS`)
2. Document workflow in `.github/AGENTS.md`
3. Ensure concurrency group follows naming pattern: `{prefix}-${{ github.event.pull_request.number || inputs.pr_number }}`

---

## Commit Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST NOT mix multiple logical changes in one commit | code-style-conventions | commit-msg hook |
| SHOULD use one logical change per commit | code-style-conventions | commit-msg hook |
| SHOULD limit to max 5 files OR single topic | code-style-conventions | commit-msg hook |
| MUST use conventional commit format | code-style-conventions | commit-msg hook |

**Reference**: Use `mcp__serena__read_memory` with `memory_file_name="code-style-conventions"`

### PR Scope Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| SHOULD plan PRs for <=20 commits; validation may allow <=40 after a qualifying base merge | PR #908 retrospective, Issue #934, Issue #3596 | `git rev-list --count HEAD ^origin/main`; thresholds in `scripts/validation/pr_commit_count.py` |
| SHOULD limit PRs to <=10 changed files | PR #908 retrospective, Issue #934 | `git diff --stat origin/main` |
| SHOULD limit PRs to <=500 added lines | PR #908 retrospective, Issue #934 | `git diff --stat origin/main` |

**Rationale Summary**: PR #908 had 59 commits, making review slow and merge risky. Smaller PRs get faster reviews, fewer conflicts, and easier rollbacks.

**Remediation**: If limits are exceeded, squash related commits (`git rebase -i origin/main`) or split into multiple PRs.

**Format**:

```text
<type>(<scope>): <description>

<optional body>
```

**Types**: feat, fix, docs, refactor, test, chore, style

---

## Session Protocol Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST initialize Serena before any other action | AGENTS.md | Tool output in transcript |
| MUST read the latest per-issue handoff before starting work | AGENTS.md | Content in context |
| MUST preserve incomplete issue state | ADR-014 | Per-issue handoff |
| MUST validate a staged or supplied session log, if one is present | `.claude/rules/session-logs.md` | Validator output |
| MUST NOT create a new session log (creation discontinued) | `.claude/rules/session-logs.md` MUST 1 | No new `.agents/sessions/*.json` file |

**Reference**: [`.claude/rules/session-logs.md`](../../.claude/rules/session-logs.md)

**Rationale Summary**: Transcript, pull request, handoff, and Serena evidence
replace mandatory committed logs. Supplied logs remain validate-if-present.

---

## Security Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST pin GitHub Actions to commit SHA | security-practices | Pre-commit hook, workflow validation |
| MUST NOT use version tags (@v4, @v3, @v2) | security-practices | Pre-commit hook blocks |
| MUST include version comment for maintainability | security-practices | Code review |

**Reference**: [security-practices.md](../steering/security-practices.md#github-actions-security)

**Rationale Summary**: SHA pinning prevents supply chain attacks where action maintainers (or compromised accounts) move version tags to malicious commits. Immutable SHA references ensure reviewed code cannot be silently replaced.

**Pattern**:

```yaml
# Correct: SHA with version comment
uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2

# Incorrect: Version tag only
uses: actions/checkout@v4
```

**Exceptions**: None. All third-party actions must be SHA-pinned.

---

## YAML Frontmatter Constraints

| Constraint | Source | Verification |
|------------|--------|--------------|
| MUST use block-style arrays for tool fields in agent, prompt, and command frontmatter | ADR-040 Amendment, Session 826 RCA | Code review; generator output validation |
| MUST NOT use inline array syntax `['tool1', 'tool2']` for tool fields | ADR-040 Amendment, Session 826 RCA | Code review; generator output validation |
| MUST use hyphen-bulleted format for `tools`, `allowed-tools`, `tools_vscode`, `tools_copilot` arrays | ADR-040 Amendment, Session 826 RCA | Generator output validation |

**Rationale**: Inline array syntax fails on GitHub Copilot CLI with CRLF line endings due to stricter YAML parser. Block-style arrays work universally across VS Code, Copilot CLI (Windows/macOS/Linux), and Claude Code.

**Pattern**:

```yaml
# Correct: Block-style array
tools:
  - vscode
  - read
  - edit

allowed-tools:
  - Bash(git:*)
  - Read
  - Grep

tools_vscode:
  - vscode
  - read
  - search

# Incorrect: Inline array (fails on Copilot CLI + Windows CRLF)
tools: ['vscode', 'read', 'edit']
allowed-tools: [Bash(git:*), Read, Grep]
tools_vscode: ['vscode', 'read', 'search']
```

**Evidence**:
- GitHub Copilot CLI parser with CRLF line endings (see [github/copilot-cli#694](https://github.com/github/copilot-cli/issues/694) and [rjmurillo/ai-agents#893](https://github.com/rjmurillo/ai-agents/issues/893)): "failed to parse front matter: Unexpected scalar at node end"
- Session 826 Retrospective: 88 files converted, 32 tests passed, 0 failures, user validation confirmed
- ADR-040 Amendment (2026-01-13): Cross-platform compatibility analysis

**Exceptions**: Existing skill metadata arrays such as `metadata.domains`,
`metadata.inputs`, and `metadata.outputs` may remain inline. This constraint
targets tool-exposure fields that determine which tools the harness exposes.

---

## Validation Checklist

Use this checklist during session start:

- [ ] Read this document (PROJECT-CONSTRAINTS.md)
- [ ] For GitHub operations: Verify skill exists before writing code
- [ ] For new scripts: Verify Python (no .sh files per ADR-042)
- [ ] For workflow changes: Verify logic in modules, not YAML; actions are SHA-pinned, not version tags
- [ ] For workflow changes: Run `gh act` locally before pushing (MUST)
- [ ] For tool fields in frontmatter: Verify block-style arrays (not inline `['tool1', 'tool2']`)
- [ ] Before commit: Verify atomic commit rule (single logical change)

---

## Existing Violations (Grandfathered)

None currently documented. Add here if legacy code violates constraints but is accepted.

---

## Maintenance

| Attribute | Value |
|-----------|-------|
| Owner | Retrospective agent (quarterly review) |
| Update trigger | When ADRs added/amended, new preferences documented |
| Review cadence | Quarterly (align with agent consolidation review) |
| Validation | Link checker (all Source links valid) |

---

## Related Documents

- [`.claude/rules/session-logs.md`](../../.claude/rules/session-logs.md) - Session log mechanics
- [ADR-005-powershell-only-scripting.md](../architecture/ADR-005-powershell-only-scripting.md) - Language decision
- [ADR-006-thin-workflows-testable-modules.md](../architecture/ADR-006-thin-workflows-testable-modules.md) - Workflow architecture
- [Analysis 002 - Project Constraints Consolidation](../analysis/002-project-constraints-consolidation.md) - Background analysis
