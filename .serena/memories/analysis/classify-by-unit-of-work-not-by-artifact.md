# Skill: Classify by the unit you will act on, not by the artifact (MED)

## Statement

When sizing a batch of work, count the units you will actually process, not the
items inside them. A per-artifact tally answers a different question than
"how many of these can I handle the cheap way", and the two diverge whenever one
unit mixes easy and hard items.

## Evidence

2026-08-02, session 4234. Sizing a conflict backlog across 30 open PRs, I
tallied conflicted files by kind: 12 in `.claude-plugin/plugin.json`, 6 in
ratchet baselines, 4 in generated mirrors, 8 in real code. I offered the user a
"mechanical sweep of roughly 18 PRs" on that basis.

The real classifier is per PR: does this PR conflict *only* in regenerable
files. Under that test **one** PR (#4109) qualified. Every other plugin.json
conflict sat alongside a code conflict in the same PR, so resolving the
mechanical half bought nothing on its own. Eight more PRs had exactly one
non-mechanical file, which is the honest tractable wedge.

The estimate was off by roughly 18x on the thing that mattered, and the user
chose an option partly on that number.

## Recipe

Group first, then classify each group by its worst member:

```python
pure = [pr for pr, files in groups.items() if all(is_mechanical(f) for f in files)]
```

Say which classifier produced the count when reporting it. "18 files are
mechanical" and "1 PR is mechanically resolvable" are both true and only one is
decision-relevant.

## Related

- `.claude/rules/testing.md` MUST-10: report a scope measurement together with
  the size of the scope. Same failure shape, applied to counts rather than gates.
