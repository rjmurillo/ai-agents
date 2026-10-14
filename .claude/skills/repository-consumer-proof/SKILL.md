---
name: repository-consumer-proof
version: 1.0.0
description: >-
  Verify ai-agents hooks, installed dispatch, and behavior beyond green builds.
  Do NOT use for PR blockers (use repository-pr-recovery).
license: MIT
metadata:
  distribution: repo-local
  capability:
    kind: orchestrator
    status: active
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan selects this repository outcome composition from its intents
    user-facing: true
    intents:
      - prove an ai-agents capability works
      - plugin initializes but never executes
      - hook fails from foreign cwd
      - plugin initializes foreign cwd
      - installed plugin intended marker
      - build passes consumer behavior uncertain
      - ai-agents runtime parity
---

# Repository consumer proof

Requires the `rjmurillo/ai-agents` checkout and its contributor-only sibling skills.

Inputs: requested capability, selected harness, consumer context, and allowed execution environment.
Apply the [common execution contract](../repository-pr-recovery/references/library.md#common-execution-contract).
Define success as observable consumer behavior, including valid neighboring behavior.
Reuse generation, portability, empirical probes, and validation instead of adding another framework.

## Triggers

- `prove an ai-agents capability works`
- `plugin initializes but never executes`
- `hook fails from foreign cwd`

## Process

### Phase 1: Select the missing proof and source before implementation

Write the expected observation and one negative control in task context.
A negative control changes one condition and should invert the relevant observation.
Select the lowest layer that lacks evidence:

| Missing evidence | First discriminating action | Required observation |
|---|---|---|
| Canonical ownership or output drift | Read the artifact row in the linked binplace manifest and build guide. | Source, plugin output, and installed output agree on ownership. |
| Hook executes only from repository cwd | Select runtime-contract and plugin-root cases. | Installed launcher reaches the intended implementation from foreign cwd. |
| Plugin initializes but a command does not execute | Select the installed completion-dispatcher case. | Parsed criterion output proves dispatch actually ran. |
| Structural tests pass but agent behavior is wrong | Select a runtime parity fixture and negative control. | Valid live samples meet the maintained behavioral thresholds. |

For generated artifacts, inspect current owners before loading older generation instructions.
`.claude/skills/*/SKILL.md`, hooks, settings, agents, and rules are generated outputs.
Skill support files remain canonical under `.claude/skills/`, except the review validator sidecar.
See [build ownership](../../../build/AGENTS.md),
[binplace manifest](../../../templates/platforms/binplace.yaml),
and [.claude ownership](../../../.claude/AGENTS.md).
Do not repair a mirror or edit canonical input merely to match a stale output.

If diagnosis is requested, report the discriminating result without changing code.
For authorized repairs, use [ai-agents-portability-campaign](../../../.claude/skills/ai-agents-portability-campaign/SKILL.md)
for hook adaptation and [agent-harness-reference](../../../.claude/skills/agent-harness-reference/SKILL.md)
for the current host contract.
Change only the actual owning source and its required generated outputs.

### Phase 2: Prove the selected runtime layer

For an authorized checkout test environment, select the relevant existing suite:

```bash
uv run pytest tests/build_scripts/test_generate_hooks_runtime_contract.py tests/build_scripts/test_generate_hooks_plugin_root.py -q
uv run pytest tests/test_run_completion_gate_install.py -q
```

Run only the suite corresponding to the missing proof.
These tests create fixtures and execute subprocesses; they require writable test space.
Do not execute them under a read-only-only investigation.
Source verification of their commands is not a runtime test result.

The hook suites exercise foreign cwd and host-supplied plugin-root variables.
Require the intended marker and the bare-relative-path negative control.
Keep source selection, initialization, launch location, and actual execution distinct.
Read [the runtime suite](../../../tests/build_scripts/test_generate_hooks_runtime_contract.py)
and [plugin-root suite](../../../tests/build_scripts/test_generate_hooks_plugin_root.py).

For the installed dispatcher, select `test_the_bundled_config_runs_its_criteria_end_to_end`.
Require parsed `gate_ran`, execution status, trust classifications, and criterion results.
Absence of refusal text does not establish dispatch.
This expectation comes from [the maintained installation test](../../../tests/test_run_completion_gate_install.py).

After authorized source changes, use the maintained generation procedure.
Bind `WORKFLOW_REPO_ROOT` to the checkout root before running these commands.
Invoke the linked generator through that absolute root, then its `--check` form.
See the [common generator commands](../repository-pr-recovery/references/library.md#working-boundary).
Read the [build guide](../../../build/AGENTS.md) for generator order and platform coverage.
Run generation only when the current task authorizes those output writes.
Use `ai-agents-change-control` to classify the required gates.
Use `ai-agents-validation-and-qa` to produce evidence at the final head.
Avoid repeating full gates during edits.
Inspect whether local test selection executed tests or used collection-only fallback.
Neither collection nor selective success proves subprocess dependencies were exercised.
The [pre-push definition](../../../lefthook.yml) leaves complete-suite acceptance to CI.

### Phase 3: Promote behavior evidence through existing acceptance

For a behavioral defect or supported research, take these three steps:

1. Select the existing fixture and predict the positive and negative observations.
2. Validate deterministic controls using the maintained runtime evaluator's dry-run route.
3. Obtain authorized runtime space, run valid live samples, and compare both observations.

Use the [evaluation guide](../../../scripts/eval/README.md) for supported launchers and options.
For completion-terminal behavior, the source-verified POSIX form is:

```bash
WORKFLOW_REPO_ROOT="$PWD"
uv run python "$WORKFLOW_REPO_ROOT/scripts/eval/eval_runtime_parity.py" --fixtures tests/evals/completion-terminal-runtime-fixtures.json --model "$MODEL_ID" --harnesses claude --dry-run
```

Resolve `MODEL_ID` from current supported choices rather than copying an old pin.
Dry-run controls do not execute semantic behavior assertions.
Keep those assertions `not_run`; missing CLI or invalid grading supplies no passing sample.
The falsifiable milestone is valid live evidence that controls invert and behavior meets thresholds.
Read current thresholds in the maintained guide before evaluating them.
Rank supported solutions by the failed layer: correct source, repair launch, then alter behavior.
Require a mechanism explaining both observations before promoting a repair.
Reopen a historical workaround only when changed host versions or evidence justify it.

Pass measured artifacts and the exact remaining action to `review`, then `ship` when authorized.
Use [repository-completion-proof](../repository-completion-proof/SKILL.md) for PR acceptance.
Use [ai-agents-generation-and-release](../../../.claude/skills/ai-agents-generation-and-release/SKILL.md)
for release routing, checking current ownership against the sources above.
An artifact build does not prove publication, promotion, or consumer adoption.
Report each measured layer, the consumer-visible result, and remaining operator work.
If live runtime access is unavailable, report runtime impact as unmeasured.

## Verification

- [ ] The selected layer has observed positive and negative evidence.
- [ ] Unmeasured behavior and operator-owned work remain explicitly visible.

## Anti-Patterns

Follow the [shared outcome boundary](../repository-pr-recovery/references/library.md#common-execution-contract).

## Evolution

Follow the [shared maintenance policy](../repository-pr-recovery/references/library.md#maintenance).
