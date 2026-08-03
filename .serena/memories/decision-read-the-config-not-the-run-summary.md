# Read the config, not the run summary

A tool's human-readable output is a display, not a source of truth. Deriving a
fact from it produces a wrong answer that looks confirmed, because the number
you compute from the display is internally consistent with the display.

## The instances

**lefthook group scheduling.** Four consecutive pushes on 2026-08-02 reported
a group duration exactly equal to the sum of its member jobs (1017.69, 950.28,
930.85, 926.49) while the longest single job sat well below (818.73, 765.34,
738.28, 733.33). Those numbers are a dated record of that one session, not a
measurement to expect on a rerun. The arithmetic identity was read as proof the
group ran serially, and a MUST item was written on it. `lefthook.yml` declares
`parallel: true` on that same group, and still does, which is the part you can
check at any time. The summary reports a sum regardless of scheduling, so the
identity carried no information about scheduling at all. The rule had to be
pulled and rewritten before it shipped.

**Worktree GC removal set.** A removal set derived from the report text with
`grep -v "KEEP:"` swept in protected worktrees. The mechanism is narrower than
the first write-up of it claimed, and the narrow version is the one to carry
forward. In `scripts/maintenance/gc_worktrees.py`, the `Kept:` group emits one
KEEP line per kept worktree, and that line always carries the token
(`gc_worktrees.py:426-431`):

```python
lambda d: f"    - {d.path} [{d.branch}] KEEP: {d.reason}",
```

`format_report` itself emits more than that group. It calls
`_append_disposition_group` immediately before the `Kept:` group
(`gc_worktrees.py:425`), which runs only over `report.needs_disposition`, the
subset of kept worktrees whose reason is `KEEP_UNPUSHED` ("unpushed commits and
not merged to base"), and prints each of them a second time without the token:

```python
lines.append(f"    - {decision.path} [{decision.branch}] unpushed and unmerged")
```

`format_report`'s own output is therefore one KEEP line per kept worktree plus
one tokenless disposition line per `KEEP_UNPUSHED` worktree. Only the `Kept:`
group is one line per kept worktree.

The inverted-filter hazard is real but scoped. It is not "two lines per kept
worktree" and not a property of a mode; it is that one subset of kept worktrees
is printed a second time without the token the filter keys on, alongside that
group's two header lines. The episode write-up also reports that the derived
removal count matched the count the tool printed, and read that agreement as
confirmation. That part was not re-checked when the mechanism above was
corrected, so carry it as the reporter's recollection, not as a verified fact.

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
  weakest possible evidence, and it is what the lefthook failure produced.

When no authoritative source exists, say the claim is unverified rather than
inferring it. An inferred fact that later proves false is more expensive than
an admitted gap, because it gets written into a rule and then has to be
retracted.

## Related

- `.claude/rules/ci-scripts.md` MUST 9 states the git-specific form of this.
- `.claude/rules/ci-scripts.md` MUST 15 states the lefthook-specific form.
