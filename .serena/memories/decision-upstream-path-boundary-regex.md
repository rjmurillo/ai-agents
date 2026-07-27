# Decision: one shared boundary constant for upstream path patterns

## Question

How should `UPSTREAM_PATTERNS` in `scripts/validation/check_skill_md_portability.py`
decide where an upstream path reference starts, so that `/templates/agents/` counts
and `src/templates/agents/` does not.

## Conventional answer

Add a word-boundary lookbehind in front of the pattern. That is the reflexive fix for
"my regex matched in the middle of a longer token", and it is what PR #3463 did:

```python
r"(?<![\\/\w.-])(?:\.[\\/]+)?templates[\\/]+agents..."
```

## First-principles position

A bare lookbehind is wrong for filesystem paths because a leading separator is not
noise, it is meaningful. `/templates/agents/x.md` is how GitHub renders a repo-root
link, so it is the single most likely shape a skill author writes when citing upstream
provenance. The lookbehind sees the leading `/` and rejects the match.

The correct shape optionally *consumes* the leading separator first, then applies the
lookbehind to whatever precedes it:

```python
_BOUNDARY = r"(?<![\w.\-/\\])(?:\.[\\/]+|[\\/]+)?"
```

`/templates/` passes because nothing precedes the consumed `/`. `src/templates/` fails
because `src` precedes it. That single constant is now shared by all five patterns.

`../templates/` stays excluded on purpose: it resolves outside the repo root, so it
ships with whatever contains it. An existing test asserts this, and an earlier draft of
`_BOUNDARY` that allowed `../` was caught by that test.

## Evidence

Measured against the module as it shipped on `main` (`303f918ea`), calling
`count_upstream_refs` directly. Four false negatives:

```
/templates/agents/security.shared.md   -> 0
/templates/platforms/copilot.yaml      -> 0
\templates\agents\x.md                 -> 0
See /templates/agents/ for the source  -> 0
```

Five false positives, from the three legacy patterns that PR #3463 never touched:

```
src/.agents/foo                -> 1
https://example.com/.agents/x  -> 1
src/.claude/lib/y              -> 1
https://x.com/.claude/lib/z    -> 1
src/.claude/review-axes/q      -> 1
```

The legacy patterns used `(?<![\\\w.])`, which omits `/` from the excluded set, so any
path or URL segment ending in `/` before a dot-directory matched.

## Decision

`_BOUNDARY` is defined once and applied to all five entries of `UPSTREAM_PATTERNS`.
The three legacy patterns also gained `?#` in their terminator class so URL query and
fragment forms terminate the match the same way the `templates` patterns already did.

Coverage adds seventeen cases in `tests/validation/test_check_skill_md_portability.py`,
split across two classes. Fourteen sit in the new `TestDotPrefixedUpstreamBoundary`,
which covers `.agents`, `.claude/lib`, and `.claude/review-axes`. Three extend the
pre-existing `TestCountUpstreamRefs.test_counts_paths_that_name_the_upstream_dir`
parametrize with the `templates` shapes this fix repairs.

Nine of the seventeen change verdict against the previous regex, so they are regression
proof rather than decoration. The other eight pin behavior that already held, which is
what makes the nine meaningful.

Filed as issue #3471. Landed after PR #3463 merged, because the fix was still local
when that PR merged.

## Transferable lesson

When a regex matches inside a longer path, do not reach for a bare lookbehind. Decide
first whether a leading separator is meaningful in the domain. For repo-relative paths
it is: consume it, then apply the boundary to what came before it.
