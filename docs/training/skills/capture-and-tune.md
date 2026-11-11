# Capture a workflow and tune it

## Goal

Run the capture-then-tune loop on a safe sample. You will:

1. Pass a workflow through the `skillify` gate and see it accepted.
2. See a weak workflow rejected.
3. Check a written skill with `skillify verify`.
4. Run the `skillopt` held-out gate on shipped sample data, and see one change accepted and one rejected.

The checked outcome is two gate verdicts: `ACCEPT_PARETO` and `REJECT`.

This page uses a scratch directory and sample files. It writes nothing into your skill library. Which skill to pick in the first place is covered in [Choose the right skill tool](choose-a-skill.md).

## Before you start

- A checkout of this repository, with `python3` on your path.
- A shell open at the repository root.
- Five minutes. No model calls happen on this page. Every command is a local script.

Set a scratch directory:

```bash
S="$(mktemp -d)"
echo "$S"
```

## Steps

### Part 1: Capture with `skillify`

`skillify` turns a workflow you just finished into a skill. The first check is a gate. It rejects one-offs, so a skill library does not fill up with noise.

1. Write an audit for a workflow worth keeping. It had nine tool calls, three decisions, two gotchas, and a phrase you would say to start it.

```bash
cat > "$S/audit.json" <<'EOF'
{"tool_call_count": 9, "reusable_class": true, "decision_points": 3, "gotchas": 2, "trigger_phrase": "draft release notes"}
EOF
python3 .claude/skills/skillify/scripts/skillify.py gate --audit "$S/audit.json"
```

   Expected output:

```json
{
  "status": "PROCEED",
  "reasons": [],
  "approval_gate_required": false,
  "recovery_paths_required": false,
  "proactive_eligible": true
}
```

2. Run the gate on a weak workflow: one tool call, no decisions, no trigger phrase.

```bash
cat > "$S/weak.json" <<'EOF'
{"tool_call_count": 1, "reusable_class": false, "decision_points": 0, "gotchas": 0, "trigger_phrase": ""}
EOF
python3 .claude/skills/skillify/scripts/skillify.py gate --audit "$S/weak.json"
```

   The status is `REJECT`. Four reasons come back: `one_off`, `trivial_wrapper`, `no_real_procedure`, and `no_trigger_phrase`. The command still exits `0`. Read the `status` field, not the exit code.

3. Check for overlap. `skillify` patches an existing skill when 70 percent of the workflow's terms are already covered.

```bash
cat > "$S/workflow.json" <<'EOF'
{"actions": ["collect merged PRs", "draft release notes", "group by type"], "terms": ["release", "notes", "changelog", "merged", "pull", "requests"], "trigger_phrase": "draft release notes"}
EOF
python3 .claude/skills/skillify/scripts/skillify.py overlap --workflow "$S/workflow.json" --root .claude/skills
```

   The status is `CREATE`. The closest existing skill covers about 64 percent of the terms, which is under the 70 percent line. The exact list of near matches changes as the skill library grows.

4. Write the skill. In a real run, the agent does this after `resolve` picks the skills directory. Here, write a small one into the scratch directory by hand. Use the section order from [skill-skeleton.md](../../../.claude/skills/skillify/references/skill-skeleton.md).

```bash
mkdir -p "$S/skills/release-notes-draft"
cat > "$S/skills/release-notes-draft/SKILL.md" <<'EOF'
---
name: release-notes-draft
description: Draft release notes from merged pull requests. Use when you say `draft release notes`.
---
# Release Notes Draft

Release notes drift when each one is written from memory. This skill drafts them from the merged pull requests.

## Triggers

`draft release notes`

## Contract

- A draft file exists that lists every merged pull request since the last tag.
- Nothing is published.

## Procedure

1. List merged pull requests since the last tag.
2. Group them by conventional commit type.
3. Write the draft to a local file.

## Anti-patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Writing notes from memory | Changes get missed | List the pull requests first |
| Publishing the draft | Readers see unreviewed text | Leave sharing to the user |

## Pitfalls

- Squash merges hide the original commit types. Read the pull request title.
- Tags can be missing in a shallow clone. Fetch tags first.

## Verification

- [ ] The draft names every merged pull request since the last tag.
EOF
```

5. Read the skill back with `verify`.

```bash
python3 .claude/skills/skillify/scripts/skillify.py verify --skill "$S/skills/release-notes-draft" --audit "$S/audit.json"
```

   The status is `PASS` and `failures` is empty. The command exits `0`. A `verify` pass shows the file is well formed. It does not show the skill helps. That is what Part 2 is for.

### Part 2: Tune with `skillopt`

`skillopt` improves a skill through small patches. A patch lands only if it adds at least one passing task in a held-out set and loses none. The reason is in [ADR-087](../../../.project-toolkit/architecture/ADR-087-held-out-validated-improvement.md). If you score every edit against the same tasks you read while editing, the score measures how well you fit those tasks. It stops measuring the skill.

The repository ships a sample eval set and two result files. The eval has ten tasks. Six are `train` tasks that the author may see. Four are `sel` tasks, the held-out set.

6. Run the gate on the sample, where the candidate fixes one held-out task and breaks none.

```bash
R=.claude/skills/skillopt/references
python3 .claude/skills/skillopt/scripts/skillopt.py pair-gate \
  --eval "$R/example-eval.json" \
  --incumbent-results "$R/example-incumbent-results.json" \
  --candidate-results "$R/example-candidate-results.json"
```

   Expected output, exit code `0`:

```json
{
  "accepted": true,
  "verdict": "ACCEPT_PARETO",
  "split": "sel",
  "selection_tasks": 4,
  "incumbent_passes": 2,
  "candidate_passes": 3,
  "gains": [
    "t8"
  ],
  "regressions": [],
  "unverified": []
}
```

7. Break one held-out task and run the gate again. This copy of the candidate results fails `t7`, which the incumbent passed.

```bash
python3 - "$R/example-candidate-results.json" "$S/regressed.json" <<'EOF'
import json, sys
results = json.load(open(sys.argv[1]))
results["t7"] = False
json.dump(results, open(sys.argv[2], "w"))
EOF
python3 .claude/skills/skillopt/scripts/skillopt.py pair-gate \
  --eval "$R/example-eval.json" \
  --incumbent-results "$R/example-incumbent-results.json" \
  --candidate-results "$S/regressed.json"
```

   Expected output, exit code `1`:

```json
{
  "accepted": false,
  "verdict": "REJECT",
  "split": "sel",
  "selection_tasks": 4,
  "incumbent_passes": 2,
  "candidate_passes": 2,
  "gains": [
    "t8"
  ],
  "regressions": [
    "t7"
  ],
  "unverified": []
}
```

   The candidate gained `t8` and lost `t7`. The pass counts are equal, and the gate still says no. One regression blocks the edit.

## Check your result

- Step 1 printed `"status": "PROCEED"`.
- Step 2 printed `"status": "REJECT"`.
- Step 5 printed `"status": "PASS"`.
- Step 6 printed `"verdict": "ACCEPT_PARETO"` and exited `0`.
- Step 7 printed `"verdict": "REJECT"` and exited `1`.

Check an exit code with `echo $?` right after the command.

Delete the scratch directory (`$S`) when you finish.

## If it does not work

- `audit field 'reusable_class' must be true or false`. Use a JSON boolean, not a string. `skillify.py gate` exits `1`.
- `skillify.py overlap` returns `PATCH`. A skill in your tree already covers the workflow. Read it and patch it. The skill's own steps tell the agent to confirm the target path with you first.
- `pair-gate` exits `2`. The eval has no `sel` split, an exposed task sits in `sel`, or a result file is missing a task. Read the message, then [eval-set-format.md](../../../.claude/skills/skillopt/references/eval-set-format.md).
- `REJECT_UNVERIFIED`. A result is missing or not a literal `true` or `false`. The gate does not count it.

## What this page does not do

A real `skillopt` run needs two isolated runners. One session writes the candidate and sees only `train` tasks. A second session holds the `sel` tasks and sends back only the verdict. If the same agent wrote the candidate and the held-out tasks, those tasks are exposed and cannot count as `sel`. The steps above run the gate on shipped sample results, so you can see how it decides. They are not an improvement claim for any skill.

ADR-087 has `status: proposed` as of 2026-11-10. Read it as the reasoning behind the gate. It is not a rule in force.

## Next

- [Choose the right skill tool](choose-a-skill.md): when to use each of the five skills.
- [skillopt SKILL.md](../../../.claude/skills/skillopt/SKILL.md): the full loop, including the budget, patch, and null-control steps.
- [skillify SKILL.md](../../../.claude/skills/skillify/SKILL.md): destination rules and the capability gate.
- [SKILL-AUTHORING.md](../../SKILL-AUTHORING.md): frontmatter and validation for any skill you write.
