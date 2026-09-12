---
description: Stopping rules for how much code, reasoning, and context a change is allowed to spend. Apply before writing new code.
applyTo: src/**,scripts/**,build/**,tests/**
---

# Efficiency

<!-- vendor-portability: the only upstream-tree paths in this file are the
`scripts/**` and `build/**` globs of its own `applyTo` scope declaration, which
tell the harness where the rule loads and are not instructions to the reader to
open those directories. Prose carries no upstream path. -->

Three budgets are spent on every change: the code you add, the reasoning you
burn deciding what to add, and the context you pull in to decide. This rule
sets a stopping rule for each. It governs how much you build, never how well.

## The Ladder

Walk these rungs in order and stop at the first one that holds:

1. Does this need to exist at all? (YAGNI)
2. Already in this codebase? Reuse it.
3. Standard library does it? Use it.
4. Native platform feature covers it?
5. Already-installed dependency solves it?
6. Can it be one line?
7. Only then: the minimum code that works.

No unrequested abstractions. Deletion over addition. Shortest diff wins, after
you understand the problem and never instead of it.

Rungs 2 through 5 are the operational form of `search-before-building.md`
Layer 1: the existing solution is cheaper than the one you would write, and
you cannot know which rung holds without looking. Skipping straight to rung 7
is the reinvention that rule exists to prevent.

## The Ladder Is A Stopping Rule, Not A Checklist To Narrate

Reasoning tokens bill at the same rate as written ones, so a walk down all
seven rungs in visible thinking costs what the code costs. Stop at the first
rung that holds. Do not re-derive the rungs above it or weigh alternatives the
stop already excluded. An obvious fix gets given, not reviewed: a one-line
change earns no design discussion.

This never licenses thinking less about the problem. Root-cause the bug. Read
what you are about to edit. Depth belongs where the problem is actually hard
and nowhere else. The budget is on deliberation about the shape of the
solution, not on understanding the failure.

## Context Diet

Tool output is billed again on every later turn of the session, so a file read
once is paid for many times.

- Find the symbol first, then read only the matching region. `lsp-first.md`
  ranks the navigation tools for this; the point here is what you read after
  the tool answers.
- Narrow at the source, not after. `ls <dir>` over `ls -R`; pipe long output
  through `tail` or `grep` before it lands in the transcript.
- Never re-read what is already in context unless it changed.

The diet trims transport, never understanding. Never skim a span you are about
to edit: a wrong edit bills the edit, the review, the fix, and the re-review,
which is the arithmetic `token-economy.md` opens with.

## Never Minimal About

The ladder bounds construction. It does not bound behavior. These are never
trimmed to shorten a diff:

- Input validation at trust boundaries.
- Error handling that prevents data loss.
- Security.
- Accessibility.
- Anything the user explicitly asked for.

## Reconciling With Boil The Lake

`builder-ethos.md` section 1 says the marginal cost of completeness is near
zero, so do the complete thing. This rule says stop at the first rung that
holds. They do not conflict, because they bound different axes.

Boil the Lake bounds **coverage**: edge cases, error paths, negative tests,
documentation accuracy. Complete that.

This rule bounds **construction**: how many new files, layers, abstractions,
and dependencies you introduce to get that coverage. Minimize that.

The failure mode each one catches is the other's excess. A shortcut that
handles only the demo path fails Boil the Lake. A four-layer abstraction
around a call the standard library already makes fails the ladder. The
"Never Minimal About" list above is the seam: where the two would disagree,
coverage wins.

## Response Economy

`voice.md` owns prose style and is always-on, so it is not restated here. One
thing it does not cover: structure is tokens too.

Answer at the question's altitude. Do not manufacture headings, bullet lists,
or sections the question did not ask for. "Compare X and Y" is the trap that
draws a headed pro-and-con wall out of a two-sentence answer: name the
decisive trade-offs in prose, give the verdict, stop.

Substantive deliverables are exempt, the same carve-out `voice.md` makes for
them under "Clear The Gate Or Drop The Claim". A specification, an ADR, an
analysis report, or a design document is structured because its reader needs
the structure. A reply about a one-line fix is not.

## Why This Rule Is Scoped Rather Than Language-Universal

It is deliberately not `paths: ["**/*.py", ...]` across every code extension,
and the reason is a measurement rather than a preference.

The `instruction_budget.py` validator, under the validation-scripts tree,
scores the corpus whose generated `applyTo` matches every file of a language.
Measured on this branch before this rule existed, a `.py` edit loaded 10 files
totalling 98,221 bytes against a 99,000-byte ceiling, and `.cs` and `.ps1` sat
within roughly 2,200 bytes of the same line. This rule generates several
kilobytes, multiples of that 779-byte headroom. A language-universal scope
would have taken all three languages over the ceiling, and the only ways to
fund it are cutting other always-on content or raising the ceiling, both of
which the rule-audit procedure in the context-optimizer skill gates behind
replicated eval runs on two models. This rule carries no such evidence and
does not claim to. (The validator's directory prefix is omitted above because
this rule ships in the plugin instruction mirrors, where an upstream-only path
would dangle.)

The globs in the frontmatter are the trees where code is authored in this
repository and in a consumer install: application source, scripts, build
tooling, tests, and agent configuration. That is where a wrong or overbuilt
edit costs a review cycle. None of them matches every file of any language, so
this rule adds nothing to the language baselines. Re-run the validator before
widening the scope; the measurement, not this paragraph, is the authority.
