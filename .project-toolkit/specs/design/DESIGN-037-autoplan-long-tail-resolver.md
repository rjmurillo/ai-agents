---
type: design
id: DESIGN-037
title: Autoplan long-tail resolver and routing intents
status: implemented
priority: P1
related:
  - REQ-039
  - REQ-038
  - DESIGN-036
  - TASK-048
created: 2026-09-25
updated: 2026-09-25
author: spec-generator
tags:
  - skills
  - routing
  - autoplan
---

# DESIGN-037: Autoplan long-tail resolver and routing intents

## Requirements Addressed

REQ-039 criteria 1 to 13.

## Where intents live

Intents extend the DESIGN-036 routing block. They stay in the skill that owns
them, so no second registry exists:

```yaml
metadata:
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan's long-tail resolver matches a developer-friction audit
    user-facing: true
    intents:
      - developer experience
      - developer friction
      - onboarding friction
```

The routing-role gate accepts `intents` only on a `front-door` skill, as a
non-empty list of non-empty strings.

## Resolver

`.claude/skills/autoplan/scripts/resolve_route.py` ships with the skill.

```text
resolve_route.py --request TEXT [--skills-root PATH[=NAMESPACE] ...]
```

With no `--skills-root`, the resolver reads the skills directory that holds
the `autoplan` skill. The namespace comes from the nearest
`.claude-plugin/plugin.json` `name` above that directory, or `local` when no
manifest exists.

### Matching

1. Lowercase the request and split it into word tokens. Drop a short list of
   stop words. Fold one trailing `s` on both sides (tokens longer than three
   characters), so `libraries` and `library` do not match but `packages` and
   `package` do.
2. An intent matches when every one of its tokens appears in the request.
3. A skill's score is its count of matching intents. The tie-break is the
   total token count of those intents.

### Order

1. **Explicit.** A `/name`, `/namespace:name`, or "use the name skill" that
   names an installed skill returns `explicit`. A name that is the router
   itself is dropped, and resolution continues on the rest of the request.
   A name that is not installed is reported in the rationale and ignored.
   A bare name that exists in two namespaces prefers the router's own
   namespace. With no own-namespace match it returns `ambiguous`.
2. **Multi-domain.** A marker such as `in parallel`, `across services`, or
   `multi-agent` returns `orchestrator`.
3. **Specialist.** One top-scoring eligible skill returns `specialist`. A tie
   returns `ambiguous` with the tied names.
4. **None.** Otherwise `none`. The skill body then applies the lifecycle chain
   or asks.

The high-traffic table is prose that the model reads, so the resolver does
not repeat it. The model checks the table first and runs the resolver only on
a miss.

### Output

```json
{"kind": "specialist", "route": "project-toolkit:dx-review",
 "candidates": ["project-toolkit:dx-review"],
 "rationale": "matched intents: developer friction"}
```

`kind` is one of `explicit`, `orchestrator`, `specialist`, `ambiguous`, or
`none`. Keys are sorted, so output is byte-stable.

Exit codes: 0 on any resolution, including `none`. 2 for a missing skills
root, a missing PyYAML module, or bad arguments.

## Identity in mixed catalogs

The router's stable identity is `project-toolkit:autoplan`. `/autoplan` stays
the local alias, so nothing is renamed.

| Context | Name the model sees | Contract selected |
|---|---|---|
| This repository, `.claude/skills` | `autoplan` | this router |
| Packaged plugin | `project-toolkit:autoplan` | this router |
| Mixed catalog with gstack | `project-toolkit:autoplan` and `gstack:autoplan` | router by qualified name; gstack review pipeline only by its qualified name |

The resolver identifies itself by path, not by name. A foreign `autoplan` has
no `intents`, so intent matching can never select it. Only an explicit
qualified name can select it.

## New capability

The table row changes from "buy-vs-build-framework first" to
"programming-advisor prior-art discovery first, then buy-vs-build-framework
only for a strategic decision". `programming-advisor` becomes `front-door`
with invoker `autoplan`. REQ-019 criterion 3 changes to match.

## Reclassified skills

`business-strategy`, `book-to-skill`, `world-model-diagnostic`, and
`dx-review` change from `explicit-only` to `front-door` with intents.
`ai-agents-external-claims` and `validation-authority` stay `explicit-only`
for issues #5388 and #5387. Their rationale strings are quoted, because the
unquoted `#` truncated them in YAML.

## Recursion

The resolver drops its own name and never returns it. A test reads the
orchestrator shared source and fails when it gains an `autoplan` invocation.
