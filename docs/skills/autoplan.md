# autoplan

Routes a request that names no skill to the right skill, lifecycle command, or agent chain. It applies sensible defaults and stops only for decisions that are yours. You get one summary block at the end.

## When to use it

- You have a concrete request and do not want to pick from the full skill catalog, such as "why is CI failing", "investigate the flaky test", or "redo the login fix properly".
- You say `/autoplan`, `do it`, `handle it`, `figure this out`, or `your call`.
- You want the route reported before it runs: `figure this out` and `your call` classify first, then report the route.

## When not to use it

- You name a specific skill or lifecycle command: invoke that skill directly. An explicitly named, installed skill always wins.
- You want multi-agent coordination for work you already know spans several domains: use the [`orchestrator`](../agents/orchestrator.md) agent. Autoplan routes to it, and it never routes back.
- You have an approved plan file to run or resume: use [`planner`](planner.md).

## Quick start

This skill is the toolkit's router for requests that name no skill. In Claude Code, after a plugin install, run:

```text
/project-toolkit:autoplan fix the flaky retry test in tests/test_sync_job.py
```

On other hosts, name it in your prompt:

```text
Use the /autoplan skill to fix the flaky retry test in tests/test_sync_job.py.
```

The agent also loads it on its own when your request names no skill.

Autoplan reads your repository's stack first, then classifies the request by intent and size. It runs the chosen route with defaults applied. It ends with a final gate summary.

> [!NOTE]
> Another toolkit, gstack, ships an unrelated skill also called `autoplan`. In a catalog that has both, use the qualified name `project-toolkit:autoplan` for this router.

## What you get

Every run ends with one summary block, not a stream of narration:

| Item | Contents |
| --- | --- |
| Route taken | The route and why, in one line |
| Auto-decided items | A count of mechanical defaults, plus each taste decision with a one-line rationale |
| Open sovereignty questions | Decisions that need you, with 2 to 3 options and trade-offs |
| Evidence | Tests run and their counts, gates passed, artifacts produced |

Decisions fall into four classes. Mechanical decisions have one defensible answer (run tests, fix lint, sync a mirror) and are made silently. Taste decisions have low reversal cost (naming, small refactor shape) and are made, then surfaced in the final gate. PR approval decisions (an architecture, ADR, rule, breaking, or security change in the repo) are implemented, then surfaced for approval at the top of the PR. Sovereignty decisions (your stated direction, a destructive or production action outside the repo, a required human approval) stop the blocked action and ask you.

## Advanced use

**Phases.** Phase 0 recon reads the target repository's own signals (`CONTRIBUTING*`, `AGENTS.md`, `CLAUDE.md`, build manifests, test layout) so plans match the detected stack. For an issue URL, it also checks for an in-flight pull request with `check_existing_pr_for_issue.py` from the `github` skill. Only exit `0` clears new work; exit `1` means an open PR claims the issue, and exits `2` to `4` stop and report.

**Size tiers.** Phase 1 picks the smallest honest tier:

| Tier | Signal | Pipeline |
| --- | --- | --- |
| Trivial | One known file, no contract change | Fix, test, commit |
| Standard | Bounded change on an existing surface | `/build`, `/test`, `/review`, `/ship` |
| Feature | New capability or ambiguous requirements | `/spec`, `/plan`, then the Standard chain |

When unsure, it starts one tier down and escalates on evidence.

**Routing table.** Phase 2 maps intents to destinations, for example: bugs go to [`analyze`](analyze.md) then [`build`](build.md); PR and issue operations go to [`github`](github.md); review threads go to [`pr-comment-responder`](pr-comment-responder.md); merge conflicts go to the [`merge-resolver`](../agents/merge-resolver.md) agent; "push, ship, open a PR" goes to [`ship`](ship.md) or [`push-pr`](push-pr.md); "what do we know about X" goes to [`memory-search`](memory-search.md). Multi-domain work goes to the [`orchestrator`](../agents/orchestrator.md) agent. The full table is in the source file.

**Long-tail resolver.** When a single-domain request matches no table row, Phase 2b runs `resolve_route.py`. It reads local `SKILL.md` frontmatter and prints one JSON line. It opens no network connection. Run it from the root of a checkout:

```bash
uv run python .claude/skills/autoplan/scripts/resolve_route.py --help
```

Flags: `--request REQUEST` (required) and a repeatable `--skills-root PATH[=NAMESPACE]`. Exit `0` covers any resolution, including `none`. Exit `2` is a config or usage error, such as a missing skills root or PyYAML module.

The JSON `kind` field tells autoplan what to do:

| `kind` | Action |
| --- | --- |
| `explicit` | Invoke `route`; the request already named it |
| `orchestrator` | Delegate to the `orchestrator` agent |
| `specialist` | Invoke `route`, the one eligible skill that matched |
| `ambiguous` | Ask you to pick from `candidates` |
| `none` | Fall through to the lifecycle chain, or the `orchestrator` agent |

**Precedence.** An explicitly named skill wins, then a table row, then the resolver, then the lifecycle chain, then the orchestrator. The router never routes to itself.

**References.** The skill ships `decision-procedure.md` (the six-step walk from scope to terminal), `golden-age.md` (task-compression table), and `writing-style-and-confusion-protocol.md`. Five `orchestrator-*.md` files serve the orchestrator agent, not this router.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`spec`](spec.md), [`plan`](plan.md), [`build`](build.md), [`ship`](ship.md): the lifecycle chain autoplan routes feature work through.
- [`orchestrator`](../agents/orchestrator.md): the destination for multi-domain work.
- Source: [`SKILL.md`](../../src/claude/skills/autoplan/SKILL.md)
- References: [`decision-procedure.md`](../../src/claude/skills/autoplan/references/decision-procedure.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
