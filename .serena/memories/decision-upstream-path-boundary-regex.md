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

Coverage grows the file from 55 tests on `main` to 106, across four classes. The new
`TestDotPrefixedUpstreamBoundary` covers `.agents`, `.claude/lib` and
`.claude/review-axes`. `TestCountUpstreamRefs.test_counts_paths_that_name_the_upstream_dir`
gains the `templates` shapes this fix repairs. `TestPathStartAnchor` pins the shapes that
supply their own root. `TestBlockquotedFence` pins fence handling inside a blockquote.

Twenty-two of the 96 that predate this follow-up fail against `main`'s module, so they are regression proof rather than
decoration; the rest pin behavior that already held, which is what makes the failures
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

## Follow-up: the closed set has to be closed on purpose (issue #3489)

A third review round found the predicted failure mode. The anchor set omitted `>`, so a
tight blockquote `>/templates/agents/x.md` stopped counting while the spaced form kept
counting. That is a regression the old lookbehind did not have, and it is exactly the
"missed reference a test can name" that the lesson above predicted. `>` was added.

The same round proposed adding `:` and `=` alongside it. Both were measured and both were
rejected, which is the more useful result.

| candidate | fixes | breaks |
|---|---|---|
| `:` | `[x]:/templates/agents/x.md`, `path:/templates/agents/x.md` | `C:\templates\agents\x.md`, `C:\.agents\specs\x.md` |
| `=` | `<img src=/templates/agents/x.md>` | `[x](https://example.com/p?next=/.agents/x)` |

A Windows drive letter is a colon followed by a single separator. A URL query parameter is
an equals sign followed by a root-relative path. Both are the exact shape the anchor
accepts, so each candidate trades one false negative for one false positive. Net zero.
`TestPathStartAnchor.test_shapes_that_colon_or_equals_anchors_would_break` pins the
casualties so a future contributor who adds either character sees the failure.

The blockquoted-fence handling had a second defect. A fenced code block has no lazy
continuation, so it ends when its blockquote ends, but the close test stripped the
blockquote prefix from every later line without checking the quote was still active. An
unquoted line inside a quoted fence, and an unterminated quoted fence, both swallowed real
top-level prose. False negatives are the dangerous direction for a gate: a genuine
upstream dependency passes undetected. The fix ends the fence when the blockquote ends and
re-reads that line at top level, so a bare fence marker there opens the top-level fence it
should.

### Transferable lesson from the follow-up

When a reviewer proposes widening a boundary, measure what the widening costs before
accepting it. Two of the three proposed characters were net-negative, and the only way to
know was to run the candidate set against the shapes the boundary already rejects. A
suggestion that fixes a named case is not evidence it fixes more than it breaks.
