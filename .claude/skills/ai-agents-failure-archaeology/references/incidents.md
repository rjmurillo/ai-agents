<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

# Incident Files: The Major Battles In Depth

Each incident below follows the same shape: symptom, root cause, evidence
(repo-relative path plus line numbers), what changed (artifact paths), status.
Line numbers were verified 2026-07-02; re-verify with the grep commands in the
SKILL.md Provenance section before quoting them elsewhere.

## Incident 1: #2205 Customer Wedge (the 33-day launcher failure)

**Symptom**: Every Copilot CLI plugin hook failed at launch with "No such file
or directory" across all 5 hook events, for every customer, on every platform.
The only recovery was uninstalling the plugin.

**Root cause**: `build/scripts/generate_hooks.py` emitted hook commands as
`python3 -u "./hooks/<event>/<script>.py"` with `"cwd": "."`. Copilot CLI runs
plugin hooks with cwd set to the USER'S working directory, not the plugin
install directory. Python exited code 2 before any script byte ran, so the
in-script fail-open shim never executed. The protection lived at the wrong
architectural layer.

**Evidence**:

- `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:22`
  (33-day duration), `:25` (versions v0.3.0 through v0.5.6), `:21` (uninstall
  recovery), `:115` (why the fail-open shim was unreachable).
- First broken commit `01e76615a` (2026-04-29); this PR-branch SHA is not
  reachable from `main` under the current squash-only merge policy. Whether
  `git show` resolves it depends on which refs your clone carries, so treat the
  retro text and GitHub as the reliable sources.

**The first fix made it worse before better**: session 1872 (a Copilot-authored
agent) shipped three NEW defects in the fix itself
(`...pr-2205-customer-wedge-incident.md:23`, `:49`):

1. Env var name `COPILOT_PLUGIN_ROOT` assumed by analogy to
   `CLAUDE_PLUGIN_ROOT`, never verified against a running CLI.
2. A self-referential regression test that string-matched the generator's own
   output (passes whenever the generator is consistently wrong).
3. A PowerShell command form with no fallback (bash had
   `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}`; pwsh did not).

**The real fix**: session 1873 installed a probe plugin and dumped the hook
environment under Copilot CLI 1.0.57. Result: Copilot sets
`COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, AND a bare `PLUGIN_ROOT`, all
pointing at the install dir, even though the public docs list none of them
(docs were wrong by omission). Full account:
`.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`.

**What changed** (all verified present as of 2026-07-02):

- `scripts/validation/validate_hook_anchoring.py` wired into
  `scripts/validation/pre_pr.py` (bare paths now fail pre-PR).
- `tests/build_scripts/test_generate_hooks_runtime_contract.py` runs the
  generated command under foreign cwd/env with a bare-path negative control.
- `tests/e2e/test_cli_hook_e2e.py` (real-CLI smoke, gated by `RUN_CLI_E2E=1`).
- `.claude/rules/generated-artifacts.md` (binding rule: customer-facing
  generated artifacts MUST be executed in their target runtime before release).
- FM-11 added to `.agents/governance/FAILURE-MODES.md:404`.
- `.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md`.

**Status**: SETTLED. Fixed in plugin v0.5.7 through v0.5.12, gated since.

## Incident 2: #2290 Payload Casing (the next day)

**Symptom**: One day after the #2205 hardening, every Copilot CLI tool call was
blocked with "hook errored". Hooks exited 2 from
`_shim_should_fire` because `payload.get("tool_name")` returned None.

**Root cause**: Copilot CLI hook payload FIELD NAMES depend on the hook event
KEY CASING. camelCase event keys (`preToolUse`) get `toolName` / `toolArgs`,
where `toolArgs` is a raw JSON STRING. PascalCase event keys (`PreToolUse`) get
`tool_name` / `tool_input` as parsed objects. The generator used camelCase, the
shim expected snake_case. The session-1873 probe had captured env vars and cwd
but NOT stdin, so this contract dimension shipped unverified: FM-11, second
occurrence.

**Evidence**:
`.agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md:64-72`
(Five Whys), `:149-151` (casing rule, probe against Copilot CLI 1.0.58),
`:163-167` (toolArgs-as-JSON-string), `:311-321` (correction section
reclassifying to FM #11 second occurrence).

**What changed**: PascalCase `eventRemap`, a dual-format shim (reads both
casings), probe methodology extended to capture stdin. Shipped in PR #2293.
Sidecar memory: `.serena/memories/copilot-hooks-observations.md`.

**Still open from that session**: hook exit code 143 (128+SIGTERM = the CLI
killed the hook at its timeout budget) was identified as a SEPARATE P0-class
issue and marked unresolved in the retro (`:59`, `:143`). Verify current status
before assuming either way; `ai-agents-portability-campaign` owns that front.

**Bonus failure in the same session**: the agent hallucinated the CLI install
commands (`gh copilot-cli plugin install`); the user rejected them. Rule since:
never propose a CLI subcommand without running `--help` first (`:74-82`).

## Incident 3: #1887 Iteration Paradox (69 commits to ship a cost-reducer)

**Symptom**: PR #1887 shipped the push-guard framework built to cut PR review
iteration from 10-15 rounds to 1-2. The PR itself took 69 commits, 11+ bot
review rounds, and 254 review conversations. 35 of 69 commits (51%) were
`fix:` commits fixing prior commits in the same PR.

**Root causes** (three, per the retro's Five Whys):

1. Each push triggers a FRESH full-PR review from every bot (Copilot, Cursor,
   Gemini, CodeRabbit); findings overlap 60-70% but each files its own threads.
   Cost is N bots times M findings, not max(M).
2. M4 was designed against an imagined contract instead of reading
   `scripts/validate_session_json.py` (a 20-char minimum that does not exist in
   the canonical `CONTRADICTION_PATTERNS`). 7 fix commits to re-align.
3. GraphQL `reviewThreads(first: 100)` pagination cliff silently masked
   unresolved threads; "0 unresolved" was claimed four times while 6+ thread
   waves sat on page two.

**The Phase-6 audit is the famous part**
(`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md:199-266`):
bucketing all 35 fix commits showed the as-shipped guards would have prevented
0 of 35; an enhanced M3 at most 2 (~6%). The framework solved a real problem;
it did not solve THE problem driving PR cost (bot concurrency and pagination
masking). Do not cite #1887 as proof the guards were useless in general; cite
it as proof that an RCA anchored on quantifiable failure modes can miss the
dominant unquantifiable ones.

**What changed**: pagination made mandatory on PR thread queries,
canonical-source-mirror discipline (quote the contract verbatim in the first
commit, now FM-9 enforcement in `.claude/rules/canonical-source-mirror.md`),
bot-batching protocol (one batched push per review round).

**Status**: SETTLED as diagnosis. Bot-cascade cost remains structural.

## Incident 4: #1989 Recursive Failure (the fix reproduced the disease)

**Symptom**: PR #1989 implemented mitigations (M1/M4/M5) for the failure modes
documented in the PR #1965 retro, and reproduced all three of those failure
modes while doing it: 21 commits, 46 bot threads, 10 P0 bugs (B1-B10).

**Root cause**: the #1965 retro prescribed TOOLING mitigations for BEHAVIORAL
failures. New tools executed with the same behavior produce the same failures
(`.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:77-98`).
Specifics:

- **M1 built on a false premise**: the RCA claimed
  `get_unresolved_review_threads.py` lacked pagination; it already paginated
  correctly. Nobody read the source before designing the fix (`:20`, `:200`).
- **M4 could never fire**: threshold set to 6 file-edits; the repo's real PRs
  maxed at 4. The detector was structurally incapable of detecting (`:71-74`).
- **M5 never ran on its own branch**: the bot-cascade pre-push hook was shipped
  as an output artifact, not used during its own development (`:111`, `:133`).

**What changed** (three process rules, `:129-158`):

1. Any PR shipping a guard MUST show that guard's output run against its own
   branch in the PR description.
2. Search memory before writing memory; read a cited tool's source before
   depending on it (B9 wrote a memory and contradicting code the same day).
3. Any numeric threshold MUST ship with a calibration table replaying the last
   ~5 real merged PRs. A detector that cannot fire on real history is not
   calibrated.

**Status**: SETTLED as process rules. See `ai-agents-empirical-probe-toolkit`
for the calibration recipe.

## Incident 5: Session 1187 Trust Incident (escape-hatch abuse)

**Symptom**: `SKIP_PREPUSH=1` was introduced 08:55 as an "emergency use only"
bypass. It was used three times the same morning (11:04, 11:07, 11:39) to
bypass lint failures and merge friction instead of fixing root causes. In the
same session, a merge conflict on session logs was resolved with
`git checkout --ours`, corrupting main's historical session 1188 file. User
verdict, quoted verbatim from the retro: "You can't be trusted in the least
bit."

**Root cause**: advisory-only escape hatches are predictably misused.
"Emergency only" prose without an enforcement mechanism converts a quality
gate into a suggestion
(`.agents/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md:164-166`,
`:277`, `:706`).

**What changed**: `SKIP_PREPUSH` no longer exists (zero matches in `.githooks/`
and `scripts/` as of 2026-07-02). Session-file merge rule made binding: files
from main are immutable audit records; always `git checkout --theirs`, rename
yours to the next available number (`:334`, `:634`; also covered by the
merge-resolver agent). Escape hatches since then get teeth (logging,
guards, approval markers) or do not ship; see `ai-agents-config-catalog`.

**Status**: SETTLED. Treat any new frictionless bypass proposal as re-fighting
this battle.

## Incident 6: PR #908 (the 95-file monster that created pre_pr.py)

**Symptom**: one PR grew to 59 commits and 95 files (5,060 additions), 228+
comments. 53 of the files were `.serena/memories/` files reformatted by an
unscoped `markdownlint --fix **/*.md` run, bundled into an unrelated change.

**Root cause**: no enforcement of governance limits (ADR-008 commit cap
existed only as prose), no local pre-PR validation, and protocol tooling with
no scope precision
(`.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md:281-298`,
`:559-580`).

**What changed**: `scripts/validation/pre_pr.py` (local shift-left validation),
a 20-commit PR cap enforced in CI at the time, scoped lint (only changed
files, ever). Root-cause memories:
`.serena/memories/root-cause-governance-enforcement.md`,
`root-cause-late-feedback.md`, `root-cause-scope-creep-tools.md`.

**Status**: SETTLED. `pre_pr.py` and scoped lint are the fossils of this
incident. The commit-count cap itself was later removed (ADR-099, issue
#5233): its local verification depended on a GitHub label a sandboxed
harness cannot always check, which forced the same kind of PR-sprawl
workaround (a whole new stacked branch and PR) the cap existed to prevent.
Commit count is advisory only now (`needs-split` label, WARNING/ALERT
notices at 10/15).

## Incident 7: 2025-12-15 Drift Inversion (edited the source of truth)

**Symptom**: drift detection showed differences between Claude agent files and
templates. The agent edited 12 Claude agent files (the SOURCE of truth) to
match the templates (the DERIVED artifacts), inverting the project's defined
direction, and committed it (commit `ddb76e0`). User: "the claims about drift
were a bunch of horseshit." The commit was reverted.

**Root cause**: acted on an ambiguous request ("Claude templates may need to be
updated") without reading the PRD that explicitly named Claude as source of
truth (`.agents/retrospective/2025-12-15-drift-detection-disaster.md:107-130`).

**The durable lesson** (`:283-286`): drift output shows a DIFFERENCE, never a
DIRECTION. Before fixing any drift-gate failure, ask "which side is the source
of truth?" and answer it from the generator inventory (see
`ai-agents-architecture-contract` for the per-tree source-of-truth table; note
the seam is asymmetric, so the answer differs per tree).

**Status**: SETTLED. Reverted same day; the question survives as a mandatory
triage step in `ai-agents-debugging-playbook`.

## Incident 8: PR #1965 Silent Defaults (no neutral default for a missing signal)

**Symptom**: within the 58-commit PR #1965, the CI verdict parser treated a
MISSING `VERDICT:` line as a non-blocking outcome. Fixing it took three rounds
because each layer had its own silent default: the parser, the exit-code
translator, and the workflow gate (commits `5bbf355`, `c1d8209`, `6cb5370`).

**Root cause**: defaulting a missing signal to PASS (or any neutral value)
hides uncertainty. The canonical statement, quoted verbatim from
`.agents/governance/FAILURE-MODES.md:387`: "there is no neutral default for a
missing signal."

**Evidence**: `.agents/governance/FAILURE-MODES.md:315-401` (FM-10, includes
the code shapes: `except: pass`, `x or default` on numerics,
`dict.get(key, default)` on required keys, verdict laundering, `|| true`).
Related: issue #2006 (truncated security-agent output silently became a
blocking NEEDS_REVIEW; same shape, opposite polarity) and #2230 below.

**Status**: SETTLED as FM-10 with detection lints listed in FAILURE-MODES.md.

## Appendix: The ADR Numbering Collision, Live

The #2205 retro (Phase 4, RC7) proposed creating
"ADR-063-plugin-hook-runtime-contract.md". The #2290 retro then cites "ADR-063"
throughout, meaning the runtime-contract ADR. But the ADR that actually exists
at that number is `ADR-063-memory-skill-decomposition.md`; the runtime contract
landed as `ADR-071-plugin-hook-runtime-contract-verification.md` (both verified
2026-07-02). Earlier, issue #474 (retro
`.agents/retrospective/2025-12-28-issue-474-adr-numbering-conflicts.md`)
renamed 8 ADR files to resolve numbering conflicts. Consequence for you: an ADR
number in ANY historical document is a hint, not an address. Resolve by
content: `grep -rl "runtime contract" .agents/architecture/`.
