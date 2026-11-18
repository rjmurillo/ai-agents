# debug agent

The `debug` agent finds and fixes a bug through four phases: assessment, investigation, resolution, and quality assurance. It hands back a fix, the root cause, and preventive measures.

## When to use it

- You have an error message, stack trace, or failure report and need the root cause.
- You see behavior that differs from what you expect and need a reproduction.
- You want a narrow fix with a regression test and a final report.

## When not to use it

- The fix is large or complex: use [`implementer`](implementer.md) instead.
- You need deeper research into a cause before any change: use [`analyst`](analyst.md) instead.
- The fix is done and needs regression testing: use [`qa`](qa.md) instead.
- You found a security vulnerability: use [`security`](security.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
debug: tests/test_checkout.py fails with a KeyError on the coupon field, find the root cause and fix it
```

In GitHub Copilot CLI:

```bash
copilot --agent debug --prompt "tests/test_checkout.py fails with a KeyError on the coupon field, find the root cause and fix it"
```

In VS Code or Visual Studio Copilot Chat:

```text
@debug tests/test_checkout.py fails with a KeyError on the coupon field, find the root cause and fix it
```

## What you get

A final report that summarizes the fix and its root cause and documents preventive measures. The agent writes reproduction steps before it attempts a fix. It adds or updates tests to prevent the bug from returning. It uses the text status markers `[PASS]`, `[FAIL]`, `[WARNING]`, `[COMPLETE]`, and `[BLOCKED]`.

## Advanced use

The four phases, in order:

1. Assessment: gather context from errors and recent changes, then reproduce and triage. If a fix is not merited, the agent reports and stops.
2. Investigation: trace execution paths, check for null references, off-by-one errors, and race conditions, then form ranked hypotheses.
3. Resolution: take the narrowest change that closes every open problem in the report, then run the tests, the original reproduction, and broader suites.
4. Quality assurance: review the fix for maintainability, add regression tests, and write the report.

The agent stays on the specific bug. It hands off as follows:

| Target | When | Purpose |
| --- | --- | --- |
| `implementer` | Complex fix needed | Apply resolution |
| `analyst` | Deeper investigation required | Research root cause |
| `qa` | Fix verified | Regression testing |
| `security` | Security vulnerability found | Security assessment |

A multi-step prompt:

```text
debug: reproduce the flaky failure in tests/test_export.py, list ranked hypotheses, fix the most likely one with the smallest change, then run the full test file and report the root cause.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`implementer`](implementer.md): applies complex fixes.
- [`analyst`](analyst.md): researches root causes in depth.
- [`qa`](qa.md): runs regression testing after the fix.
- [`security`](security.md): assesses security vulnerabilities found during debugging.
- Source template: [`debug.shared.md`](../../templates/agents/debug.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
