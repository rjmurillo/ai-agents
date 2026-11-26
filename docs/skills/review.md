# review

Reviews your branch or pull request before merge. It runs a spec-compliance gate first, then the review axes that match the risk of your diff, and gives you one final verdict with a findings table.

## When to use it

- You finished `/test` and want a verdict before you merge.
- You want the diff checked against the spec or the PR's acceptance criteria.
- Trigger phrases: `/review`, `/review BRANCH_OR_PR`, `review before merge`.

## When not to use it

- You want one quality check on its own: use [`code-qualities-assessment`](code-qualities-assessment.md), [`doc-accuracy`](doc-accuracy.md), [`golden-principles`](golden-principles.md), or [`taste-lints`](taste-lints.md) directly. For a full review, let `review` select them.
- You want to prove the change works: use [`test`](test.md).
- You want to run pre-flight checks and open the PR: use [`ship`](ship.md).
- You want to answer reviewer comments on a PR: use [`pr-review`](pr-review.md) or [`pr-comment-responder`](pr-comment-responder.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:review 1234
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/review 1234`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /review skill to ...`.

With no argument, `review` reviews the current branch against the base branch. It reads the base from `gh pr view --json baseRefName` and falls back to `main`.

## What you get

You get a findings table with one row per axis, a final verdict line, and an optional marker commit.

| Output | Details |
| --- | --- |
| Findings table | Columns: Axis, Verdict, Selection, Emoji, Summary. Skipped axes show their reason. |
| Final verdict | `PASS`, `WARN`, `CRITICAL_FAIL`, or `UNKNOWN`, merged from all axes. |
| Correctness row | An always-on `correctness` row from the code-review pass. |
| CodeQL status line | Printed under the table when the `security` axis ran. |
| Flagged notes | After round 1 only: findings that do not count toward the verdict. |
| Marker commit | An empty commit on top of the reviewed tip, written only on a PASS, or a WARN where every WARN was acknowledged. |

How the verdict forms:

- Each axis ends with a verdict line. An axis that crashes or prints something unparseable counts as `UNKNOWN`.
- Any failing token (`CRITICAL_FAIL`, `REJECTED`, `FAIL`, `NEEDS_REVIEW`, `NON_COMPLIANT`) gives `CRITICAL_FAIL`.
- Otherwise any `WARN` or `PARTIAL` gives `WARN`, then any `UNKNOWN`, `DID_NOT_RUN`, or unrecognized token gives `UNKNOWN`. All `PASS` gives `PASS`.
- `UNKNOWN` never hides a real finding. `WARN` plus `UNKNOWN` merges to `WARN`.

Hand-off (ADR-123): Writes `review-marker`. Next: [`ship`](ship.md). `metadata.inputs` and `metadata.outputs` in the skill's frontmatter declare the same data.

## Advanced use

### Stages

1. Stage 1 is the `spec-compliance` gate. A Stage-1 `CRITICAL_FAIL` stops the review. Every other axis shows `SKIPPED`. A Stage-1 `UNKNOWN` (no spec found) does not stop it.
2. Stage 2 runs the axes that `select_axes.py` picks from the changed paths and diff effects. `analyst` always runs. Callers can pin more axes.
3. Local-only axes (`code-qualities-assessment`, `doc-accuracy`, `golden-principles`, `taste-lints`) run as sibling skills after the canonical axes. In a repository without `.agents/governance/golden-principles.md`, a new shell script yields `WARN` on the `golden-principles` axis, not `FAIL`.
4. A deep review runs every canonical axis. Ask for a "deep" or "full" review, or run it as a pre-merge gate.

The canonical axes are `analyst`, `architect`, `qa`, `security`, `devops`, `roadmap`, `reliability`, `observability`, `agent-safety`, `decision-rigor`, and `code-quality`. Each has a prompt at `references/<axis>.md`.

### Rounds

`review` runs each axis once per invocation. If you chain "fix, then re-review", stop after 5 rounds. In round 5, `PASS` ships. Any other verdict goes to a human with every open finding. After round 1, only defects the diff introduced and unmet acceptance criteria count. The rest become flagged notes.

### The marker

A passing review writes an empty commit. Its body holds the review report. Its trailers are `Reviewed-By: /review@<axis-list> on <reviewed-tip-sha>` and `Review-Artifact: sha256:<digest>`. New code on top makes the marker stale. `ship` reads it.

### Scripts

Run these from the root of a checkout of this repository:

```bash
uv run python .claude/skills/review/scripts/select_axes.py --help
uv run python .claude/skills/review/scripts/validate_review_marker.py --help
uv run python .claude/skills/review/scripts/review_depth_tier.py --help
uv run python .claude/skills/review/scripts/validate_findings_scope.py --help
```

| Script | Purpose | Exit codes |
| --- | --- | --- |
| `select_axes.py` | Picks axes. Flags: `--changed-path`, `--effect`, `--pin`, `--deep`, `--references-dir`. Prints JSON. | `0` selection printed, `2` unknown pinned axis or no references directory |
| `validate_review_marker.py` | Checks the SHA-bound marker. Flags: `--ref`, `--base-ref`, `--require-axis`, `--digest REPORT_FILE`, `--repo-root`, `--references-dir`. | `0` valid, `1` missing, stale, or bad, `2` config error |
| `review_depth_tier.py` | Reads a diff on stdin and prints a depth tier as JSON. Flag: `--exclude GLOB`. | `0` tier printed, `2` no diff headers |
| `validate_findings_scope.py` | Marks findings outside the PR diff. Flags: `--worktree`, `--base-branch` (`main` or `origin/main`), `--text`, `--emit-adjusted-text`, `--frozen`. | `0` all in scope, or diff empty or unavailable, `1` some out of scope, `2` no input, or `--base-branch` names no commit (scope check did not run) |

The skill also ships `codeql_local_scan.py`, `codeql_prestep.py`, and `codeql_scanner_guard.py` for the CodeQL pre-step of the `security` axis.

### Other behavior

- If a host has no agent for an axis, `review` falls back to a general-purpose agent. The axis prompt drives the review.
- With no subagent tool, each axis runs in a fresh `claude -p` process, or else in your session. A review run only in your session never writes the marker.
- Every axis input starts with `CONTEXT_MODE: full`, `summary`, or `partial`. An axis cannot return `PASS` on evidence it never saw.
- When the `devops` axis runs on a diff that changes CI itself (a workflow, a composite action, or a script a workflow reads), it does not accept a green run as proof. It checks for coverage loss, events the pull request run never exercised, and other workflows that consume the change. It returns `WARN` when a gate is dropped without evidence of equivalent coverage, or when evidence cannot answer a check about changed behavior. By path, `review` selects `devops` for CI files such as those under `.github/workflows/` and `.github/actions/`. A script-only change reaches it through a diff effect, a pin, or a deep review. The method is in [`ci-change-validation.md`](../../src/claude/skills/review/resources/ci-change-validation.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`test`](test.md): run it before `review`.
- [`ship`](ship.md): runs pre-flight checks and requires the review marker.
- [`pr-review`](pr-review.md): answers review comments and gives a completion-gate verdict.
- [`analyst`](../agents/analyst.md): the axis that always runs.
- Source: [`SKILL.md`](../../src/claude/skills/review/SKILL.md)
- Axis prompts: [`spec-compliance.md`](../../src/claude/skills/review/references/spec-compliance.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
