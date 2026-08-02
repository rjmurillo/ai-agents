# The always-on instruction budget gate already exists, and it is nearly full

## Question

An analysis note says this repo has no instrument measuring the passive context
cost of always-on instruction files, and prescribes building a ratchet. Do you
build it?

## Conventional answer

The note is specific and the numbers check out. A single `.py` edit really does
load about 218 KB of always-on rules, `AGENTS.md:31` really does carry the only
budget line (`Knowledge -> context (<8KB)`), and
`.agents/analysis/context-engineering.md` really is stale. The gap is real, so
close it.

## First-principles position

Every premise in the note can be true and the conclusion still wrong, because
the note is dated. It describes the repo on the day it was written, not today.
Before building the prescribed fix, check whether the repo already shipped it,
and check the git log dates on the artifacts the note says are missing.

## Evidence

`scripts/validation/instruction_budget.py` exists. It cites the same ~218 KB
figure, references the same issue (#3419), implements exactly the prescribed
per-language ratchet, and is wired into `.github/workflows/instruction-budget.yml`
as `uv run --frozen python3 -m scripts.validation.instruction_budget --ci`.
Supporting modules: `instruction_budget_globs.py`,
`instruction_budget_constants.py`, `instruction_budget_types.py`, plus
`passive_context_budget.py`.

It landed in `db46e0305` on 2026-07-27. The note was written 2026-07-26. The
repo shipped the fix the day after the gap was recorded.

Live reading:

```text
Ext     Files     Bytes   Ceiling   Tokens~    Usage  Status
.cs        19    218480    220000     57555    99.3%    PASS
.md         9     81622     83000     21564    98.3%    PASS
.ps1       19    218312    220000     57588    99.2%    PASS
.py        19    218603    220000     57651    99.4%    PASS
```

Two figures can both be right and disagree. An independent count of the same
tree gave 222,475 bytes across 20 files. The gate reports 218,603 across 19
because it counts only *language-universal* rules; directory-scoped rules such
as `scripts/**` are excluded by design, since they do not load on an arbitrary
edit. Neither number is wrong.

Do not read universality as a list of blessed spellings. `is_language_universal`
decides it by *matching*, not by enumeration: it splits `applyTo` on commas,
reduces each pattern to its harness-effective form, and asks whether every probe
path for the extension is matched by at least one pattern, plus a special case
for all-files wildcards (`_ALL_FILES_FORMS`). Universality is a property of the
union, so a rule whose depths are split across disjoint globs still counts.
That is deliberate: under-counting is the dangerous direction for an upper
bound, and an exact-form table let broad shapes (`?` wildcards, zero-segment
globstars, absolute anchors) dodge the budget. Read the function before quoting
either number.

## The headroom is the story

Re-measured on `origin/main` at `ede9fd1fe`, 2026-08-02:

```text
Ext     Files     Bytes   Ceiling    Usage   Free
.cs        11     95599     99000    96.6%   3401
.md         9     82603     83000    99.5%    397
.ps1       11     95431     99000    96.4%   3569
.py        11     95722     99000    96.7%   3278
```

A rule whose `applyTo` is `**` counts against all four languages at once, so the
binding constraint is the smallest headroom. **The largest always-on rule that
can be added today is 397 bytes**, which is smaller than the frontmatter plus
heading of an empty rule file. The next always-on rule addition breaks the
build.

The earlier revision of this memory recorded the `.md` figure as 1378 bytes.
Headroom has since fallen to 397, and the `.md` ceiling is 83000 while the other
three sit at 99000. Re-measure before quoting any number in this section. The
memory that warns an analysis note is a claim about a date rather than about the
tree is subject to its own rule.

## Scoping is free, and it is the fix

The instinct on a budget failure is to compress the rule or raise
`DEFAULT_CEILINGS_BYTES`. Both are usually wrong. `instruction_budget.py` counts
only universally scoped files, so a rule moved to a narrower `applyTo` costs
zero bytes rather than fewer bytes.

Worked example, `.agents/**` session-log mechanics:

| Placement | Always-on cost | Gate |
|---|---|---|
| `universal.md`, `applyTo: **` | +855 bytes against 397 free | FAIL at 100.8% |
| `session-logs.md`, `applyTo: .agents/**` | 0 bytes, 82603 before and after | PASS |

Identical prose, identical mirrors, identical enforcement. The only change was
the frontmatter glob. Before compressing anything, ask whether the rule was ever
universal: a rule that describes what happens when a change touches one tree
never was. Raising a ceiling to clear a violation you introduced is forbidden
regardless, since it converts a real signal into a silent one.

That is also why this note is a memory and not a rule. Documenting the budget in
an always-on rule file would consume the budget it documents, and there is not
room. The tier choice here is a measurement, not a preference.

## Decision

Do not build a context-budget instrument. Read
`scripts/validation/instruction_budget.py` first.

When adding steering that would otherwise be always-on, scope `applyTo` to the
narrowest path glob that fires where the guidance applies. Directory-scoped
rules do not count against these ceilings. Reserve `**` for guidance that
genuinely binds every file in every language.

Rule to carry forward: an analysis note asserting an artifact is missing is a
claim about a date, not about the tree. Check `git log` on the thing it says
does not exist before building it.

Refs #3419, `db46e0305`.
