# Chesterton's Fence: Deep Analysis

**Analysis Date**: 2026-01-03
**Analyst**: Claude Sonnet 4.5
**Sources**:
- [Farnam Street: Chesterton's Fence](https://fs.blog/chestertons-fence/)
- [Wikipedia: G.K. Chesterton - Chesterton's Fence](https://en.wikipedia.org/wiki/G._K._Chesterton#Chesterton's_fence)

---

## Executive Summary

Chesterton's Fence is a principle of epistemic humility stating: "Do not remove a fence until you know why it was put up." It requires understanding the original purpose and context of existing structures before changing them. The principle guards against the arrogance of assuming that if you don't understand why something exists, it must be useless.

**Key Insight**: The burden of proof lies with the reformer, not the status quo. You must demonstrate understanding before you earn the right to change.

**Application to ai-agents**: Enforce investigation phase before changes to existing code, protocols, ADRs, or constraints. Prevents preventable incidents like ADR-037 P0-3 (recursion guard missing) and skills-first violations.

---

## 1. Core Principle and Origin

### The Principle

> "In the matter of reforming things, as distinct from deforming them, there is one plain and simple principle; a principle which will probably be called a paradox. There exists in such a case a certain institution or law; let us say, for the sake of simplicity, a fence or gate erected across a road. The more modern type of reformer goes gaily up to it and says, 'I don't see the use of this; let us clear it away.' To which the more intelligent type of reformer will do well to answer: 'If you don't see the use of it, I certainly won't let you clear it away. Go away and think. Then, when you can come back and tell me that you do see the use of it, I may allow you to destroy it.'"
>
> — G.K. Chesterton, "The Thing" (1929)

### Origin Context

G.K. Chesterton (1874-1936) was an English writer, philosopher, and Christian apologist. The fence metaphor appeared in his 1929 essay collection "The Thing" in the context of political and social reform.

**Historical context**: Post-WWI era of rapid social change, where traditional institutions were being questioned and dismantled. Chesterton was responding to reformers who viewed all tradition as mere superstition to be swept away.

### Modern Reformulation

**Decision rule**: Before removing or changing an existing structure:
1. Understand why it exists
2. Understand what problem it solves
3. Understand what breaks if you remove it
4. Only then decide whether to remove/modify/preserve it

---

## 2. Philosophical Foundations

### 2.1 Epistemic Humility

**Definition**: Recognizing the limits of individual knowledge versus accumulated institutional knowledge.

**Core insight**: Just because YOU don't understand why something exists doesn't mean it's useless. It may mean:
- You lack historical context
- You haven't experienced the problem it solves
- You don't see the invisible work it's doing
- The knowledge wasn't documented (tacit knowledge)

**Practical application**: The default assumption should be "I don't understand this yet" rather than "this is stupid."

### 2.2 Lindy Effect

**Relationship**: The longer something has survived, the more likely it is to continue surviving (for non-perishable things like ideas, technologies, institutions).

**Implication**: A 50-year-old practice has proven its worth through survival. The burden of proof increases with age.

**Application to ai-agents**: Long-standing patterns (like PowerShell-only from ADR-005) have survived because they solve real problems. Changes require stronger justification than for new code.

### 2.3 Second-Order Thinking

**Definition**: Considering not just the direct effects of an action but the consequences of those consequences.

**Chesterton's Fence connection**:
- **First-order thinking**: "This fence blocks the road, remove it"
- **Second-order thinking**: "Why is the fence here? What happens downstream if I remove it?"

**Example from ai-agents**:
- **First-order**: "Skills-first is annoying, just use `gh` commands directly"
- **Second-order**: "Skills enable testing, version control, and consistent error handling. Removing this creates untestable code."

### 2.4 Via Negativa

**Definition**: Improving systems by removing harmful elements rather than adding beneficial ones.

**Relationship to Chesterton's Fence**: Via negativa says "subtraction is often better than addition," but Chesterton's Fence says "understand before you subtract."

**Synthesis**: Remove things, but only after understanding why they're there. Some fences prevent disasters rather than provide benefits.

---

## 3. Decision Framework (Four Phases)

### Phase 1: Investigation (BLOCKING)

**You MUST complete these steps before proceeding:**

1. **Document the fence's existence and current function**
   - What is it? (code, protocol, constraint, architecture)
   - Where is it? (file paths, ADR numbers, locations)
   - What does it do right now? (current behavior)

2. **Research its historical origin and original purpose**
   - When was it added? (git blame, commit date, PR)
   - Who added it? (author, their role, their context)
   - What was happening at the time? (related issues, PRs)

3. **Identify who erected it and what problem it solved**
   - What problem existed before the fence?
   - What was the intended solution?
   - Were alternatives considered? Why were they rejected?

4. **Map dependencies: what relies on this fence?**
   - What code references it? (grep, symbol search)
   - What processes assume it exists?
   - What implicit contracts does it enforce?

5. **Trace consequences: what happens if removed?**
   - What breaks immediately?
   - What breaks eventually?
   - What silent failures might occur?

**Deliverable**: Investigation report documenting all findings

**Gate**: Cannot proceed to Phase 2 without completed investigation

### Phase 2: Understanding (MUST complete before proceeding)

**Test your understanding:**

1. **Can you articulate the original rationale?**
   - Can you explain it to someone who wasn't there?
   - Can you steelman the argument for why it was built?

2. **Does the original problem still exist?**
   - Has the environment changed?
   - Has technology evolved to make the problem obsolete?
   - Are the constraints that led to this solution still present?

3. **Have conditions changed enough to invalidate the solution?**
   - Are there new tools that solve this better?
   - Has the scale changed (10x user growth, etc.)?
   - Have regulations changed?

4. **What unintended functions has it acquired over time?**
   - Does it prevent problems that weren't originally anticipated?
   - Have people built workflows around it?
   - Does it serve as documentation or a teaching tool?

**Verification**: Can you explain to the original author why they built it and have them agree?

### Phase 3: Evaluation (Only after Phases 1-2)

**Now you can make judgments:**

1. **Is the original problem better solved another way now?**
   - What's the alternative solution?
   - Is it actually better, or just newer?
   - What are the migration costs?

2. **Do costs of keeping the fence exceed its benefits?**
   - Maintenance burden vs. value provided
   - Complexity cost vs. safety provided
   - Developer friction vs. protection provided

3. **Can you mitigate removal risks?**
   - Can you add tests to catch what the fence prevented?
   - Can you monitor for the failure modes?
   - Do you have a rollback plan?

4. **What's the reversibility cost if you're wrong?**
   - Can you put it back if needed?
   - What's the blast radius of being wrong?
   - How long until you'd know you were wrong?

**Analysis**: Cost-benefit with uncertainty factored in

### Phase 4: Action (Conditional)

Based on your investigation, understanding, and evaluation:

**REMOVE** if:
- You fully understand the original rationale
- The original problem no longer exists OR
- You have a demonstrably better solution
- Risks are mitigated or acceptable
- Reversibility is low-cost

**MODIFY** if:
- Core function is still valid
- Implementation is suboptimal
- You can improve it without losing key properties
- Migration path is clear

**PRESERVE** if:
- Original problem still exists
- No better solution available
- Risks of change outweigh benefits
- You don't fully understand it yet (default to preserve)

**REPLACE** if:
- It's a poorly designed fence (solves real problem badly)
- You have a better solution
- You understand what it prevents
- You have a migration plan that preserves the protection

**DOCUMENT** (always):
- Why you made this decision
- What you learned from investigating
- What future reformers should know

---

## 4. Application to Software Engineering

### 4.1 Code

**Scenario**: Legacy code that seems unnecessarily complex

**Chesterton's Fence approach**:
1. Git blame to find when it was added
2. Find the PR/issue that introduced it
3. Read the discussion: what problem was being solved?
4. Check for edge cases in tests that rely on this complexity
5. Understand the problem space before refactoring

**Anti-pattern**: "This code is ugly, I'll rewrite it" → introduces bugs the original code prevented

**Example**: Thread-safe singleton with double-checked locking looks like over-engineering until you learn about the initialization race condition it prevents.

### 4.2 Architecture

**Scenario**: Monorepo vs. polyrepo decision

**Chesterton's Fence approach**:
1. If company uses monorepo, investigate why
2. Was it chosen to solve dependency hell? Build consistency? Code sharing?
3. What breaking changes has it prevented?
4. Before proposing polyrepo, understand the original problems

**Anti-pattern**: "Google uses monorepo so we should too" (or vice versa) without understanding your organization's specific constraints

### 4.3 Protocols and Processes

**Scenario**: Mandatory code review process

**Chesterton's Fence approach**:
1. Why was code review mandated? (quality issues, security breaches, knowledge silos?)
2. What incidents led to this rule?
3. What failure modes does it prevent?
4. Only then propose alternatives (like pair programming)

**Example from ai-agents**: Skills-first mandate exists because:
- Raw CLI usage created untestable code
- Inconsistent error handling across scripts
- Knowledge silos (each agent re-implementing same logic)
- Before removing, need to solve these problems another way

### 4.4 Constraints and Conventions

**Scenario**: Coding standard that seems arbitrary (like "no nested ternaries")

**Chesterton's Fence approach**:
1. Search code history for bugs caused by nested ternaries
2. Find the PR that added this rule
3. Understand readability problems it prevents
4. Only then propose relaxing it if you have better tooling (like auto-formatting)

**Example from ai-agents**: PowerShell-only constraint (ADR-005):
- Original problem: Bash/PowerShell duplication, Windows testing gaps
- Solving: Unified testing, single maintenance path
- Before adding .sh files, solve the original problem

---

## 5. Relationship to Other Principles

### 5.1 Second System Effect (Brooks' Law)

**Second System Effect**: When rebuilding a system, architects tend to over-engineer the replacement because they "learned" from the first system's "mistakes."

**Chesterton's Fence correction**: Before labeling first system features as "mistakes," understand why they exist. Some "warts" are actually scars from battle-tested edge cases.

**Example**: "The old API has weird error codes, let's use HTTP status codes in v2" → HTTP codes don't map to domain errors, creating new problems

### 5.2 YAGNI (You Aren't Gonna Need It)

**YAGNI**: Don't add functionality until it's needed.

**Relationship**: YAGNI says "don't add fences preemptively." Chesterton's Fence says "don't remove existing fences without understanding them."

**Synthesis**: Both fight complexity, but from opposite directions. YAGNI prevents speculative complexity. Chesterton prevents regrettable simplification.

### 5.3 Boy Scout Rule ("Leave it better than you found it")

**Boy Scout Rule**: Always leave code cleaner than you found it.

**Potential conflict**: Scout rule might encourage removing "ugly" code that's actually a necessary fence.

**Resolution**: Chesterton's Fence is a meta-rule: understand before improving. The Scout rule applies AFTER you understand why things are the way they are.

### 5.4 Hyrum's Law

**Hyrum's Law**: "With a sufficient number of users, every observable behavior of your system will be depended upon by somebody."

**Relationship**: Hyrum's Law explains WHY Chesterton's Fence matters in software. That "unused" API endpoint? Someone is using it. That weird behavior? Someone wrote code around it.

**Implication**: Even if you can't find why the fence was built, assume someone depends on it existing.

### 5.5 Defensive Programming

**Defensive Programming**: Add checks and guards against unexpected inputs.

**Relationship**: Defensive programming CREATES fences (validation, error handling). Chesterton's Fence says don't remove these guards without understanding what attacks they defend against.

**Example**: "This null check is redundant because the caller never passes null" → until the caller changes

---

## 6. Real-World Applications

### 6.1 Google's Monorepo

**The Fence**: Google uses a single monorepo for most of their code (billions of lines).

**Naive reformer**: "This is insane, split into separate repos!"

**Chesterton's investigation reveals**:
- Monorepo enables atomic cross-project refactoring
- Prevents diamond dependency problems
- Enforces consistent tooling/build system
- Enables large-scale static analysis
- Trades git performance for dependency management simplicity

**Lesson**: Before proposing polyrepo, understand what problems monorepo solves for Google's scale.

### 6.2 Unix "Everything is a file"

**The Fence**: Unix treats devices, sockets, pipes as file descriptors.

**Naive reformer**: "This is a leaky abstraction, give devices proper APIs!"

**Chesterton's investigation reveals**:
- Uniform interface enables powerful composition (pipes, redirection)
- Single set of permissions model
- Tools like `cat`, `grep`, `sed` work on everything
- Simplifies kernel interface

**Lesson**: The abstraction's "leakiness" is a feature, not a bug. Enables composability.

### 6.3 Null (Tony Hoare's "Billion Dollar Mistake")

**The Fence**: Most languages have null/nil references.

**Naive reformer**: "Null causes crashes, remove it!"

**Chesterton's investigation reveals**:
- Null represents "absence of value" - a real domain concept
- Alternative (Option types) requires different syntax, migration cost
- Null is efficient (single pointer value vs. tagged union)
- Existing code relies on null for control flow

**Nuanced decision**:
- New languages (Rust, Swift): use Option types from start (no fence to remove)
- Existing languages (Java, C#): add nullability annotations rather than remove null
- Migration cost matters

### 6.4 QWERTY Keyboard

**The Fence**: QWERTY layout, supposedly designed to SLOW typists (prevent typewriter jams).

**Naive reformer**: "Typewriters are gone, switch to Dvorak (faster layout)!"

**Chesterton's investigation reveals**:
- Network effects: everyone knows QWERTY
- Retraining cost is massive
- Speed difference is smaller than advocates claim
- Touch typing technique matters more than layout
- Switching cost exceeds benefits for most users

**Lesson**: Sometimes the fence is "everyone is used to this" and that's a valid reason.

---

## 7. Common Failure Modes

### 7.1 "I don't understand it, so it must be stupid"

**Failure**: Assuming complexity is unnecessary rather than investigating its purpose.

**Example**: Junior developer removes "redundant" validation → production incident

**Prevention**: Default to "I don't understand this YET" rather than "this is bad."

### 7.2 "Old = Bad, New = Good" (Chronological Snobbery)

**Failure**: Assuming newer technologies/patterns are better simply because they're newer.

**Example**: "Let's rewrite in microservices" without understanding why the monolith exists

**Prevention**: Evaluate on merits, not age. Old systems survived for reasons.

### 7.3 "This was a mistake" (Hindsight Bias)

**Failure**: Judging past decisions with present knowledge, ignoring constraints they faced.

**Example**: "They should have used Kubernetes from the start" → Kubernetes didn't exist then

**Prevention**: Understand historical context. What tools/knowledge were available then?

### 7.4 "I can fix this in 2 weeks" (Optimism Bias)

**Failure**: Underestimating complexity of replacement, overestimating quality of solution.

**Example**: "I'll rewrite this spaghetti code" → 6 months later, still not done, new bugs

**Prevention**: The fence survived because it works. Replacement must match that durability.

### 7.5 "The original author was an idiot"

**Failure**: Attributing bad design to incompetence rather than investigating constraints.

**Example**: "Why did they use XML instead of JSON?" → JSON spec didn't exist when they started

**Prevention**: Assume competence. If it looks stupid, you're missing context.

### 7.6 "Nobody uses this anymore"

**Failure**: Removing "unused" features that are actually used in rare but critical scenarios.

**Example**: Deprecating API endpoint → breaks customer's disaster recovery script

**Prevention**: Hyrum's Law. If it's observable, someone depends on it.

### 7.7 "Let's just try it and see"

**Failure**: A/B testing fence removal without understanding what it prevents.

**Example**: Removing rate limiting in experiment → DDoS yourself

**Prevention**: Some fences prevent catastrophic failures, not gradual degradation.

---

## 8. Limitations and Critiques

### 8.1 "This leads to paralysis"

**Critique**: If you can't remove anything without perfect understanding, nothing ever changes.

**Response**: Chesterton's Fence sets the bar at "understand," not "perfect knowledge." It's about investigation, not paralysis.

**Practical resolution**:
- Time-box investigation (1 day, 1 week)
- Severity matters: higher risk changes need deeper understanding
- Can proceed with uncertainty IF you have monitoring and rollback

### 8.2 "Some fences ARE stupid"

**Critique**: Sometimes things exist due to politics, cargo-culting, or actual incompetence.

**Response**: True, but you need to DEMONSTRATE that through investigation. Saying "it's stupid" without investigation is exactly what Chesterton's Fence prevents.

**Example**:
- Bad: "This code is stupid" (opinion)
- Good: "This code was added in PR #123 to work around bug #456, but that bug was fixed in #789, so this code is now dead" (evidence)

### 8.3 "Not all changes are removals"

**Critique**: Chesterton's Fence is about removing fences, but most changes are additions or modifications.

**Response**: The principle generalizes to "understand the system before changing it."
- Additions: what implicit fences are you breaking?
- Modifications: what original design choices are you invalidating?

### 8.4 "Historical knowledge is lost"

**Critique**: In practice, the original author is gone, documentation is missing, and you CAN'T know why.

**Response**: This is why documentation matters. But even without it:
- Git history preserves some context
- Behavior testing preserves what it does (even if not why)
- Community knowledge (Stack Overflow, issue trackers)

**Practical approach**: Investigate what you can, document what you learn, proceed with caution when knowledge is missing.

### 8.5 "This privileges status quo"

**Critique**: Putting burden of proof on reformer makes change harder, which favors those who benefit from status quo.

**Response**: Yes, deliberately. Chesterton's argument is that unreflective change is MORE harmful than excessive caution.

**Counter-argument**: When status quo is actively harmful (not just unclear), different rules apply. Chesterton's Fence assumes the fence isn't actively on fire.

---

## 9. Application to ai-agents Project

### 9.1 Existing "Fences" in the Project

| Fence | Location | Original Purpose | Still Valid? |
|-------|----------|------------------|--------------|
| **PowerShell-only** | ADR-005 | Bash/PS duplication, Windows testing gaps | YES - Windows support still required |
| **Skills-first mandate** | usage-mandatory | Testability, consistency, reuse | YES - prevents untestable inline code |
| **BLOCKING gates** | SESSION-PROTOCOL | <50% compliance with trust-based guidance | YES - achieves 100% compliance |
| **Memory-first** | ADR-007 | Context loss, repeated mistakes | YES - enables learning from history |
| **Atomic commits** | code-style-conventions | Easier rollback, clearer history | YES - enables git bisect |
| **Branch verification** | git-004 | Cross-PR contamination (PR #669) | YES - 100% prevention when enforced |
| **No logic in YAML** | ADR-006 | Untestable workflows | YES - enables Pester testing |
| **Session logs** | ADR-014 | HANDOFF.md 80% merge conflict rate | YES - distributed > centralized |

### 9.2 Past Incidents Prevented by Chesterton's Fence

**Incident 1: ADR-037 P0-3 (Recursion Guard)**
- **What happened**: Git hook sync strategy lacked recursion guard
- **Why it happened**: No one asked "why don't existing git hooks call git commands?"
- **How Chesterton's Fence would have helped**: Investigation phase would have revealed recursion risk pattern
- **Lesson**: If a pattern is consistently absent (hooks NOT calling git), investigate why before breaking it

**Incident 2: Skills-first violations**
- **What happened**: Repeated use of raw `gh` commands despite skills existing
- **Why it happened**: Didn't understand why skills exist (testability, consistency)
- **How Chesterton's Fence would have helped**: Required investigation of "why do skills exist?" before bypassing them
- **Lesson**: Convenience without understanding leads to protocol violations

**Incident 3: Session protocol drift**
- **What happened**: Proposals to change session protocol without understanding constraints
- **Why it happened**: Didn't research why BLOCKING gates exist vs. guidance
- **How Chesterton's Fence would have helped**: Investigation would show <50% compliance before BLOCKING gates, 100% after
- **Lesson**: "Annoying" constraints often exist because gentler approaches failed

### 9.3 When to Apply Chesterton's Fence in ai-agents

**ALWAYS require investigation for**:
1. **Removing ADR constraints** (PowerShell-only, thin workflows, etc.)
2. **Bypassing protocols** (skills-first, BLOCKING gates, memory-first)
3. **Deleting >100 lines of code** (likely has battle-tested edge cases)
4. **Changing session protocol** (likely has history of why it evolved this way)
5. **Removing validation/error handling** (probably prevents specific failure modes)

**SOMETIMES require investigation for**:
1. **Refactoring complex code** (understand edge cases it handles)
2. **Changing workflow structure** (understand why it's organized this way)
3. **Modifying agent prompts** (understand what behaviors they enforce)

**RARELY need investigation for**:
1. **Adding new features** (not removing fences)
2. **Fixing obvious bugs** (unless "bug" is actually undocumented feature)
3. **Documentation improvements** (low risk)

---

## 10. Decision Matrix

Use this matrix to decide investigation depth:

| Change Type | Risk Level | Investigation Required |
|-------------|------------|------------------------|
| **Remove ADR constraint** | CRITICAL | Full 4-phase investigation + ADR amendment |
| **Bypass protocol (skills-first, BLOCKING gates)** | HIGH | Phase 1-2 investigation, written justification |
| **Delete >100 lines** | HIGH | Git blame, PR search, dependency analysis |
| **Modify core protocol** | HIGH | Historical research, incident review |
| **Refactor complex code** | MEDIUM | Understand edge cases, check test coverage |
| **Change workflow** | MEDIUM | Review git history, understand constraints |
| **Add validation** | LOW | Minimal (understand what you're validating) |
| **Documentation** | LOW | None (but verify accuracy) |
| **Fix obvious bug** | LOW | None (unless "bug" might be feature) |

**Risk factors that escalate investigation requirement**:
- Age of code (>6 months = higher risk)
- Absence of tests (less safety net)
- Critical path (failure affects core functionality)
- Security-sensitive (failure creates vulnerabilities)
- Public API (external dependencies)

---

## 11. Implementation Checklist

When you encounter a "fence" you want to change:

### Phase 1: Investigation (BLOCKING)
- [ ] **Document what exists**: What is the fence? Where is it? What does it do?
- [ ] **Git archaeology**: When was it added? (git blame, git log)
- [ ] **Find the PR/commit**: What was the context? (gh pr list, gh issue list)
- [ ] **Read the rationale**: What problem did it solve? (PR description, commit message)
- [ ] **Search for related issues**: What bugs/incidents led to this? (gh issue search)
- [ ] **Map dependencies**: What relies on this? (grep, symbol search)
- [ ] **Identify failure modes**: What breaks if removed? (tests, documentation)

### Phase 2: Understanding (MUST complete)
- [ ] **Can you articulate original rationale?**: Explain to original author
- [ ] **Original problem still exists?**: Has environment changed?
- [ ] **Conditions changed?**: New tools, scale, regulations?
- [ ] **Unintended functions?**: What else does it do now?

### Phase 3: Evaluation (Only after 1-2)
- [ ] **Better solution exists?**: What is it? Is it actually better?
- [ ] **Cost-benefit analysis**: Maintenance burden vs. value
- [ ] **Risk mitigation**: How do you prevent the original problem?
- [ ] **Reversibility**: Can you undo if wrong? At what cost?

### Phase 4: Decision
- [ ] **Choose action**: Remove, Modify, Preserve, Replace
- [ ] **Document decision**: Write rationale for future reformers
- [ ] **Create migration plan** (if removing/replacing)
- [ ] **Add monitoring** (if risk exists)
- [ ] **Update documentation**

### Phase 5: Validation (After change)
- [ ] **Did the problem return?**: Monitor for original failure mode
- [ ] **Unexpected breakage?**: What did we miss in investigation?
- [ ] **Document learnings**: What did we learn? What would we do differently?

---

## 12. References

### Primary Sources
- Chesterton, G.K. (1929). "The Thing"
- [Farnam Street: Chesterton's Fence](https://fs.blog/chestertons-fence/)
- [Wikipedia: G.K. Chesterton - Chesterton's Fence](https://en.wikipedia.org/wiki/G._K._Chesterton#Chesterton's_fence)

### Related Principles
- Second-order thinking (Farnam Street Mental Models)
- Lindy Effect (Nassim Taleb)
- Hyrum's Law (Hyrum Wright, Google)
- Brooks' Law / Second System Effect (The Mythical Man-Month)
- YAGNI (Extreme Programming)

### Application Examples
- [Chesterton's Fence: A Lesson in Second Order Thinking](https://fs.blog/chestertons-fence/)
- [Why you should understand a fence before removing it](https://abovethelaw.com/2014/01/the-fallacy-of-chestertons-fence/)

---

## 13. Conclusion

Chesterton's Fence is fundamentally about **epistemic humility** and **second-order thinking**. It recognizes that:

1. **Individual knowledge is limited** compared to institutional knowledge
2. **Complexity often has reasons** that aren't immediately obvious
3. **Change carries risk** that must be weighed against benefits
4. **Understanding must precede judgment**

For the ai-agents project, this means:
- **Investigate before changing** existing ADRs, protocols, constraints
- **Assume competence** of original authors until proven otherwise
- **Document rationale** to help future reformers
- **Enforce investigation** through BLOCKING gates (like memory-first)

The principle doesn't prevent change. It ensures change is **informed, deliberate, and reversible** rather than **impulsive, ignorant, and catastrophic**.

**Final heuristic**: If you're about to remove a fence and you can't explain to the original builder why they put it there, you're not ready to remove it yet.

---

**Related Work**:
- Issue #748: Incorporate Chesterton's Fence into agent workflow
- ADR-007: Memory-First Architecture (similar investigation-before-action pattern)
- SESSION-PROTOCOL.md: BLOCKING gates pattern (enforcement model)
