# analyze

Runs a guided, multi-step analysis of a codebase. You get findings ranked by severity, each with file and line evidence, and a prioritized action plan.

## When to use it

- The investigation spans several files or components.
- You want an architecture review, a security assessment, or a code quality evaluation.
- You need findings prioritized by severity, with `file:line` evidence.
- You say `analyze this codebase`, `run security assessment`, `architecture review of this system`, `find code smells`, or `review code quality`.

## When not to use it

- You are checking one file or function, or the answer sits at a known location: read the code or search directly.
- You want to score one file's maintainability: use [`code-qualities-assessment`](code-qualities-assessment.md) instead.
- You want to scan for CWE-78 command injection patterns: use [`security-scan`](security-scan.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:analyze architecture review of the auth system
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/analyze`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /analyze skill to ...`.

The skill runs its script at once and follows the script's required actions. It does not explore first. At step 1 it delegates exploration to Explore agents, then you continue step by step to a final synthesis.

## What you get

Each script call prints guidance for one step. The workflow has these phases:

| Phase | Step | What happens |
| --- | --- | --- |
| Exploration | 1 | Explore agents map the codebase. |
| Focus selection | 2 | Areas are classified as architecture, performance, security, or quality, with priorities P1 to P3. |
| Investigation planning | 3 | You commit to files, questions, and hypotheses. |
| Deep analysis | 4 to N-2 | You read files and collect evidence with `file:line` references and quoted code. |
| Verification | N-1 | The plan from step 3 is audited for gaps. |
| Synthesis | N | Findings are grouped by severity (critical, high, medium, low), with systemic patterns and an action plan. |

Minimum steps by focus:

| Focus | Minimum steps |
| --- | --- |
| Architecture review | 6 |
| Security assessment | 7 to 9 |
| Code quality | 6 to 7 |
| Broad investigation | 9 to 12 |

## Advanced use

Run the script from the root of a checkout of this repository:

```bash
uv run python .claude/skills/analyze/scripts/analyze.py --step-number 1 --total-steps 6 --thoughts-file findings.md
```

| Flag | Meaning |
| --- | --- |
| `--step-number` | Current step. Starts at 1. |
| `--total-steps` | Estimated total. Minimum 6. Raise it as understanding grows. |
| `--thoughts` | Accumulated findings as inline text. |
| `--thoughts-file` | Path to a file with the accumulated findings, read as UTF-8. |

Give exactly one of `--thoughts` or `--thoughts-file`. The script exits 0 after it prints step guidance. It exits 1 when the step number is below 1, the total is below 6 or below the step, or the thoughts file is unreadable.

> [!WARNING]
> Use `--thoughts-file`, not `--thoughts`, for request-derived text. The shell expands `$(...)` and backticks inside a double-quoted `--thoughts "..."` value before the script runs. Write the text to a file with the Write tool, then pass the path.

Before step 1, the skill records the live default-branch revision with [`scripts/validation/live_revision_grounding.py`](../../scripts/validation/live_revision_grounding.py) and carries `grounded_sha` and `finding_status` into each finding that depends on repository state. A finding marked `STALE` or `UNVERIFIED` is never the sole basis for an issue. That helper lives in the upstream checkout only. A consumer install follows the manual fallback in the [`github`](github.md) skill.

When deep analysis meets conditions such as low test coverage, hard-to-test seams, retries, or schema evolution, the skill loads [`software-engineering-library`](software-engineering-library.md) and opens the matching reference before it recommends a fix. [`autoplan`](autoplan.md) routes bug and error triage requests here before `build`.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`code-qualities-assessment`](code-qualities-assessment.md): scores one file or module on five design qualities.
- [`security-scan`](security-scan.md): scans for CWE-78 command injection patterns.
- [`software-engineering-library`](software-engineering-library.md): deeper guidance the analysis loads on demand.
- [`autoplan`](autoplan.md): routes triage requests to this skill.
- Source: [`SKILL.md`](../../src/claude/skills/analyze/SKILL.md)
- References: [`strategy-ooda-loop.md`](../../src/claude/skills/analyze/references/strategy-ooda-loop.md), [`engineering-complexity-tiers.md`](../../src/claude/skills/analyze/references/engineering-complexity-tiers.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
