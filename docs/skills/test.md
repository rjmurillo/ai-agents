# test

Proves a change works across six gates: functional, non-functional, security, DevOps, developer experience and documentation, and observability. Each gate runs its own agent and returns a verdict. You get one overall verdict at the end.

## When to use it

- You finished `/build` and want evidence the change works.
- You want to know if a diff is ready for review.
- Trigger phrases: `prove this works`, `run the test gates`, `validate this change`, `is this ready for review`.

## When not to use it

- You want to write the implementation or its first tests: use [`build`](build.md).
- You want to run pre-flight checks and open a PR: use [`ship`](ship.md).
- You want a pre-merge review of the diff: use [`review`](review.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:test the retry logic in the upload client
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/test the retry logic in the upload client`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /test skill to ...`.

With no argument, `test` tests the current branch diff against the base branch. It first classifies the diff by file type. It runs only the gates that apply, so no agent runs on a dimension the diff cannot touch.

## What you get

Each gate prints a block like this:

```text
GATE: Security
VERDICT: PASS|WARN|CRITICAL_FAIL
FINDINGS:
- [SEVERITY] (file:line) description: recommendation
```

Every finding cites `file:line`. Security findings also cite a CWE number. At the end you get a table with one row per gate and one overall verdict.

| Gate | Agent or skill | Checks |
| --- | --- | --- |
| 1 Functional | [`qa`](../agents/qa.md), plus [`code-qualities-assessment`](code-qualities-assessment.md) | Unit, integration, and acceptance coverage, edge cases, error paths |
| 2 Non-functional | [`analyst`](../agents/analyst.md) | Performance, scalability, reliability, complexity, maintainability |
| 3 Security | [`security`](../agents/security.md), plus [`security-scan`](security-scan.md) | Injection, authentication, secrets, input validation, dependencies |
| 4 DevOps | [`devops`](../agents/devops.md) | Pipeline impact, Actions security, shell quality, reproducible builds, artifacts |
| 5 DX and docs | [`orphan-ref-validator`](orphan-ref-validator.md), [`dx-review`](dx-review.md), [`doc-accuracy`](doc-accuracy.md) | Broken references, developer experience, documentation accuracy |
| 6 Observability | [`architect`](../agents/architect.md) | Logging, metrics, alerting, tracing, health checks |

Gate 5 can also return `ERROR`. The overall verdict is `CRITICAL_FAIL` if any gate fails or reports `ERROR`. It is `WARN` if any gate warns. Otherwise it is `PASS`. The skill hands the gate verdicts to [`quality-grades`](quality-grades.md) for the overall score.

## Advanced use

### Which gates run

Step 0 classifies changed files and prints `PR TYPE: [type]. Running gates: [list].`

| Type | Patterns | Gates |
| --- | --- | --- |
| CODE | `*.py`, `*.ps1`, `*.ts`, `*.js`, `*.cs` | 1 to 6 |
| WORKFLOW | `*.yml` under `.github/workflows/` | 1, 3, 4, 5 |
| CONFIG | `*.json`, `*.yaml` outside workflows | 3, 4, 5 |
| DOCS | `*.md`, `*.txt`, `*.rst` | 5 only |
| MIXED | A combination | Per-file rules |

Gate 5 runs for every type. A plugin manifest is a CONFIG file and still a developer interface. The Gate 5 trigger decides whether `dx-review` runs, not the file extension.

### Behavior to know

- A `CRITICAL_FAIL` in one gate does not stop the others. Findings add up.
- Gates run once, at the final head. During edits, run focused checks only.
- When a test fails, the skill forms a hypothesis before it changes code.
- If the diff touches Claude Code or Copilot CLI hooks, the skill loads `agent-harness-reference` and the portability campaign check. It requires unit coverage for translation plus a real-harness smoke test for each affected harness.
- If `/build` handed over a validation record, Gate 4 re-runs it against the changed paths. Exit `1` or `2` is `CRITICAL_FAIL`.

### Trigger scripts

Run these from the root of a checkout of this repository:

```bash
uv run python .claude/skills/test/scripts/dx_trigger.py --help
uv run python .claude/skills/test/scripts/doc_accuracy_trigger.py --help
```

| Script | Decides | Flags | Exit codes |
| --- | --- | --- | --- |
| `dx_trigger.py` | Whether Gate 5 runs `dx-review` | `--changed-path`, `--effect`, `--classifier` | `0` decision printed as JSON, `2` classifier could not load |
| `doc_accuracy_trigger.py` | Whether Gate 5 runs `doc-accuracy` | `--diff-base` (required), `--changed-path`, `--effect`, `--build-record`, `--classifier` | `0` decision printed as JSON, `2` classifier not loadable, blank diff base, or unreadable build record |

Both print a decision of `skip` or `activate` with a reason. On a skip, the gate records `DX REVIEW: SKIPPED` or `DOC ACCURACY: SKIPPED` and quotes the reason. An unknown `--effect` value fails closed.

The `dx_trigger.py` effects are `cli-surface`, `public-api`, `onboarding-flow`, `agent-behavior`, `user-task-docs`, and `contributor-workflow`.

### Extending it

A seventh gate needs a `## Gate 7` section, a row in the Step 0 table, and a row in the output table, all together. A project that scores differently swaps the one `quality-grades` call.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`build`](build.md): write the change before you test it.
- [`review`](review.md): run it after `test`.
- [`ship`](ship.md): run pre-flight and open the PR.
- Source: [`SKILL.md`](../../src/claude/skills/test/SKILL.md)
- Gate 5 procedure: [`doc-accuracy-gate.md`](../../src/claude/skills/test/references/doc-accuracy-gate.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
