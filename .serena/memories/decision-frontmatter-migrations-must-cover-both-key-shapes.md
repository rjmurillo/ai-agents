# A frontmatter key migration must cover both shapes, and the two commit gates fight above 100 files

## Question

What does a repo-wide agent frontmatter key rename actually cost here, and what
does a single-pass regex miss?

## Conventional answer

A frontmatter field rename is mechanical: match `^<key>:` in the leading block,
rewrite, regenerate, done. One regex, one pass.

## First-principles position

Two things break that, both measured on issue #5130 (`tier:` -> `role:`).

### 1. The same logical field lives in two shapes

The agent trees carry the field at the top level AND nested under `metadata:`:

```yaml
# templates/agents/*.shared.md, .github/agents/*.agent.md, and the two
# generated src trees: top level
role: executor

# .claude/agents/*.md and src/claude/*.md: nested
metadata:
  role: support
```

A `^tier:` regex caught 136 files and silently left 50. Grep for `'^\s*tier:'`,
not `'^tier:'`, and confirm with a YAML parse that walks nested maps. The miss
did not surface as a test failure; it surfaced as the install-parity gate
(`pre_pr.py`, "Install Parity (agents and rules)") demanding the untouched
`.claude/agents/<name>.md` and `src/claude/<name>.md` siblings of every shared
agent the change touched. That gate is the backstop for this class, so read its
"missing (required siblings)" list as "you missed a shape", not as "add empty
edits".

At the time of the miss, nothing read the nested key. `build/generate_agent_catalog.py`
reads templates, and `scripts/openclaw_bridge.py` read only a top-level key, so
the nested copy was documentation and no test could observe it.

**That is no longer true, and the reason matters more than the fact.** The
top-level-only read was itself the bug: `.claude/agents/architect.md` declared
`strategic` and the bridge exported it as `support`, silently, for every
nested-shape agent. Reading one shape did not make the other shape inert; it
made the export wrong. `_read_declared_role` now reads both, so the nested key
is runtime input with five regression cases covering it.

The lesson to carry forward is the inverse of the one this paragraph first
recorded: do not conclude a second shape is documentation because no consumer
reads it. Check whether a consumer *should* read it. A shape nothing reads is
either dead metadata to delete or a consumer bug to fix, and telling them apart
is the work. Assuming the first is how this migration shipped a silent
misclassification.

### 2. The atomic-commit and commit-count gates are incompatible above 100 authored files

- `.claude/rules/universal.md` MUST-6 and `git_hook_policy.py atomic-commit`:
  at most 5 authored files per commit. The check prints "This local pre-commit
  check has no PR-label bypass."
- `scripts/validation/pr_commit_count.py`: `BLOCK_THRESHOLD = 20` commits per
  PR (40 if the branch merges main).

5 x 20 = 100 authored files is the ceiling for a single conforming PR. Issue
#5130 needed 124, so no commit split satisfies both. Generated trees are exempt
from the atomic count (`GENERATED_GLOBS` in `git_hook_policy.py`, which covers
`src/copilot-cli/agents/*.agent.md`, `src/vs-code-agents/*.agent.md`,
`docs/agent-catalog.md`), but `.claude/agents/`, `src/claude/`, `.github/agents/`,
and `templates/agents/` all count as authored. Verified empirically: staging 6
files from `.claude/agents` + `src/claude` fails the check, 4 passes.

The reliefs are per-gate and separate:

- 50-file PR scope hard limit (`scripts/detect_scope_explosion.py`,
  `BLOCK_THRESHOLD = 50`): `SKIP_SCOPE_CHECK=1` env var, owner-approved.
- 20-commit limit: the `commit-limit-bypass` PR label, checked by the
  Enforce Blocking Issues step.

Both are needed for a change this size. Budget for asking before starting, not
after 20 commits are already on the branch.

## Evidence

- Issue #5130, branch `claude/pr-5174-merge-review-gvrype`. 186 agent metadata
  files carried the key, of which 124 are hand-maintained copies the
  atomic-commit gate counts. The PR as a whole had changed 208 files across
  73 commits when this was written, and kept growing through review; the
  migration itself is the fixed 186. Labelled explicitly because an earlier
  revision of this memory gave 186 as the PR total, which understates what a
  bulk migration actually costs to plan for. Take the 186 as the durable
  number and the PR total as a snapshot: the ratio is the lesson, not the
  second figure. Refs #5177 review (Copilot).
- `grep -rc '^tier:'` returned 136; `grep -rc '^\s*tier:'` returned 186.
- `uv run python scripts/validation/git_hook_policy.py atomic-commit` with 6
  staged Claude-side agents: fails. With 4: passes.
- `scripts/validation/pr_commit_count.py:60-65` (thresholds),
  `scripts/detect_scope_explosion.py:50` (scope limit).

## Decision

Migrate both shapes in one change. Before starting a bulk frontmatter rename,
count authored files first: above 100, the change cannot conform to both gates,
so get the scope bypass and the label agreed up front or split the work across
PRs at a seam the install-parity gate tolerates.

## Related

- `.claude/rules/universal.md` MUST-6 (atomic commits), MUST NOT-2 (forbidden
  hook bypasses; neither `SKIP_SCOPE_CHECK` nor `commit-limit-bypass` is on
  that list)
- `.serena/memories/git/git-hooks-observations.md` (SKIP_SCOPE_CHECK provenance)
