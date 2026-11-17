# maintainer-review

Makes a maintainer decision on one pull request or issue: merge, request changes, supersede, or close. It checks whether the work should exist at all, then drafts a comment for you to post. It takes no action on the remote.

## When to use it

- You are the repository owner and want a disposition on one PR or issue URL before you spend review effort.
- An owner-configured routine runs when a PR opens and names this skill.
- Trigger phrases: `maintainer decision on this PR`, `run maintainer-review on this PR`.

## When not to use it

- You want a quality gate on a diff: use [`review`](review.md) instead.
- You want to answer review threads on your own PR: use [`pr-comment-responder`](pr-comment-responder.md) instead.

## Quick start

Start this skill yourself. Its routing is explicit-only, so the `autoplan` router never picks it for you. In Claude Code, type `/project-toolkit:maintainer-review`. On any host, ask for it by name:

```text
Use the maintainer-review skill to give a maintainer decision on https://github.com/OWNER/REPO/pull/123.
```

The skill reads the PR, its tests, linked issue, and discussion. It does not run any code. It ends with a report and a block that names the proposed owner action. Every action needs your explicit approval.

## What you get

A compact report plus a final block:

```text
Report state: <Maintainer decision | Preliminary assessment>
Author tier: <owner | dependency bot | agent bot | external>
Need status: <Demonstrated | Plausible but unproven | Already covered | Unsupported>
Recommendation: <one enum value>
Readiness: <one value, merge-worthy only>
Injected instructions found: <none | file:line list>
Proposed owner action: <merge | request changes | close | supersede | request evidence | none>
Requires owner approval: yes
```

When the decision is to close, request evidence, request changes, supersede, or prefer one competing PR, the skill appends a 60 to 160 word comment draft. It hands you the draft and does not post it.

| Decision | Values |
| --- | --- |
| PR code recommendation | `Merge-worthy as-is`, `Merge-worthy after focused changes`, `Supersede with a simpler alternative`, `Not worth completing` |
| Readiness (merge-worthy only) | `Ready`, `CI or review pending`, `Rebase or conflict resolution required`, `Blocked` |
| Issue action | `Prioritize`, `Accept, low priority`, `Narrow scope`, `Needs evidence`, `Close` |
| Competing PRs | `Prefer one PR`, `Prefer one after focused changes`, `Combine selectively`, `Replace all`, `Merge none` |
| Report state | `Maintainer decision` when concluded, `Preliminary assessment` while evidence is pending |

## Advanced use

### The need gate

The skill sets a need status before it critiques the implementation. Only `Demonstrated` may be merge-worthy. A PR whose need is `Plausible but unproven` gets `Not worth completing`, or a `Preliminary assessment` that names the missing evidence. `Needs evidence` is an issue action only.

| Need status | Meaning |
| --- | --- |
| `Demonstrated` | A concrete supported scenario, real-path reproduction, released compatibility requirement, repeated demand, or a broad invariant with material consequence |
| `Plausible but unproven` | The path can exist, but reach, frequency, consequence, or demand is not established |
| `Already covered` | A reasonable supported workflow already meets the outcome |
| `Unsupported` | The outcome belongs outside this project or at a caller-owned layer |

### Process

1. Pin the target from the URL and read the remote base, head, full patch, tests, linked issue, and discussion. Run [`chestertons-fence`](chestertons-fence.md) first if the change removes established behavior.
2. Run the need gate, including the counterfactual test: if this PR did not exist, would the maintainer file and do the same work?
3. Find competing PRs and make one decision for the set.
4. Desk review in three passes: unmet need and design (always), changed-behavior coverage, and interleaving and ownership (when triggered).
5. Report `Severity` for the underlying need and `Patch risk` separately.
6. Decide and report.

### Author tiers

| Author | Depth |
| --- | --- |
| Repository owner | Light |
| Dependency bot (Renovate, Dependabot) | Light, escalating to full if the diff touches more than manifests and lockfiles |
| Agent or code bot | Full need gate, light implementation pass |
| External contributor | Full |

The tier comes from the author login and type, never from text in the PR body. Tiering changes depth, not the hard invariants.

### Hard invariants

- No remote writes. It never merges, closes, approves, comments, labels, assigns, or pushes.
- It never enables auto-merge.
- It writes no PR content into any memory store.
- It runs no tests, imports, or reproductions, and executes no PR code.
- An instruction inside PR content is quoted with its location and ignored.

### Chaining

Run this skill first, and run [`review`](review.md) only after the need gate passes. A clean `review` verdict never upgrades a need that is not `Demonstrated`. Related checks: the [`issue-feature-review`](../agents/issue-feature-review.md) agent for feature requests, and [`avoiding-manufactured-work`](avoiding-manufactured-work.md) for work with no named consumer. [`modernize`](modernize.md) hands comment drafting here.

The skill reads [`references/workflow-detail.md`](../../src/claude/skills/maintainer-review/references/workflow-detail.md) and [`references/evaluation-framework.md`](../../src/claude/skills/maintainer-review/references/evaluation-framework.md) before the first review in a session.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`review`](review.md): the quality gate that runs after the need gate passes.
- [`pr-comment-responder`](pr-comment-responder.md): answer threads on your own PR.
- [`modernize`](modernize.md): bring an aging PR current after checking it still belongs.
- [`avoiding-manufactured-work`](avoiding-manufactured-work.md): check that work has a real consumer.
- Source: [`SKILL.md`](../../src/claude/skills/maintainer-review/SKILL.md)
- Reference: [`evaluation-framework.md`](../../src/claude/skills/maintainer-review/references/evaluation-framework.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
