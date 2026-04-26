# Refactoring

This rule encodes the discipline from Martin Fowler's _Refactoring_. Use it when you change the structure of code without changing what it observably does, and when reviewers need to tell whether a change is a refactoring, a feature, or a bug fix in disguise.

Refactoring is a means to an end. It exists so the next change is easier to make. If a refactoring does not make a concrete next step easier, do not do it on this branch.

## Definitions

Use these terms precisely. Mixing them is the source of most review confusion.

- **Refactoring**: a change to the internal structure of code that does not change its observable behavior. Same inputs, same outputs, same side effects.
- **Behavior change**: a change that any caller, test, or downstream system could detect. New feature, bug fix, API change, performance change visible to a caller.
- **Code smell**: a surface symptom in the code that suggests a deeper structural problem. Smells are hints, not verdicts.
- **Transformation**: one named, mechanical step (Extract Function, Inline Variable, Move Method). Each step has a known shape and a known safety check.
- **Characterization test**: a test written to capture what the code currently does, before you change anything, so you can detect any drift.

## Core Discipline

These rules are non-negotiable. Reviewers should reject changes that violate them.

1. **Refactoring preserves observable behavior.** If your change alters what callers see, it is not a refactoring. Stop, split the work, and re-classify.
2. **Never refactor and add behavior in the same commit.** Two hats: the refactoring hat and the feature hat. Wear one at a time. If you find yourself wanting to "just also fix" something, stash it and come back to it on a separate commit.
3. **Tests must pass between every step.** "Between" is literal: each transformation lands with a green build before the next one starts. If you cannot run tests cheaply, that is a precondition you fix first, not a reason to skip the rule.
4. **Small, named, mechanical steps.** Each step should map to a refactoring with a known name (Extract Function, Replace Conditional with Polymorphism). If you cannot name what you are doing, you are improvising; slow down.
5. **No big-bang rewrites disguised as refactoring.** Replacing a module wholesale is not refactoring, it is a rewrite. Treat it as a feature with a migration plan, not as a structural cleanup.
6. **If you have no tests, write characterization tests first.** Refactoring without tests is editing in the dark. The first transformation on legacy code is almost always "add a test that pins current behavior."

## When to Refactor

Refactor in service of a concrete next step. Do not refactor on speculation.

Apply when:

- **Rule of Three**: you are about to write the third near-duplicate of the same logic. Two duplicates is a coincidence; three is structure asking to emerge.
- **Preparatory refactoring**: the next change you have to make is hard. Reshape the code so the change becomes obvious, then make the change. "Make the change easy, then make the easy change."
- **Comprehension refactoring**: you just figured out what a confusing piece of code does. Encode that understanding in names and structure before you forget.
- **Litter-pickup**: you are already editing a file and notice a small, local mess. Fix it, but only if the fix is minutes, not hours, and it stays in the same diff scope.
- **Planned refactoring**: an explicit ticket for a known structural problem, time-boxed and reviewed on its own.

Do not refactor when:

- You have no concrete next change in mind. "It might be useful later" is YAGNI.
- The code is about to be deleted or replaced.
- You are on a hot path and cannot run the relevant tests.
- The branch is already large or risky; add the refactoring as a follow-up.

## Code Smells

Smells are hints to investigate, not commands to refactor. Each smell suggests one or more transformations; pick the one that addresses the actual problem, not the textbook answer.

- **Long Function**: a function that no longer fits one screen and one idea. Suggests Extract Function. Be aggressive: a six-line function with a clear name beats a forty-line function whose body you have to scan.
- **Long Parameter List**: more than three or four parameters, especially when several are always passed together. Suggests Introduce Parameter Object or Preserve Whole Object.
- **Large Class**: a class doing several jobs. Suggests Extract Class along the seams between jobs. Look at field clusters and method clusters as evidence.
- **Duplicated Code**: the same expression in two places. The same idea in two shapes is also duplication; do not let cosmetic differences fool you. Suggests Extract Function, Pull Up Method, or Form Template Method.
- **Divergent Change**: one module changes for many unrelated reasons. Suggests Extract Class to split by reason for change.
- **Shotgun Surgery**: one change requires edits in many places. The inverse of Divergent Change. Suggests Move Method or Inline to gather the change in one place.
- **Feature Envy**: a method that uses another object's data more than its own. Suggests Move Method to where the data lives.
- **Data Clumps**: the same group of fields or parameters appearing together. They want to be an object. Suggests Extract Class or Introduce Parameter Object.
- **Primitive Obsession**: strings, ints, and dicts standing in for domain concepts. Suggests Replace Primitive with Object, especially at boundaries where validation should live.
- **Switch Statements**: repeated `switch`/`if` chains over a type code. Suggests Replace Conditional with Polymorphism, or a table-driven dispatch when polymorphism would be overkill.
- **Repeated Conditionals**: the same boolean expression appearing in many places. Suggests Extract Function with an intention-revealing name.
- **Mysterious Name**: a name you have to read the body to understand. Suggests Rename. Renames are cheap and almost always undervalued.
- **Comments**: a comment explaining what the code does usually marks code that wants to be a function with that name. Suggests Extract Function and Rename, then delete the comment.
- **Dead Code**: code no caller reaches. Delete it. Version control remembers if you need it back.
- **Speculative Generality**: hooks, abstract classes, and parameters added for "future flexibility" that no caller exercises. Inline the indirection until a real second case appears.
- **Temporary Field**: a field set only in some branches and ignored in others. Suggests Extract Class to hold the optional state, or rework the control flow so the field is always meaningful.
- **Message Chains**: `a.getB().getC().getD()`. Violates Law of Demeter. Suggests Hide Delegate or, if the chain is load-bearing, accept the coupling and document it.

## The Mechanics

Each refactoring is a recipe with steps and safety checks. Follow them.

- **Make the smallest change that compiles and tests.** Then commit (or at least snapshot). Then make the next.
- **Run tests after every step.** "Step" is finer-grained than "commit." If a step breaks tests, undo just that step rather than puzzling through a broken intermediate state.
- **Prefer automated refactorings when your tooling supports them.** A tool-driven Rename or Extract is safer than a manual one because the tool knows about every call site.
- **When manual, use the compiler as a checklist.** Break the type signature deliberately so the compiler points you at every site that needs updating; only then fix them.
- **Avoid mixing in cleanup.** When you spot another smell mid-refactoring, write it down and finish the current transformation first.

## Refactoring And Performance

Performance and refactoring trade in opposite directions some of the time. Do not let speculative performance fears block structural cleanup.

- Write code for clarity first. Most code is not on a hot path.
- Measure before you optimize. A profile beats an opinion.
- When you do optimize, isolate the optimization. Keep the optimized region small and well named so the rest of the code stays clean.
- A clean structure is easier to optimize than a tangled one. Refactor first, then optimize the bottleneck.

## Refactoring In Pull Requests

These rules tighten the general discipline for the way changes land in this repository.

- **One hat per commit.** Do not mix refactoring commits with feature commits. Reviewers should be able to tell at a glance which is which.
- **Refactoring commits are pure restructure.** No new conditionals, no new error handling, no new logging. If you find yourself adding any of these, you are wearing the wrong hat.
- **Behavior commits ride on top of clean structure.** Land the preparatory refactoring first (or in an earlier commit on the same branch), then add the feature in a focused commit.
- **Each refactoring step counts toward the per-PR commit budget.** ADR-008 caps commits per PR. Plan your refactoring so the necessary steps fit, or split the work across PRs along a clean seam.
- **Conventional commit prefixes encode the hat.** Use `refactor:` for pure structural changes, `feat:`/`fix:` for behavior changes. Reviewers should be able to filter by prefix and find no surprises.
- **PR description names the refactorings used.** "Extract Function on `Foo.handle`, Move Method `bar` from `A` to `B`." Named steps are reviewable; unnamed structural changes are not.

## Anti-Patterns

These shapes appear under the label "refactoring" but break the discipline. Reject them in review.

- **Drive-by refactoring inside a feature PR.** A `feat:` PR that also reshapes ten unrelated files. Split it: refactor first on its own branch, then add the feature.
- **"While I was in there" cleanups.** Single-line stylistic changes scattered across many files. Each one is harmless; the aggregate is unreviewable. Save them for a dedicated cleanup PR or use a formatter run.
- **Renaming during a behavior change.** Rename and behavior change at the same time. Reviewers cannot tell which lines moved and which lines do something new. Rename in a separate commit.
- **Refactoring without tests on legacy code.** Changing the shape of code that has no characterization tests, then claiming "I did not change behavior." You do not know that. Add the tests first.
- **Pattern-driven restructuring with no concrete benefit.** Inserting a Strategy or Factory because "the patterns book says so," not because two implementations exist. Inline the indirection until the second case arrives.
- **Big-bang rewrite labeled as refactoring.** Replacing a module wholesale and calling it a refactoring. Reclassify as a rewrite, with migration and rollout, not as a structural cleanup.
- **Refactoring that breaks the build, deferred to a later commit.** Each step must leave the tree green. "I will fix the tests in the next commit" is not refactoring; it is debt.

## Boundaries With Existing Codebase

ai-agents has conventions that interact with this rule. Honor them.

- **ADR-008 commit budget**: refactoring steps count. Plan accordingly. If a refactoring needs more steps than your budget allows, split along a seam and land each half on its own PR.
- **Atomic commits (no more than five files)**: each refactoring step is a separate commit and stays within the file budget. If a transformation cannot fit, pick a smaller transformation.
- **Conventional commits**: `refactor(<scope>):` for pure structure, `feat(<scope>):` and `fix(<scope>):` for behavior. Do not relabel a `feat` as a `refactor` to dodge review.
- **Session protocol**: refactoring sessions still produce a session log with evidence. The evidence for a refactoring is "tests passed before, tests passed after, no behavior change."
- **Existing rules**: this rule sits alongside `enterprise-patterns.md`. When a refactoring moves code across the Repository, Service Layer, or Data Mapper boundary, follow that rule for the target shape and this rule for the mechanics.

## Quick Self-Review

Before you label a change as a refactoring, walk this list.

- Can a caller, test, or downstream system observe any difference? If yes, this is not a refactoring.
- Did tests pass at every intermediate step, not just at the end?
- Can you name the transformation you used? Extract Function, Move Method, Replace Conditional with Polymorphism?
- Is the diff free of new conditionals, new error handling, and new logging?
- Is the commit prefix `refactor:`, and does it describe the structural change rather than the motivation?
- Is there a concrete next change that this refactoring makes easier? If not, why are you doing it on this branch?
- If the code had no tests when you started, did you add characterization tests before reshaping it?

If any answer is "no" or "not sure," fix the change before review.
