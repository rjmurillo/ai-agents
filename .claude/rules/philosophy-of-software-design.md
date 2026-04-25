---
description: Ousterhout's heuristics from "A Philosophy of Software Design". Apply when shaping module boundaries, designing tool or plugin interfaces, naming things, or deciding how much complexity to expose. Prefer deep modules with simple interfaces and hidden internals over shallow wrappers.
alwaysApply: false
---

# Philosophy of Software Design

This rule encodes the design heuristics from John Ousterhout's _A Philosophy of Software Design_ that fit ai-agents best. Use it when you create a new agent capability, tool, skill, plugin seam, or any module whose interface other code depends on.

The single sharpest lens is the deep-vs-shallow module test. Most other rules in this file follow from it. When you cannot decide between two designs, pick the one that hides more complexity behind a smaller interface.

## Core Vocabulary

Use these terms consistently in code, comments, and PR descriptions.

- **Complexity**: anything that makes a system hard to understand or modify. It is what slows you down, not what looks ugly.
- **Module**: any unit with an interface and an implementation. A class, a function, a script, a skill, an agent prompt, a plugin.
- **Interface**: everything a caller must know to use the module. Includes signatures, side effects, error modes, ordering constraints, performance characteristics.
- **Deep module**: rich functionality behind a small, simple interface. High value per unit of interface surface.
- **Shallow module**: small functionality behind an interface nearly as large as the implementation. Low value, high cost to use.
- **Information hiding**: a module keeps a design decision inside itself, so callers do not see it and do not become coupled to it.
- **Information leakage**: the same decision shows up in two or more places, so changing it requires changing all of them.
- **Cognitive load**: how much a reader must hold in their head to use or change the module correctly.
- **Strategic programming**: investing in design now to make future change cheaper. Opposite of tactical, where each change is the smallest local fix.

## Symptoms of Complexity

Three symptoms tell you a design is wrong, even before you can name why. Use them in code review and self-review.

- **Change amplification**: a single conceptual change forces edits in many places. Look for the duplicated decision and hide it in one module.
- **Cognitive load**: a reader must learn many unrelated facts before they can safely change anything. Reduce it by hiding details, naming clearly, and shrinking the interface.
- **Unknown unknowns**: a reader cannot tell, from the interface alone, what they have to know to use it correctly. The most dangerous symptom. Fix by surfacing the constraint in the interface or eliminating it entirely.

If you cannot point to which of these three a refactor reduces, the refactor is not paying for itself.

## Deep Modules

A module is deep when its interface is much smaller than what it does inside.

Apply when:

- You design a tool, agent, skill, or plugin entry point.
- You wrap an external system, library, or service.
- You expose a workflow that a caller would otherwise have to assemble from parts.

Rules:

- Measure the interface as everything a caller must know: arguments, return shape, side effects, ordering, retries, error modes. Not just the function signature.
- Push complexity downward. The caller pays for every option, flag, callback, and corner case you expose. The implementation pays once.
- Eliminate options whose right value is obvious. A parameter that 95 percent of callers set the same way is a leak; bake the answer in and provide an escape hatch only if the remaining 5 percent need one.
- Let the common case drive the interface. Optimize for what the typical caller writes. Tolerate the rare case being slightly more verbose.
- General-purpose tends to be deeper than special-purpose. A module that solves the broader problem usually has a smaller interface than a stack of narrow ones.

Smell: a class or function whose body is a one-liner that delegates with renamed arguments. You moved a name; you did not hide complexity.

Smell: an option whose only documented use is "set this to true if X." If X is knowable inside the module, decide it inside the module.

## Information Hiding and Leakage

Hide every decision that callers do not need to make. When two modules share a decision, exactly one of them owns it.

Apply when:

- You add a configuration knob.
- You expose a data structure or schema across a boundary.
- A bug fix in one place required a matching change in another.

Rules:

- Decisions that change together belong together. If editing a format requires editing both a writer and a reader, they share information; collapse to one owner or define the format once and depend on that definition from both sides.
- Leaked decisions show up as parallel switch statements, mirrored constants, or "remember to also update X" comments. Treat each as a bug, not a style issue.
- Temporal decomposition leaks information. Splitting a module by "first do A, then do B" tends to expose B's data structure to A. Split by what changes together, not by execution order.
- Pass-through methods leak by widening the interface. If A.foo just calls B.foo, callers depend on both A and B, not one. Either hide B behind A entirely or let callers talk to B directly.

Smell: a comment that says "keep this in sync with...". You found a leak. Fix the design so the comment is unnecessary.

## Different Layer, Different Abstraction

Each layer should change the level of abstraction. If a layer adds nothing, it leaks the layer beneath it.

Rules:

- A method whose name matches a method on a collaborator, with the same arguments and same return, is almost always a pass-through. Remove it or replace it with one that does real work at this layer.
- Decorators that add no behavior beyond delegation are pass-throughs in disguise. Allow them only when the type itself is the abstraction (for example, a stable interface contract callers should depend on).
- Wrappers exist to translate, validate, enrich, or constrain. If yours does none of those, delete it.

## Pull Complexity Downward

Given a choice, the module with more knowledge should absorb the complexity.

Apply when:

- You weigh "should the caller handle this case or should the module?"
- You document a precondition.
- You add a flag that defaults differently in different callsites.

Rules:

- Default rule: the module handles it. Callers exist in many places; the module exists in one. Cost scales with the number of callsites.
- A precondition the module could check itself is a missed opportunity to hide complexity. Check inside; throw or return a clear error if violated.
- Watch for symmetric blame. If you and the caller's author each think the other should handle a case, the module should, because the module is the smaller surface area.

## Define Errors Out of Existence

Many error cases are products of design choices, not laws of nature. Eliminate them rather than handle them.

Apply when:

- An exception forces every caller to wrap the call.
- An error message says "this can happen but rarely; recover by retrying."
- A function returns a sentinel value (null, empty, -1) that callers must check.

Rules:

- Prefer designs that make the error unrepresentable. A delete that succeeds whether or not the entry existed beats a delete that throws on missing keys.
- Idempotent operations remove a class of errors entirely. Reach for them at the boundaries of agent runs, retries, and external calls.
- When you cannot eliminate an error, handle it in one place. Centralize the recovery logic; do not push it to every caller.

Smell: a try/except whose body is `pass` or a log line. Either the error matters and you should handle it, or it does not and you should change the design so it never arises.

## Design It Twice

Your first design is rarely your best.

Apply when:

- You are about to commit to an interface that other code will depend on.
- Reviewing a PR that introduces a new abstraction.
- Sketching a new tool, skill, or agent.

Rules:

- Write down two materially different designs before you pick one. "Same design with a renamed function" does not count.
- Compare them on the metrics in this rule: interface size, cognitive load, change amplification, ability to eliminate errors. Pick the one that wins on the most.
- For new public surface in ai-agents, capture the trade-off briefly in the PR description. One short paragraph. The point is to prove the second design existed, not to write a thesis.

## Comments Describe What Code Cannot

Comments exist to record what the code itself cannot say. Names, types, and structure carry the rest.

Rules:

- Comment the why, not the what. A comment that paraphrases a clearly named function is dead weight that rots when the code changes.
- Comment hidden constraints, invariants, and the reasons behind non-obvious decisions. If removing the comment would surprise a future reader, keep it.
- Write the interface comment first, before the implementation. If you cannot describe the contract in two sentences, the interface is too complex.
- Do not document parameters that the type and name already explain. Document the things the signature cannot capture: ordering, side effects, allowed states, performance, retry semantics.
- Avoid restating change history in comments. Git already does that. Comments referencing PRs, issues, or tickets rot fastest.

This rule reinforces the codebase-wide guidance to default to no comments and to keep the surviving ones tight. See `AGENTS.md` and the project comment policy.

## Modify Existing Code Consistently

When you change existing code, follow the conventions already in place, even if you would have chosen differently in greenfield.

Rules:

- Match naming, ordering, error handling, and abstraction level of the surrounding code. Inconsistency raises cognitive load more than the local "improvement" lowers it.
- If the existing pattern is wrong, fix it across the affected surface in a separate, named refactor. Do not split the codebase between old and new conventions in passing.
- Reuse existing repositories, services, and skills rather than introducing parallel ones. The second mechanism is almost always a leak.
- Consistency is a form of information hiding: a reader who has learned one part of the system has already learned this one.

## Strategic vs Tactical

Tactical programming optimizes for the current change. Strategic programming optimizes for the next ten changes.

Rules:

- Default to strategic on shared code: agent prompts, orchestrator hooks, public skill interfaces, anything imported in more than one place. Spend the extra design time.
- Tactical is appropriate for one-off scripts, throwaway analyses, and code with a known short life. Mark it as such; do not let it accumulate.
- The cost of a tactical fix is paid by the next reader, not by you. If the next reader is you in a month, you will still pay it; you will just have forgotten why.

## Anti-Patterns

These shapes appear in code reviews more often than they should. Reject them.

- **Shallow class**: a class that exposes everything it does. Combine it with its caller, push behavior down, or absorb it into a deeper sibling.
- **Conjoined methods**: two methods that must be called together in a specific order to be correct. Combine into one operation or hide the ordering inside a single entry point.
- **Pass-through method**: a method that exists only to call a method with the same name and arguments on a collaborator. Remove the layer.
- **Configuration soup**: a module that exposes a dozen flags so callers can tailor behavior. Each flag is a leaked decision; eliminate the ones with an obvious right answer, and group the rest behind a named mode.
- **Comment as crutch**: a long comment that explains what the code is doing because the code does not say so. Rename, restructure, or extract until the code speaks; keep the comment only if it captures something the code cannot.
- **Premature abstraction**: a layer added "in case we need it later." If no second consumer exists, the layer is shallow by definition. Wait until the variation actually appears.

## Boundaries with Existing Codebase

ai-agents already applies several of these rules implicitly. Reuse, do not duplicate.

- **Tool and skill interfaces**: each skill and tool is a module. The deep-module test applies directly. Resist exposing implementation flags through the interface; absorb them.
- **Agent prompts**: prompts are interfaces between the orchestrator and an agent. Treat input fields as interface surface; every required field raises cognitive load on every caller. Default to fewer, wider, well-named fields over many narrow ones.
- **Plugin seams**: when you add a plugin extension point, design it twice and prefer the deeper version. The seam will outlive the first plugin that uses it.
- **Hooks**: hooks are an information-hiding mechanism. Logic that belongs inside the hook should not be re-implemented in the calling code. If callers feel they must "duplicate the hook's logic just in case," the hook's interface is too narrow.
- **Memory systems**: Serena and Forgetful are deep modules. Reach for the named operation rather than threading raw reads through your code; if a named operation is missing, add it to the module rather than working around it at the call site.
- **Session and orchestrator seams**: keep them deep. New cross-cutting behavior (telemetry, retries, idempotency) belongs inside, not duplicated in every entry point.

When you find a place where this rule and the code disagree, prefer a small, focused refactor on the path you are already touching over a sweeping rewrite. Note the deviation in the PR description so future readers can follow your reasoning.

## Quick Self-Review

Before opening a PR that adds or changes a module, walk this list.

- Is the interface smaller than the implementation? If not, the module is shallow; consider folding it in.
- Could a caller use this without reading its source? If not, the interface is too implicit.
- Will a single conceptual change require edits in more than one module? If so, locate the leaked decision and move it.
- Is there an option whose right value is obvious? Remove it.
- Is there a precondition the module could check itself? Move the check in.
- Is there a parallel implementation of something that already exists? Reuse instead.
- Did you draft and reject at least one alternative design? If not, draft one now.
- Do the comments explain why or only repeat what? Cut the latter.

If any answer is "no" or "not sure," fix the design before review.
