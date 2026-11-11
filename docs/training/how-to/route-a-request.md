# Route a request with /autoplan

## Goal

Predict where `/autoplan` sends a request, then confirm the guess with the route resolver. You will also learn how to skip the router and name a skill yourself.

Outcome you can check: five requests resolve to the `kind` you predicted, printed by `resolve_route.py`.

## Before you start

- A clean checkout of this repository, or the `project-toolkit` plugin installed. See [installation](../../installation.md).
- `uv` on your path. The resolver imports PyYAML. Plain `python3` often lacks it. `uv run python` has it.
- Five minutes.

## Steps

### 1. Know what the router does

`/autoplan` is the front door. You give it a request that names no skill. It picks one destination: a skill, a lifecycle command, or an agent chain. It then runs that route and ends with a short summary block. The summary names the route taken, the decisions it made for you, any open question for you, and the evidence.

The router follows this order. The first match wins. The full rules are in [Precedence](../../../.claude/skills/autoplan/SKILL.md#precedence).

1. You named an installed skill or command. The router steps aside.
2. The request matches a row in the routing table.
3. A single-domain request misses the table. The resolver script picks a specialist.
4. A feature, bug, or shipping request with no specialist. The router uses the lifecycle chain.
5. Multi-domain or multi-agent work. The router hands off to `orchestrator`.

The router never routes to itself. The orchestrator never calls the router back. The rule from [ADR-078](../../../.project-toolkit/architecture/ADR-078-autoplan-orchestrator-router-boundary.md) is short: autoplan routes, orchestrator coordinates specialists.

### 2. Size the work

When the request is a feature, bug, or ship request, the router picks the smallest honest tier. The tiers come from [Phase 1: Classify](../../../.claude/skills/autoplan/SKILL.md#phase-1-classify).

| Tier | Signal | Chain |
|------|--------|-------|
| Trivial | One known file, no contract change | Fix, test, commit |
| Standard | Bounded change on an existing capability | `/build`, `/test`, `/review`, `/ship` |
| Feature | New capability, new module, or unclear requirements | `/spec`, `/plan`, then the Standard chain |

When two tiers fit, the router starts one tier down. It moves up when evidence says so, such as failing tests or a growing diff.

### 3. Predict, then ask the resolver

The resolver script backs step 3 of the order above. It reads the `routing.intents` list in each front-door skill's `SKILL.md` and prints one JSON line. It also reports an explicit skill name and multi-domain marker phrases. It opens no network connection.

Write down your guess for each request, then run it. Run these from the repository root.

We call the resolver directly so you can see every kind. In a real run, the router checks its routing table first. A request such as "add a retry" also matches the table row for building a feature. The resolver runs only when no row matches.

```bash
uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "add retry to the webhook sender"
```

```json
{"candidates": [], "kind": "none", "rationale": "no explicit reference, multi-domain marker, or intent match", "route": null}
```

`none` means no specialist fits. The router falls through to the lifecycle chain, sized by the tier table.

```bash
uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "audit our CLI for developer friction"
```

```json
{"candidates": ["project-toolkit:dx-review"], "kind": "specialist", "rationale": "matched intents: developer friction", "route": "project-toolkit:dx-review"}
```

`specialist` means one skill matched. The router invokes it.

```bash
uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "use the review skill on my diff"
```

```json
{"candidates": ["project-toolkit:review"], "kind": "explicit", "rationale": "explicit skill reference: project-toolkit:review", "route": "project-toolkit:review"}
```

`explicit` means your request already named the skill.

```bash
uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "coordinate multiple agents across the repo to migrate every service"
```

```json
{"candidates": ["orchestrator"], "kind": "orchestrator", "rationale": "multi-domain marker: multiple agents", "route": "orchestrator"}
```

`orchestrator` means a multi-domain marker phrase fired. The router starts `Task(subagent_type="orchestrator")`.

```bash
uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "/autoplan add a retry to the sync job"
```

```json
{"candidates": [], "kind": "none", "rationale": "dropped self-reference `project-toolkit:autoplan`; no explicit reference, multi-domain marker, or intent match", "route": null}
```

The router drops its own name and resolves the rest. The fifth kind, `ambiguous`, lists candidates and asks you to pick. We have no stable example that triggers it, so this page does not show one.

The first `uv run` in a fresh checkout also prints environment setup lines before the JSON. Ignore them.

### 4. Name a skill to skip the router

Name the skill or type its slash command. Nothing reroutes you.

```text
/review
/spec Add a retry to the webhook sender
```

Use this when you already know the phase you want. The user choice beats every table row. Do not name a skill to dodge a decision the router would stop and ask you about. That stop is on purpose.

### 5. Know when the router asks you

The router decides small things and tells you after. It stops only for choices that are yours: architecture, new ADRs, breaking changes, security posture, and anything external or irreversible. The classes are in [Phase 3](../../../.claude/skills/autoplan/SKILL.md#phase-3-execute-with-defaults).

The router stops when the task is done. [ADR-105](../../../.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md) defines that end state: every requested deliverable meets the task contract and no blocker remains.

## Check your result

You pass when all five resolver calls print the `kind` shown above: `none`, `specialist`, `explicit`, `orchestrator`, `none`. Each call exits with code 0.

```bash
uv run python .claude/skills/autoplan/scripts/resolve_route.py --request "audit our CLI for developer friction" > /dev/null; echo "exit $?"
```

```text
exit 0
```

Now make up two requests of your own. Predict the `kind`, then run them. A wrong guess teaches more than a right one.

## If it fails

`python3` prints this and exits 2:

```text
error: missing required module: yaml (PyYAML). Read skill descriptions directly instead of running this resolver.
```

Run the script with `uv run python` from the repository root. If you cannot run Python, read each skill's `description` field and pick the closest match. The router uses this fallback ([Phase 2c](../../../.claude/skills/autoplan/SKILL.md#phase-2c-resolver-ambiguity-from-a-home-repo-run)).

A request you expected to match returns `none`. The resolver only matches front-door skills that list `intents`. A table row in `SKILL.md` can route a request that the resolver does not match. Read [Phase 2](../../../.claude/skills/autoplan/SKILL.md#phase-2-route) before you decide the router is wrong.

## Next

- [Your first change](../first-change.md): take one small change through `/spec`, `/plan`, `/build`, `/test`, `/review`, and `/ship`.
- [Router boundary, ADR-078](../../../.project-toolkit/architecture/ADR-078-autoplan-orchestrator-router-boundary.md) and the [autoplan skill](../../../.claude/skills/autoplan/SKILL.md) for the full reference.
- [Orchestrator routing algorithm](../../orchestrator-routing-algorithm.md) for how the orchestrator picks agents after the handoff.
