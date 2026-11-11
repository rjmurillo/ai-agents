# ADR Debate Log: ADR-109 repo-only hooks amendment (issue #7231)

## Summary

- **Rounds**: 1 of 10
- **Prior debate logs**: `.project-toolkit/critique/ADR-109-debate-log.md` (original consensus) and `.project-toolkit/critique/ADR-109-debate-log-2.md` (the D32 follow-up, closed)
- **Outcome**: Consensus in round 1. Four agents voted Accept. The critic and the independent-thinker voted Disagree-and-Commit. No agent voted Block.
- **Final Status**: accepted (unchanged; this edit appends a dated amendment)
- **Subject**: the section "Amendment 2026-11-11: repo-only hooks render straight to `.claude/hooks/`".
- **Trigger**: owner decision on issue #7231 item 1 (2026-11-11): "Register the hooks that we want vendor installed. Skip hooks that are only for this repository."
- **Panel**: full (architect, critic, independent-thinker, security, analyst, high-level-advisor). The amendment changes the binplace manifest, which defines the `.claude/` write allowlist, and the `Hook Template Drift` target set. Other gates read both.
- **Design pre-review**: an architect agent reviewed the design before this debate and voted approve with changes. Its four missing touchpoints (write allowlist, surface parity row, deletion of stale copies, two-direction reachability test) were folded in before round 1.

## Round 1

| Agent | Vote | Findings |
|-------|------|----------|
| architect | Accept | P1: five stale statements say every hooks-class file renders to `src/claude/hooks/`. P2: "four" and "three" guard callers do not reconcile. P2: say why hooks use a central list when skills and rules do not. P2: name the surface shape. |
| critic | Disagree-and-Commit | P1: the `binplace.yaml` list and the surface parity `include:` list are two lists for one fact. P1: the same stale statements as the architect. P2: define how imports are found. P2: four versus three. P2: rollback has no after-check. |
| independent-thinker | Disagree-and-Commit | P1: deriving the shipped set from `hooks.json` reachability would remove the declared list. If the list stays, say why. P2: a separate templates directory is worse. P2: two tests keep synthetic strings naming a deleted path; they still pass. |
| security | Accept | P1: say how the executable bit is kept for `session-start.sh`. P1: a stray file under a listed directory gets no binplace report. P2: name validation misses `.`, empty, backslash, and symlinked entries. |
| analyst | Accept | 11 of 12 claims VERIFIED, 1 UNVERIFIED (the byte total, which the high-level-advisor and the author measured as 118716). P2: four versus three. P2: the first-part rule holds for copy rows only. |
| high-level-advisor | Accept | P1: record the directory-level list as known debt in the PR body. P1: say in the PR body that the shipped `dispatch_groups.json` keeps three unregistered groups on purpose. P2: trim enforced rules from prose. |

## Changes made after round 1

- Added one sentence naming every stale statement the change updates: the `binplace.yaml` hooks comment, the `hook_templates.py` and `build_all.py` docstrings, the `checks_portability.py` drift docstring, `build/AGENTS.md`, and DESIGN-025 B4. (architect P1, critic P1-2)
- The surface parity paragraph now says a test checks that the `include:` list equals the files under the listed entries, with a negative control that edits one side only. (critic P1-1)
- The decision now says why hooks use a declared list: scripts carry no frontmatter, `session-start.sh` is shell, and `_bootstrap.py` is read by path at build time. Walking registrations cannot find either one. (independent-thinker P1, architect P2-2)
- The gates paragraph now states that the render copies the template's file mode. Verified at `build/scripts/hook_templates.py:315-343`: mode is copied on write and drift-checked on validate. (security P1-1)
- The surface parity paragraph now says a stray file under a listed directory is unclassified, so the surface parity check fails on it. (security P1-2)
- Loader validation now names separators, dot names, and symlinked entries, and points at the loader tests for the exact rules. (security P2-1, high-level-advisor P2)
- Named the three guard-only hooks and said the drift check is repo-only for what it does. (architect, critic, analyst P2)
- Narrowed the first-part rule to the `hooks` copy row. (analyst P2-b)
- The import walk is defined: parse each reachable file, resolve against its own directory and the hooks root, and leave plugin `lib/` imports out of scope. (critic P2-1)
- Rollback now checks that `src/claude/hooks/` holds 18 files again. (critic P2-3)

## Dissent and residuals

- The independent-thinker still prefers a derived shipped set. The declared list stands because two repo-only files cannot be derived from registrations. The two-direction test keeps the list and the registrations in agreement.
- The critic's two-list concern is mitigated by a test, not removed. Surface parity YAML is static data and cannot read the `binplace.yaml` list.
- The directory-level list means a future shipped `SessionStart` hook needs the entry split first. The high-level-advisor asked that the PR body record this as known debt.
- The shipped `dispatch_groups.json` keeps the three `sessionstart-*` groups. No registration names them and the dispatcher reads only the invoked group. The PR body states this.
- `tests/skills/taste-lints/test_taste_lints.py:1296` and `tests/skills/code-qualities-assessment/test_assess.py:1941` keep synthetic path strings. They are classifier inputs and still pass. Left unchanged.
