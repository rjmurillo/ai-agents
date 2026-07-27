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
Supporting modules: `instruction_budget_globs.py`, `_constants.py`, `_types.py`,
plus `passive_context_budget.py`.

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
because it counts only *language-universal* `applyTo` patterns (`**`, `**/*`,
`**/*.<ext>`); directory-scoped rules such as `scripts/**` are excluded by
design, since they do not load on an arbitrary edit. Neither number is wrong.
Read `is_language_universal` in `instruction_budget_globs.py` before quoting
either one.

## The headroom is the story

Subtracting current from ceiling:

```text
.cs    1520 bytes free
.md    1378 bytes free
.ps1   1688 bytes free
.py    1397 bytes free
```

A rule whose `applyTo` is `**` counts against all four languages at once, so the
binding constraint is the smallest headroom. **The largest always-on rule that
can be added today is 1,378 bytes.** A rule file with frontmatter and any real
content exceeds that. The next always-on rule addition breaks the build.

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
