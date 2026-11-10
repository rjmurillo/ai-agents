---
name: "skill-doctor"
description: "Use for `diagnose skill usage`, `grade my agent setup`, or `run skill-doctor`. Do NOT use for skill creation (use skill-bootstrap) or tuning (use skillopt)."
metadata:
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan matches a request to diagnose installed skills from local sessions
    user-facing: true
    intents:
      - diagnose skill usage from sessions
      - grade my agent setup
      - run skill-doctor
---
# skill-doctor

Forked from warpdotdev/common-skills by the Warp team, under MIT.
Copyright (c) 2026 Denver Technologies, Inc. See `LICENSE`.
Maintainers: read `references/upstream-sync.md` before reconciling upstream changes.

Grade the user's agent setup by scoring recent local agent conversations, then surface unevaluated improvement candidates with handoff prompts and render one shareable report page.

The report can cover conversations in the current repository, conversations in selected projects, or all local conversations. It can evaluate project skills alone or project and global skills together.

Collection and rendering run locally.
Scoring uses the active agent's configured model provider.
Do not upload journals or excerpts to additional services.
Share only artifacts the user explicitly authorizes.

## Operating systems

The collector and renderer support Linux, macOS, and Windows.
They require Python 3.10+ and use only its standard library.
Git enables automatic repository discovery.
Use the Bash examples on Linux and macOS, or PowerShell examples on Windows.
Use `python3` on POSIX and `python` on Windows.
If Windows exposes only the Python launcher, substitute `py -3` for `python`.
Quote script, project, and report paths, including paths with spaces or Unicode.

Let `SKILL_ROOT` be the directory containing this SKILL.md.
Set its absolute path from the loaded skill's actual file location.
Do this before either example, even when plugin environment variables are unset.
Never derive it from the user's working directory or require a Git checkout.

```bash
: "${SKILL_ROOT:?Set SKILL_ROOT from the absolute path of the loaded SKILL.md}"
test -f "$SKILL_ROOT/scripts/collect_sessions.py" || exit 1
```

In PowerShell, set the same loaded-skill path and use native temporary storage:

```powershell
if (-not $SKILL_ROOT -or -not (Test-Path (Join-Path $SKILL_ROOT 'scripts\collect_sessions.py'))) {
    throw 'Set SKILL_ROOT from the absolute path of the loaded SKILL.md.'
}
$REPORT_DIR = Join-Path ([System.IO.Path]::GetTempPath()) ("skill-doctor-" + [guid]::NewGuid())
```

Create the report directory only after the startup gate and scope choices.

## Triggers

- `diagnose skill usage`
- `grade my agent setup`
- `run skill-doctor`

## Scripts

| File under `$SKILL_ROOT/scripts` | Purpose |
| --- | --- |
| `collect_sessions.py` | Collect selected journals into `inventory.json` and bounded transcripts. |
| `render_report.py` | Render scored `report.json` into `report.html`; `--open` requests browser launch. |
| `audit_scores.py` | Validate per-session rubric results in `scores.json` and compute the Step 3 aggregates. |
| `audit_manifest.py` | Validate an `audit_manifest.json` written by `collect_sessions.py --audit-manifest`. |
| `audit_batches.py` | `assign` immutable review batches from `inventory.json`; `import` one batch of score rows into an accepted file. |
| `public_export.py` | Write an aggregate-only summary of `report.json` that is safe to share. |
| `warp_decoder.py` | Imported Warp protobuf decoder, not a standalone CLI. |

Every CLI accepts `--help`.
Exit 0 means success, 1 means failure (for `audit_scores.py`, `audit_manifest.py`, `audit_batches.py`, `public_export.py`, and `render_report.py`: invalid input, an unsupported claim, or a private value in an export; nothing is written), and 2 means invalid CLI arguments or an unreadable file.
Use absolute script paths, as shown below, from any working directory.

## Process

### Step 0: Start the run

#### Verify the executing harness

Read `$SKILL_ROOT/references/supported-harnesses.md` and identify the harness executing this skill from the runtime context. If it is unsupported or cannot be identified confidently, follow the reference's stop behavior. Do not create a report directory or read conversation history.

#### Ask which conversations to grade

When skill-bootstrap invokes this skill, reuse its validated repository and
project-only skill scope. Ask only for missing scope, never repeat answered questions.
Use the supplied repository paths for `--repo`, not the caller's working directory.
Return artifacts to that parent run without applying proposed edits.
Do not invoke skill-bootstrap from a bootstrap child run.

First check whether the current directory is inside a git repository:

```bash
git rev-parse --show-toplevel
```

Use the harness's user-question tool when available.

When a current repository is available, ask **“Which conversations should I grade?”** with:

1. **Conversations in this repository** - recommended. Covers the main checkout and its registered Git worktrees.
2. **All conversations**.
3. **Choose projects to analyze**.

When there is no current repository, ask the same question with:

1. **All conversations** - recommended.
2. **Choose projects to analyze**.

If the user chooses projects, ask for one or more project paths. Expand and validate every path as a git repository before continuing. The run produces one combined report across those projects.

#### Ask which skills to evaluate

Then ask **“Which skills should I evaluate?”** with:

1. **Project skills + global skills** - recommended.
2. **Project skills only**.

For an all-conversations run, “Project skills” means skills from local git repositories inferred from the conversations' working directories. After these answers, proceed immediately.

Never write artifacts into the user's repo. Create one fresh, collision-free scratch directory per run and use it as `REPORT_DIR` for every artifact:

```bash
REPORT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/skill-doctor-XXXXXXXX")"
```

### Step 1: Collect

Build the collector arguments from the startup answers:

- Current repository: `--repo "$REPO"`. The run adds the main checkout and registered worktrees from Git metadata.
- Selected projects: repeat `--repo PATH` for every project.
- Many checkouts of one repository: pass each authorized checkout as `--repo PATH`. The collector expands each Git common directory once and resolves each working directory once per run. Do not write a custom discovery or traversal script.
- All conversations: `--all-conversations`.
- Project and global skills: add `--include-global-skills`.
- Project skills only: do not add `--include-global-skills`.

```bash
python3 "$SKILL_ROOT/scripts/collect_sessions.py" \
  --out "$REPORT_DIR" \
  <conversation-scope arguments> \
  <skill-scope arguments>
```

By default `--harness auto` scans every locally available supported source. Read `$SKILL_ROOT/references/supported-harnesses.md` for source identifiers, storage details, skill locations, and source-specific override flags.

PowerShell example for Copilot history, the current repository, and project skills only:

```powershell
python (Join-Path $SKILL_ROOT 'scripts\collect_sessions.py') `
    --out $REPORT_DIR --harness copilot --repo (git rev-parse --show-toplevel)
```

Replace the scope arguments with the user's choices before execution.

Useful flags:

- `--harness VALUE` - which local session sources to scan; use the reference's collector IDs.
- `--repo PATH` - include a project and its registered worktrees; repeatable.
- `--no-worktrees` - grade only the listed paths.
- `--all-conversations` - do not filter conversations by project.
- `--include-global-skills` - also grade global skills.
- `--days N` - lookback window (default 45).
- `--max-sessions N` - cap on sampled sessions across all harnesses (default 12).
- `--skills-dir PATH` - nonstandard skill locations.
- `--include-subagents` - include child or sidechain sessions.
- `--min-idle-minutes N` - skip sessions active within the last N minutes (default 15; 0 keeps every session).
- `--timeline-supplement N` - add up to N no-skill sessions spaced across the window, tagged as their own stratum. The sample stays non-probability; the inventory says so.
- `--audit-manifest` - also write `audit_manifest.json`: declared inputs and caps, source revision, upstream identity evidence, scope, and the content-aware skill catalog. It exits 1 and writes no manifest when the evidence contradicts the declared scope.

Read `$REPORT_DIR/inventory.json`, including `collection_status` and `collection_issues`.
State `scope_resolution` in the report: included roots with their session counts, rejected roots with reasons, and that clone discovery is unsupported.
A removed worktree joins only when the user confirms its path and you pass it as `--repo PATH`. A directory name or shared prefix never grants access.
Note `stats.sessions_skipped_idle`: sessions whose last record is newer than `--min-idle-minutes` (default 15) are skipped because they may still be running; disclose the count.
Disclose partial collection before interpreting usage or recommending changes.
Same-name definitions with different content stay in usage and coverage.
`skill_variants` in `inventory.json` lists each one with its paths and `sha256`, and names the current edit target.
`stats.ambiguous_skills` counts these names. It is information, not a collection failure.
Historical attribution for these names is `unresolved`: the transcript does not record which bytes ran.
Never present a fingerprint as the version a past conversation executed.
A session's `skill_attribution` marks usage whose definition is unresolved, with `evidence` of `path`, `bare_name`, `qualified_name`, or `unrecorded`.
If `sessions_sampled` is 0, report no scoreable conversations and stop.
If `skills_found` is 0, continue with `skill_coverage` set to 0.
Recommend creation only when a failed conversation demonstrates a capability gap.

#### Sampling disclosure

The collector splits the `--max-sessions` cap across harnesses, so one harness cannot take the whole sample. The deterministic rule, also stored as `sampling.rule` in `inventory.json`:

Harnesses with scoreable sessions are ranked by scoreable count (descending), then by harness name (ascending). The --max-sessions cap is dealt one slot at a time to that ranking, round-robin, and a harness never receives more slots than it has scoreable sessions. When the cap is lower than the number of harnesses, only the first harnesses in the ranking receive a slot. A harness with no scoreable session takes no slot.

Inside each harness, sessions that used an installed skill are taken first, newest first, until each skill has --per-skill sessions. Remaining slots go to sessions that used no skill, newest first, up to --no-skill. This is skill-first selection: it favors sessions that exercise skills, so per-harness grades describe that slice, not the harness as a whole. The --per-skill and --no-skill caps apply within each harness, and a quota the caps cannot fill is left unused.

Read `stats.per_harness` and `sampling` in `inventory.json`. Each harness entry holds `scoreable` (candidates), `skill_candidates`, `quota`, `sampled`, and `sampled_with_skills`. Report candidate and sampled counts for every harness separately.
When `sampling.harness_coverage_complete` is false, state in the report that the cap prevented full harness coverage. Name each entry of `sampling.omitted_harnesses` with its `scoreable` count, and quote `sampling.notice`.
Disclose that selection is skill-first within each harness. Harness balance alone does not make the sample representative.

When the run covered exactly one repository (`conversation_scope` is `projects` and `repos` has one entry), you can pass the inventory to `skill-bootstrap` as an initial candidate seed. Bootstrap rejects all-conversations and multi-project inventories.
In a bootstrap child run, return it to the caller instead of starting another run.
Its discovery miner also accepts offline hosted PR, issue, and work-item observations.
Use deterministic inventory counters, not the qualitative grades from Step 2.
Read skill-bootstrap's friction-input reference for its import contract.
Bootstrap owns verification, authoring, and evaluation; a seed grants none of those outcomes.
Keep this handoff separate from the report's failed-conversation scoring.

### Step 2: Score each sampled transcript

Scoring is based on efficiency, code quality, procedure compliance, and verbosity for the sessions sampled. Process datasets of 50 transcripts or fewer in a single batch. For datasets with more than 50 transcripts, use parallel batches (20 transcripts per batch recommended). Score batches in the current agent process. Delegate only within the user's authorized data boundary. A locally launched agent can still use a remote model provider. Pass the following rubrics as context:

- `$SKILL_ROOT/scorers/efficiency.md`
- `$SKILL_ROOT/scorers/code-quality.md`
- `$SKILL_ROOT/scorers/procedure-compliance.md`
- `$SKILL_ROOT/scorers/verbosity.md`

Instructions: For each session in `inventory.json` with `sampled: true`, read its `transcript_path`. Ignore other files in `$REPORT_DIR/transcripts/`, which can be left over from an earlier run. Read each transcript and judge it against all four rubrics. For each scorer record: label, numeric score (from the rubric's label table), and a 1-3 sentence reason citing specifics from the transcript. Apply the code-quality scorer only where the transcript shows code changes; otherwise record `insufficient_evidence` and exclude that result from the code-quality average and failed-conversation filter.

### Step 3: Aggregate

Write every scored result to `$REPORT_DIR/scores.json` in the shape `$SKILL_ROOT/references/audit-workflow.md` defines, then compute the aggregates with the script instead of by hand:

```bash
python3 "$SKILL_ROOT/scripts/audit_scores.py" "$REPORT_DIR/scores.json" --out "$REPORT_DIR/score_artifact.json"
```

Copy each `dimensions.<name>.score` and `overall` from `score_artifact.json` into `report.json`; use its `failed_conversations` and `per_harness` values. The reference also covers `pre_cutoff` on terminated sessions and batched reviews. The formulas below define what the script computes:

- `raw_efficiency` = mean of efficiency scores across all scored sessions.
- `raw_code_quality` = mean of code-quality scores, excluding `insufficient_evidence`. If no session had enough evidence, set it to 0.5 and say so in the findings.
- `raw_procedure_compliance` = mean of procedure-compliance scores across all scored sessions.
- `raw_verbosity` = mean of verbosity scores across all scored sessions.
- Curve qualitative rubric means into letter-grade report scores with `curve(score) = 0.5 + 0.5 * score`.
- `efficiency = curve(raw_efficiency)`.
- `code_quality = curve(raw_code_quality)`.
- `procedure_compliance = curve(raw_procedure_compliance)`.
- `verbosity = curve(raw_verbosity)`.
- `skill_coverage` = fraction of sampled sessions where at least one installed skill was detected. If `skills_found` is 0, coverage is 0.
- `overall = 0.25 * efficiency + 0.25 * code_quality + 0.2 * procedure_compliance + 0.15 * verbosity + 0.15 * skill_coverage.`

For each harness in `stats.per_harness` that has scored sessions, also compute that harness's `overall` by applying the formulas above to its sessions only. Report these next to the combined `overall`; they are never averaged back into it.

These upstream weights reward skill adoption independently of accepted outcomes.
Skill coverage does not prove that skills improved those outcomes.

Then, define `failed_conversations` from each conversation's raw, uncurved scorer results. A conversation fails when at least one applicable efficiency, code-quality, procedure-compliance, or verbosity score is below `0.5`. An `insufficient_evidence` result does not make a conversation fail. A failure caused only by provider termination does not count: when a session's `stats.terminated_by` is set (for example `usage_limit_exceeded`, `server_overloaded`, or `usage_limit_reached`), the transcript ends at a provider cutoff, so a missing final report or terse ending there is not an agent defect. Leave such a conversation out of `failed_conversations` unless it also fails a score on evidence from before the cutoff, and state how many were left out in the findings. Use only `failed_conversations` as evidence for skill-improvement suggestions and draft skill edits.

Then derive the substance:

- `top_findings`: the 3 most impactful, specific patterns across sessions. These lead the report and the spoken summary. Make each summary concrete and concise, following the STE-100 standard.
- `suggestions`: one candidate per supported finding, ranked by frequency times severity. Each names a skill (existing or proposed-new) or a tooling owner and a specific change: a trigger-description fix so it fires when it should, a missing step or check, a command to encode, a new skill to create. Suggestions must trace back to observed waste or defects in `failed_conversations`, not generic best practices - cite the failed session, scorer, and moment that motivated each one. An installed skill that never triggered in a failed conversation is usually a description problem and worth a suggestion of its own. No static change bar suppresses a candidate; when evidence is too thin to name one, record what is missing.

### Step 4: Draft skill edits

Follow `$SKILL_ROOT/references/skill-improvements.md` to propose improvements to project skills based only on `failed_conversations`.

Every candidate keeps `status: "unevaluated"`. Static diagnosis cannot measure whether a change helps.
Do not start skillopt or skillforge, and do not edit installed skill files. Drafts under `$REPORT_DIR/proposed/` are diagnosis output, not edits. The report supplies the handoff prompts; the user chooses the next action.
Skillopt evaluates only `skill` candidates with an existing target. A `new-skill` candidate routes through skillforge first, and a `tooling` candidate goes to its named code owner; the renderer writes those routing notes in place of a skillopt run.

1. Read the skill's current file: `path` in its `skills` entry of `inventory.json`. Set `target` to that exact path and state its `sha256` in the suggestion's `change` text. When the name is in `skill_variants`, leave `target` empty, list every variant's `path` and `sha256` in `variants`, and draft no diff: the user selects the edit target. Never draft against a global-home copy while a repository copy exists.
2. Write the full improved version to `$REPORT_DIR/proposed/<skill-name>/SKILL.md`, changing only what the evidence justifies. Improve the parts the sessions actually exercised: the trigger description that failed to fire, the missing preflight check, the step the agent had to figure out by trial and error.
3. Produce a unified diff with Python's `difflib.unified_diff`, reading both files as UTF-8. Store it in the suggestion's `diff` field so it renders in the report.

For a proposed-new skill, write the complete new SKILL.md to the same `proposed/` directory and set `diff` to its full content as an addition.

Do not modify the user's real skill files in this step.

### Step 5: Write report.json and render

Write `$REPORT_DIR/report.json`. Store the curved `efficiency`, `code_quality`, `procedure_compliance`, and `verbosity` values, literal `skill_coverage`, and weighted `overall` in `scores`; do not store the raw rubric means there.

```json
{
  "title": "Agent Skill Report",
  "generated_at": "<ISO timestamp>",
  "harness": "<harness from inventory.json>",
  "handle": "<repo_name from inventory.json>",
  "stats": {
    "sessions_analyzed": 0, "sessions_scanned": 0,
    "skills_found": 0, "skills_used": 0, "window_days": 45
  },
  "sampling": {
    "harness_coverage_complete": true,
    "notice": null,
    "per_harness": {
      "<harness>": {"scoreable": 0, "skill_candidates": 0, "sampled": 0, "overall": 0.0}
    }
  },
  "scores": {
    "efficiency": 0.0,
    "code_quality": 0.0,
    "procedure_compliance": 0.0,
    "verbosity": 0.0,
    "skill_coverage": 0.0,
    "overall": 0.0
  },
  "top_findings": ["", "", ""],
  "suggestions": [
    {
      "skill": "",
      "status": "unevaluated",
      "owner": "skill | new-skill | tooling",
      "owner_target": "<tooling owner, only when owner is tooling>",
      "target": "<exact skill path, or empty when variants are unresolved>",
      "variants": [{"path": "", "sha256": ""}],
      "change": "<one-sentence summary of the edit>",
      "evidence": "<observed fact: which session(s), scorer, and what happened>",
      "mechanism": "<hypothesis: the behavioral change and why it may help>",
      "expected_improvement": "<unmeasured expected behavior change>",
      "reproduction": "<smallest useful reproduction>",
      "acceptance_checks": ["<check skillopt can score>"],
      "risks": ["<known risk or counterexample>"],
      "missing_evidence": ["<what the transcripts do not show>"],
      "proposed_path": "<path under proposed/, if an edit was drafted>",
      "diff": "<unified diff, or full content for a new skill>"
    }
  ],
  "evaluation": {"diagnosis": "static", "optimization": "not_run"}
}
```

Copy `harness_coverage_complete`, `notice`, and each harness's `scoreable`, `skill_candidates`, and `sampled` from `inventory.json`.
Optional `audit` sections and the shareable aggregate export are in `$SKILL_ROOT/references/audit-workflow.md`.
Keep `evaluation.optimization` at `not_run` for every skill-doctor run.
Only a later skillopt result may set `evaluation.optimization` to `run` and a suggestion `status` of `accepted`, `rejected`, or `inconclusive`; that suggestion then needs its own `"evaluation": {"baseline": "<ref>", "candidate": "<ref>"}` object with non-empty references.
The renderer exits 1 on a measured status without that evidence, a drafted diff for unresolved variants, or a "no beneficial change" verdict without scored evaluation.
It builds the skillopt and skillforge handoff prompts from each suggestion's own fields. Set `overall` from the per-harness computation in Step 3, or omit it for a harness with no scored session.

```bash
python3 "$SKILL_ROOT/scripts/render_report.py" "$REPORT_DIR/report.json" --open
```

PowerShell equivalent:

```powershell
python (Join-Path $SKILL_ROOT 'scripts\render_report.py') (Join-Path $REPORT_DIR 'report.json') --open
```

For a bootstrap child run, omit `--open` and return the report path.

This writes a single self-contained `$REPORT_DIR/report.html` and attempts to open it in the default browser. The scorecard, findings, and suggested skill edits appear on one page. Long diffs are collapsed behind a "show more" toggle, and a "share as png" button exports a 1200x675 share image locally. There is no separate card file to open or screenshot.

### Step 6: Output

Tell the user the grade and the three findings, in text.
Then state the `evaluation:` line that `render_report.py` printed, verbatim. It matches the report's evaluation status.
Name each candidate with its status. Never describe an empty or static-only suggestion list as evidence that no change would help.

Finish with the absolute path to `REPORT_DIR/report.html`.
Do not apply suggested edits without the user's explicit instruction.
The report carries no vendor branding. The fork's MIT attribution remains in `LICENSE` and the header of this file.

## Verification

- [ ] `inventory.json` reflects the chosen projects, sources, and skill scope.
- [ ] The report states per-harness candidate and sampled counts, and says when the cap prevented full harness coverage.
- [ ] Each proposed edit cites a failed conversation and its scorer evidence.
- [ ] Every candidate is `unevaluated` and carries both handoff prompts; nothing started skillopt or skillforge.
- [ ] The spoken summary repeats the renderer's `evaluation:` line.
- [ ] `report.html` exists and displays scores and proposed edits.
- [ ] Standalone runs open the report; bootstrap child runs return its path.
- [ ] Original skill files remain unchanged.

If no sessions were sampled, report that result instead of fabricating scores.
