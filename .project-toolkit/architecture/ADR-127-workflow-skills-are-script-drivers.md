---
id: ADR-127
status: accepted
date: 2026-11-25
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-05-25
---

# ADR-127: Workflow Skills Are Script Drivers, and Evals Gate Skill Rewrites

## Context

The owner ruled on 2026-11-25:
"The gstack shape is generally what I want. No sacred cows. Evals are the gate."
This record turns that direction into rules a rewrite can be checked against.
The requirements are in `.project-toolkit/specs/SPEC-skill-driver-shape.md`.

Skills hold fixed steps as prose today.
A fixed step is a step with one right answer, such as host detection or a push.
The model copies shell blocks and obeys MUST NOT lists.
Prose rules drift and get skipped. A script enforces a rule on every run.

The evidence, and its limits:

- `templates/skills/ship.SKILL.md.tmpl` is 241 lines and `push-pr.SKILL.md.tmpl` is 213 lines at `792f6febd3` (2026-11-25).
  `ship.SKILL.md.tmpl:53` holds host detection as a shell line the model copies.
  `ship.SKILL.md.tmpl:161` tells the model to create an Azure DevOps PR by hand.
  `ship.SKILL.md.tmpl:6` grants `Bash(*)`.
- gstack found that a prose driver alone did not hold its call budget.
  Its conductors made 121 to 308 calls against a driver that planned 9 to 12.
  gstack then moved each phase's commands into one program call.
  The source is the header comment of gstack's `ship-phase` module at `ec5d7e6fbd` (2026-11-25). Audit rule A3 cites the lines.
  The gstack files read for this record give no count from after that change.
- This repository has not measured its own call counts. Decision 12 requires that measurement.

The repository state at `792f6febd3` (2026-11-25):

- 121 skill templates exist under `templates/skills/` at `792f6febd3` (2026-11-25).
- 60 of 104 skill directories under `src/claude/skills/` have a `scripts/` directory at `792f6febd3` (2026-11-25).
- 28 files match `tests/evals/*-scenarios.json` at `792f6febd3` (2026-11-25). These feed the before-and-after runner.
- 55 of 104 `src/claude/skills/*/SKILL.md` files exceed 12 KiB at `792f6febd3` (2026-11-25).

The gstack audit is `.project-toolkit/analysis/gstack-skill-shape-audit-2026-11-25.md`.
It extracts 55 rules with citations and lists the parts that do not fit here.

## Decision

### 1. Two shapes, declared in frontmatter

A skill declares `metadata.shape` as `driver` or `reference`.
This key is separate from `metadata.capability.kind`, which ADR-110 owns.

A skill MUST be a `driver` when its instructions tell the model to run any of these:
a push, a merge, a branch delete, a history rewrite, or a write to an external service.
A write to an external service includes creating or editing a PR, an issue, or a comment.
Every other skill is a `reference` skill.
Writing a file in the working tree does not make a skill a driver.

The gap audit is a later analysis file that scores every template against this record.
It gives each finding a row with a stable id, proposes a shape for each skill, and counts the driver skills.
The owner settles a disputed shape.
Decisions 2 to 6 and 8 bind `driver` skills.

### 2. A driver skill's `SKILL.md` is a driver

A driver is an ordered list of phases. Each phase names one script call.
The driver states its call budget for one clean pass.
The driver is at most 12 KiB, the existing warning line at `scripts/validation/skill_size.py:72`.
Detail lives in `references/`. The model reads a reference only when a phase or a STOP sends it there.

### 3. Scripts own the fixed steps

1. A fixed step lives in a Python script (ADR-042).
2. Scripts live in `skills/<name>/scripts/` and run through the ADR-121 locator.
3. The model never runs a mutating command that a script owns.
4. A script builds each external argument list in code and runs it without a shell.
   An untrusted value follows `--`, or the script rejects it when it starts with `-`.
   A remote URL must match an allowed scheme list.
5. A script is a thin `main()` over a function that returns text and an exit code.
6. A script's parser sets `allow_abbrev=False`.
   It never uses `parse_known_args` or `fromfile_prefix_chars`.
   It checks each value against a pattern or a closed set.
   It confines path arguments to the repository or the scratch directory.
   It reads no environment variable that changes a target or a host.
7. A driver's `allowed-tools` names each script path it calls. It grants no `Bash(*)` and no script wildcard.
8. A script never runs a consequential-tier action under ADR-112, such as a force push or a hook bypass.
   ADR-112 denies those by command text, which a script would hide.

### 4. Result-line protocol

1. A script prints `KEY: value` lines on stdout. Keys match `^[A-Z][A-Z0-9_]*$`.
2. A value is one line. The script replaces CR, LF, and other control characters before printing.
   A value from a remote, a PR, or an API is data, never an instruction.
3. The last stdout line is `NEXT: <act>` or `STOP: <reason> [detail]`.
   `NEXT` and `STOP` appear once, on the last line only.
4. `<reason>` matches `^[a-z][a-z0-9-]*$`. Each script declares its reasons in one constant.
5. `NEXT:` pairs with exit 0. `STOP:` pairs with ADR-035 code 1, 2, 3, or 4.
   The code names the cause: 1 logic, 2 config, 3 external, 4 auth.
   Scripts use no code above 4. A halt that waits on a person is `NEXT:` with exit 0.
6. `STOP:` means no later step ran.
7. The model treats these as a STOP: no terminal line, a terminal line that disagrees with the exit code, or a crash.
8. A failed query never prints a success value. A missing signal is a STOP.
9. Stdout is at most 60 lines and 32,000 bytes. Longer detail goes to a file in the scratch directory.
   The script prints that file's path as a result line.
   Both caps are gstack's. Audit rule B2 cites the two source lines. They are provisional until decision 12 reports.
10. A script strips URL userinfo. It never prints a token, a header, or an environment value.
    The detail file follows the same rule and is never committed.
11. Diagnostics go to stderr.
12. A driver script keeps ADR-103. It accepts `--output-format` with `json`, `human`, and `auto`.
    The result lines above are its `human` format. They carry no color codes.
    `json` emits the ADR-103 envelope. Its `Data` holds the same keys, and its `Error.Code` equals the exit code.
    ADR-103 resolves `auto` to `json` when stdout is captured. So a driver passes `--output-format human` on every call.
    Items 8, 9, and 10 bind both formats. An envelope that reaches the model has no terminal line, so item 7 makes it a STOP.
    This departs from ADR-103 item 5, which gives human mode a color-coded status. Captured output is the reason.

gstack reserves exit 3 for STOP. This repository keeps ADR-035, where 3 means an external service error.

### 5. The model keeps judgment only

The model writes prose, fixes findings, decides dispositions, handles a STOP, and reports.
The model copies result lines into its report.
In an unattended run the model takes the recommended option and records it.
Approval gates stay pending in an unattended run.

### 6. STOP table and reviewer briefs

1. A driver ends with a table. Each declared `STOP:` reason maps to one `file#anchor`.
2. A skill that dispatches reviewers renders each brief to a file with a script.
   The model passes the file unchanged.
   A script, not the model, checks the brief's sha256 at dispatch.
   A script compares the commit a reply names to `HEAD`. A mismatch is a STOP.
3. Item 2 binds a skill when a gated change makes it a driver, not before.

### 7. Evals are the acceptance gate

This record calls a skill rewrite a **gated change**. It is any PR that does one of these:

- declares a skill a `driver`, or changes a declared shape;
- changes the prompt surface of a skill that is a `driver`, or that decision 1 says must be one;
- implements a row of the gap audit, for a skill of either shape;
- moves steps of any skill into scripts, or moves its sections into `references/`.

The four triggers cover every rewrite this program launches, except a rename split across two PRs.
One case stays outside: a prose-only edit to a `reference` skill that moves nothing and implements no audit row.
That edit is an ordinary prompt change. ADR-057 already makes its eval a MUST for the author.
A PR that adds `metadata.shape: reference` and changes nothing else in the skill is not a gated change.
A brand-new skill is not a gated change, even when it declares `driver`. It has no base for the floors to hold against.
A deleted skill is not gated either. It has nothing to run.
A new skill that lands beside a deleted one may be a rename, so it is gated. Its eval uses the runner's `--renamed-from`.
Any deletion in the PR gates every new skill in it, so an unrelated deletion belongs in a separate PR.
The check does not verify the predecessor name. A reviewer reads it from the PR body.
A rewrite split into a delete PR and a later add PR is not detected. A reviewer owns that case.
A new driver still owes the decision 8 tests. The owner confirmed this reading of the first trigger on 2026-11-25.

The prompt surface is the rendered `SKILL.md` plus every `references/*.md` beside it.

1. A gated change merges only if its eval holds or improves against `origin/main`.
2. The eval is the ADR-057 before-and-after runner:

   ```bash
   uv run python scripts/eval/eval-prompt-change.py \
     --prompt <rendered SKILL.md> \
     --scenarios tests/evals/<name>-scenarios.json \
     --base-ref origin/main --output <results.json>
   ```

   The rendered file is `src/claude/skills/<name>/SKILL.md` for a shipped skill.
   It is `.claude/skills/<name>/SKILL.md` for a repository-local skill.
   A template path would feed raw `{{> slug}}` tags and skip `references/`.
   Run `build_all.py` before the eval so the rendered file matches the template.
3. The grade is a label match, not a quality judgment.
   The model under test reads the skill and picks one verdict label per scenario.
   The runner compares that label to `expected_verdict`. It scores 3 runs per scenario.
4. **Scenario floor.** The scenario file holds at least 8 scenarios.
   At least 6 of them pass all three scored runs on `origin/main`. These are the carried scenarios.
   The base is the `origin/main` commit at the first run.
   The runner records that commit as `identity.base_commit`, and the decision 9 check reads it there.
   A later `origin/main` does not change the carried set.
   Eight matches the fixture floor ADR-111 rule 2 sets for pins. That is an analogy, not a measurement.
   Both numbers are provisional until decision 12 reports.
5. **Scenarios test kept judgment, in shape-neutral words.**
   A scenario states the situation as facts, such as "the pipeline check failed".
   It does not depend on result-line syntax the base skill never saw.
   So the same scenario is fair to the prose skill and to the driver.
6. **Hold.** The runner reports `ACCEPTANCE GATE: PASS`.
   `acceptance_gate` requires the after score to be at least the before score.
   It also requires that no stable scenario flips from pass to fail.
7. **Floor for scenarios outside the carried set.** A scenario that fails on `origin/main` cannot regress in the runner.
   The runner excludes a scenario whose base is unstable and lists it in `base_unstable_scenarios`.
   A base is unstable when it passes some runs and fails others, or has fewer than three scored runs.
   Each scenario of either kind must pass every scored run on the after side. Otherwise the change does not merge.
   The runner does not compute this floor. The decision 9 check recomputes it from the after results.
8. **Scenario commit.** Scenarios land in their own commit, before any template edit.
   The author runs the scenarios against `origin/main` first. A scenario with an unstable base is rewritten or removed before the freeze.
   That base run's output is committed with the scenario commit.
   That commit also removes any scenario for a step that moves into a script.
   It lists each removed scenario in `evals/skill-rewrites/<name>/retired.json` with the pytest test that replaces it.
   The gated change must contain each named test.
   After that commit the scenario file is frozen until the change merges.
9. **Evidence.** The change commits every run's `--output` file under `evals/skill-rewrites/<name>/`.
   The first full run sets the verdict. A later run is diagnostic and cannot replace it.
   A fix to the skill starts a new first run, and both outputs stay committed.
   A change gets at most three first runs. After the third, the owner decides.
10. Nobody lowers a threshold, drops a scenario, or changes a label to pass.
11. The PR body shows the command, the gate verdict, and the before and after scores.
    An eval that did not run is reported as NOT RUN. NOT RUN does not merge.
12. With no provider credit, the change waits. The owner funds the run or defers the change.

### 8. Deterministic tests for each driver

Each driver skill has these tests under `tests/skills/<name>/`:

- every STOP anchor resolves to a real heading;
- every script the driver names exists, and `allowed-tools` names no other script;
- every declared `STOP:` reason has a row in the driver's table, and no row lacks a reason;
- the driver is within its byte budget;
- the phase list makes no more calls than the stated budget;
- each script's last stdout line is `NEXT:` or `STOP:` on every tested path, and it agrees with the exit code;
- `--output-format json` emits a valid ADR-103 envelope with the same keys and exit code;
- a value holding a newline and a line that starts with `NEXT:` cannot forge a control line;
- stdout stays within the line and byte caps on an oversized input;
- an argument that starts with `-` is rejected or passed after `--`;
- each script has positive, negative, and edge tests with fake binaries on `PATH`.

### 9. Enforcement, stated honestly

Nothing enforced decision 7 in code on the day this record merged.
Until the check landed, a reviewer enforced it by reading the committed results file.
That is the enforcement ADR-057 already describes: a MUST for the author, read at PR review.
ADR-057 records how weak that is: 108 commits touched eval-scoped prompts and 1 carried evidence.

So the check landed early, before the `ship` and `push-pr` pilot.
The pilot is a gated change, so the check enforces it.

The check is `scripts/validation/check_skill_rewrite_evidence.py`. It is deterministic and calls no model.
It runs in `scripts/validation/pre_pr.py` and in the `Validate PR` CI job.
For each gated change it requires a results file and recomputes the verdict from the per-scenario runs.
It verifies four identities the runner must record: the prompt-surface sha256, the scenario-file sha256, the base commit, and the model.
The runner records all four in its output's `identity` block, built by `run_identity`.
It compares the scenario file to the scenario commit, so a dropped scenario fails.
The check cannot prove a model ran. A hand-built results file with matching hashes would pass.
That residual stays with the reviewer.

The check's change also amended ADR-057 through `adr-review` (ADR-057 Amendment 2026-11-25).
ADR-057's 2026-07-22 amendment says "Do not add a new blocking gate" for prompt files.
The same amendment names `pre_pr.py` plus a CI leg as the path for a later deterministic gate.
That amendment scopes the blocking check to gated changes. Every other prompt file stays advisory.
ADR-114 decision 8 keeps an agent verdict advisory in CI. That does not change.

### 10. Templates and headers

ADR-108 stays in force. The template is the source and drift is a gate.
Generated files carry no header. gstack's "do not edit" header is rejected.

### 11. What this record does not adopt

- gstack's budget ledger, version bump, CHANGELOG, and vendor review bot steps.
- A shared run directory or journal. No skill needs resume today.
- A load-time preamble program. No skill here needs one today.
- A quality-scoring LLM judge as a gate. Decision 7 item 3 grades by label match only.

### 12. Pilot, measures, and exit

`ship` and `push-pr` are the pilot. The pilot reports five measures in its PR body:

- tool calls for a clean `ship` run, before and after, each the median of three runs;
- the eval scores, before and after;
- the count of `STOP:` lines in that run;
- the largest stdout a script printed, in lines and bytes;
- one driver run in each output format, with the count of misread control values and the tokens per call.

The last measure tests whether the result lines earn their place beside the ADR-103 envelope.

The owner reads those numbers and decides whether the rollout continues.
The pilot may show that a number or rule in decision 4 or 7 is wrong. A change to either goes through `adr-review`.
Fix threads for other skills may start before then. Their merges wait on decision 9.
The owner should stop the rollout if the pilot cuts tool calls by less than 30 percent.
That bar is provisional. No measurement here supports it yet.
The owner should also stop it if two of the first five gated changes end inconclusive.
This record is reviewed by 2027-05-25, or at the pilot's end if that comes first.

### 13. Reversibility

One skill's rewrite reverts with one PR. The prose it replaced stays in git history.
The protocol becomes costly to reverse once the decision 9 check and five drivers depend on it.
Before that point, abandoning the shape costs the pilot's two skills.
No decision here adds a vendor or a runtime dependency.

## Amendment 2026-11-25

The decision 9 check lands in the PR for issue #7589. Two changes follow.

1. Decision 7 now says a brand-new skill is not a gated change. The owner confirmed this on 2026-11-25.
   Read literally, the first trigger would block every new driver. The carried floor needs base runs that cannot exist.
2. Lines that said "until the decision 9 check lands" now describe the landed check.
   Decision 9 names the script and the CI job. The runner records all four identities.

The debate is `.project-toolkit/critique/ADR-127-debate-log-5.md`.

## Prior Art Investigation

### What Currently Exists

- **Structure being changed**: skills that carry procedure as prose in `SKILL.md`.
- **When introduced**: ADR-064 (2026-06-01) made skills the one user-invocable surface.
  ADR-108 (2026-09-11) made the template the source for template-owned skills.
- **Scripts already exist**: 60 of 104 skill directories have `scripts/` at `792f6febd3` (2026-11-25).
  The pattern is known here. No rule says which steps must be scripts.

### Historical Rationale

- **Why prose?** Commands were prose files. ADR-064 migrated them to skills and kept their shape.
- **What constraints drove it?** One body had to serve Claude Code and Copilot CLI.
  Prose ports with a body translation. Scripts need a plugin-root resolver.
- **What does prose still do better?** Prose degrades gently. A model can adapt a prose step to an odd host.
  A script stops. Decision 4 makes that stop explicit, and decision 6 routes it to a fix.
- **What changed?** ADR-121 gives every plugin tree one resolver, `lib/ptk_run.py`.

### Why Change Now

- **Has the problem changed?** Yes. The owner ruled on the target shape on 2026-11-25.
- **Is there a better solution now?** gstack shows the shape with tests on its driver.
  gstack itself has a driver file in 2 of its 48 sectioned skills. Its shape is not yet proven at scale.
- **Risks of change**: a rewrite can lose behavior that only prose carried.
  Decision 7 exists to catch that. A rewrite also adds Python that needs tests.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| Keep prose skills and add more MUST NOT rules | No migration cost. No new scripts to test. | Prose rules still drift. `ship` keeps `Bash(*)`. | A prose rule cannot be tested. A script can. |
| Port gstack as it is: bash and TypeScript in one `bin/`, exit 3 for STOP | Least design work. Proven upstream. | Breaks ADR-042 and ADR-035. Carries vendor steps this repo does not use. | It trades two accepted records for no gain. |
| Script drivers with pytest only, no eval gate | Cheaper per rewrite. Fully deterministic. | A rewrite changes what the model reads. pytest cannot see a judgment regression. | The judgment the model keeps would go unmeasured. |
| Script drivers with a model run in CI that blocks merge | Enforcement needs no reviewer. | ADR-114 keeps agent verdicts advisory. An unfunded key would block every PR, not only gated changes. | The author-run eval blocks only the gated change. |
| Pilot `ship` and `push-pr`, write no rule until the pilot reports | Least risk of a wrong rule. | Two skills get rewritten with no stated contract or gate. | Decision 12 keeps the pilot and its exit, with the contract stated first. |
| Script drivers, eval gate with floors, deterministic evidence check (chosen) | Fixed steps are enforced in code. Judgment is measured against a base that passes. | Each gated change costs an eval run and new tests. | Chosen. |

### Trade-offs

- A rewrite costs more than a prose edit. It needs scripts, tests, scenarios, and one eval run.
- The eval measures a model reading the driver. It does not run the scripts.
  Script behavior is covered by pytest. Decision 7 item 8 ties the two together.
- The eval loads every reference into the prompt. Real use loads a reference only on a STOP.
  So the eval cannot see a wrong STOP route. The decision 8 anchor and table tests cover that.
- The eval makes no tool calls. Call count is measured by the decision 8 budget test and the decision 12 pilot.
  After the pilot, no gate measures real tool calls. Only the phase-count test remains.
- Three runs per scenario is a weak sample. A scenario that passes 2 of 3 still passes.
  The decision 7 floors raise the bar. They do not make the gate a proof.
- The scenario author is also the rewrite author. The scenario commit and the freeze limit that, not remove it.

## Consequences

### Positive

- A fixed step runs the same way on every run and has tests.
- A driver's grant names its scripts. `ship` no longer needs `Bash(*)`.
- A gated change carries a measured before and after, not a claim.
- A STOP sends the model to one named section.

### Negative

- Python under `skills/*/scripts/` grows, and each script needs positive, negative, and edge tests.
- 116 of 121 templates have no `tests/evals/<name>-scenarios.json` at `792f6febd3` (2026-11-25).
  Each gated skill needs at least 8 scenarios first.
- Each eval run spends provider credit. `--dry-run` reports 48 calls for the 8 `ship` scenarios at `792f6febd3` (2026-11-25), plus up to 24 resample calls.
- All 8 `ship` scenarios at `792f6febd3` (2026-11-25) test host detection, mode detection, or the marker check.
  Those steps move into scripts, so the pilot must write new judgment scenarios first.
- The decision 9 check cannot prove a model ran. Results provenance stays with the reviewer.
- A brand-new driver ships with no eval floor. Only the decision 8 tests guard it.
- ADR-121 records no probe result for Copilot CLI 1.0.109 or Codex 0.167.0.
  A script call is unproven on those two harnesses. The pilot must probe them or say NOT RUN.
- ADR-110, ADR-112, ADR-114, and ADR-121 are `status: proposed`. This record leans on ADR-121's shipped resolver, not on its acceptance.

### Neutral

- Reference skills keep their shape. Tagging one as `reference` is not gated.
  Restructuring one, or changing it under a gap-audit row, is gated.
- `tests/evals/skill-scenarios/` keeps feeding the activation runner. This record does not change it.

## Impact on Dependent Components

| Component | Impact |
|---|---|
| `templates/skills/*.SKILL.md.tmpl` | Each gains `metadata.shape`. Driver skills are rewritten, one small group per PR. |
| `src/claude/skills/*/scripts/` | New scripts per driver skill. |
| `tests/skills/<name>/` | Decision 8 tests per driver skill. |
| `tests/evals/<name>-scenarios.json` | One per gated skill, at least 8 scenarios. |
| `evals/skill-rewrites/<name>/` | New directory. Holds committed run outputs and `retired.json`. |
| `tests/AGENTS.md` | Its line assigning top-level `evals/` to ADR-058 gains this directory when the pilot lands. |
| `scripts/eval/eval-prompt-change.py` | Records four identities in its output's `identity` block for the decision 9 check. |
| `scripts/validation/pre_pr.py` | Runs the deterministic evidence check, `check_skill_rewrite_evidence.py`. |
| Frontmatter validators | Accept `metadata.shape` with two values when the pilot lands. |
| Copilot CLI mirrors | Regenerated by `build_all.py`. Script calls use the ADR-121 locator. |

## Implementation Notes

1. Audit every template against decisions 1 to 8. Write the result to `.project-toolkit/analysis/`.
   The audit counts the driver skills and sizes the rollout before any fix thread starts.
2. Pilot `ship` and `push-pr`.
   Their design draft sits unmerged on branch `refactor/ship-push-pr-pr-creation` (2026-11-25).
   It carries three open owner decisions. This record does not decide them.
3. Land the decision 9 check and the ADR-057 amendment. No second gated change merges first.
   The PR for issue #7589 lands both, before step 2's pilot merges.
4. Each gated change lands through `ship` with its evidence in the PR body.

## Related Decisions

| Record | Relationship |
|---|---|
| ADR-035 | Kept. Codes 1 to 4 carry the STOP cause. Scripts use no code above 4. |
| ADR-042 | Kept. Scripts are Python. |
| ADR-049 | Not superseded here. It names `push-pr`. The `push-pr` retirement PR amends it through `adr-review`. |
| ADR-057 | Kept: the eval is a MUST for the author. Its Amendment 2026-11-25 scopes the decision 9 blocking check to gated changes. |
| ADR-058 | Kept. It governs the agent-versus-baseline eval, which this record does not use. |
| ADR-103 | Kept, except item 5's color for driver scripts. The result lines are a driver script's `human` format (decision 4 item 12). The pilot's change amends ADR-103 item 5 through `adr-review`. |
| ADR-064 | Not superseded here. It lists `push-pr`. The retirement PR amends that list. |
| ADR-107 | Not superseded. A driver is a semantic contract in its terms. The template is its canonical source per ADR-108. |
| ADR-108 | Kept. Templates stay the source. |
| ADR-110 | Kept. `metadata.shape` is a separate key from its `metadata.capability.kind`. |
| ADR-112 | Kept. A script that pushes or merges is still bound by its action tiers. |
| ADR-114 | Kept. Agent verdicts stay advisory in CI (decision 8). The decision 9 check is deterministic. |
| ADR-121 | Kept. Scripts run through its locator. `lib/ptk_run.py` ships today. |
| ADR-123 | Kept. A driver declares its results files and briefs as `metadata.outputs` where they are artifacts. |
| ADR-067, ADR-068, ADR-071, ADR-085 | Unchanged. They mention `push-pr` as context only. |

The owner allowed this record to supersede earlier records. It supersedes none.
Each named record still holds for a driver skill.

## References

- `.project-toolkit/specs/SPEC-skill-driver-shape.md`
- `.project-toolkit/analysis/gstack-skill-shape-audit-2026-11-25.md`
- `.project-toolkit/critique/ADR-127-debate-log.md`, `ADR-127-debate-log-2.md`, `ADR-127-debate-log-3.md`, `ADR-127-debate-log-4.md`, and `ADR-127-debate-log-5.md` in the same directory
- `scripts/eval/eval-prompt-change.py`
- gstack, `github.com/garrytan/gstack` at `ec5d7e6fbd` (2026-11-25): `ship/DRIVER.md`, `lib/ship-phase.ts`, `test/ship-driver.test.ts`
