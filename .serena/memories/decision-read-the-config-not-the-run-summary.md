# Read the config, not the run summary

A tool's human-readable output is a display, not a source of truth. Deriving a
fact from it produces a wrong answer that looks confirmed, because the number
you compute from the display is internally consistent with the display.

## The instances

**lefthook group scheduling.** Four consecutive pushes reported a group
duration exactly equal to the sum of its member jobs (1017.69, 950.28, 930.85,
926.49) while the longest single job sat well below (818.73, 765.34, 738.28,
733.33). That arithmetic identity was read as proof the group ran serially, and
a MUST item was written on it. `lefthook.yml` declares `parallel: true` on that
same group. The summary reports a sum regardless of scheduling, so the identity
carried no information about scheduling at all. The rule had to be pulled and
rewritten before it shipped.

**Worktree GC removal set.** `gc_worktrees.py` prints two lines per kept
worktree and only the second carries `KEEP:`. A removal set derived with
`grep -v "KEEP:"` therefore swept in protected worktrees. The derived count
matched the count the tool itself reported, which read as confirmation. It was
an artifact of both numbers being wrong in the same direction.

## The pattern

In both cases the check that felt like verification was a comparison between
two quantities computed from the same flawed source. Cardinality agreement is
not membership agreement, and arithmetic consistency within a display says
nothing about the state the display describes.

## What to do instead

Name the authoritative source and read it:

- Scheduling, timeouts, and job wiring: the config file (`lefthook.yml`), not
  the run summary.
- What a repository contains: a named git ref via `git ls-tree -r -z HEAD`,
  not a directory walk and not `git log --all`.
- A tool's own decisions: its machine-readable output (`--json`, a structured
  report object) rather than re-deriving them from its prose output.
- Set membership: enumerate and compare the elements. A matching count is the
  weakest possible evidence and is exactly what both failures produced.

When no authoritative source exists, say the claim is unverified rather than
inferring it. An inferred fact that later proves false is more expensive than
an admitted gap, because it gets written into a rule and then has to be
retracted.

## Related

- `.claude/rules/ci-scripts.md` MUST 9 states the git-specific form of this.
- `.claude/rules/ci-scripts.md` MUST 11 states the lefthook-specific form.
