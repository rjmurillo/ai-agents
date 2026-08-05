# Conflict markers in this repo come in fours, not threes

## The trap

Scripts and habits built around three conflict markers corrupt files here.
This repository resolves with diff3 or zdiff3 conflict style, which emits
**four** markers:

```
  <<<<<<< ours
  ...our side...
  ||||||| f36f1ed72b
  ...the merge base...
  =======
  ...their side...
  >>>>>>> theirs
```

That example is indented by two spaces on purpose. The `conflict-marker-policy`
hook matches `^(?:<{7}|\|{7}|>{7}) \S`, anchored at line start and requiring a
trailing ref name, so an unindented example inside a code fence would block its
own commit. A bare `=======` line is deliberately not matched, because ordinary
prose and Markdown rules use it.

A resolver that splits on `<<<<<<<`, `=======`, and `>>>>>>>` treats everything
between `<<<<<<<` and `=======` as "ours". That span silently includes the
`|||||||` marker line and the entire merge-base region. The base content gets
written into the resolved file as though a human had authored it.

## How it surfaces

Not at resolution time. The `conflict-marker-policy` pre-commit hook catches it,
but only after a full commit attempt:

```
ERROR: staged content contains git conflict markers:
  .agents/governance/GOTCHAS.md:639: ||||||| f36f1ed72b
```

So the cost is a wasted commit cycle plus the pre-commit suite, and the failure
names the symptom rather than the cause.

## The correct parse

Locate all four marker line numbers and assert ordering before touching
anything:

```python
assert a < b < c < d, "markers out of order, not a diff3 conflict block"
ours  = lines[a + 1 : b]
base  = lines[b + 1 : c]
theirs = lines[c + 1 : d]
```

If `base` is empty, both sides purely appended and neither deleted anything from
the other. That is the common case for append-only prose files, and it means a
union of both sides loses no content. A non-empty base means at least one side
removed or rewrote existing text, so read it before choosing.

## Recovery after a botched resolution

`git checkout --merge -- <path>` restores the conflict markers for one file
without aborting the merge. Reach for it instead of `git merge --abort`, which
throws away correct resolutions of every other conflicted file.

## Why this recurs here

Two files draw most of the repository's conflicts because many branches append
to them: `.agents/governance/GOTCHAS.md` and `.serena/memories/memory-index.md`.
Conflict resolution is therefore routine rather than rare, and a resolver script
gets reused.

Note that the two files need different treatment.
`memory-index.md` has a mechanical repair: take either side, then run
`scripts/update_memory_index_tokens.py` followed by
`scripts/ci/memory_index_token_ratchet.py`. `GOTCHAS.md` has none, and its
duplicate risk is semantic rather than lexical, so it needs a human read. See
`quality/union-merge-hides-semantic-duplicates.md`.

## Verification after resolving

Do not trust the absence of a hook error. Check directly:

```bash
git grep -n -e '^<<<<<<< ' -e '^||||||| ' -e '^=======$' -e '^>>>>>>> ' -- <path>
```

Then confirm every heading you expected to keep appears exactly once, and every
heading you deliberately dropped appears zero times. A count of two on a heading
means both sides contributed it and the resolution kept both.
