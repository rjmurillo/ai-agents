# QA Skills

**Extracted**: 2025-12-16
**Source**: `.agents/qa/` directory

## Skill-QA-001: Test Strategy Gap Checklist (90%)

**Statement**: Verify test plans include cross-platform, negative, edge, error, and performance tests

**Context**: Test strategy review and QA planning

**Evidence**: Agent consolidation test strategy review identified missing categories

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Checklist**:

- [ ] Cross-platform consistency tests
- [ ] Negative tests (invalid inputs, error conditions)
- [ ] Edge cases (boundary values, empty/null)
- [ ] Error handling tests (exception paths)
- [ ] Performance tests (if applicable)

**Detection**: Test plan missing these categories
**Fix**: Add missing test categories before implementation

**Source**: `.agents/qa/001-agent-consolidation-test-strategy-review.md`

---

## Skill-QA-002: QA Agent Routing Decision (85%)

**Statement**: Route to qa agent after implementing features unless tests are comprehensive and passing

**Context**: After feature implementation, before commit

**Trigger**: Feature code complete

**Evidence**: Serena transformation (2025-12-17): Manual testing skipped qa agent workflow. Pattern observed in prior sessions where agents short-circuited workflow without clear criteria.

**Atomicity**: 85%

**Impact**: 7/10

**Tag**: helpful

**Created**: 2025-12-17

**Updated**: 2025-12-20

**Status**: SUPERSEDED by Skill-QA-003 (strengthens SHOULD → MUST with BLOCKING gate)

**Validated**: 2 (Serena transformation, PR #60 violation)

**Definition of "Comprehensive"**:

- Coverage >80%
- Multiple test cases per function
- Edge cases included
- Negative tests present
- Error handling verified

**When to Skip QA Agent** (exceptions to workflow):

- Tests are comprehensive (per definition above)
- All tests passing
- Change is trivial (docs, comments, formatting)

**When QA Agent is MANDATORY**:

- New features
- Complex logic
- Cross-platform concerns
- Security-sensitive code
- Breaking changes

---

## Skill-QA-003: QA Routing BLOCKING Gate (90%)

**Statement**: Add BLOCKING gate to SESSION-PROTOCOL.md: MUST route to qa after feature implementation before commit

**Context**: After feature implementation, before git commit

**Evidence**: PR #60 skipped qa (Skill-QA-002 violation), vulnerability not caught until PR #211

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-20

**Pattern**:

```markdown
## Phase X: QA Validation (BLOCKING)

You MUST route to qa agent after feature implementation:

Task(subagent_type="qa", prompt="Validate [feature]")

**Verification**: QA report exists in `.agents/qa/`

**If skipped**: Untested code may contain bugs or vulnerabilities
```

**Anti-Pattern**: Skipping qa because "tests look good" (subjective)

**Source**: `.agents/retrospective/2025-12-20-pr-211-security-miss.md`

**Note**: This supersedes Skill-QA-002 by strengthening SHOULD → MUST

---

## Skill-QA-004: Prompt Files Require QA Validation (95%)

**Statement**: Files in `.github/prompts/` drive AI workflows and require QA validation like production code

**Context**: When assessing QA requirements for docs-only sessions or markdown-heavy PRs

**Evidence**: PR #143 - `.github/prompts/` changes are NOT just documentation, they control automated AI behavior and must be validated

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 8/10

**Created**: 2025-12-22

**Validated**: 1 (PR #143)

**File Type Classification**:

| Path Pattern | Type | QA Required | Rationale |
|--------------|------|-------------|-----------|
| `**/*.md` (general) | Documentation | ❌ No | Content only, no execution |
| `.github/prompts/**/*.md` | AI Configuration | ✅ YES | Controls automated behavior |
| `.github/prompts/**/*.yaml` | AI Metadata | ✅ YES | Structured AI inputs |
| `.github/workflows/**/*.yml` | CI/CD Code | ✅ YES | Executable automation |

**Why Prompt Files Are Code**:

1. **Behavioral Control**: Define how AI agents operate
2. **Execution Context**: Consumed by automation (not humans)
3. **Breaking Changes**: Invalid prompts = failed workflows
4. **Integration Testing**: Require validation like APIs

**QA Requirements for Prompt Files**:

- [ ] Syntax validation (YAML/Markdown lint)
- [ ] Schema compliance (if applicable)
- [ ] Integration test (does workflow consume correctly?)
- [ ] Regression test (existing workflows still work?)
- [ ] Documentation (explain prompt purpose/usage)

**Source**: PR #143 review, `.agents/skills/pr143-session-validation-merge-commits.md`

---

## Related Documents

- Source: `.agents/qa/001-agent-consolidation-test-strategy-review.md`
- Source: `.agents/retrospective/2025-12-17-serena-transformation-implementation.md`
- Source: `.agents/skills/pr143-session-validation-merge-commits.md`
- Related: skills-validation (validation quality patterns)
- Related: skills-implementation (test discovery workflow)
