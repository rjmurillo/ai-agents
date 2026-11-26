# skillopt

Improves a skill, agent file, or prompt through small patches and a held-out, per-task acceptance gate. A candidate lands only when it adds at least one held-out pass and loses none. With no scored eval set there is no gate, and no edit.

## When to use it

- You have a skill, agent file, or prompt with a scored eval set and want a measured improvement.
- A skill keeps failing the same way.
- Trigger phrases: `optimize this skill`, `make this skill better`, `compress these skills safely`, `tune this prompt against an eval`.

## When not to use it

- You want to create or route skills: use [`skillforge`](skillforge.md) instead.
- You want to decide skill placement or compress markdown with no eval: use [`context-optimizer`](context-optimizer.md) instead.
- You have no scored eval set. The skill stops and says so.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:skillopt optimize the skill at .claude/skills/pr-review/SKILL.md using eval.json
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/skillopt`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /skillopt skill to ...`.

The skill checks four preconditions: a target file, a scored eval set with a held-out `sel` split, a named canonical owner, and two isolated runners. The author of the candidate must not see the `sel` tasks, verifiers, or results. If your harness cannot give you two isolated runners, do not run this skill.

## What you get

- A gate verdict from `pair-gate`. `ACCEPT_PARETO` means at least one held-out gain, no held-out regressions, and every result a literal boolean.
- Other verdicts: `REJECT`, `REJECT_UNVERIFIED`, `REJECT_NULL_CONTROL`, and `REJECT_CEILING` (the incumbent already passes every `sel` task, so no candidate can win; the edit is not bad and is not buffered).
- A kept evidence trail: incumbent, candidate, patches, results, hashes, and `rejected.jsonl`.
- `ACCEPTED_NOT_DEPLOYED` when you stop short of promotion. An eval-workspace candidate is never called installed.

## Advanced use

One step: baseline, budget (`budget --step T --total N` prints the cosine-decayed patch cap), reflect on `train` evidence only, `buffer-check`, `apply` to a candidate, re-roll every task, then `pair-gate`. Never edit the target by hand, because the gate would not see the edit.

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/skillopt/scripts/skillopt.py --help
uv run python .claude/skills/skillopt/scripts/skillopt.py budget --step 0 --total 5
uv run python .claude/skills/skillopt/scripts/skillopt.py hash target.md
uv run python .claude/skills/skillopt/scripts/skillopt.py pair-gate --eval eval.json --incumbent-results incumbent_results.json --candidate-results candidate_results.json
uv run python .claude/skills/skillopt/scripts/mine_sessions.py sources
```

Subcommands: `budget`, `apply`, `run`, `gate`, `pair-gate`, `efficiency-gate`, `report`, `score`, `hash`, `buffer-check`, `buffer-add`, `where`.

`apply` runs skillforge's `lint_skill_frontmatter.py` on the incumbent and the candidate. It exits `2` when the candidate adds a MUST failure the incumbent did not have, such as a SKILL.md over the byte cap or frontmatter the stdlib parser refuses. New SHOULD findings print as warnings.

| Command | Exit codes |
| --- | --- |
| `budget`, `apply`, `score`, `buffer-add` | `0` success, `2` usage or validation error |
| `gate`, `pair-gate` | `0` accept, `1` reject, `2` usage or validation error |
| `efficiency-gate` | `0` `ACCEPT_EFFICIENCY`, `1` reject, `2` usage error |
| `run` | `0` results written, `1` a task `UNVERIFIED`, `2` refused or invalid |
| `hash --expect SHA` | `0` match, `1` `MISMATCH` |
| `buffer-check` | `0` `KNOWN-BAD` (discard), `1` `NOVEL` (proceed) |

`buffer-check` is inverted on purpose, so branch on the printed word, never on `&&`.

**Nondeterministic scorer.** Set `"scorer": "nondeterministic"` in the manifest and rerun the byte-identical incumbent into `null_results.json`. Pass `--null-results`, `--incumbent-sha256`, and `--null-sha256` to `pair-gate`. A gain the no-op also produced is noise.

**Before promotion.** Run `pair-gate --split train` and review lost training passes. Promote to the canonical source, hash it against the accepted candidate, regenerate mirrors, run the owner's tests, and confirm the live copy hashes to the canonical file.

**Protected sections.** Fence guidance that edits must never touch between `SLOW_UPDATE_START` and `SLOW_UPDATE_END` comment markers.

**Finding targets.** `mine_sessions.py` (`sources`, `rank`, `tasks`, `collect`, `merge`) ranks skills by usage and a weak correction signal. A correction nominates a candidate; confirm the defect in the target and in two sessions first. Session data stays local.

**Descriptions.** Output-quality rollouts do not measure activation, so score a description change on trigger rate. Read [`references/description-optimization.md`](../../src/claude/skills/skillopt/references/description-optimization.md) first.

The gate compares incumbent against candidate. It never measures skill against no skill; that baseline lives in [`skill-bootstrap`](skill-bootstrap.md) (`bootstrap_eval.py score`). The method is from arXiv:2605.23904.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`skillforge`](skillforge.md): creates and routes skills; hand back a first draft here.
- [`skill-bootstrap`](skill-bootstrap.md): measures a skill against no skill.
- [`skill-doctor`](skill-doctor.md): produces candidates for skillopt to evaluate.
- [`context-optimizer`](context-optimizer.md): placement and compression with no eval.
- Source: [`SKILL.md`](../../src/claude/skills/skillopt/SKILL.md)
- Eval set format: [`eval-set-format.md`](../../src/claude/skills/skillopt/references/eval-set-format.md)
- Eval authoring: [`eval-authoring.md`](../../src/claude/skills/skillopt/references/eval-authoring.md)
- Judge grading discipline: [`judge-grading-discipline.md`](../../src/claude/skills/skillopt/references/judge-grading-discipline.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
