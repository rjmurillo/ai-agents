# Your first change: from /spec to /ship

## Goal

Take one small, real change through all six lifecycle commands: `/spec`, `/plan`, `/build`, `/test`, `/review`, and `/ship`.

Outcome you can check: your branch ends in a `/review` PASS marker commit that binds your code, `validate_review_marker.py` prints `[PASS]`, and `/ship` reports `RESULT: SHIPPED` with a pull request link.

This is a teaching run. `/autoplan` would size this change as Trivial and skip `/spec` and `/plan`. We run every phase once so you see what each one produces. [Skip a phase](#when-to-skip-a-phase) shows what to drop on real work.

## Before you start

- A clean checkout of this repository with `main` up to date. If you have not set up yet, see [installation](../installation.md) and [getting started](../getting-started.md).
- Claude Code with the `project-toolkit` plugin, or the checkout opened directly. The lifecycle commands are skills, so they run the same way in both.
- `uv` and `git` on your path.
- GitHub access for `/ship`. The skill opens the pull request for you.

Two docs describe the same pipeline, and neither is repeated here:

- [Getting started](../getting-started.md) lists 7 phases. It splits `/spec` into the Grill Me interview and the PRD-to-spec step.
- [Lifecycle commands](../workflow-commands.md) lists the 6 commands. This tutorial follows the 6 commands.
- [Plan, implement, and review with a team of agents](../plan-implement-review.md) compares this toolkit with other agent setups.

## Steps

### 1. Pick the change and cut a branch

We use a real defect. `docs/workflow-commands.md` says `/ship` runs five pre-flight checks. The [ship skill](../../.claude/skills/ship/SKILL.md) defines four: pipeline, security, reviewed, and tests.

Confirm both claims:

```bash
grep -n "pre-flight checks (pipeline" docs/workflow-commands.md
grep -n "Run all 4 pre-flight" .claude/skills/ship/SKILL.md
```

```text
186:1. Runs 5 pre-flight checks (pipeline, security, review, tests, standards)
85:Task(subagent_type="devops"): You are a release engineer. Run all 4 pre-flight checks below, branching by the `host`, `mode`, and `pr` set in Mode Detection. Report pass/fail for each with specific evidence. Any failure blocks shipping.
147:1. Run all 4 pre-flight checks, branching by `host`, `mode`, and `pr`.
```

If the first command prints nothing, someone already fixed this. Pick another doc claim that disagrees with a skill, and use it in place of ours. Every step below stays the same.

Cut a branch from current `main`:

```bash
git fetch origin
git switch -c docs/fix-preflight-count origin/main
git branch --show-current
```

```text
docs/fix-preflight-count
```

Never commit to `main`. The universal rules forbid it.

### 2. Ask /autoplan which way to go (optional)

Type the request with no skill name:

```text
/autoplan docs/workflow-commands.md says /ship runs 5 pre-flight checks. The ship skill defines 4. Make the doc match the skill.
```

`/autoplan` ends with one summary block: the route it took, the decisions it made for you, any open question, and the evidence. For this request, expect a Trivial tier: fix, test, commit. See [Route a request with /autoplan](how-to/route-a-request.md) for how it decides.

To follow the full loop, name each skill yourself from here. Naming a skill bypasses the router.

### 3. /spec: write down what done means

```text
/spec docs/workflow-commands.md says /ship runs 5 pre-flight checks. The ship skill defines 4. Make the doc match the skill.
```

The [spec skill](../../.claude/skills/spec/SKILL.md) runs a blocking First Principles gate first. It asks six questions: who asked, what the workaround is, who is blocked, the narrowest fix, the evidence, and whether it still makes sense at 10x. Answer each one in plain words. The gate checks answers for hedge phrases, and a failed check can stop the spec. A memory gate then searches prior work and halts if the question is already answered.

What it produces: a requirements document with a problem statement, numbered acceptance criteria, out-of-scope items, and open questions. The spec generator writes durable files to these paths:

- `.project-toolkit/specs/requirements/REQ-NNN-<title>.md`
- `.project-toolkit/specs/design/DESIGN-NNN-<title>.md`
- `.project-toolkit/specs/tasks/TASK-NNN-<title>.md`

The skill's [Output section](../../.claude/skills/spec/SKILL.md#output) lists every section. For this change, write acceptance criteria you can test with `grep`: the doc says 4, and the doc lists the same four checks as the skill.

### 4. /plan: split the work

```text
/plan
```

The [plan skill](../../.claude/skills/plan/SKILL.md) reads the spec. It returns milestones with exit criteria, atomic tasks sized S, M, or L, a dependency graph, a risk register, and deferred items. The `execution-plans` skill saves the plan under `.project-toolkit/plans/active/<slug>.md`.

If you have no spec, `/plan` sends you back to run `/spec` first. Planning an idea nobody gated creates work that may not matter.

### 5. /build: make the change

```text
/build Fix the pre-flight count in docs/workflow-commands.md
```

The [build skill](../../.claude/skills/build/SKILL.md) works in thin slices, test first, with atomic commits. A doc change has no unit test, so your check is the `grep` from step 1.

The finished diff should look like this. We applied the edit by hand on a throwaway branch of `main` to capture the output:

```bash
git diff --stat
git diff | grep -E '^[+-][^+-]'
```

```text
 docs/workflow-commands.md | 3 +--
 1 file changed, 1 insertion(+), 2 deletions(-)
-1. Runs 5 pre-flight checks (pipeline, security, review, tests, standards)
+1. Runs 4 pre-flight checks (pipeline, security, review, tests)
-| Standards | Golden principles and taste lints pass | Yes |
```

Your agent may word it differently. Four exit gates must come back clean before `/build` is done: code qualities, taste lints, the documentation gate, and the orphan reference check. A failed gate stays failed. The skill lists them under [Mandatory Exit Gates](../../.claude/skills/build/SKILL.md#mandatory-exit-gates).

The build commits for you. The message follows `type(scope): description`:

```text
docs(workflow-commands): match /ship pre-flight count to the skill
```

### 6. /test: prove it works

```text
/test
```

The [test skill](../../.claude/skills/test/SKILL.md) has six gates: functional, non-functional, security, DevOps, developer experience, and observability. It first classifies the diff and prints `PR TYPE: [type]. Running gates: [list].`. A diff of only `*.md` files is type DOCS. DOCS runs Gate 5, the developer experience and documentation accuracy gate. The other gates are skipped on purpose.

Each gate prints `VERDICT: PASS`, `WARN`, or `CRITICAL_FAIL`. The overall verdict is `CRITICAL_FAIL` if any gate fails or cannot run. A gate that could not run proved nothing.

Run the Markdown check yourself too. It auto-fixes, so look at `git status` after:

```bash
uv run python scripts/validation/pre_pr.py --markdown-lint-only docs/workflow-commands.md
echo "exit $?"
```

```text
Auto-fixing 1 selected markdown file(s)...
exit 0
```

The first `uv run` in a fresh checkout prints environment setup lines before this.

### 7. /review: get a bound verdict

```text
/review
```

The [review skill](../../.claude/skills/review/SKILL.md) runs a Stage-1 spec-compliance gate first. If it returns `CRITICAL_FAIL`, the review stops there and the other axes are marked `SKIPPED`. Otherwise it picks Stage-2 axes by risk. The `analyst` axis always runs. It prints a table with one row per axis and a `FINAL VERDICT`. Findings carry a severity (Critical, Important, or Suggestion), a `file:line` location, and a one-sentence fix.

On a PASS, the skill writes a marker: an empty commit on top of the code you reviewed. Its message holds the report and two trailers. This is the shape of a real marker from this repository's history:

```text
review: /review PASS marker

--- review report ---
Reviewed-SHA: 38b0caa6b863a2de9d81328f0dcdfdc4ab659c66
spec-compliance: PASS
analyst: PASS
--- end review report ---

Reviewed-By: /review@spec-compliance,analyst on 38b0caa6b863a2de9d81328f0dcdfdc4ab659c66
Review-Artifact: sha256:3add82e37792ca2e07b1c1047dbdd21d326647540bb9777ac0fd93d314386f45
```

Your SHAs and axis list will differ. Any new commit on top of the marker makes it stale. Check it:

```bash
python3 .claude/skills/review/scripts/validate_review_marker.py --ref HEAD
```

On a valid marker it prints one line like this. The SHA is the reviewed commit, so yours differs:

```text
[PASS] reviewed: /review@spec-compliance,analyst binds 38b0caa6b863 (2 axis/axes)
```

On a branch with no marker, HEAD is an ordinary commit and the check fails:

```text
[FAIL] HEAD (b959011e3f60) changes files; a review marker must be an empty commit whose Reviewed-By trailer names its parent. Re-run /review after the code tip is ready.
```

### 8. /ship: open the pull request

```text
/ship
```

The [ship skill](../../.claude/skills/ship/SKILL.md) detects your host and mode, then runs four pre-flight checks: pipeline, security, reviewed, and tests. Any failure blocks the ship. With no pull request yet, the pipeline check is deferred. It is checked again once the pull request exists.

It ends with a report in this shape:

```text
HOST: github|ado
MODE: owner|contributor
PR-AT-PREFLIGHT: none|#<number>
PRE-FLIGHT:
  Pipeline:  PASS|FAIL|DEFERRED->PASS|DEFERRED->FAIL (evidence)
  Security:  PASS|FAIL (evidence)
  Reviewed:  PASS|FAIL|ADVISORY (evidence)
  Tests:     PASS|FAIL (evidence)
RESULT: SHIPPED|VALIDATED|BLOCKED
PR: [link]
WARNINGS: [non-blocking concerns]
NEXT: [monitoring, follow-up items]
```

On a branch you own, you want `RESULT: SHIPPED` and a link. `VALIDATED` is what a contributor gets on someone else's branch. It means checks ran and nothing was created or merged.

Before you leave, run the repo gate the pull request will face:

```bash
uv run python scripts/validation/pre_pr.py
```

Fix every BLOCKING finding. Then stop. [ADR-105](../../.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md) says a task is terminal when every requested deliverable meets its contract and no blocker remains. A shipped pull request is that point. Do not keep polishing.

## When to skip a phase

The rules come from the skills. We did not invent them.

| Phase | Skip it when | Do not skip it when |
|-------|--------------|---------------------|
| `/spec` | The tier is Trivial or Standard: a bounded change on a known capability ([autoplan Phase 1](../../.claude/skills/autoplan/SKILL.md#phase-1-classify)). | The change adds a capability, adds a module, or has unclear requirements. |
| `/plan` | Same as `/spec`. | The tier is Feature. With no `/spec` output, `/plan` sends you back to `/spec` ([plan skill](../../.claude/skills/plan/SKILL.md)). |
| `/build` | Not for a code change. | Always there: its four exit gates are hard preconditions for done. |
| `/test` | Do not skip the phase. Gates that do not apply skip themselves: a DOCS diff runs Gate 5 only. | The diff touches code. All six gates run. |
| `/review` | Not before `/ship` on your own branch. | Always there: the `/ship` reviewed check needs the marker. |
| `/ship` | Use `push-pr` instead only when you must open a pull request without the gates. | You want the pre-flight evidence. |

## Check your result

Run these on your branch before you close the tutorial:

```bash
git log -1 --format='%(trailers:key=Reviewed-By,valueonly)'
python3 .claude/skills/review/scripts/validate_review_marker.py --ref HEAD
git branch --show-current
```

You pass when:

- The first command prints a `/review@... on <sha>` line.
- The second prints `[PASS]`.
- The third prints `docs/fix-preflight-count`.
- The `/ship` report says `RESULT: SHIPPED` and shows a pull request link.

## If it fails

- **`/spec` stops at the First Principles gate.** A hedged or empty answer blocks it. Name a real person or system, a real workaround, and a real signal. If you cannot, the change may not be worth making yet.
- **`/spec` halts at the memory gate.** The search found the question already answered. Read the answer it cites.
- **`/plan` asks for a spec.** Run `/spec` first, or say you accept an ungated plan.
- **A `/build` exit gate fails.** Fix the cause in your diff and rerun that gate. Do not add suppression comments or change baselines.
- **`/test` returns `CRITICAL_FAIL`.** A gate failed or could not run. Fix it, then rerun `/test`.
- **`/review` stops after Stage 1.** The diff does not meet your acceptance criteria. Fix the unmet criterion and rerun `/review`.
- **`validate_review_marker.py` prints `[FAIL]`.** HEAD is not a marker, or a commit landed after it. Rerun `/review`.
- **`/ship` returns `BLOCKED`.** The report names the failing check. Fix it on the branch and rerun.

## Next

- [Route a request with /autoplan](how-to/route-a-request.md): how the router sizes work and when it hands off to the orchestrator.
- [Lifecycle commands](../workflow-commands.md): the full command reference.
- [Autonomous issue development](../autonomous-issue-development.md): run the same pipeline without a human in the loop.
- Sources: [spec](../../.claude/skills/spec/SKILL.md), [plan](../../.claude/skills/plan/SKILL.md), [build](../../.claude/skills/build/SKILL.md), [test](../../.claude/skills/test/SKILL.md), [review](../../.claude/skills/review/SKILL.md), [ship](../../.claude/skills/ship/SKILL.md), [autoplan](../../.claude/skills/autoplan/SKILL.md), [ADR-078](../../.project-toolkit/architecture/ADR-078-autoplan-orchestrator-router-boundary.md), [ADR-105](../../.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md).
