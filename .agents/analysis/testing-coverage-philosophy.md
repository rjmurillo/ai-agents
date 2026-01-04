# Testing Coverage Philosophy: Evidence Over Metrics

**Date**: 2026-01-03
**Context**: Evaluating testing approaches for PowerShell/Pester in ai-agents project
**Sources**: [Dan North](https://dannorth.net/blog/we-need-to-talk-about-testing/), [Rico Mariani](https://ricomariani.medium.com/100-unit-testing-now-its-ante-f0e2384ffedf), [industry research](https://about.codecov.io/blog/the-case-against-100-code-coverage/)

---

## Executive Summary

The pursuit of 100% code coverage as a quality metric creates perverse incentives and wastes engineering effort. Instead, testing should focus on **increasing stakeholder confidence through evidence**, as Dan North argues. Rico Mariani positions 100% unit test coverage as merely "ante" (the baseline), not the end goal. Industry research shows diminishing returns beyond 80% coverage, with the final 20% requiring disproportionate effort for minimal gain.

**Key Takeaways:**

1. **Testing is about evidence, not metrics**: Coverage percentages measure code execution, not quality, security, or stakeholder confidence
2. **80% is the pragmatic target**: Google's guidelines (60% acceptable, 75% commendable, 90% exemplary) align with diminishing returns analysis
3. **Quality over quantity**: 80% coverage with thoughtful tests beats 95% with brittle, low-value tests
4. **Unit tests alone are insufficient**: Even 100% unit coverage doesn't eliminate integration bugs, security issues, or missing requirements

**Application to ai-agents**: Current practice (Session 68: 69.72% coverage with comprehensive critical path testing) aligns with industry best practices. Maintain focus on **testable modules (ADR-006)**, **critical path coverage**, and **realistic scenarios** over chasing metrics.

---

## Core Concepts

### Dan North: Evidence-Based Testing

Dan North reframes testing with precision:

> "The purpose of testing is to **increase confidence** for **stakeholders** through **evidence**."

> "You are testing **if and only if** you are increasing confidence for stakeholders through evidence."

**Unpacking the definition:**

- **Stakeholders**: "Anyone who is affected, directly or indirectly, through the work we do" — developers, users, compliance officers, security teams, operations
- **Confidence**: "Understanding the things that the stakeholder cares about, and how the work we are doing—or are about to embark on—might impact those things"
- **Evidence**: "Incontrovertible information or data" — not opinions, assumptions, or coverage percentages

**Implications:**

1. **Test theater doesn't count**: Running tests that don't produce evidence (e.g., testing getters/setters, trivial code) wastes time
2. **Different stakeholders need different evidence**: Security stakeholders care about threat models, not line coverage
3. **Manual testing is legitimate**: If hands-on exploration increases confidence through evidence, it's testing

North's critique of test-driven development:

> "TDD, BDD, ATDD, and related methods categorically do not replace testing, whatever their names may suggest."

TDD is a **design technique** that helps write testable code. The tests produced are **programmer-facing unit tests** that verify implementation details, not stakeholder-facing evidence of system behavior.

> "A programmer's confidence in their own code is a notoriously poor indicator of quality."

This challenges the assumption that comprehensive unit tests (written by the same person who wrote the code) provide adequate testing. Developers have blind spots about their own work.

### Rico Mariani: 100% Unit Testing Is "Ante"

Rico Mariani, a Microsoft performance architect, makes a **provocative argument**: 100% block coverage is the **minimum** (ante), and the "diminishing returns" argument is "flatly wrong."

> "In 2024, 100% unit-test coverage is only ante" — meaning it's just the entry requirement, not the end goal.

> "100% unit-test coverage is absolutely positively not enough to get you to the finish line. You will need a lot of other kinds of things to round out the picture."

**What "ante" means:**

In poker, the ante is the minimum bet required to participate. You can't win with just the ante — you need strategy, skill, and additional bets. Similarly:

- **100% unit coverage** = baseline for "acceptance testing" (good enough to accept for real testing)
- **Real testing** = integration tests, end-to-end tests, performance tests, security tests, compliance testing, observability

Mariani's pragmatism:

> "At my core I am a pragmatist, I do things because they work, not because they look nice on paper."

**Why Mariani Rejects the "Diminishing Returns" Argument:**

> "That unit-testing inherently suffers from diminishing returns is just flatly wrong."

**Two key rebuttals:**

1. **Tests don't get harder**: "If you have (e.g.) 1000 tests the 1001st test is not inherently harder to write than the 1000th was, that never happens. If anything, it's typically easier to write the n+1st test. This is because tests tend to use all the same infrastructure to get their job done."

2. **Bugs found at all coverage levels**: "Tests encountering new untested code are just as likely to find bugs in that code whether it was the first 1% or the last 1%. This is borne out in my experience all the time. Down to a few blocks to test I'm thinking 'well this is a waste but ok I'll do it because hygiene' and then I look at the code thinking about how to test it and I see it's wrong. This happens all the time."

**The Security and Privacy Argument:**

Mariani's strongest case for 100% coverage comes from **security and privacy concerns**:

> "Attackers do not care if the code they are attacking is on a rare path. In fact, they probably prefer that it is on a rare path because such code less likely to be tested or fixed. ALL the paths need to be run under ASAN or whatever other tools you are using to help shake out problems because attackers will force the weakest code to run."

> "A data leak on a path so rare that only 0.1% of your customers see it is still a catastrophe. For a large company 0.1% might still be half a million people."

**Value of Tests Even Without Assertions:**

> "As a thought experiment, suppose the tests merely execute the flows and otherwise verify nothing. Even then (and I don't recommend this) you still get tons of value. Those same tests can be run under ASAN, LEAKSAN, TSAN, UBSAN, all the SANS! That means, with no extra effort, if you (e.g.) leak a connection, even if the test validation doesn't notice the leak, your test infra will."

**Three Outcomes Mariani Targets:**

1. **Everything runs in a test at least once to enable sanitizers**
2. **Error cases get exercised, however rare** (because attackers will force them to run)
3. **It's super easy to spot the code that still needs tests** (100% is clear; 98% requires "oh but not that stuff" mental overhead)

### Synthesis: Two Opposing Views

**The Tension:**

- **Rico Mariani (Microsoft)**: 100% block coverage is the minimum; diminishing returns is "flatly wrong"
- **Industry Consensus (Google, Martin Fowler, etc.)**: 80% is optimal; chasing 100% has diminishing returns

**How both can be correct:**

1. **Context matters**: Rico worked on **Messenger and Microsoft Edge** (massive scale, security-critical, privacy-sensitive). Industry guidelines are for **typical software** (not under constant attack, smaller user base).

2. **Coverage type matters**: Rico specifies **block coverage** (control flow), not line coverage. Block coverage catches bugs in rare branches; line coverage can be gamed.

3. **Infrastructure matters**: Rico assumes **sanitizers (ASAN, LEAKSAN, TSAN, UBSAN)** are available. Without sanitizers, tests only find what they assert. With sanitizers, tests find memory leaks, data races, undefined behavior even without explicit assertions.

4. **Risk profile matters**:
   - **High-security/privacy systems** (Messenger, Edge): 100% is minimum because attackers exploit rare paths
   - **Internal tools, scripts, non-critical systems**: 60-80% is pragmatic

**Resolution for ai-agents:**

**CRITICAL**: ai-agents **IS** under attack threat:
- **Prompt injection**: Attackers will manipulate AI behavior
- **Secret disclosure**: Attackers will attempt credential extraction
- **Ability abuse**: File system access, git operations, GitHub API are exploitable
- **Open source exposure**: Prompts, tools, guardrails are public (attack surface visible)

**Revised risk profile**: High-security system (adversarial environment) WITHOUT sanitizer infrastructure.

Therefore:

- **Apply Rico's 100% principle** to ALL security-sensitive code:
  - Secret handling (API keys, tokens, credentials)
  - Input validation (user prompts, file paths, git commands)
  - Authorization checks (GitHub operations, file system access)
  - Command execution (bash, PowerShell, git)
  - Path sanitization (prevent directory traversal)
- **Apply industry consensus (60-80%)** ONLY to:
  - Non-sensitive utilities (markdown formatting, text parsing)
  - Read-only analysis code (grep, search)
  - Documentation generation
- **Focus on Dan North's evidence** for all testing: Security stakeholder confidence is paramount

### Industry Consensus: Diminishing Returns

Multiple sources (outside high-security contexts) confirm the **80% coverage sweet spot**:

**Google's Coverage Guidelines:**

- **60%**: Acceptable
- **75%**: Commendable
- **90%**: Exemplary

**Diminishing Returns Analysis:**

> "Reaching from 80% to 100% coverage means a lot of work, usually requiring complex, difficult-to-maintain tests to test all edge cases and unusual flows."

> "The closer you are to 100%, the less valuable the return of work will be."

> "Getting from 80-90% coverage to 100% typically needs intricate, hard-to-maintain tests."

**Why the last 20% is expensive:**

1. **Unreachable code**: Defensive checks for "impossible" states
2. **Logging and diagnostics**: Verbose output statements with low bug risk
3. **Error branches**: Edge cases that require complex mocking
4. **Platform-specific code**: Conditional logic for different OS/versions that's hard to test comprehensively

**Quality over coverage:**

> "You can have all lines covered by tests, but if those tests are not high-quality, they will not uncover bugs."

> "High coverage numbers are too easy to reach with low quality testing."

> "It's better to have fewer well-written tests than more tests with poor quality."

---

## Frameworks and Models

### Evidence-Based Testing Framework (Dan North)

**Three-Part Test:**

1. **Does this work increase confidence** for at least one stakeholder?
2. **Is that confidence based on evidence** (data, reproducible results)?
3. **Is the confidence gain worth the effort**?

If any answer is "no," you're not testing — you're doing test theater.

**Application Protocol:**

```text
BEFORE writing a test:
│
├─ Identify stakeholder: Who benefits from this evidence?
├─ Define confidence gain: What will they know after this test?
├─ Specify evidence type: What data does this produce?
└─ Assess effort/value: Is this the best way to gain this confidence?
    │
    └─ If yes → Write test
        If no → Find better testing approach or skip
```

### Coverage Tiers Model (Industry Consensus + Session 68)

| Coverage % | Focus | Typical Uncovered Code | Effort Multiplier |
|------------|-------|------------------------|-------------------|
| **60-70%** | Happy paths, core logic | Error handling, logging, edge cases | 1x (baseline) |
| **70-80%** | Core + major error paths | Verbose logging, rare edge cases | 2x |
| **80-90%** | Core + comprehensive errors | Defensive code, impossible states | 4x |
| **90-100%** | Everything | Often requires brittle/artificial tests | 8x+ |

**Interpretation:**

- **60-70%**: Appropriate for scripts, utilities, configuration code
- **70-80%**: Standard for business logic modules
- **80-90%**: Critical paths, security-sensitive code, financial calculations
- **90-100%**: Rarely justified; pursue only for highest-risk code with regulatory requirements

### Priority-Based Testing Model

**Tier 1: Must Have 100% Coverage**

- Critical business logic (data transformation, calculations, core algorithms)
- Security-sensitive code (input validation, path sanitization, auth/authz)
- Edge cases with known issues (boundary values, empty collections, null/undefined)
- Regulatory compliance code (financial, healthcare, data privacy)
- Public APIs with strong contracts

**Tier 2: Target 80%+ Coverage**

- Error handling for realistic scenarios (invalid input, missing files, network failures)
- Integration points with external systems
- Configuration and setup logic
- Common user workflows

**Tier 3: Accept 60-70% Coverage**

- Verbose logging statements (low risk, high effort to test)
- Diagnostic utilities
- Wrappers around well-tested libraries
- Platform-specific workarounds

**Tier 4: Skip Testing**

- Impossible error states (can't happen in practice)
- Defensive null checks when nulls are guaranteed impossible
- Dead code branches (delete instead of testing)
- Trivial getters/setters with no logic

---

## Applications

### Example 1: Session 68 — Generate-Skills.Tests.ps1

**Context**: PowerShell script testing in ai-agents project
**Application**: Pragmatic coverage targeting critical paths
**Outcome**: 69.72% coverage, high quality

**Details:**

- **Target**: 100% code coverage (initial goal)
- **Achieved**: 69.72% with 60 passing tests
- **Covered**: All critical paths (YAML parsing, section extraction, frontmatter generation)
- **Uncovered**: Verbose logging, minor edge cases, some error branches
- **Result**: High-quality, maintainable test suite despite not reaching 100%

**Functions with 100% coverage:**

- `Normalize-Newlines`: Core transformation logic with multiple input scenarios
- Critical YAML parsing functions
- Section extraction logic

**Functions with ~0% coverage:**

- `Write-Log`: Only called with `-VerboseLog` parameter, low risk (just Write-Host wrapper)
- Platform-specific fallback code

**Lesson**: 70% coverage with thoughtful tests covering all critical paths provides more confidence than 95% coverage achieved by testing logging statements and impossible states.

### Example 2: Google's Coverage Guidelines in Practice

**Context**: Large-scale software development at Google
**Application**: Tiered coverage expectations
**Outcome**: Balanced quality/effort trade-off

**60% (Acceptable):**

- New experimental features
- Internal tools with limited users
- Prototype code

**75% (Commendable):**

- Production services
- Libraries with multiple consumers
- Business-critical workflows

**90% (Exemplary):**

- Payment processing
- Security-critical systems
- Data transformation pipelines
- Public APIs

**Insight**: Even at Google scale, 90% is "exemplary," not baseline. This reflects understanding that diminishing returns make 100% wasteful.

### Example 3: Testable Modules Pattern (ADR-006)

**Context**: ai-agents architecture — thin workflows, testable modules
**Application**: Extract logic from untestable YAML workflows into .psm1 modules
**Outcome**: Fast local testing, high coverage of business logic

**Pattern:**

```text
GitHub Actions Workflow (YAML)
│
├─ Orchestration only (<100 lines)
├─ Calls PowerShell module
│
PowerShell Module (.psm1)
│
├─ Business logic (100+ lines)
├─ Testable with Pester
│
Pester Tests (.Tests.ps1)
│
├─ 80%+ coverage target
├─ Fast local feedback (seconds, not minutes)
```

**Why this works:**

1. **Untestable YAML problem**: GitHub Actions workflows can't be tested locally (edit → push → wait 1-5 min)
2. **Testable module solution**: Logic in .psm1 enables fast Pester tests (run in seconds)
3. **Coverage where it matters**: Business logic in modules gets 80%+ coverage; thin YAML orchestration doesn't need testing

**Lesson**: Architecture decisions (ADR-006) enable high-value testing by making code testable, rather than chasing coverage metrics on untestable code.

---

## Failure Modes

### Anti-Pattern 1: Coverage Theater

**Description**: Writing tests solely to increase coverage percentage, not to gain confidence

**Example:**

```powershell
# Anti-pattern: Testing trivial code for metrics
It "should return input string unchanged" {
    $result = Get-ConfigValue -Key "SomeKey"
    $result | Should -Be "SomeValue"
}

# This test:
# - Increases coverage by 2%
# - Provides zero new confidence
# - Tests a simple property access
# - Will pass as long as config exists
```

**Why it fails**: The test doesn't prevent bugs, detect regressions, or provide stakeholder evidence. It's box-checking.

**Root cause**: Using coverage percentage as a target instead of a byproduct of good testing

**Correction**: Ask "Does this test increase confidence through evidence?" If no, delete it.

### Anti-Pattern 2: Brittle Mocks for Edge Cases

**Description**: Complex, fragile test setup to cover unreachable code branches

**Example:**

```powershell
# Anti-pattern: Mocking impossible scenarios
It "should handle file system returning null for directory that exists" {
    Mock Test-Path { $true }
    Mock Get-ChildItem { $null }  # Impossible: directory exists but returns null

    $result = Get-DirectoryFiles -Path "C:\Exists"
    $result | Should -BeNullOrEmpty
}
```

**Why it fails**:

- **Impossible state**: Directory exists (Test-Path = true) but Get-ChildItem returns null (can't happen)
- **Brittle**: Requires maintaining complex mocking logic
- **Low value**: Tests code that will never execute in production
- **False confidence**: Makes coverage report look good while testing nothing real

**Root cause**: Chasing 100% coverage without evaluating whether the uncovered code is reachable

**Correction**: Delete unreachable defensive code, or accept that some branches won't be covered

### Anti-Pattern 3: Unit Tests as Only Testing

**Description**: Believing 100% unit test coverage means "done testing"

**Example:**

Project achieves 100% unit test coverage with mocked dependencies, but:

- Integration fails when real database returns unexpected schema
- Performance degrades under load (unit tests run with tiny datasets)
- Security vulnerability exists in authentication flow (tested in isolation, not end-to-end)
- UI breaks because API contract changed (both sides tested separately)

**Why it fails**:

> "100% unit test coverage does not mean we had good tests or even that the tests are complete, and doesn't say anything about missing code, missing error handling, or missing requirements."

Dan North:

> "TDD, BDD, ATDD, and related methods categorically do not replace testing, whatever their names may suggest."

**Root cause**: Confusing unit testing (design technique) with comprehensive testing (evidence gathering)

**Correction**: 100% unit coverage is "ante" — add integration tests, end-to-end tests, performance tests, security tests

### Anti-Pattern 4: Test Quality Ignored for Quantity

**Description**: Adding low-quality tests to reach coverage targets

**Example:**

```powershell
# Low-quality test: doesn't verify behavior
It "should not throw" {
    { Invoke-ComplexLogic -Input $data } | Should -Not -Throw
}

# Low-quality test: tests mocks, not code
It "should call dependency" {
    Mock Get-Data { "mock" }
    Invoke-Workflow
    Assert-MockCalled Get-Data -Exactly 1
}
```

**Why it fails**:

- **First test**: Passes as long as no exception is thrown, doesn't verify output correctness
- **Second test**: Verifies mock was called, not that the code does the right thing with the data

> "You can have all lines covered by tests, but if those tests are not high-quality, they will not uncover bugs."

**Root cause**: Coverage percentage incentivizes quantity over quality

**Correction**: Measure test quality through mutation testing, review for assertions that verify behavior (not just execution)

---

## Relationships

### Connection to ADR-006: Thin Workflows, Testable Modules

**How they relate**:

ADR-006 solves the **testability problem** by architectural decision:

- **Problem**: GitHub Actions workflows can't be tested locally → slow feedback, low coverage
- **Solution**: Extract logic to PowerShell .psm1 modules → fast Pester testing, high coverage of logic

**Coverage philosophy complements ADR-006**:

- **Thin workflows** (<100 lines of YAML orchestration): Accept 0% coverage — can't test YAML locally
- **Testable modules** (.psm1 business logic): Target 80% coverage with thoughtful tests
- **Result**: High coverage where it matters, zero waste testing untestable YAML

**Synergy**:

```text
ADR-006 (Architecture)          Coverage Philosophy (Testing)
        │                                   │
        ├─ Makes code testable              ├─ Focuses tests on value
        ├─ Separates orchestration/logic    ├─ Accepts gaps in low-value code
        └─ Enables fast feedback  ──────────┴─ Prioritizes critical paths
                    │
                    └─ Combined: High-quality testing at optimal effort
```

### Connection to Existing Memory: testing-004-coverage-pragmatism

**Similarity**: Both advocate 60-80% coverage sweet spot

**ai-agents experience**:

- Session 68: 69.72% coverage with comprehensive critical path testing
- Uncovered: Verbose logging, impossible states, defensive checks
- Result: High confidence despite missing 30% coverage

**Dan North/Rico Mariani add**:

- **Philosophical foundation**: Why pragmatism works (evidence > metrics)
- **Stakeholder focus**: Coverage doesn't measure confidence
- **"Ante" concept**: 100% unit coverage is baseline, not end goal

**Integration**:

Existing testing-004-coverage-pragmatism memory documents **what** (60-80% is fine, prioritize critical paths). This research adds **why** (philosophical justification from Dan North, industry evidence, Rico's "ante" framing).

**Enhanced guidance**:

| Existing Memory | New Research |
|-----------------|--------------|
| "70% coverage is often fine" | **Why**: Diminishing returns, quality > quantity |
| "Prioritize critical paths" | **Why**: Evidence-based testing targets stakeholder confidence |
| "Session 68: 69.72% was high quality" | **Context**: Aligns with Google (60-75%), Dan North (evidence), Rico (ante) |

---

## Applicability to ai-agents Project

### Risk Profile Analysis (CRITICAL REVISION)

**Initial Assessment WAS WRONG**: ai-agents is NOT a low-risk internal tool.

**Actual Risk Profile**: **HIGH-SECURITY** (adversarial environment)

**Attack Vectors**:
1. **Prompt injection**: Attackers manipulate AI behavior to bypass guardrails
2. **Secret disclosure**: Attempts to extract API keys, tokens, credentials
3. **Ability abuse**: Exploit file system access, git operations, GitHub API
4. **Open source exposure**: All prompts, tools, guardrails are public (attack surface fully visible)

**Security Stakeholders**:
- Users trusting the AI with repository access
- Organizations whose secrets are in environment variables
- GitHub API (rate limits, unauthorized operations)
- File system integrity

**Implication**: ai-agents aligns with **Rico Mariani's high-security context** (Messenger/Edge), not typical internal tools.

**Revised Coverage Targets**:

| Code Category | Coverage Target | Rationale |
|---------------|----------------|-----------|
| **Security-critical (100%)** | Secret handling, input validation, command execution, path sanitization, auth checks | Attackers exploit rare paths; open source = visible attack surface |
| **Business logic (80%)** | Text parsing, workflow orchestration, non-sensitive utilities | Standard quality bar |
| **Read-only/docs (60-70%)** | Documentation generation, read-only analysis | Low attack surface |

**Key Change**: Most ai-agents code is security-critical because it operates with GitHub credentials, file system access, and handles untrusted user prompts.

### Integration Points

#### Agent System

**Which agents benefit**:

- **qa agent**: Should evaluate tests using evidence-based criteria, not just coverage metrics
- **implementer agent**: Should write tests during implementation (test-first per testing-002), but not chase 100%
- **critic agent**: Should validate that testing approach provides stakeholder confidence

**How to apply**:

Update agent prompts to reference testing philosophy:

- qa agent: "Evaluate whether tests increase stakeholder confidence through evidence, not just coverage percentage"
- implementer agent: "Target 80% coverage with thoughtful tests; accept gaps in logging/impossible states"

#### Protocols

**Session protocol enhancement**:

Currently session protocol doesn't enforce testing quality gates. Could add:

```markdown
### Testing Quality Checklist (if code changes)

- [ ] Critical paths have tests (100% coverage)
- [ ] Realistic error scenarios tested (80%+)
- [ ] Tests verify behavior, not just execution
- [ ] Coverage gaps are in low-value code (logging, impossible states)
```

**Handoff protocol**:

When handing off to qa agent, document:

- What stakeholder confidence does this testing provide?
- What evidence do tests produce?
- Why is current coverage level sufficient?

#### Memory and Knowledge Management

**Serena memory update**:

- Update testing-004-coverage-pragmatism with philosophical foundations
- Add references to Dan North, Rico Mariani, industry research
- Document "ante" concept for future reference

**Forgetful memory creation**:

- Create atomic memories for key concepts (evidence-based testing, diminishing returns, priority tiers)
- Link to existing testing strategy memories
- Enable semantic search for "why not 100% coverage"

#### Constraint and Governance

**Should coverage targets become a project constraint?**

No. Existing approach (pragmatic, case-by-case) is correct.

**Rationale**:

- ADR-006 already enables testability (thin workflows, modules)
- testing-004-coverage-pragmatism documents 60-80% guideline
- Flexibility needed: security code (100%), scripts (60%), libraries (80%)

**What to add**:

Document **anti-patterns** in .agents/governance/:

- ❌ Chasing 100% coverage universally
- ❌ Using coverage as primary quality metric
- ❌ Writing tests solely to increase percentage
- ✅ Prioritizing critical paths
- ✅ Evidence-based testing (stakeholder confidence)
- ✅ Quality over quantity

#### Skills and Automation

**Skill enhancement: Pester testing skills**

Current skills (skills-pester-testing-index) could be enhanced:

- Add test quality evaluation (not just coverage reporting)
- Suggest gaps in critical path coverage (actionable insights)
- Flag brittle tests (complex mocking, testing mocks not behavior)

**Could this be encoded in a skill?**

Yes — a **test-quality-reviewer** skill:

**Purpose**: Evaluate Pester tests for evidence-based quality

**Workflow**:

1. Analyze test files (.Tests.ps1)
2. Identify coverage gaps in critical paths (red flag)
3. Identify high coverage in low-value code (yellow flag)
4. Assess test quality:
   - Do tests verify behavior or just execution?
   - Are mocks realistic or brittle?
   - Do assertions provide evidence?
5. Provide actionable recommendations

---

### Proposed Applications

#### 1. Update qa Agent Prompt with Evidence-Based Criteria

**What**: Add testing philosophy to qa agent's evaluation framework

**Where**: `.agents/AGENT-SYSTEM.md` (qa agent section)

**Why**: Prevents qa agent from requesting 100% coverage or flagging gaps in low-value code

**Effort**: Small (add 2-3 paragraphs to agent prompt)

**Change**:

```markdown
## Testing Evaluation (qa agent)

Evaluate tests using evidence-based criteria:

- **Do tests increase stakeholder confidence?** (not just pass/fail)
- **What evidence do tests produce?** (behavior verification, regression prevention)
- **Is coverage appropriate for code risk level?** (100% for critical paths, 60-80% for scripts)

**Red flags**:
- Critical business logic without tests
- Security-sensitive code with gaps
- Tests that verify mocks, not behavior

**Not red flags**:
- 70% coverage with all critical paths tested
- Uncovered logging statements
- Missing tests for impossible error states
```

#### 2. Enhance testing-004-coverage-pragmatism Memory

**What**: Add philosophical foundations from Dan North, Rico Mariani

**Where**: `.serena/memories/testing-004-coverage-pragmatism.md`

**Why**: Existing memory documents "what" (70% is fine); add "why" (evidence, diminishing returns)

**Effort**: Small (append 100-200 words)

**Addition**:

```markdown
## Philosophical Foundation

**Dan North**: "Testing increases stakeholder confidence through evidence, not coverage percentages."

**Rico Mariani**: "100% unit coverage is ante (baseline), not the end goal."

**Industry**: Diminishing returns beyond 80%; Google guideline is 60% acceptable, 75% commendable, 90% exemplary.

**Implication**: ai-agents Session 68 (69.72% coverage) aligns with best practices when critical paths are fully tested.
```

#### 3. Document Testing Anti-Patterns in Governance

**What**: Create `.agents/governance/TESTING-ANTI-PATTERNS.md`

**Where**: New governance document

**Why**: Explicit guidance prevents coverage theater and brittle tests

**Effort**: Medium (1-2 hour to write, integrate into workflows)

**Content**:

```markdown
# Testing Anti-Patterns

## Anti-Pattern 1: Coverage Theater
**Description**: Writing tests solely to increase coverage percentage
**Detection**: Tests that don't verify behavior, just execute code
**Correction**: Delete tests that don't provide evidence

## Anti-Pattern 2: Chasing 100% Universally
**Description**: Requiring 100% coverage for all code
**Detection**: Complex mocks for impossible states, tested logging
**Correction**: Use tiered targets (100% critical, 80% standard, 60% scripts)

## Anti-Pattern 3: Test Quality Ignored
**Description**: Accepting low-quality tests if coverage is high
**Detection**: Tests verify mocks, not behavior; no meaningful assertions
**Correction**: Review tests for evidence (do they prevent bugs?)
```

---

### Priority Assessment

**High Priority**:

1. **Update qa agent prompt** (Small effort, immediate impact on test quality)
2. **Enhance testing-004-coverage-pragmatism** (Small effort, improves memory quality)

**Medium Priority**:

3. **Document anti-patterns in governance** (Medium effort, prevents future mistakes)
4. **Add testing philosophy to session protocol checklist** (Medium effort, enforces quality gates)

**Low Priority**:

5. **Create test-quality-reviewer skill** (Large effort, nice-to-have automation)

---

## References

- [Dan North: We need to talk about testing](https://dannorth.net/blog/we-need-to-talk-about-testing/)
- [Rico Mariani: 100% Unit Testing — Now It's Ante](https://ricomariani.medium.com/100-unit-testing-now-its-ante-f0e2384ffedf)
- [Codecov: The Case Against 100% Code Coverage](https://about.codecov.io/blog/the-case-against-100-code-coverage/)
- [Testim: Code Coverage: Why 100% Isn't the Holy Grail](https://www.testim.io/blog/code-coverage-why-100-isnt-the-holy-grail/)
- [Martin Fowler: Test Coverage](https://martinfowler.com/bliki/TestCoverage.html)
- [StickyMinds: 100 Percent Unit Test Coverage Is Not Enough](https://www.stickyminds.com/article/100-percent-unit-test-coverage-not-enough)

---

**Word count**: ~4,850 words
