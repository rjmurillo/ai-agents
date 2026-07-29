# A Declared Merge Driver Is Not a Running Merge Driver

**Category**: Git Operations
**Source**: 2026-07-28, PR #3636. Verified on git 2.43.0 against `origin/main` at `9b7e10df53`.

Symptom this explains: a merge driver that looks configured and does nothing,
and a `check-attr` reading that answers a different question than the one asked.

Companion memory: `git-merge-driver-github-disagreement.md`, for local and server
merges that disagree. Establish the answer here first.

## check-attr reports an attribute, not a driver

`git check-attr merge -- <path>` reports the effective `merge` attribute after
consulting the working tree `.gitattributes`, `.git/info/attributes`, and any
global attributes file. It resolves attributes from the **checkout**, so pass
`--source=<sha>` when diagnosing a branch you are not standing on.

Four attribute states, and only one of them names a custom driver:

| state | meaning |
|---|---|
| set (`merge`) | built-in three way text merge |
| unset (`-merge`) | keep our version, declare a conflict |
| a string (`merge=name`) | the driver named `name`, built-in or configured |
| unspecified | falls through to the `merge.default` config value |

**Unspecified does not mean no driver.** If `merge.default` names a configured
driver, every otherwise-unspecified path is served by it. Verified: in a repo with
no `.gitattributes` at all, `check-attr` reports `f.txt: merge: unspecified`, and
with `merge.default` pointing at a driver that rewrites its output, the merge
exits 0 and the file contains the driver's text. Remove `merge.default` and the
identical merge exits 1 with conflict markers and the driver is never called.
Any triage that filters `unspecified` away without checking `merge.default` has a
blind spot exactly where a repository-wide driver would sit.

## Selection, invocation, and outcome are three different things

Keep them separate. Conflating them is how a wrong diagnosis gets made.

1. **Selection**: git resolves the attribute to a driver name.
2. **Invocation**: git runs the configured command, if a `[merge "<name>"]`
   section with a `driver` line exists.
3. **Outcome**: the command succeeds, fails, or cannot be found.

Stage 2 is skipped silently when no definition exists anywhere. Stage 3 is where
a definition that exists can still leave you with a conflict.

| case | invoked | user visible output |
|---|---|---|
| no `[merge "<name>"]` definition | no | ordinary text merge, nothing said |
| definition exists, command missing | yes | `<cmd>: not found` on stderr, then `CONFLICT` |
| definition exists, command fails quietly | yes | `CONFLICT`, and nothing else |

**The first and third rows are indistinguishable from the output.** Verified: a
driver script that appends to a sentinel file and exits 1 produced byte-identical
merge output to an undefined driver name, while the sentinel proved it ran.

So do not infer invocation from silence. Prove it:

```bash
GIT_TRACE=1 git merge <ref> 2>&1 | grep run_command
```

An invoked driver appears as
`trace: run_command: '/path/to/driver .merge_file_XXXX .merge_file_YYYY ...'`.
No such line means stage 2 never happened.

The built-in driver names are exactly `text`, `binary`, and `union`, read from
`man gitattributes` on git 2.43.0 and from `ll_merge_drv[]` in `merge-ll.c` at
tag `v2.43.0`. Re-read that array before trusting the list on a newer git.

**`ours` is not one of them.** `-s ours` is a whole tree merge strategy and
`-X ours` is a strategy option that resolves conflicting hunks our way while
still taking non-conflicting changes from theirs. Neither is a gitattributes
driver. A bare `merge=ours` with no `[merge "ours"]` section is the silent row.

A driver is invoked only when a file level merge is actually needed. One sided
and identical changes resolve without it, so a broken driver stays hidden until
a genuinely divergent edit lands.

## Current state of this repository

`.gitattributes` on `origin/main` declares two merge drivers, and `origin/main`
ships a definition for neither:

| path | line | attribute | status |
|---|---|---|---|
| `.agents/HANDOFF.md` | 408 | `merge=ours` | not a built-in, no definition shipped |
| `.agents/handoffs/*.md` | 483 | `merge=handoff-aggregate` | not a built-in, never implemented |

Evidence, in the order that settles it:

- Neither name is in the built-in list.
- `git config --show-origin --get merge.<name>.driver` exits 1 for both in a
  clone that has not added one.
- `git grep -l handoff-aggregate origin/main` returns nine paths: `.gitattributes`,
  four ADR and analysis documents, two archived session records, a session log,
  and a `.claude-mem` backup. Declarations, comments, and prose. No executable
  implementation and no registration code.
- Confirming run: merging divergent edits to both paths in a scratch repo
  carrying this `.gitattributes` conflicted both at `UU`, identically to a plain
  `text` control in the same merge.

The confirming run does not settle it on its own, because an installed driver may
also decline. The missing built-in and missing definition are the evidence.

Consequence: `.agents/HANDOFF.md` does **not** resolve to main's copy on merge.
It conflicts like any other file. Open issue #3625.

Scope this claim carefully. It says `origin/main` ships no definition for those
two names. A definition can also live in a clone's `.git/config`, in the user's
global config, or in system config, and it can survive the removal of the
attribute that used it. Run the condition check in the clone that is misbehaving.

## History and cleanup

The only custom driver this repository ever shipped was `causal-graph`, a union
driver over `.agents/memory/causality/causal-graph.json`. PR #3643 removed the
Tier 3 causal memory graph: the file, `scripts/validation/merge_causal_graph.py`,
`.claude/skills/memory/scripts/update_causal_graph.py`,
`scripts/maintenance/install_merge_drivers.py`, and the `.gitattributes` entry.

Clones that ran the installer before #3643 still define it. Verified in this
clone on 2026-07-28:

```text
merge.causal-graph.driver -> file:.git/config
  "python3" scripts/validation/merge_causal_graph.py "%O" "%A" "%B"
```

Not harmless. Checking out or merging a historical branch that still carries
`merge=causal-graph` invokes a script that no longer exists, which is the loud
row above. Clear it idempotently, because a second removal exits 128:

```bash
git config --local --remove-section merge.causal-graph 2>/dev/null || true
```

## Related

- `git-merge-driver-github-disagreement.md`. The companion symptom.
- Issue #3625, open. The two inert declarations.
- ADR-089 and `.agents/analysis/2026-07-27-adr-089-causal-tier-removal-debate.md`.
- `.gitattributes` lines 408 and 483.
