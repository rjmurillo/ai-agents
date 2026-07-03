---
name: ai-agents-portability-campaign
description: Executable decision-gated campaign for the cross-harness portability problem, keeping generated Copilot CLI plugin hooks honoring the empirically settled runtime contract (cwd, plugin-root anchor, payload casing, kill budget). Use when you say `run the portability campaign`, `port hooks to a new harness`, `copilot hook timeout regression`. Do NOT use for harness fact lookups (use `agent-harness-reference`) or generic probe recipes (use `ai-agents-empirical-probe-toolkit`).
version: 1.0.0
license: MIT
---

# ai-agents Portability Campaign

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
This is a battle plan, not an essay. The problem: this repo ships ONE plugin to two
harnesses (a harness is the CLI runtime that loads the plugin: Claude Code or GitHub
Copilot CLI). Copilot CLI's runtime contract (the observable behavior a hook actually
gets: working directory, environment variables, stdin payload shape, time budget)
diverges from Claude Code's, and the vendor docs have been wrong by omission twice
(plugin-root env vars, issue #2205; payload field casing, issue #2290). Every phase
below gives exact commands, the EXPECTED observation, and an explicit branch if you
see something else. Never proceed on memory of the digest; verify at each gate.

Harness facts live in `agent-harness-reference`. Probe method depth lives in
`ai-agents-empirical-probe-toolkit`. Incident history lives in
`ai-agents-failure-archaeology`. This skill is the campaign that uses all three.

## Triggers

- `run the portability campaign`
- `port hooks to a new harness`
- `copilot hook timeout regression`
- `verify the copilot runtime contract`
- `new copilot cli release, recheck the contract`

## Campaign Success Definition (measurable)

The campaign is won when ALL rows below hold, proven by command output, never by eye.

| # | Criterion | Measurement command | Baseline (as of 2026-07-03) |
|---|-----------|--------------------|------------------------------|
| 1 | Runtime-contract suites green | `uv run pytest tests/build_scripts/test_generate_hooks_runtime_contract.py tests/build_scripts/test_generate_hooks_plugin_root.py tests/build_scripts/test_generate_dispatcher.py tests/build_scripts/test_copilot_dispatcher_artifact.py -q` | 38 passed (6 + 32), observed 2026-07-03 |
| 2 | Anchoring gate clean | `python3 scripts/validation/validate_hook_anchoring.py` | exit 0 |
| 3 | Hook kill rate zero on pinned CLI | count `exit 143` / `hook errored` events in a monitored session sample | pre-dispatcher: 3 of 197 preToolUse calls killed (issue #2295, ADR-068); post-dispatcher rate UNMEASURED in repo |
| 4 | Every contract dimension 3-layer covered | Phase 1 coverage table: probe memory + generator enforcement + runtime test per row | 4 of 5 dimensions fully covered; timeout dimension has no in-repo runtime measurement |
| 5 | New CLI release absorbed without hand edits | Phase 2 probe re-run, then `python3 build/scripts/build_all.py --check` | contract pinned at Copilot CLI 1.0.57 |

## Process

### Phase 0: Ground Yourself in the Settled Contract

Read the settled artifacts. Do not re-litigate them (see Fenced Wrong Paths).

```bash
cat .serena/memories/decision-copilot-cli-hook-plugin-root-contract.md
cat .claude/rules/generated-artifacts.md
ls .agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md \
   .agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md
```

EXPECTED: the memory opens with `# Decision: Copilot CLI plugin-hook path anchoring
(issue #2205)` and pins the probe to Copilot CLI 1.0.57. The rule opens with a
frontmatter `paths:` block and the P0 wedge story (33 days broken, v0.3.0 to v0.5.6,
recovery was uninstall). Both retro files exist.

Branch: if any file is missing, STOP. The chronicle moved; recover it via
`ai-agents-failure-archaeology` before touching anything. Full local history is
present (~1471 commits as of 2026-07-03), but retro-cited short SHAs may not
resolve, so route archaeology through retros and memories, not `git log`.

The settled contract (each row was verified by experiment, not docs):

| Dimension | Settled fact | Evidence |
|-----------|--------------|----------|
| cwd | Copilot CLI runs a plugin hook with cwd = the USER's working dir, not the plugin install dir | memory above; retro 2026-06-02-pr-2205 |
| Env anchor | `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, and bare `PLUGIN_ROOT` are all exported, pointing at the install dir; vendor docs omit all three | probe env dump in the memory, CLI 1.0.57 |
| Payload casing | Event-key casing controls field names: camelCase keys send `toolName`/`toolArgs` (args as a JSON string); PascalCase keys send `tool_name`/`tool_input` | retro 2026-06-02-issue-2290, line 16 and Learning 1 (~lines 148-151) |
| Matchers | Copilot CLI ignores per-hook `matcher`; every registered entry runs on every call | ADR-068 Context, item 1 |
| Kill budget | Host kills a hook at 2-3 s with SIGTERM (exit 143 = 128 + SIGTERM); `timeoutSec` in hooks.json does NOT raise the budget | ADR-068 lines 32 and 132 |

The generator encodes these: `templates/platforms/copilot-cli.yaml` sets
`dispatcher: true` (line 51) and a PascalCase-only `eventRemap` (line 52), and
`build/scripts/generate_hooks_emit.py::_build_copilot_entry` (re-exported by
`generate_hooks.py`) emits the anchored
`${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}` command form.

### Phase 1: Baseline the Contract Test Suites

```bash
uv run pytest tests/build_scripts/test_generate_hooks_runtime_contract.py -q
```

EXPECTED: `6 passed` (observed `6 passed in 2.12s` on 2026-07-03). This suite RUNS the
generated commands from a foreign cwd with the contract env, plus a negative control
(a deliberately broken input proving the test can fail): a bare `./hooks/...` path
must fail the same way it failed in production.

```bash
uv run pytest tests/build_scripts/test_copilot_dispatcher_artifact.py \
  tests/build_scripts/test_generate_dispatcher.py \
  tests/build_scripts/test_generate_hooks_plugin_root.py -q
```

EXPECTED: `32 passed` (observed 2026-07-03).

Branch: if ANY test fails, a settled contract regressed. Stop the campaign. First
reproduce on main (a red that also exists on main is not your branch's fault; PR #1361
lesson). Then triage via `ai-agents-debugging-playbook` and route the fix through
Phase 4 as a P0. Do not continue to Phase 2 or 3 on a red baseline.

Coverage of the five settled dimensions (as of 2026-07-03):

| Dimension | Probe memory | Generator enforcement | Runtime test | Verdict |
|-----------|--------------|----------------------|--------------|---------|
| cwd anchoring | yes | `_build_copilot_entry` | `test_generate_hooks_runtime_contract.py` (foreign cwd + negative control) | covered |
| Env anchor fallback | yes | same | `test_bash_falls_back_to_claude_plugin_root` | covered |
| Static anchoring, both hooks.json trees | yes | generator + `scripts/validation/validate_hook_anchoring.py` | gate reads expected shape FROM the generator, so it cannot drift | covered |
| Payload casing | `.serena/memories/copilot-hooks-observations.md` | PascalCase `eventRemap` pinned in `templates/platforms/copilot-cli.yaml` | generator remap tests in `tests/build_scripts/test_generate_hooks.py` and `test_generate_hooks_plugin_root.py`; no live-CLI payload replay | mostly covered |
| Timeout budget | ADR-068 measurements (~246 ms per shim cold start on Windows, ~8.7 s aggregate pre-dispatcher) | dispatcher consolidation (`build/scripts/generate_dispatcher.py`) | NONE in-repo against a live pinned CLI | OPEN, see Phase 3 |

### Phase 2: Probe Protocol for Any New Contract Dimension

Use this whenever you must learn a NEW fact about a harness (new event type, new CLI
release, new field, a third harness). Never trust vendor docs alone; they were wrong
by omission twice here. Full recipe depth: `ai-agents-empirical-probe-toolkit`.

1. Pin the version: `copilot --version` (or the target harness equivalent). Record it.
   A contract fact without a version is not a fact.
2. State the hypothesis and the EXPECTED observation BEFORE running anything.
3. Build a minimal probe hook that dumps what you need (env, cwd, raw stdin) to a
   temp file. Install it as a real plugin; do not simulate the host.
4. Run from a foreign cwd (any directory that is not the plugin install dir), because
   that is the production condition that broke #2205.
5. Run a negative control: an input or path that MUST fail. A probe that cannot fail
   proves nothing (self-referential test ban, see Fenced Wrong Paths).
6. Record the result in a Serena decision memory named
   `decision-copilot-cli-<dimension>.md` with: question, docs-say answer, measured
   answer, CLI version, date, probe transcript. Model:
   `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`.
7. Encode the fact: generator change + runtime-contract test with negative control.
   Then go to Phase 4.

Branch: if the probe contradicts an existing settled row in Phase 0, do NOT silently
update the table. That is a contract CHANGE by the vendor: re-probe on the previous
pinned version to confirm the delta, then file an issue with both transcripts and take
the fix through Phase 4.

### Phase 3: The Open Front, Exit-143 Timeout Budget

Status timeline, verified in-repo (as of 2026-07-03). Re-verify before acting; the
front may have moved:

1. Retro 2026-06-02-issue-2290 flagged exit 143 (SIGTERM timeout) as a P0 follow-up,
   distinct from the payload crash (exit 2). Lines 16, 27, 309.
2. Issue #2295 (quoted in ADR-068 Context): 3 of 197 preToolUse invocations in one
   session killed at the 2-3 s budget; fail-closed policy (block when the guard
   errors, per ADR-066/ADR-071) turned a latency defect into false denials.
3. ADR-068 decided ONE dispatcher entry per (plugin, event) instead of one per shim.
   IMPLEMENTED: `build/scripts/generate_dispatcher.py` exists, wired via
   `dispatcher: true` in `templates/platforms/copilot-cli.yaml`;
   `src/copilot-cli/hooks/hooks.json` carries a single `_dispatch.py` entry per event.
   The module docstring cites #2342 and claims about 75 percent spawn reduction
   (docstring claim, not independently re-measured).
4. ADR-068's Status header still reads `Proposed` (line 5) even though the
   implementation shipped. Known weak point: ADR status headers lag reality here;
   weigh what the file body and the generated artifacts show on disk over the
   status header, and verify by content, not by ADR number or status.
5. NOT found in repo: any post-dispatcher kill-rate measurement under a live pinned
   Copilot CLI, and the GitHub open/closed state of #2295 (issue state is not in
   the local tree; check the issue tracker when online).

First, verify current state before assuming anything:

```bash
python3 -c "import json; h=json.load(open('src/copilot-cli/hooks/hooks.json'))['hooks']; print({k: len(v) for k, v in h.items()})"
```

EXPECTED: exactly 5 events (PreToolUse, PostToolUse, SessionStart, SessionEnd,
UserPromptSubmit), each with value `1` (one consolidated dispatcher entry per
event). Do NOT use `grep -c "_dispatch.py"` as the check: it returns 10 on a
healthy tree because each entry names `_dispatch.py` twice (`bash` and
`powershell` command fields). Branch: if any event's count is greater than 1, or
you see per-shim entries, the consolidation regressed; treat as P0, go to Phase 4
now.

```bash
uv run pytest tests/e2e/test_plugin_load_smoke.py --collect-only -q | tail -1
```

EXPECTED: `9 tests collected` (observed 2026-07-03). Branch: collection error means
the e2e harness itself is broken; fix that first, you cannot close this front blind.

Solution menu, RANKED. Options differ in kind, not coverage; each carries obligations
you accept by choosing it:

| Rank | Option | What it buys | Obligations |
|------|--------|--------------|-------------|
| a | Finish ADR-068: measure the consolidated dispatcher cold start under the 2-3 s budget on the slowest supported platform (Windows `py -3`, the ~246 ms/shim environment) | Closes the open front with numbers; lets ADR-068 leave Proposed | Timing transcript in a decision memory (version + date); kill-rate sample comparable to the 3/197 baseline; ADR status change goes through the `adr-review` debate gate |
| b | Work-shedding inside hooks: defer or skip non-gate work when near budget | Headroom on slow machines | EVENT= stderr telemetry proving what was shed; a negative control proving gate guards still BLOCK when they must (fail-closed preserved, no silent defaults, FM-10); calibrate any threshold against the last ~5 real PRs |
| c | Contract-test pinning per CLI release: re-run the Phase 2 probe on every Copilot CLI release, keep a version table | Early warning when the vendor moves the budget or the contract | A repeatable probe script; a pinned-version table in the decision memory; a campaign trigger (`new copilot cli release, recheck the contract`) actually exercised |

Recommended order: a, then c as standing practice; b only if a's measurement shows the
consolidated dispatcher still grazes the budget.

### Phase 4: Promotion Protocol

Any contract change (generator, hooks, dispatcher, hooks.json shape) promotes ONLY
through this ladder. Classification and review rules: `ai-agents-change-control`.
Evidence standards: `ai-agents-validation-and-qa`. Pipeline mechanics:
`ai-agents-generation-and-release`.

```bash
uv run pytest tests/build_scripts/ -q                      # contract + generator suites
python3 scripts/validation/validate_hook_anchoring.py      # anchoring gate, expect exit 0
python3 build/scripts/build_all.py --check                 # drift gate, exit 2 = stale mirror
uv run pytest tests/e2e/test_plugin_load_smoke.py -q       # e2e smoke
python3 scripts/validation/pre_pr.py                       # full local shift-left
```

Plus, non-negotiable:

1. Regenerate, never hand-edit, `src/copilot-cli/**`. Edit the canonical source
   (`.claude/hooks/**`, `templates/**`, `build/scripts/**`), run
   `python3 build/scripts/build_all.py`, commit source and generated output together.
2. Bump the touched tree's plugin manifest to a strictly greater semver:
   `src/copilot-cli/.claude-plugin/plugin.json`, and `.claude/.claude-plugin/plugin.json`
   (0.5.254 as of 2026-07-03) if `.claude/` content changed. A stale version ships a
   stale cache to customers (PR #1942).
3. New contract facts need a NEW runtime-contract test with a negative control, in
   `tests/build_scripts/`, before merge (FM-11: never ship an unrun generated artifact).
4. Success is defined as the suites green on BOTH harness artifacts (Claude plugin
   hooks.json AND Copilot generated tree), never by eyeballing generated output.

Branch: if `build_all.py --check` reports drift, determine DIRECTION before touching
anything: which side is canonical? The 2025-12-15 incident edited the SOURCE to match
the GENERATED tree and had to be reverted. Drift output shows difference, not
direction.

## Fenced Wrong Paths

Settled negative results. Re-proposing one without new evidence re-fights a lost
battle; see `ai-agents-failure-archaeology` for full depth.

| Wrong path | Why it is fenced | Evidence |
|------------|------------------|----------|
| Launcher-level fail-open wrapper (exit 0 shim around a failing hook) | Rejected as a silent-failure anti-pattern; prevention at generation time + fail closed and loud won | issue #2230, closed addressed-by-prevention; retro 2026-06-02-pr-2205 lines 393 and 411 |
| Self-referential tests (string-match generator output against itself) | The first #2205 fix shipped exactly this; it cannot catch a wrong env var name | `tests/build_scripts/test_generate_hooks_runtime_contract.py` module docstring |
| Hand-editing `src/copilot-cli/**` | Generated tree; drift gate goes red and the next regeneration erases you; direction confusion caused the 2025-12-15 revert | `.claude/rules/generated-artifacts.md` |
| Assuming env vars by analogy with Claude Code | The first #2205 fix assumed an env var instead of probing; probe cost is 15 minutes, assumption cost was a P0 | `.serena/memories/copilot-hooks-observations.md` |
| Raising `timeoutSec` in hooks.json to beat the kill budget | Host-controlled budget; kill-budget semantics live in `agent-harness-reference` anti-patterns | ADR-068 line 132 |
| camelCase event keys in `eventRemap` | Flips payload fields to `toolName`/`toolArgs` with args as a JSON string, breaking every shim | retro 2026-06-02-issue-2290 |

## Anti-Patterns

- Starting at Phase 3 because "the tests were green last week". Baselines expire;
  re-run Phase 1, it costs under 10 seconds.
- Declaring the timeout front closed because the dispatcher merged. The dispatcher is
  a mechanism; the success criterion is a measured kill rate of zero on a pinned CLI.
- Trusting an ADR Status header ("Proposed") or an ADR number over file content and
  shipped artifacts. Numbers collide historically; content wins.
- Citing vendor docs as evidence for runtime behavior. Docs are a hypothesis source;
  only a probe transcript with a version pin is evidence.
- Judging generated hooks.json "looks right" by eye instead of running the
  runtime-contract suite from a foreign cwd.
- Fixing a red contract test on your branch without first reproducing on main.

## Verification

Campaign-step self-check before you claim any phase complete:

- [ ] Phase 0 artifacts read in this session, not recalled from digest or memory.
- [ ] Phase 1 suites run in this session; pass counts recorded (expect 6 and 32 as of 2026-07-03; investigate any delta, including new tests).
- [ ] Any new contract fact has a version-pinned probe transcript AND a negative control.
- [ ] Any contract change ran the full Phase 4 command block locally, all exit 0.
- [ ] Plugin manifest semver bumped strictly greater for every touched tree.
- [ ] No hand edits under `src/copilot-cli/**`; `build_all.py --check` exits 0.
- [ ] Claims of "resolved" for the exit-143 front are backed by a measured kill-rate sample, not by the existence of the dispatcher.

## Provenance and Maintenance

Authored 2026-07-03. Every volatile fact was verified against the working tree on
that date. Re-verify before relying on any row below.

| Fact | Source | Re-verify |
|------|--------|-----------|
| Settled anchor contract, CLI 1.0.57 pin | `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` | `head -25 .serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` |
| Wedge incident, 33 days, uninstall-only recovery | `.claude/rules/generated-artifacts.md`; `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` | `sed -n '15,25p' .claude/rules/generated-artifacts.md` |
| Payload casing + exit 143 P0 flag | `.agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md:16,27,227,309` | `grep -n "143" .agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md` |
| 3/197 kills, 2-3 s budget, ~246 ms cold start, timeoutSec rejected | `.agents/architecture/ADR-068-consolidated-hook-dispatcher.md:15-34,132` | `sed -n '10,35p' .agents/architecture/ADR-068-consolidated-hook-dispatcher.md` |
| ADR-068 Status still Proposed | same file, line 5 | `sed -n '3,5p' .agents/architecture/ADR-068-consolidated-hook-dispatcher.md` |
| Dispatcher implemented, #2342, one entry per event | `build/scripts/generate_dispatcher.py:1-10`; `src/copilot-cli/hooks/hooks.json` | Phase 3 json one-liner (expect 5 events, each count 1; a raw `grep -c "_dispatch.py"` prints 10, two command fields per entry) |
| dispatcher flag + PascalCase eventRemap | `templates/platforms/copilot-cli.yaml:51-57` | `sed -n '48,58p' templates/platforms/copilot-cli.yaml` |
| Contract suite pass counts (6, 32) | pytest runs on 2026-07-03 | Phase 1 commands |
| e2e smoke collects 9 tests | pytest collect on 2026-07-03 | Phase 3 second command |
| Plugin version 0.5.254 (.claude tree) | `.claude/.claude-plugin/plugin.json` | `grep version .claude/.claude-plugin/plugin.json` |
| #2230 closed addressed-by-prevention | `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:297,393,411` | `grep -n "2230" .agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` |

Maintenance triggers: a new Copilot CLI release (run Phase 2 probe, option c), any
edit under `build/scripts/generate_hooks*.py` or `generate_dispatcher.py` (re-run
Phase 1), ADR-068 leaving Proposed (update Phase 3 timeline), or a measured
post-dispatcher kill-rate sample landing in a decision memory (update row 3 of the
success table and, if zero, declare the front closed there).
