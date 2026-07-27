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
_ANCHOR = r"(?:^|(?<=[\s(\[<\"'`|,;*]))"
_BOUNDARY = _ANCHOR + r"(?:\.[\\/]|[\\/])?"
```

A path counts only when it begins at a real start of context: the start of the text,
whitespace (which includes a line start), or a Markdown or quoting delimiter. The
optional group then consumes a single leading separator, so `/templates/` counts and
`src/templates/` does not.

The first revision of this fix got the direction wrong. It consumed the separator first
and then applied a negative lookbehind, `(?<![\w.\-/\\])`. A negative test admits every
character it does not name, so `~/templates/`, `C:\templates\`, `${ROOT}/templates/`,
`%ROOT%\templates\`, `file:///templates/`, `//templates/` and a `#/templates/` URL
fragment all counted as repository-root references. Each of those supplies its own root.
Adversarial review caught it; the fix is to name the characters a path may follow rather
than the ones it may not.

Backtick is in the anchor set on purpose. `count_upstream_refs` deliberately does not
strip inline code, because SKILL.md path dependencies are normally written in backticks.

`../templates/` stays excluded on purpose, but not because it leaves the repository.
`../templates/agents` from `.claude/skills/security-review/SKILL.md` normalizes to
`.claude/skills/templates/agents`, which is still inside the repo. The real reason is
that a parent-relative path does not unambiguously name the repository-root directory:
where it lands depends on the referring file's own location, so it is not evidence of a
dependency on the upstream tree. An existing test asserts this, and an earlier draft of
the boundary that allowed `../` was caught by that test.

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

Coverage grows the file from 55 tests on `main` to 93, across four classes. The new
`TestDotPrefixedUpstreamBoundary` covers `.agents`, `.claude/lib` and
`.claude/review-axes`. `TestCountUpstreamRefs.test_counts_paths_that_name_the_upstream_dir`
gains the `templates` shapes this fix repairs. `TestPathStartAnchor` pins the shapes that
supply their own root. `TestBlockquotedFence` pins fence handling inside a blockquote.

Nineteen of the 93 fail against `main`'s module, so they are regression proof rather than
decoration; the rest pin behavior that already held, which is what makes the nineteen
meaningful. Reproduce by copying the test file into a worktree checked out at
`origin/main` and running pytest on it.

Filed as issue #3471. Landed after PR #3463 merged, because the fix was still local
when that PR merged.

## Transferable lesson

Prefer a positive assertion to a negative one when deciding where a match may start. A
negative lookbehind is an open set: it admits every character the author did not think
of, and the ones nobody thinks of are exactly the interesting ones (`~`, `:`, `}`, `%`,
`#`). A positive anchor is a closed set, so its failure mode is a missed reference that a
test can name rather than a false positive nobody predicted.

Two review rounds on this change found real defects that local tests did not, and the
defects were in the part that looked finished. Run a shape matrix that compares the old
module against the new one directly, rather than trusting that a green suite means the
boundary moved only where intended.
