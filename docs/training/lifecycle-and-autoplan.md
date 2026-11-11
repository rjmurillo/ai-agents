# Take one change from /spec to /ship, and route requests with /autoplan

## Goal

You will route five requests with `/autoplan`, then take one small change through `/spec`, `/plan`, `/build`, `/test`, `/review`, and `/ship`. This page is for contributors.

You know it worked when two things are true:

- Five calls to the route resolver print the `kind` you predicted.
- Your branch ends in a `/review` PASS marker commit, `validate_review_marker.py` prints `[PASS]`, and `/ship` reports `RESULT: SHIPPED` with a pull request link.

This is a teaching run. `/autoplan` would size the example change as Trivial and skip `/spec` and `/plan`. We run every phase once so you see what each one produces. Step 11 shows what to drop on real work.

## Before you start

- A clean checkout of this repository with `main` up to date. Set up first with [installation](../installation.md) and [getting started](../getting-started.md).
- Claude Code with the checkout open. The steps run repo scripts, so a plugin-only install is not enough.
- `uv` and `git` on your path.
- GitHub access for `/ship`, which opens the pull request for you. (`/ship` also supports Azure DevOps. This page shows GitHub.)

Other docs cover the same ground. We link them and do not repeat them:

- [Getting started](../getting-started.md) lists 7 phases. It splits `/spec` into the Grill Me interview and the PRD-to-spec step.
- [Lifecycle commands](../workflow-commands.md) lists the 6 commands. This page follows the 6 commands.
- [Plan, implement, and review with a team of agents](../plan-implement-review.md) compares this toolkit with other agent setups.

## Steps

**Part 1: route a request.**

1. **Know what the router does.** `/autoplan` is the front door. You give it a request that names no skill. It picks one destination: a skill, a lifecycle command, or an agent chain. It runs that route and ends with one summary block: the route taken, the decisions it made for you, any open question, and the evidence.

   The first match wins. The full rules are in [Precedence](../../.claude/skills/autoplan/SKILL.md#precedence).

   1. You named an installed skill or command. The router steps aside.
   2. The request matches a row in the routing table.
   3. A single-domain request misses the table. The resolver script picks a specialist.
   4. A feature, bug, or shipping request has no specialist. The router uses the lifecycle chain.
   5. The work is multi-domain or multi-agent. The router hands off to `orchestrator`.

   The router never routes to itself. The orchestrator never calls the router back. [ADR-078](../../.project-toolkit/architecture/ADR-078-autoplan-orchestrator-router-boundary.md) states the rule: autoplan routes, orchestrator coordinates specialists.

2. **Size the work.** For a feature, bug, or ship request, the router picks the smallest honest tier ([Phase 1](../../.claude/skills/autoplan/SKILL.md#phase-1-classify)).

   | Tier | Signal | Chain |
   |------|--------|-------|
   | Trivial | One known file, no contract change | Fix, test, commit |
   | Standard | Bounded change on an existing capability | `/build`, `/test`, `/review`, `/ship` |
   | Feature | New capability, new module, or unclear requirements | `/spec`, `/plan`, then the Standard chain |

   When two tiers fit, it starts one tier down. It moves up when evidence says so, such as failing tests or a growing diff.

3. **Predict, then ask the resolver.** The resolver script backs routing step 3. It reads the `routing.intents` list in each front-door skill's `SKILL.md` and prints one JSON line. It also reports an explicit skill name and multi-domain marker phrases. It opens no network connection.

   We call it directly so you can see every kind. In a real run, the router checks its routing table first. A request such as "add a retry" also matches the table row for building a feature. The resolver runs only when no row matches.

   Write down your guess for each request, then run it from the repository root. The first `uv run` in a fresh checkout prints environment setup lines before the JSON. Ignore them.

   ```bash
   uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "add retry to the webhook sender"
   ```

   ```text
   {"candidates": [], "kind": "none", "rationale": "no explicit reference, multi-domain marker, or intent match", "route": null}
   ```

   `none` means no specialist fits. The router falls through to the lifecycle chain, sized by the tier table.

   ```bash
   uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "audit our CLI for developer friction"
   ```

   ```text
   {"candidates": ["project-toolkit:dx-review"], "kind": "specialist", "rationale": "matched intents: developer friction", "route": "project-toolkit:dx-review"}
   ```

   `specialist` means one skill matched. The router invokes it.

   ```bash
   uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "use the review skill on my diff"
   ```

   ```text
   {"candidates": ["project-toolkit:review"], "kind": "explicit", "rationale": "explicit skill reference: project-toolkit:review", "route": "project-toolkit:review"}
   ```

   `explicit` means your request already named the skill.

   ```bash
   uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "coordinate multiple agents across the repo to migrate every service"
   ```

   ```text
   {"candidates": ["orchestrator"], "kind": "orchestrator", "rationale": "multi-domain marker: multiple agents", "route": "orchestrator"}
   ```

   `orchestrator` means a multi-domain marker phrase fired. The router starts `Task(subagent_type="orchestrator")`.

   ```bash
   uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "/autoplan add a retry to the sync job"
   ```

   ```text
   {"candidates": [], "kind": "none", "rationale": "dropped self-reference `project-toolkit:autoplan`; no explicit reference, multi-domain marker, or intent match", "route": null}
   ```

   The router drops its own name and resolves the rest. The fifth kind, `ambiguous`, lists candidates and asks you to pick. We have no stable request that triggers it, so this page does not show one.

4. **Name a skill to skip the router.** Type the skill or its slash command, such as `/review` or `/spec Add a retry to the webhook sender`. Nothing reroutes you. Your choice beats every table row. Do not name a skill to dodge a question the router would stop and ask you. Those stops are on purpose: architecture, new ADRs, breaking changes, security posture, and anything external or irreversible ([Phase 3](../../.claude/skills/autoplan/SKILL.md#phase-3-execute-with-defaults)).

**Part 2: take one change through the lifecycle.**

5. **Pick the change and cut a branch.** We use a real defect. `docs/workflow-commands.md` says `/ship` runs five pre-flight checks. The [ship skill](../../.claude/skills/ship/SKILL.md) defines four: pipeline, security, reviewed, and tests. Confirm both claims:

   ```bash
   grep -n "pre-flight checks (pipeline" docs/workflow-commands.md
   grep -n "Run all 4 pre-flight" .claude/skills/ship/SKILL.md
   ```

   ```text
   186:1. Runs 5 pre-flight checks (pipeline, security, review, tests, standards)
   85:Task(subagent_type="devops"): You are a release engineer. Run all 4 pre-flight checks below, branching by the `host`, `mode`, and `pr` set in Mode Detection. Report pass/fail for each with specific evidence. Any failure blocks shipping.
   147:1. Run all 4 pre-flight checks, branching by `host`, `mode`, and `pr`.
   ```

   If the first command prints nothing, someone already fixed this. Pick another doc claim that disagrees with a skill and use it in place of ours. Every step below stays the same.

   `docs/getting-started.md` repeats the same five-check list. In `/spec`, decide whether it is in scope. We keep it out and note it in the pull request.

   Cut a branch from current `main`. Never commit to `main`.

   ```bash
   git fetch origin
   git switch -c docs/fix-preflight-count origin/main
   git branch --show-current
   ```

   ```text
   docs/fix-preflight-count
   ```

6. **Ask /autoplan which way to go (optional).** Type the request with no skill name:

   ```text
   /autoplan docs/workflow-commands.md says /ship runs 5 pre-flight checks. The ship skill defines 4. Make the doc match the skill.
   ```

   Expect a Trivial tier: fix, test, commit. To follow the full loop, name each skill yourself from here.

7. **/spec: write down what done means.**

   ```text
   /spec docs/workflow-commands.md says /ship runs 5 pre-flight checks. The ship skill defines 4. Make the doc match the skill.
   ```

   The [spec skill](../../.claude/skills/spec/SKILL.md) runs a blocking First Principles gate first. It asks six questions: who asked, what the workaround is, who is blocked, the narrowest fix, the evidence, and whether it still makes sense at 10x. Answer each in plain words. The gate checks answers for hedge phrases, and a failed check can stop the spec. A memory gate then searches prior work and halts if the question is already answered.

   It produces a requirements document: problem statement, numbered acceptance criteria, out-of-scope items, and open questions. The spec generator writes durable files to these paths:

   - `.project-toolkit/specs/requirements/REQ-NNN-<title>.md`
   - `.project-toolkit/specs/design/DESIGN-NNN-<title>.md`
   - `.project-toolkit/specs/tasks/TASK-NNN-<title>.md`

   The skill's [Output section](../../.claude/skills/spec/SKILL.md#output) lists every section. For this change, write acceptance criteria you can test with `grep`: the doc says 4, and it lists the same four checks as the skill.

8. **/plan: split the work.**

   ```text
   /plan
   ```

   The [plan skill](../../.claude/skills/plan/SKILL.md) reads the spec. It returns milestones with exit criteria, atomic tasks sized S, M, or L, a dependency graph, a risk register, and deferred items. The `execution-plans` skill saves the plan under `.project-toolkit/plans/active/<slug>.md`. With no spec, `/plan` sends you back to `/spec`.

9. **/build: make the change.**

   ```text
   /build Fix the pre-flight count in docs/workflow-commands.md
   ```

   The [build skill](../../.claude/skills/build/SKILL.md) works in thin slices, test first, with atomic commits. A doc change has no unit test, so your check is the `grep` from step 5. Four exit gates must come back clean: code qualities, taste lints, the documentation gate, and the orphan reference check. A failed gate stays failed. See [Mandatory Exit Gates](../../.claude/skills/build/SKILL.md#mandatory-exit-gates).

   The finished diff should look like this. We applied the edit by hand on a throwaway branch of `main` to capture the output. Your agent may word it differently.

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

   The build commits for you. The message follows `type(scope): description`, for example `docs(workflow-commands): match /ship pre-flight count to the skill`.

10. **/test, then /review.** Run the test gates:

    ```text
    /test
    ```

    The [test skill](../../.claude/skills/test/SKILL.md) has six gates: functional, non-functional, security, DevOps, developer experience, and observability. It classifies the diff first and prints `PR TYPE: [type]. Running gates: [list].`. A diff of only `*.md` files is type DOCS, which runs Gate 5 only. Each gate prints `VERDICT: PASS`, `WARN`, or `CRITICAL_FAIL`. Gate 5 can also print `ERROR`. The overall verdict is `CRITICAL_FAIL` if any gate fails or reports `ERROR`.

    Run the Markdown check yourself too. It auto-fixes files, so run `git status --short` after it. If it lists a change, commit it before `/review`, because `/ship` fails on a dirty tree.

    ```bash
    uv run python scripts/validation/pre_pr.py --markdown-lint-only docs/workflow-commands.md
    echo "exit $?"
    ```

    ```text
    Auto-fixing 1 selected markdown file(s)...
    exit 0
    ```

    Then run the full repo gate. It takes a few minutes. Fix every BLOCKING finding and commit the fix:

    ```bash
    uv run python scripts/validation/pre_pr.py
    ```

    Now review:

    ```text
    /review
    ```

    The [review skill](../../.claude/skills/review/SKILL.md) runs a Stage-1 spec-compliance gate first. If it returns `CRITICAL_FAIL`, the review stops and the other axes show `SKIPPED`. Otherwise it picks Stage-2 axes by risk, and `analyst` always runs. It prints one row per axis and a `FINAL VERDICT`. Each finding has a severity (Critical, Important, or Suggestion), a `file:line` location, and a one-sentence fix.

    On a PASS, the skill writes a marker: an empty commit on top of the code you reviewed. The message holds the report and two trailers. This is the shape of a marker written by an earlier `/review` run in this repository. That commit may not exist in your clone:

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

    Your SHAs and axis list will differ. A new code commit on top of the marker makes it stale. A clean merge of `origin/main` on top does not. Check it:

    ```bash
    uv run python .claude/skills/review/scripts/validate_review_marker.py --ref HEAD
    ```

    On a valid marker it prints one line like this. The SHA is the reviewed commit, so yours differs:

    ```text
    [PASS] reviewed: /review@spec-compliance,analyst binds 38b0caa6b863 (2 axis/axes)
    ```

    On a branch with no marker, HEAD is an ordinary commit and the check fails:

    ```text
    [FAIL] HEAD (a6291bbba6d3) changes files; a review marker must be an empty commit whose Reviewed-By trailer names its parent. Re-run /review after the code tip is ready.
    ```

11. **Know what you can drop.** The rules come from the skills. We did not invent them.

    | Phase | Can you drop it? | Why |
    |-------|------------------|-----|
    | `/spec` | Yes, for a Trivial or Standard change. | [Phase 1](../../.claude/skills/autoplan/SKILL.md#phase-1-classify) starts the Feature tier at `/spec`. Keep it for a new capability, a new module, or unclear requirements. |
    | `/plan` | Yes, for a Trivial or Standard change. | Only the Feature tier includes it. With no `/spec` output, `/plan` sends you back to `/spec` ([plan skill](../../.claude/skills/plan/SKILL.md)). |
    | `/build` | No, for a code change. | Its four exit gates are hard preconditions for done. |
    | `/test` | Not the phase. Some gates skip themselves. | A DOCS diff runs Gate 5 only. A code diff runs all six gates. |
    | `/review` | No, before `/ship` on your own branch. | The `/ship` reviewed check needs the marker. |
    | `/ship` | Only if you open the pull request with `push-pr`. | `push-pr` skips the pre-flight checks. Use it only when you do not want that evidence. |

12. **/ship: open the pull request.**

    ```text
    /ship
    ```

    The [ship skill](../../.claude/skills/ship/SKILL.md) detects your host and mode, then runs four pre-flight checks: pipeline, security, reviewed, and tests. Any failure blocks the ship. With no pull request yet, the pipeline check is deferred, then checked again once the pull request exists. It ends with a report in this shape:

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

    On a branch you own, you want `RESULT: SHIPPED` and a link. `VALIDATED` is what a contributor gets on someone else's branch: checks ran, and nothing was created or merged.

    Then stop. [ADR-105](../../.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md) says a task is terminal when every requested deliverable meets its contract and no blocker remains. For this page, we read `RESULT: SHIPPED` with a pull request link as that point. Put follow-up ideas in the `NEXT:` field. Do not keep polishing.

## Check your result

Part 1 passes when the five resolver calls print the `kind` values `none`, `specialist`, `explicit`, `orchestrator`, and `none`, and each exits 0:

```bash
uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "audit our CLI for developer friction" > /dev/null; echo "exit $?"
```

```text
exit 0
```

Now make up two requests of your own. Predict the `kind`, then run them. A wrong guess teaches more than a right one.

Part 2 passes when you run these on your branch:

```bash
git log -1 --format='%(trailers:key=Reviewed-By,valueonly)'
uv run python .claude/skills/review/scripts/validate_review_marker.py --ref HEAD
git branch --show-current
```

- The first command prints a `/review@... on <sha>` line.
- The second prints `[PASS]`.
- The third prints `docs/fix-preflight-count`.
- The `/ship` report says `RESULT: SHIPPED` and shows a pull request link.

If it fails, look here first:

- **`python3` prints a PyYAML error.** Bare `python3` often lacks PyYAML, and the resolver exits 2 with `error: missing required module: yaml (PyYAML). Read skill descriptions directly instead of running this resolver.` Use `uv run python` from the repository root. With no Python, read each skill's `description` field and pick the closest match ([Phase 2c](../../.claude/skills/autoplan/SKILL.md#phase-2c-resolver-ambiguity-from-a-home-repo-run)).
- **The resolver returns `none` for a request you expected to match.** It only matches front-door skills that list `intents`. A table row in `SKILL.md` can route a request the resolver does not match. Read [Phase 2](../../.claude/skills/autoplan/SKILL.md#phase-2-route) before you decide the router is wrong.
- **`/spec` stops at the First Principles gate.** A hedged or empty answer blocks it. Name a real person or system, a real workaround, and a real signal. If you cannot, the change may not be worth making yet.
- **`/spec` halts at the memory gate.** The search found the question already answered. Read the answer it cites.
- **`/plan` asks for a spec.** Run `/spec` first, or say you accept an ungated plan.
- **A `/build` exit gate fails.** Fix the cause in your diff and rerun that gate. Do not add suppression comments or change baselines.
- **`/test` returns `CRITICAL_FAIL`.** A gate failed or could not run. Fix it, then rerun `/test`.
- **`/review` stops after Stage 1.** The diff does not meet your acceptance criteria. Fix the unmet criterion and rerun `/review`.
- **`validate_review_marker.py` prints `[FAIL]`.** HEAD is not a marker, or a code commit landed after it. Rerun `/review`.
- **`/ship` returns `BLOCKED`.** The report names the failing check. Fix it on the branch and rerun.

## Next

The next page in reading order is the review and PR feedback loop (`review-and-pr-feedback.md`, #7206). It has no page yet. See the [training index](README.md) for pages that have landed.

Reference sources this page relies on:

- Skills: [autoplan](../../.claude/skills/autoplan/SKILL.md), [spec](../../.claude/skills/spec/SKILL.md), [plan](../../.claude/skills/plan/SKILL.md), [build](../../.claude/skills/build/SKILL.md), [test](../../.claude/skills/test/SKILL.md), [review](../../.claude/skills/review/SKILL.md), and [ship](../../.claude/skills/ship/SKILL.md).
- Decisions: [ADR-078](../../.project-toolkit/architecture/ADR-078-autoplan-orchestrator-router-boundary.md) and [ADR-105](../../.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md).
- Scripts: [`resolve_route.py`](../../.claude/skills/autoplan/scripts/resolve_route.py) and [`validate_review_marker.py`](../../.claude/skills/review/scripts/validate_review_marker.py).
- Related docs: [lifecycle commands](../workflow-commands.md), [autonomous issue development](../autonomous-issue-development.md), and [orchestrator routing algorithm](../orchestrator-routing-algorithm.md).
