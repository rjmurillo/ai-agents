# Skill Routing Manifest

`.config/skill-routing-manifest.yaml` is the one reviewed source of truth that
gives every canonical skill under `.claude/skills/<name>/` exactly one **primary
routing role**. It exists so the catalog can grow without any skill silently
becoming unroutable, and so `/autoplan`'s high-traffic table never has to expand
to the full catalog (issue #5384).

The validator `scripts/validation/skill_routing_manifest.py` reads this manifest
plus the canonical `.claude` tree and runs in the pre-PR sequence as the
**Skill Routing Manifest** gate. CI fails when a new skill is added without a
role, when an entry is malformed, or when an owner contradicts its role.

## The six roles

| Role | Meaning | Owner (invoker) |
|------|---------|-----------------|
| `front-door` | Directly selectable by `/autoplan`. | `/autoplan` |
| `lifecycle` | Selected by `/spec`, `/plan`, `/build`, `/test`, `/ship`, or `/review`. | one of those commands |
| `conditional-adjunct` | Composed into another route only when a declared trigger matches. | the skill or command it composes into |
| `nested-helper` | Intentionally invoked only by another skill or agent. | that skill or agent |
| `explicit-only` | Intentionally requires an explicit user request. | `user` |
| `deprecated` | Retained temporarily with a replacement or removal reference. | any valid invoker |

## Classifying a new skill

Work down this list and stop at the first role that fits:

1. Does `/autoplan`'s Phase 2 routing table name it (or does a dependent issue
   add that row)? -> `front-door`, owner `/autoplan`.
2. Is it a documented step of `/spec`, `/plan`, `/build`, `/test`, `/ship`, or
   `/review`? -> `lifecycle`, owner that command.
3. Is it composed into another route only when a specific condition holds?
   -> `conditional-adjunct`. Add a `trigger:` describing the predicate.
4. Is it invoked only from inside another skill or agent body, never by the
   user? -> `nested-helper`, owner that skill or agent.
5. Is it a standalone tool a user must ask for by name, where auto-routing would
   be noisy or unsafe? -> `explicit-only`, owner `user`. Add a `rationale:`
   explaining why auto-routing is unsafe or noisy.
6. Is it kept only for backward compatibility? -> `deprecated`. Add a
   `replacement:` naming the successor skill or removal issue.

### Required fields

Every entry needs `role` and `owner`. Situational required fields:

- `trigger` for `conditional-adjunct`
- `rationale` for `explicit-only`
- `replacement` for `deprecated`

`user_facing`, the expected activation-scenario path
(`tests/evals/skill-scenarios/<name>.json`), and the structural inbound count
are **derived** by the validator, not written by hand. See them with
`python scripts/validation/skill_routing_manifest.py --format json`.

## Three measurements the report keeps separate

Running the validator prints a report that distinguishes three things a skill
can lack. They are independent; a skill can pass one and fail another:

1. **Structural reachability** -- is there any `Skill(skill=...)`, `Skill:`, or
   `Agent:` route to the skill in the `.claude` prompts? A skill with none is
   listed as `inbound-zero`. This never fails the gate: a skill can be
   classified with an *intended* invoker that a dependent issue has not wired
   yet, so its inbound count is legitimately zero today and the report surfaces
   the gap instead of blocking on it.
2. **Activation-scenario coverage** -- does a scenario fixture exist at
   `tests/evals/skill-scenarios/<name>.json`? That is what
   `scripts/validation/check_rule_activation_coverage.py` ratchets.
3. **Scored routing accuracy** -- would a description-matching router actually
   pick the skill for its own request? That is a live-API measurement produced
   by `scripts/eval/eval_skill_router.py`, not this gate.

## Running it locally

```bash
# Report (role totals, inbound-zero, scenario coverage):
python scripts/validation/skill_routing_manifest.py

# Full resolved manifest as JSON (reviewed fields plus derived fields):
python scripts/validation/skill_routing_manifest.py --format json
```

Exit codes follow ADR-035: `0` valid, `1` one or more findings, `2` config
error (manifest missing, unparseable, or the `.claude` tree absent).

Do **not** copy this catalog into `src/copilot-cli/` or any mirror. The validator
reads `.config/skill-routing-manifest.yaml` directly, and generated skill
surfaces are produced by `build/scripts/build_all.py`, never by hand.
