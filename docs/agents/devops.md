# devops agent

The `devops` agent designs and maintains CI/CD pipelines, build automation, and deployment workflows. It hands back pipeline configuration, infrastructure documentation, or a DevOps impact analysis for planning.

## When to use it

- You need a GitHub Actions or Azure Pipelines workflow designed or changed.
- You need a build system configured (MSBuild, NuGet, or the `dotnet` CLI).
- You need deployment automation, secrets handling, caching, matrix builds, or runner setup.
- A planner needs the DevOps impact of a feature.

## When not to use it

- You need application code written: use [`implementer`](implementer.md) instead.
- You need a security review of the pipeline: use [`security`](security.md) instead.
- You need an architecture decision on infrastructure: use [`architect`](architect.md) instead.
- You need to audit dependencies for vulnerabilities: use [`dependency-auditor`](dependency-auditor.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
devops: add a GitHub Actions workflow that runs pytest on pull requests with dependency caching, pinned to commit SHAs
```

In GitHub Copilot CLI:

```bash
copilot --agent devops --prompt "add a GitHub Actions workflow that runs pytest on pull requests with dependency caching, pinned to commit SHAs"
```

In VS Code or Visual Studio Copilot Chat:

```text
@devops add a GitHub Actions workflow that runs pytest on pull requests with dependency caching, pinned to commit SHAs
```

## What you get

Pipeline configuration, plus documentation saved under `.project-toolkit/devops/`. Each pipeline doc covers purpose, triggers, jobs (runner, steps, outputs), required secrets, and known issues with workarounds. The agent quantifies results with build time, deployment frequency, and mean time to recovery, and compares them to a baseline.

It also stores implementation notes in memory and returns a completion status and recommendations to the orchestrator.

## Advanced use

Impact analysis mode: when `milestone-planner` asks for an impact analysis during planning, the agent writes `.project-toolkit/planning/impact-analysis-devops-[feature].md`. The file has these parts:

- Impacts identified, direct and indirect.
- Affected areas with a risk level of L, M, or H.
- Build pipeline changes, deployment impact with rollback strategy, and infrastructure requirements with cost impact.
- Secrets and configuration actions.
- Performance and developer experience impact.
- Recommendations, issues discovered by priority (P0, P1, P2), dependencies, and estimated effort.

Pipeline standards the agent follows:

- Pin actions to a commit SHA with the version in a trailing comment.
- Use composite actions for reuse and matrix builds for multi-targeting.
- Cache dependencies and use job outputs for cross-job communication.
- For .NET CI builds, set `/p:ContinuousIntegrationBuild=true`, `/p:UseSharedCompilation=false`, `/m:1`, and `/nodeReuse:false`.
- Run tests with filters that exclude `localOnly`, `Benchmark`, `SOAP`, `REST`, and `IntegrationTests` categories.

The agent cannot delegate. It recommends these handoffs to the orchestrator:

| Target | When | Purpose |
| --- | --- | --- |
| `implementer` | Pipeline ready for code | Ready to build |
| `qa` | Test infrastructure needed | Test setup |
| `architect` | Infrastructure decisions | Technical direction |
| `security` | Security review needed | Compliance check |

It searches memory before pipeline work and writes learnings under a `ci/devops-[topic]` memory name. Serena writes happen only from the checkout Serena started in. If Serena is unavailable, it reads `.serena/memories/` directly.

A multi-step prompt:

```text
devops: review .github/workflows, list steps without SHA pins or caching, propose the changes with expected build-time savings against the current baseline, and name which agent should review them.
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

- [`milestone-planner`](milestone-planner.md): requests the impact analysis.
- [`implementer`](implementer.md): builds on the finished pipeline.
- [`security`](security.md): reviews pipeline security.
- [`qa`](qa.md): sets up test infrastructure with you.
- [`dependency-auditor`](dependency-auditor.md): runs dependency scans in CI.
- Source template: [`devops.shared.md`](../../templates/agents/devops.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
