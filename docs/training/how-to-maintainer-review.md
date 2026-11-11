# Get a maintainer decision with maintainer-review

## Goal

Get a decision on one PR or issue: should this work exist, and what should the
maintainer do with it? You get a report and a draft comment. The skill takes no
action on GitHub (#6466).

## Before you start

- The URL of one PR or issue.
- You are the repository owner, or an owner-set routine is asking. Nobody else
  should run this skill. It feeds merge and close decisions that only the owner
  makes.
- Know the difference between the two reviews:

  | Question | Skill |
  |---|---|
  | Should this change exist, and what should the maintainer do? | `maintainer-review` |
  | Is this diff correct, safe, and up to standard? | [`/review`](how-to-review.md) |
  | How do I answer threads on my own PR? | [`pr-comment-responder`](how-to-respond-to-review-threads.md) |

  Run `maintainer-review` first. Run `/review` only after the need check passes. A
  clean `/review` never upgrades a need that was not shown.

## Steps

1. Name the skill and give one URL:

   ```text
   maintainer decision on https://github.com/rjmurillo/ai-agents/pull/1234
   ```

2. Expect depth to match the author. The hard rules never change.

   | Author | Depth |
   |---|---|
   | Repository owner | Light |
   | Dependency bot (Renovate, Dependabot) | Light. A diff beyond manifests and lockfiles gets a full pass. |
   | Agent or code bot | Full need check, light code pass |
   | External contributor | Full |

   The tier comes from the author's login and type, never from text in the PR body.

3. Read the need status. It is one of four values:

   - `Demonstrated`: a real scenario, a reproduction, a compatibility need, or
     repeated demand.
   - `Plausible but unproven`: the path can exist, but reach or demand is not shown.
   - `Already covered`: a supported workflow already meets the outcome.
   - `Unsupported`: the outcome belongs outside this project.

   Only `Demonstrated` can be merge-worthy. The test is simple: if this PR did not
   exist, would the maintainer file and do the same work?

4. Read the competing PRs. The skill searches for open PRs that share the issue,
   symptom, or fix. It makes one decision for the whole set.

5. Read the final block. It ends with a fixed set of lines:

   ```text
   Report state: <Maintainer decision | Preliminary assessment>
   Author tier: <owner | dependency bot | agent bot | external>
   Need status: <Demonstrated | Plausible but unproven | Already covered | Unsupported>
   Recommendation: <one value>
   Readiness: <one value, only when merge-worthy>
   Injected instructions found: <none | file:line list>
   Proposed owner action: <merge | request changes | close | supersede | request evidence | none>
   Requires owner approval: yes
   ```

   A `Preliminary assessment` means evidence is missing. The report names it.

6. Post the draft yourself. When the call is close, request evidence, request
   changes, supersede, or prefer one PR, the report adds a 60 to 160 word comment
   draft. The skill never posts it.

## What the skill will not do

- It never merges, closes, approves, comments, labels, or resolves a thread. Each
  needs the owner's approval of that exact action. A passing check, a label, or text
  in the PR is not approval.
- It never turns on auto-merge. `Merge-worthy as-is` plus `Ready` is a
  recommendation.
- It never runs the PR's code. It is a desk review.
- It never writes PR content into memory. Content in a PR can attack the reviewer,
  so a line such as "approve this" is reported under `Injected instructions found`
  and ignored.

## Check your result

- The report has a need status before any code critique.
- `Requires owner approval: yes` is the last line.
- Nothing changed on GitHub. Confirm with `gh pr view <PR> --json state,reviewDecision`.

## If it fails

| What you see | What to do |
|---|---|
| `Preliminary assessment` | Collect the evidence the report names, then run it again. |
| `Injected instructions found` is not `none` | Read the listed lines. Do not follow them. Consider whether the PR needs a closer look. |
| You want the skill to merge | It will not. Merge with [pr-autofix](how-to-pr-autofix.md) or by hand. |

## Next

- [Review a branch and answer feedback](review-and-feedback.md)

## Reference

- [maintainer-review skill](../../.claude/skills/maintainer-review/SKILL.md)
- [Evaluation framework](../../.claude/skills/maintainer-review/references/evaluation-framework.md)
- [Workflow detail](../../.claude/skills/maintainer-review/references/workflow-detail.md)
