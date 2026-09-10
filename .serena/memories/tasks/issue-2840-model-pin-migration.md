# Issue #2840: Model-Pin Migration (ADR-080)

**Session 3256, 2026-07-20, branch feat/2840-model-pin-migration, commit d4b464a7.**

## Decision: kind-split migration, agents owner-gated

ADR-080 bans versioned `model:` ids on skills/commands (they cannot be
eval-swept) and allows them on agents only with a cited KEEP_PIN sweep manifest
entry. This session executed the SAFE half:

- 66 skills + 1 command de-versioned. sonnet/opus versioned ids removed
  (inherit harness default); `claude-haiku-4-5` converted to bare `haiku` +
  a cost `model-rationale` (the only alias that prices below default).
- Taught the SkillForge validator the `model-rationale` property
  (`.claude/skills/SkillForge/scripts/_constants.py`, ADR-080 point 4). Left
  the validate-skill.py inline fallback list ALONE on purpose: touching it
  drags in 3 pre-existing pyright errors (bool|None -> check()); _constants.py
  is the real import path.
- Regrowth sources closed: SkillForge skill-md-template, output-structure
  examples, `.claude/skills/github/fix-ci.md`, and the `.claude/skills/CLAUDE.md`
  model-selection guidance.
- Baseline `scripts/validation/model_pin_baseline.json` drained 113 -> 52
  (frozen_count 52). check_model_pins: warn OK, enforce exit 0, 31 tests green.
- EXCLUDED 8 skills (kept pinned, grandfathered) whose pre-existing debt the
  per-file validators surface on touch (#2993-class, not #2840): structural
  (analysis-provenance, avoiding-manufactured-work, encode-repo-serena,
  taste-lints, observability, fix-markdown-fences) and em-dash (negotiation,
  pipeline-validator).

## SUPERSEDED 2026-09-05: the agent half ran and the ratchet is at zero

Both blockers below are cleared, so read this section as history, not as a
live constraint.

1. `agent_registry.py` no longer requires `model`. `_REQUIRED_FIELDS` is
   `("name", "description")`; a pin that IS present is still checked against
   the rolling-alias allowlist.
2. The ADR-002 conflict is gone. `.claude/rules/templates.md` MUST-4 and MUST-5
   now defer to ADR-080, and issue #5313 implemented rule 5, so the generator
   injects no default `model:`.

Issue #5605 removed the remaining 37 sonnet and opus pins across 30 agents and
7 commands, in both `.claude/agents/` and the hand-maintained `src/claude/`
copies. `model_pin_baseline.json` is now `pins: {}` with `frozen_count: 0`, and
`check_model_pins.py --mode enforce` exits 0 over the 8 haiku pins that remain.
No eval sweep was run: none was needed, because a bare `sonnet` or `opus` alias
can never satisfy rule 3's below-default pricing test, so removal was the only
reachable end state and rule 2's sweep path applies only to a versioned pin
someone wants to ADD.

## Why agents were NOT touched in 2026-07 (owner-gated at the time)

1. `scripts/validation/agent_registry.py:31` requires model:
   `_REQUIRED_FIELDS = ("name","description","model")`. Removing an agent's
   pin breaks registry validation; keeping a bare `sonnet`/`opus` alias fails
   the model-pin check (only `haiku` prices below default). Agents are stuck
   until the owner reconciles.
2. ADR-080 step 2b conflicts with ADR-002 + templates.md MUST-4/5: ADR-080
   says the generator must stop injecting model; templates.md MUST-4/5 say
   agent templates MUST keep a valid model per ADR-002. Unreconciled.
   `copilot-cli.yaml:87` has a Chesterton's-fence comment gating removal, and
   it is a customer-facing generated artifact (needs a real-runtime smoke).
   Agent migration also needs eval spend to sweep the ~17 fixture-backed agents.

## Gate traps hit (for the next migration batch)

- Hard 50-file scope gate: bypass with `SKIP_SCOPE_CHECK=1` (owner-approved).
- ADR-057 eval reminder in `.githooks/pre-commit` is NON-blocking.
- SkillForge skill validation + em-dash guard + per-file pyright all BLOCK on
  STAGED files, so touching a skill drags in its latent debt (#2993 pattern).
  Exclude debt-laden files rather than paper over them.
- zsh does NOT word-split unquoted `$VAR` in `for` loops (bash does). Use a
  literal list or `${=VAR}`.

## Lesson: verify git freshness first

Local main was 101 commits behind origin/main. check_model_pins/baseline/
manifest all looked missing until git fetch + branching from origin/main.
Confirms [[pr-autofix-stale-main-and-serialization]]: fetch origin/main and
branch from it, not stale local. Skill mirrors carry model:, so a source
de-version needs a build_all regen. Related: [[architecture/install-parity]].
