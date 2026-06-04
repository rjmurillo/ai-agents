# When to Use the Lifecycle Commands

This is a fitness guide. It maps task shapes to the lifecycle commands
(`/spec`, `/plan`, `/build`, `/test`, `/review`, `/ship`) so you run the right
phases for the work in front of you and skip the ones that add cost without
value.

The full chain (`/spec` to `/plan` to `/build` to `/test` to `/review` to
`/ship`) is the default for a new feature. It is overhead for a typo fix. The
question is not "is the lifecycle good?" It is "which subset fits this task?"

For the mechanics of each command, see
[docs/workflow-commands.md](./workflow-commands.md). For routing a task to the
right agents, see [docs/task-classification-guide.md](./task-classification-guide.md).
This guide sits above both: it tells you which phases to run before you route.

## How to read the fitness table

Each row is a task shape. The columns are the six lifecycle commands. A check
means "run this phase." A dash means "skip it for this shape." The rightmost
column gives a concrete example, several harvested from this repo's own
retrospectives under `.agents/retrospective/`.

| Task shape | /spec | /plan | /build | /test | /review | /ship | Concrete example |
|------------|:-----:|:-----:|:------:|:-----:|:-------:|:-----:|------------------|
| Scaled delivery (new feature, multi-file, multi-domain) | yes | yes | yes | yes | yes | yes | OAuth2 login flow with JWT tokens. New surface, new failure modes, cross-cutting auth concerns. Run the whole chain. |
| Compliance or guardrail change (governance, security gate, validator) | yes | yes | yes | yes | yes | yes | The push-guard framework in PR #1887. It changed a canonical contract. Skipping `/spec` against the real regex produced "confident incorrectness": 69 commits, 11+ review rounds. The spec phase exists to pin the contract before you build against it. |
| Defect mitigation (fix the fix, recurring failure) | yes | yes | yes | yes | yes | yes | PR #1989 reworked three earlier mitigations. It skipped the spec-against-current-state step, inherited a misdiagnosed root cause, and reproduced all three predecessor failure modes in 21 commits. A fix that already failed once needs the full lifecycle, not a shortcut. |
| Hotfix (single known defect, clear root cause, small blast radius) | no | no | yes | yes | yes | yes | "Fix null reference in `UserService.GetById`." Root cause is known, fix is local. Go straight to `/build`, prove it with `/test`, then `/review` and `/ship`. The Quick Fix Workflow in workflow-commands.md is this shape. |
| Customer-facing generated artifact (plugin manifest, hook script, CLI config) | yes | maybe | yes | yes | yes | yes | PR #2205 shipped a Copilot CLI `hooks.json` with a bad path. It passed structural tests but was never run in its target runtime. It wedged every customer environment for 33 days across 6 releases. `/test` here means a runtime-contract test, not a schema check. Never skip `/test` and `/review` on an artifact a customer installs. |
| Exploratory spike (research, "should we", unknown answer) | yes | maybe | no | no | no | no | "Should we migrate from REST to gRPC for internal services?" Run `/spec` to frame the question and search for prior art. Stop there, or run `/plan` to sketch the path. Do not `/build` until the question is answered. The Research-First Workflow in workflow-commands.md is this shape. |
| Documentation-only change (README, guide, comment) | no | no | yes | maybe | maybe | yes | This very file. No spec, no plan. Write it, run markdownlint as the test, optional review for accuracy, then ship. |
| Context black hole (vague scope, no acceptance criteria, "we should add") | yes | yes | no | no | no | no | A GitHub issue that says "we should add caching somewhere." Run `/spec` to force testable acceptance criteria out of the vagueness. Do not build until the scope is bounded. The ideation workflow (`docs/ideation-workflow.md`) feeds this. |

## Anti-recommendations: when the full lifecycle is overkill

The lifecycle is a cost. Each phase invokes agents, runs gates, and produces
artifacts. For some task shapes that cost buys nothing. Skip phases on purpose,
not by accident.

### Typo, comment, or single-line doc fix

Do not run `/spec`. Do not run `/plan`. There is no design decision here. Edit
the file, run markdownlint if it is markdown, and ship. Running the spec phase
on a typo trains you to skim past the spec phase when it matters.

### Reverting a known-bad commit

You already know what to do and why. The spec was written when the original
change landed. Revert, run `/test` to confirm the revert is clean, and ship.
The plan phase has nothing to decompose.

### Mechanical rename across files

A pure rename with tool support (no behavior change) does not need `/spec` or
`/plan`. It needs `/test` to prove behavior is unchanged and `/review` to
confirm the diff is a rename and nothing else. Refactoring discipline lives in
the review, not in a spec.

### Dependency version bump (patch or minor, no API change)

Bump the version, let `/test` catch breakage, ship. If the bump is a major
version with breaking API changes, it stops being this shape and becomes scaled
delivery: run the full chain.

### One-off throwaway script

A script you will run once and delete is tactical by design. Do not spec it, do
not plan it, do not write a test suite for a tool with a known short life. Write
it, run it, delete it. Mark it as throwaway so it does not accumulate.

## The deciding questions

When the task shape is not obvious, answer these in order:

1. **Is the answer known?** If you do not yet know what to build, run `/spec`
   first and stop. Building against an unknown answer is the context black hole.
2. **Is the contract or root cause already pinned?** If a canonical contract,
   schema, or root cause governs this change, `/spec` exists to read it before
   you build. Skipping it is how PR #1887 and PR #1989 spent dozens of commits.
3. **Does a customer install or run the output?** If yes, `/test` and `/review`
   are mandatory, and `/test` means running the artifact in its real runtime.
   PR #2205 is the cost of skipping this.
4. **Is the blast radius small and reversible?** If yes, you can drop `/spec`
   and `/plan` and start at `/build`. If no, run the full chain.

When in doubt, the cheap mistake is running one extra phase. The expensive
mistake is skipping `/test` or `/review` on something a customer touches.

## Related documents

- [docs/workflow-commands.md](./workflow-commands.md): mechanics of each command.
- [docs/task-classification-guide.md](./task-classification-guide.md): routing a
  task to the right agents once you know which phases to run.
- [docs/ideation-workflow.md](./ideation-workflow.md): turning vague ideas into
  bounded scope before the lifecycle starts.
- `.agents/retrospective/`: the incidents behind the examples in this guide.
