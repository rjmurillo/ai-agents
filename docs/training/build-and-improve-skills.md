# Pick a skill tool, then capture a workflow and tune it

## Goal

Pick the right one of five skill tools for the job in front of you, then run the capture-and-tune loop on a safe sample. This page is for skill authors.

The five skills are `skillforge`, `skillify`, `skillopt`, `skill-bootstrap`, and `skill-doctor`. They overlap in name and not in job. Each skill's description ends with a "Do NOT use" line, and that line is the source for the table in step 1.

By the end you will have:

1. Named the skill and the phrase that starts it for your own starting point.
2. Passed a workflow through the `skillify` gate and seen it accepted, then seen a weak one rejected.
3. Checked a written skill with `skillify verify`.
4. Run the `skillopt` held-out gate on shipped sample data and seen two verdicts: `ACCEPT_PARETO` and `REJECT`.

The capture and tune steps use a scratch directory and sample files. They write nothing into your skill library. No model calls happen. Every command is a local script.

## Before you start

- A checkout of this repository, or an install of the `project-toolkit` plugin. See [installation](../installation.md).
- A shell open at the repository root, with `uv` installed.
- A rough idea of your starting point: a goal, a finished piece of work, a skill that misbehaves, a whole project, or a worry about your setup.
- Ten minutes.

Set a scratch directory for the hands-on steps:

```bash
S="$(mktemp -d)"
echo "$S"
```

## Steps

Part 1 is choosing the skill (steps 1 to 3).

1. Find your starting point in the table. Read across to the skill.

   | You have | Use | Start it with | Do not use it for |
   |----------|-----|---------------|-------------------|
   | A goal. You want a new skill, or want to know if one exists. | [`skillforge`](../../.claude/skills/skillforge/SKILL.md) | `create a skill`, `do I have a skill for`, `improve the X skill` | Scored tuning (`skillopt`). Saving finished work (`skillify`). Placement or markdown compression (`context-optimizer`). |
   | A workflow you just finished and want to keep. | [`skillify`](../../.claude/skills/skillify/SKILL.md) | `skillify this`, `save this as a skill` | Designing a skill from a goal (`skillforge`). |
   | A skill, agent file, or prompt that must get measurably better. | [`skillopt`](../../.claude/skills/skillopt/SKILL.md) | `optimize this skill`, `make this skill better` | Creating or routing skills (`skillforge`). Compressing markdown with no eval (`context-optimizer`). |
   | A whole project with unwritten workflow knowledge. | [`skill-bootstrap`](../../.claude/skills/skill-bootstrap/SKILL.md) | `bootstrap skills`, `build this repo's skill library` | One skill (`skillforge`). Scored tuning (`skillopt`). Session diagnosis (`skill-doctor`). |
   | A question about how your setup performs. | [`skill-doctor`](../../.claude/skills/skill-doctor/SKILL.md) | `diagnose skill usage`, `grade my agent setup` | Creating skills (`skill-bootstrap`). Tuning (`skillopt`). |

2. Check the common mix-ups.
   - "I did the work and now want a skill" is `skillify`, not `skillforge`. `skillify` reads what the session did. `skillforge` starts from what you want.
   - "This skill is weak" is `skillopt` only if you have scored tasks. Without them, use `skillforge` to rewrite it. `skillopt` refuses to run with no scored eval set.
   - "My skills never fire" is `skill-doctor`. It reads your past sessions and shows which skills ran.
   - "Where do my skills belong, and should this be a skill at all?" is `context-optimizer`. None of the five answer it.

3. Know how they chain. `skill-bootstrap` calls `skill-doctor` to diagnose, `skillforge` to author, and `skillopt` to tune. You can also run them in this order by hand: `skillify` or `skillforge` to write the skill, `skillopt` to improve it, `skill-doctor` to see whether it gets used.

   Short guides for the three skills this page does not walk through:

   - **`skillforge`.** Say `SkillForge: {goal}` with the goal in plain words. It first checks whether a skill already covers the goal, so you do not get a duplicate. Depth scales with risk: a small edit stays light, and an ambiguous or consequential one gets a panel. Validate the result with the scripts in the "Validation and Packaging" section of its [SKILL.md](../../.claude/skills/skillforge/SKILL.md). For the fields a skill needs, read [SKILL-AUTHORING.md](../SKILL-AUTHORING.md).
   - **`skill-bootstrap`.** Say `bootstrap skills`. It runs in one of two modes. `workflow` writes a skill only where it finds verified friction, such as repeated corrections or long review rounds. `knowledge` writes a skill only when a model without it gets a frozen test case wrong. There is no quota, so a run can write nothing. It asks at most five questions. Read [skill-bootstrap's SKILL.md](../../.claude/skills/skill-bootstrap/SKILL.md) before you start, because it needs `skillforge` and `context-optimizer` installed.
   - **`skill-doctor`.** Say `grade my agent setup`. It reads your local agent conversations and shows how your skills perform in one HTML report. Collection and rendering run on your machine. The conversation sources are Claude Code, Codex, Copilot CLI, Warp, Pi, Grok Build, ZCode, Hermes, and Factory Droid. For Factory Droid it reads `~/.factory/sessions`, and `--factory-home` points it at another location. The full table lives in [supported-harnesses.md](../../.claude/skills/skill-doctor/references/supported-harnesses.md). If your harness is not listed, `skill-doctor` stops before it reads anything.

Part 2 is capturing a workflow with `skillify` (steps 4 to 8).

`skillify` turns a workflow you just finished into a skill. The first check is a gate. It rejects one-offs, so a skill library does not fill up with noise.

4. Write an audit for a workflow worth keeping. It had nine tool calls, three decisions, two gotchas, and a phrase you would say to start it. Then run the gate.

   ```bash
   cat > "$S/audit.json" <<'EOF'
   {"tool_call_count": 9, "reusable_class": true, "decision_points": 3, "gotchas": 2, "trigger_phrase": "draft release notes"}
   EOF
   uv run python .claude/skills/skillify/scripts/skillify.py gate --audit "$S/audit.json"
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

5. Run the gate on a weak workflow: one tool call, no decisions, no trigger phrase.

   ```bash
   cat > "$S/weak.json" <<'EOF'
   {"tool_call_count": 1, "reusable_class": false, "decision_points": 0, "gotchas": 0, "trigger_phrase": ""}
   EOF
   uv run python .claude/skills/skillify/scripts/skillify.py gate --audit "$S/weak.json"
   ```

   The status is `REJECT`. Four reasons come back: `one_off`, `trivial_wrapper`, `no_real_procedure`, and `no_trigger_phrase`. The command still exits `0`. Read the `status` field, not the exit code.

6. Check for overlap. `skillify` patches an existing skill when 70 percent of the workflow's terms are already covered.

   ```bash
   cat > "$S/workflow.json" <<'EOF'
   {"actions": ["collect merged PRs", "draft release notes", "group by type"], "terms": ["release", "notes", "changelog", "merged", "pull", "requests"], "trigger_phrase": "draft release notes"}
   EOF
   uv run python .claude/skills/skillify/scripts/skillify.py overlap --workflow "$S/workflow.json" --root .claude/skills
   ```

   The status is `CREATE`. The closest existing skill covers about 64 percent of the terms, which is under the 70 percent line. The list of near matches changes as the skill library grows.

7. Write the skill. In a real run, the agent does this after `resolve` picks the skills directory. Here, write a small one into the scratch directory by hand. Use the section order from [skill-skeleton.md](../../.claude/skills/skillify/references/skill-skeleton.md).

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

8. Read the skill back with `verify`.

   ```bash
   uv run python .claude/skills/skillify/scripts/skillify.py verify --skill "$S/skills/release-notes-draft" --audit "$S/audit.json"
   ```

   The status is `PASS` and `failures` is empty. The command exits `0`. A `verify` pass shows the file is well formed. It does not show the skill helps. Part 3 covers that.

Part 3 is tuning a skill with `skillopt` (steps 9 and 10).

`skillopt` improves a skill through small patches. A patch lands only if it adds at least one passing task in a held-out set and loses none. The reason is in [ADR-087](../../.project-toolkit/architecture/ADR-087-held-out-validated-improvement.md). If you score every edit against the same tasks you read while editing, the score measures how well you fit those tasks. It stops measuring the skill.

The repository ships a sample eval set and two result files. The eval has ten tasks. Six are `train` tasks that the author may see. Four are `sel` tasks, the held-out set.

9. Run the gate on the sample, where the candidate fixes one held-out task and breaks none.

   ```bash
   R=.claude/skills/skillopt/references
   uv run python .claude/skills/skillopt/scripts/skillopt.py pair-gate \
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

10. Break one held-out task and run the gate again. This copy of the candidate results fails `t7`, which the incumbent passed.

    ```bash
    uv run python - "$R/example-candidate-results.json" "$S/regressed.json" <<'EOF'
    import json, sys
    results = json.load(open(sys.argv[1]))
    results["t7"] = False
    json.dump(results, open(sys.argv[2], "w"))
    EOF
    uv run python .claude/skills/skillopt/scripts/skillopt.py pair-gate \
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

You are done when both of these hold:

- You can fill in this sentence: "I will run `<skill>` by saying `<phrase>`, because I have `<starting point>`."
- The gate outputs match: step 4 printed `"status": "PROCEED"`, step 5 printed `"status": "REJECT"`, step 8 printed `"status": "PASS"`, step 9 printed `"verdict": "ACCEPT_PARETO"` and exited `0`, and step 10 printed `"verdict": "REJECT"` and exited `1`.

Check an exit code with `echo $?` right after the command. Delete the scratch directory (`$S`) when you finish.

To confirm the five skills exist in your install, list them. Five lines print:

```bash
ls .claude/skills | grep -E '^(skillforge|skillify|skillopt|skill-bootstrap|skill-doctor)$'
```

```text
skill-bootstrap
skill-doctor
skillforge
skillify
skillopt
```

When it fails, look here first:

- Fewer than five lines print. Your install is older than the skills, or you are on another harness. Copilot CLI keeps skills in `.github/skills`, so run the same `ls` there.
- A skill does not start when you say its phrase. Name it directly (`/skillopt` in Claude Code). Then read the "Skill Not Triggering" section of [SKILL-AUTHORING.md](../SKILL-AUTHORING.md).
- You cannot tell which skill fits. Say what you want to `/autoplan`. It routes requests that name no skill.
- `audit field 'reusable_class' must be true or false`. Use a JSON boolean, not a string. `skillify.py gate` exits `1`.
- `skillify.py overlap` returns `PATCH`. A skill in your tree already covers the workflow. Read it and patch it. The skill's own steps tell the agent to confirm the target path with you first.
- `pair-gate` exits `2`. The eval has no `sel` split, an exposed task sits in `sel`, or a result file is missing a task. Read the message, then [eval-set-format.md](../../.claude/skills/skillopt/references/eval-set-format.md).
- `REJECT_UNVERIFIED`. A result is missing or not a literal `true` or `false`. The gate does not count it.

What this page does not do: a real `skillopt` run needs two isolated runners. One session writes the candidate and sees only `train` tasks. A second session holds the `sel` tasks and sends back only the verdict. If the same agent wrote the candidate and the held-out tasks, those tasks are exposed and cannot count as `sel`. The steps above run the gate on shipped sample results, so you can see how it decides. They are not an improvement claim for any skill.

ADR-087 has `status: proposed` as of 2026-11-10. Read it as the reasoning behind the gate. It is not a rule in force.

## Next

Continue with [Safe agent actions](safe-agent-actions.md), or measure what your skills do with [Measure agent quality with evals and benchmarks](measure-agent-quality.md).

Reference sources this page relies on:

- [skillopt SKILL.md](../../.claude/skills/skillopt/SKILL.md): the full loop, including the budget, patch, and null-control steps.
- [skillify SKILL.md](../../.claude/skills/skillify/SKILL.md): destination rules and the capability gate.
- [SKILL-AUTHORING.md](../SKILL-AUTHORING.md): frontmatter, validation rules, and the authoring checklist.
- [skill-reference.md](../skill-reference.md): the catalog of skills.
