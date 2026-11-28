# skill-bootstrap

Mines a repository's git history, review rounds, and agent sessions, then authors and evaluates a library of project skills from what it finds. Each skill is measured against a no-skill baseline, and the report lists what it did not measure.

## When to use it

- You want to capture a project's unwritten workflow knowledge as skills.
- You want to build or refresh a repository's skill library from evidence.
- Trigger phrases: `bootstrap skills`, `capture project workflow knowledge`, `build this repo's skill library`, `project skill library`, `audit agent reply friction`.
- You want rates for where agent replies cost you effort, from your local Claude Code transcripts.

## When not to use it

- You want one skill created or improved: use [`skillforge`](skillforge.md) instead.
- You want scored tuning of a skill: use [`skillopt`](skillopt.md) instead.
- You want to know how installed skills performed in sessions: use [`skill-doctor`](skill-doctor.md) instead.
- You want to save a workflow you just finished: use [`skillify`](skillify.md) instead.
- You want README or architecture templates: use [`codebase-documenter`](codebase-documenter.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:skill-bootstrap
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/skill-bootstrap`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /skill-bootstrap skill to ...`.

Installing the skill does nothing by itself. An explicit request starts a run. The skill snapshots the repository, asks you to pick a mode and one to three outcomes, mines candidates, and authors skills only where evidence supports them.

## What you get

- Skills written inside the output root you choose (`.claude/skills` or `.github/skills`), each with a `reverify.json` provenance file. Scripts and their tests ship for any item a program can compute.
- A capability score per skill, with and without the skill, from frozen eval cases.
- A bootstrap report that separates authored, evaluated, and installed states and lists unmeasured results.
- The reply-friction audit yields count JSON on stdout plus one local report kept out of the repository.

A skill is an `instrument` (a script), a `scaffold` (prose), or `both`. Anything computable from repository state must ship as a script.

Exit code `0` means success and `1` means findings that need action, for every script. [`references/scripts.md`](../../src/claude/skills/skill-bootstrap/references/scripts.md) holds the exit `2` and `3` table for each.

## Advanced use

**Modes.** `workflow` (default) writes a skill only for verified friction: corrections, reverts, long review rounds, review failures, and missed items. `knowledge` requires verified content plus a frozen baseline case where a model without the skill gets it wrong. Neither mode has a quota.

**Six phases.** Scope and boundary snapshot; diagnose and mine; select and sort by tool form; author through [`skillforge`](skillforge.md); run [`context-optimizer`](context-optimizer.md), then the capability eval, then [`skillopt`](skillopt.md); independent review, then verify and deliver. A missing prerequisite skill is recorded as `UNAVAILABLE` and the dependent stage as `NOT RUN`.

**Write boundary.** The skill writes only inside the output root and paths you authorized. It runs no mutating git command, publication, or tracker change. If the repository generates skills from templates, it stops and asks you which canonical paths to authorize.

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/skill-bootstrap/scripts/bootstrap_mine.py candidates --repo . --top 10
uv run python .claude/skills/skill-bootstrap/scripts/bootstrap_forms.py --help
uv run python .claude/skills/skill-bootstrap/scripts/bootstrap_eval.py score --help
uv run python .claude/skills/skill-bootstrap/scripts/bootstrap_drift.py check --repo . --skills-root .claude/skills
```

| Script | Subcommands | Use |
| --- | --- | --- |
| `bootstrap_boundary.py` | `plan`, `snapshot`, `verify` | Check names and conflicts, record state, prove the boundary held |
| `bootstrap_mine.py` | `candidates`, `claims` | Rank reverts and hotspots; check repo paths named in authored text |
| `bootstrap_forms.py` | `check` | Validate the tool form of every plan item |
| `bootstrap_eval.py` | `freeze`, `check`, `score` | Freeze cases and score capability with and without the skill |
| `bootstrap_drift.py` | `check` | Re-verify skill provenance against the repository |
| `bootstrap_sweep.py` | `tally` | Tally judged friction incidents from outside the repo |
| `replies_audit.py` | `prepare`, `tally` | Sample agent replies into a private directory outside the repo, then turn judge labels into weighted friction rates |

`bootstrap_drift.py check` runs a `command` check only with `--allow-commands`, which executes repository code. Never pass it in a job that holds secrets or runs untrusted pull request content. Drift exit `1` lists `update_candidates` and `update_args`, which you pass as separate arguments to a new run.

`bootstrap_eval.py score` reports each case as `gain`, `no_gap`, `flat`, or `regression`. A skill whose cases are all `flat` fails, and a `regression` is a blocking finding. Per-case results have no noise floor, so run each case at least twice.

The skill's own Limits section says the instrument-first rule has not yet shown a capability gain in its one recorded run. It lists that as an open hypothesis.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`skillforge`](skillforge.md): authors each skill (Phase 4).
- [`context-optimizer`](context-optimizer.md): runs on each authored skill (Phase 5).
- [`skill-doctor`](skill-doctor.md): diagnoses existing skills (Phase 2).
- [`skillopt`](skillopt.md): tunes scored skills (Phase 5).
- Source: [`SKILL.md`](../../src/claude/skills/skill-bootstrap/SKILL.md)
- Authoring and gates: [`authoring-and-gates.md`](../../src/claude/skills/skill-bootstrap/references/authoring-and-gates.md)
- Discovery lenses: [`discovery.md`](../../src/claude/skills/skill-bootstrap/references/discovery.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
