---
description: Working with legacy code rules from Michael Feathers' Working Effectively with Legacy Code. Apply when modifying code with low test coverage, files older than six months, or any path on a To Improve fix cycle. Add tests around the change before changing behavior.
alwaysApply: false
---

# Working With Legacy Code

This rule encodes Michael Feathers' techniques from _Working Effectively with Legacy Code_. Feathers defines legacy code as any code without tests, regardless of age or quality. In ai-agents, the same risk applies to code that has tests but already failed once: a previous worker tried to change it and broke something. Treat both classes the same way.

The point of these techniques is not to refactor for its own sake. The point is to make a specific change safely. Add only the structure you need to land your change. Resist the urge to clean the whole module while you are there.

## When To Apply This Rule

Activate the techniques in this rule when any of the following holds for the file you are about to change.

- The file has low test coverage. There are no characterization tests, or coverage is below the project floor for the area you are touching.
- The file is older than six months and has not been substantively edited in that time. Behavior has solidified through use; an unguarded change is more likely to surprise a downstream caller than a recent file would be.
- The change is part of a To Improve fix cycle. A previous worker (junior or medior, in the auto-escalation ladder) attempted this change and the attempt failed or regressed. The escalated worker MUST add tests around the surface area before reproducing or extending the prior attempt.
- The class or function is hard to instantiate in a test (large constructor graph, hidden singletons, file or network access in the constructor).
- The function is long, deeply nested, or branches on flags you do not control.

If none of these holds, you are working in well-tested code. Use the normal code-quality rule and skip the techniques below.

## Core Vocabulary

Use these terms consistently in PR descriptions and review comments.

- **Characterization test**: a test that pins down what the code does today, not what it should do. You write it to lock current behavior so that an unintended change shows up as a test failure.
- **Seam**: a place where you can alter behavior in your program without editing in that place. Common seams in this codebase are constructor parameters, function parameters, and module-level injection points.
- **Enabling point**: the location where you decide which behavior the seam selects. For a parameter seam, the enabling point is the call site.
- **Sprout method or sprout class**: new behavior added in a new method or new class, called from a single new line in the legacy code. The legacy code is barely touched.
- **Wrap method or wrap class**: a new method or class that calls the existing one and adds behavior before or after. The original is renamed; the new method takes the old name.
- **Dependency-breaking technique**: a small refactor whose only purpose is to make the existing code testable. Examples: extract interface, parameterize constructor, introduce instance delegator.

If you cannot point to the seam, the enabling point, and the characterization tests in your PR description, you have not applied the rule yet.

## Step Order: Tests Before Edits

This is the rule that protects the change. Run these steps in order. Do not skip steps to save time. The order is the safety.

1. Identify the smallest unit of behavior you need to change.
2. Find a seam that lets you call that unit from a test. If no seam exists, apply a dependency-breaking technique to create one.
3. Write characterization tests that pin the current behavior at the seam. Tests pass on unchanged code, by definition.
4. Make the change.
5. Update only the assertions that should change. Every other assertion still passes; if it fails, you broke something unrelated and you need to know now.
6. If a characterization test fails after your change, do not delete it and do not weaken it. Investigate the failure. Either revert, or update the assertion with a comment that explains the deliberate behavior change.

The most common failure mode is reversing steps three and four. An agent confident in the change writes the new behavior first, runs the tests, and rationalizes the failures. The result is undocumented behavior drift. Do not do this.

## Characterization Tests

Use a characterization test when you need to lock in current behavior before you change it.

Apply when:

- You are about to edit a function with no direct tests.
- You are about to touch a path that a previous worker already broke once.
- You are not sure what the function actually does in the corner cases.

Rules:

- Test what the code does, not what the docstring says it does. Run the function with realistic inputs and write the actual output as the assertion.
- Cover the inputs that route through each branch. You do not need full path coverage; you need every branch you might step on while making the change.
- Use real collaborators where you can. Use fakes only where the real collaborator does I/O or is non-deterministic.
- Name the tests after the observed behavior, not after the code structure. `returns_empty_list_when_session_has_no_messages` is better than `test_get_messages_branch_3`.
- A characterization test that surprises you is the most valuable kind. The surprise is the bug or the contract you did not know about. Document it in the test name and in the PR.

Smell: a characterization test that asserts the code is correct. You do not yet know it is correct. Assert what it does, then have the conversation about whether that is right.

## Seams

Use seams to change behavior without editing the place where the behavior is observed.

Common seam types in this codebase:

- **Object seam**: pass a different collaborator into the constructor or the function. Preferred when the collaborator is already injected or easy to inject.
- **Link or import seam**: replace a module-level dependency at test time (for example, a `requests` client, or a filesystem helper). Use sparingly; broad mocking hides design problems.
- **Preprocessor or build seam**: build-time substitution. Almost never the right answer at this layer; raise a flag in review if you find yourself reaching for it.

Rules:

- Pick the seam closest to the behavior you need to change. The closer the seam, the smaller the test setup and the smaller the risk that you also change unrelated behavior.
- Make the enabling point obvious. A reader should see at the call site that test code passes one collaborator and production code passes another.
- Do not introduce a seam that only the test uses, then leave production code unchanged. Either production passes through the seam too, or you have written a test against a fake of the production object.

Smell: a seam that requires monkey-patching a private attribute. Promote the dependency to a constructor parameter or a function parameter instead.

## Sprout Method And Sprout Class

Use sprout when you need to add new behavior to a function that is hard to test in place.

Apply when:

- The new behavior is conceptually distinct from the surrounding function.
- The surrounding function lacks tests, and writing them would take significantly longer than the change itself.
- You can call the new code from a single new line in the legacy function.

Rules:

- Write the new method or new class with full test coverage. Tests live with the new code, not the old.
- The single new call site in the legacy code is the only legacy edit. Keep it to one line where you can.
- Name the sprout after what it does, not after where it lives. `compute_retry_delay` is better than `legacy_helper_two`.
- Sprout class instead of sprout method when the new behavior already needs more than one method, or when it needs its own state.

Smell: a sprout that grows. The first sprout is one line; the second sprout to the same legacy function is a sign you need to extract a collaborator and inject it through a seam.

## Wrap Method And Wrap Class

Use wrap when you need to add behavior before or after the legacy function on every call.

Apply when:

- The added behavior is cross-cutting (logging, metrics, retries) and applies to all callers.
- You cannot edit every caller, or the cost of editing every caller exceeds the cost of wrapping.
- The legacy function has a clear input and output you can pass through unchanged.

Rules:

- Rename the legacy function (`do_thing` becomes `do_thing_internal` or `_do_thing`). Introduce a new function under the original name that calls the renamed one and adds the new behavior.
- The wrap must not change the original return shape unless that is the explicit point of the change. Wrapping a function and silently returning a different type breaks every caller in a way that is hard to grep for.
- Test the wrap separately. Test the renamed inner function separately. Each layer is now a unit.
- If you find yourself wrapping a wrap, stop. The behavior belongs in a single explicit collaborator that the entry point composes; introduce one.

Smell: a wrap that has its own branching logic deciding whether to call the inner function. That is a strategy, not a wrap. Make it explicit.

## Dependency-Breaking Techniques

These techniques exist to make legacy code testable. Pick the smallest one that gets you to a passing characterization test.

- **Extract interface**: pull the methods you actually use into an interface or a `Protocol`. Have the legacy class implement it. Now your tests can pass a fake that implements the same interface.
- **Parameterize constructor**: a class news up its own collaborator inside the constructor. Move the construction out to a parameter with a sensible default. Tests pass a fake; production passes the default.
- **Introduce instance delegator**: a static or module-level function makes testing hard because you cannot replace it. Add an instance method that calls the static, and have the legacy code call the instance method. Tests subclass and override the instance method.
- **Subclass and override**: when the class is too big to refactor today, subclass it in tests and override only the methods that block your test. Use this as a stepping stone, not a destination.
- **Pull up dependency**: move the construction of an awkward collaborator one level up the call chain so that the level you care about can take it as a parameter.

Rules:

- These refactors are behavior-preserving. Run the existing tests, including any characterization tests you just wrote, before and after each one. Both runs must agree.
- Land each technique as its own commit when you can. Reviewers can read the safety case for each step.
- Do not stack five of these in one PR. If you need that many to make the change, the underlying class needs a redesign and that is a separate conversation.

Smell: a dependency-breaking refactor that also changes the behavior you came to change. Split the commit. Refactor first, change second.

## Never Delete Failing Tests To Make A Refactor Pass

This is a hard rule. The presence of a failing test is information. Deleting the test deletes the information.

- If a test fails because the code is wrong, fix the code.
- If a test fails because the test is wrong (the assertion encoded a misunderstanding), fix the test and explain the change in the commit message. The reviewer must be able to see what the test used to assert and why the new assertion is correct.
- If a test fails because the behavior intentionally changed, update the assertion and explain the deliberate change in the commit message. Reference the issue or the design decision.
- If you cannot tell which of the three above applies, you are not yet ready to land the change. Stop and investigate.

Tests deleted to make CI green will be reviewed as a regression. The escalation ladder for To Improve cycles depends on the previous attempt's tests being intact. Removing those tests removes the safety net that makes the next attempt cheaper.

## Boundaries With Existing Codebase

ai-agents has working seams and rules already in place. Reuse them.

- **Sessions, hooks, skills**: these are entry points and they should stay thin. When you need to change behavior they orchestrate, change the underlying service or repository, not the entry point. The entry point is a sprout site, not a place to grow business logic.
- **Memory and orchestrator**: the memory systems and the agent orchestrator are repositories and service layers in the sense of `enterprise-patterns.md`. Apply the techniques here at the seams those rules already define.
- **Pre-commit and CI**: lint, type checks, and unit tests are the floor. Characterization tests for legacy code go alongside the regular tests under `tests/`. They are not optional.
- **Auto-escalation ladder**: when an issue lands on you because a junior or medior worker already tried, your first commit is characterization tests around the failure surface. The second commit is the change. Skipping the first commit forfeits the safety the ladder is designed to provide.

When the codebase already has the seam you need, use it. Do not introduce a parallel injection point. If the existing seam is in the wrong place, raise that in the PR description rather than route around it silently.

## Quick Self-Review

Before opening a PR that touches legacy code (low coverage, old file, or a To Improve cycle), walk this list.

- Did you write characterization tests before you changed behavior?
- Can you point to the seam, the enabling point, and the test that uses it?
- Is your change isolated through a sprout or a wrap, or did you edit deep into the legacy function?
- If you applied a dependency-breaking technique, is the refactor in its own commit, with the existing test suite passing on both sides?
- Did you keep every failing test? If you removed one, did you explain why in the commit?
- Could a future worker on a To Improve cycle for this same file rerun your tests and trust the result?

If any answer is "no" or "not sure," fix the change before review.
