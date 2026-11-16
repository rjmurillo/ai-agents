# An ADR debate log number can collide with one main added

## What happens

An ADR edit needs a debate log in `.project-toolkit/critique/`, named `ADR-NNN-debate-log-<n>.md`.
You pick `<n>` as the next free number on your branch.
Another PR can merge the same number to main first.
Merging main into your branch then gives an add/add conflict on that file.

## Practice

- Pick the number from `origin/main` right before you push, not from your branch base.
- On an add/add conflict, keep main's file as is and rename yours to the next free number.
- Fix any reference to the old name, such as the ADR's amendment note.
- During `git merge origin/main`, stage `:2` is your branch and stage `:3` is main. `git show :3:<path>` prints main's file.

## Evidence

- [2026-11-16] [orchestrator session, PR #7387]: The branch added `ADR-115-debate-log-4.md`. PR #7395 merged its own `-4` to main first. Main's file was kept and the branch's log became `ADR-115-debate-log-5.md`.

## Relations

- **related_to**: [decision-every-merge-invalidates-every-open-pr](../decision-every-merge-invalidates-every-open-pr.md)
