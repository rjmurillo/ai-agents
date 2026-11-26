# ADR-127 Claims Ledger

Factual claims in ADR-127, checked on 2026-11-25.
Rows 8 and 13 back sentences that review rounds removed from the ADR. They stay as a record.
Repository rows were read from the working tree at `792f6febd3` (2026-11-25).
gstack rows were read from a clone of `github.com/garrytan/gstack` at `ec5d7e6fbd` (2026-11-25).

| # | Claim | Kind | Command | Result |
|---|-------|------|---------|--------|
| 1 | gstack measured 121 to 308 calls where the driver plans 9 to 12 | quote | `sed -n 2,3p lib/ship-phase.ts` in the gstack clone | VERIFIED: "measured conductors made 121-308 calls where the driver plans 9 to 12" |
| 2 | `ship.SKILL.md.tmpl` is 241 lines and `push-pr.SKILL.md.tmpl` is 213 lines | count | `wc -l` on both templates | VERIFIED: 241 and 213 |
| 3 | `ship.SKILL.md.tmpl:53` holds host detection as a shell line | path | `sed -n 53p` | VERIFIED: `remote_url="$(git remote get-url origin 2>/dev/null \|\| true)"` |
| 4 | `ship.SKILL.md.tmpl:161` tells the model to create an Azure DevOps PR by hand | path | `sed -n 161p` | VERIFIED: "create the PR with `az repos pr create --output json`" |
| 5 | 121 skill templates exist | count | `ls templates/skills/*.SKILL.md.tmpl \| wc -l` | VERIFIED: 121 |
| 6 | 60 of 104 skill directories have `scripts/` | count | `ls -d src/claude/skills/*/scripts \| wc -l`; `ls -d src/claude/skills/*/ \| wc -l` | VERIFIED: 60 and 104 |
| 7 | 28 files match `tests/evals/*-scenarios.json` | count | `ls tests/evals/*-scenarios.json \| wc -l` | VERIFIED: 28 |
| 8 | 58 files exist under `tests/evals/skill-scenarios/` | count | `ls tests/evals/skill-scenarios/*.json \| wc -l` | VERIFIED: 58 |
| 9 | The audit extracts 55 rules | count | `grep -c -E '^\| [A-H][0-9]+ \|'` on the audit file | VERIFIED: 55 |
| 10 | 116 of 121 templates have no `tests/evals/<name>-scenarios.json` | count | loop over templates testing for the file | VERIFIED: 5 with, 116 without. The 5 are adr-generator, memory, ship, spec, world-model-diagnostic |
| 11 | `acceptance_gate` passes when the after score is not below the before score and no stable scenario flips pass to fail | behavior | read `scripts/eval/eval-prompt-change.py:711-760` | VERIFIED: docstring criteria 1 and 2; base-unstable scenarios are excluded from regressions |
| 12 | The runner prints `ACCEPTANCE GATE: <verdict>` | path | `sed -n 1167p scripts/eval/eval-prompt-change.py` | VERIFIED |
| 13 | The gate fails as inconclusive when under half the scenarios keep a stable base | quote | `acceptance_gate` docstring; ADR-057 amendment 2026-09-30 | VERIFIED |
| 14 | `--dry-run` reports 48 calls for the 8 `ship` scenarios | behavior | `uv run python scripts/eval/eval-prompt-change.py --prompt src/claude/skills/ship/SKILL.md --scenarios tests/evals/ship-scenarios.json --base-ref origin/main --dry-run` | VERIFIED: `"scenarios": 8`, `"est_api_calls": 48` |
| 15 | The runner's output records no prompt hash today; it records the model (`"model": args.model`, line 1094) | absence | `grep -n -E 'sha256\|hashlib' scripts/eval/eval-prompt-change.py` | VERIFIED: no match in that file. Scope: that one file |
| 16 | ADR-035 assigns 1 logic, 2 config, 3 external, 4 auth | quote | `sed -n 54,58p` on ADR-035 | VERIFIED |
| 17 | gstack reserves exit 3 for STOP | quote | `sed -n 161p lib/headless-artifacts.ts`; `sed -n 16p bin/gstack-ship-phase` | VERIFIED: `refused: 3`; "3 stop". Other gstack programs differ (audit B5) |
| 18 | ADR-057's 2026-07-22 amendment reserves a deterministic evidence check in `pre_pr.py` plus a CI leg | quote | `sed -n 271,290p` on ADR-057 | VERIFIED: "it belongs in `scripts/validation/pre_pr.py` plus a CI leg" |
| 19 | ADR-114 says agent workflows never block merges | quote | `sed -n 13p` on ADR-114 | VERIFIED: title "Never Block Merges (Except the Plugin CLI Smoke)" |
| 20 | ADR-058 keeps an LLM judge advisory | quote | `sed -n 53p` on ADR-058 | VERIFIED: "optional advisory LLM-as-judge sidecar" |
| 21 | ADR-064 is dated 2026-06-01 and ADR-108 is dated 2026-09-11 | quote | `grep -n "date:"` on both | VERIFIED |
| 22 | ADR-121 gives every plugin tree one resolver, `lib/ptk_run.py` | path | `ls src/claude/lib/ptk_run.py .claude/lib/ptk_run.py`; ADR-121 decision 2 | VERIFIED: both files exist. ADR-121 is `status: proposed` |
| 23 | `universal.md` bans generated headers | quote | `sed -n 48p src/claude/rules/universal.md` | VERIFIED: MUST NOT 5 |
| 24 | gstack generated files carry a "do not edit" header | quote | `sed -n 632p scripts/gen-skill-docs.ts` in the gstack clone | VERIFIED |
| 25 | ADR-049 and ADR-064 name `push-pr` | path | `grep -c push-pr` on both | VERIFIED: 1 match in ADR-049 (line 97, Implementation Notes) and 3 in ADR-064 |
| 26 | `evals/skill-rewrites/` does not exist yet | absence | `ls -d evals/skill-rewrites` | VERIFIED: no such directory |
| 27 | gstack tests its driver's STOP anchors and byte budget | path | `sed -n 271,289p test/ship-driver.test.ts` in the gstack clone | VERIFIED |
| 28 | The runner reads the prompt file plus every `references/*.md` beside it, on both sides | behavior | read `load_prompt_surface_from_ref` and `load_prompt_surface_from_file` in `scripts/eval/eval-prompt-change.py`; dry-run on both paths | VERIFIED: rendered path reports `before_chars: 33271`; template path reports 19402 |
| 29 | A template path feeds raw partial tags and skips `references/` | behavior | `grep -c '{{>' templates/skills/ship.SKILL.md.tmpl`; `ls templates/skills/references` | VERIFIED: 5 partial tags; no such directory |
| 30 | The grade is a label match and the default is 3 runs per scenario | behavior | read `judge_scenario`; dry-run output `"runs": 3` | VERIFIED |
| 31 | ADR-114 decision 8 keeps a listed agent workflow's failed check non-blocking | quote | `sed -n 53p` on ADR-114 | VERIFIED: "Failed is non-blocking by design" |
| 32 | ADR-067, ADR-068, ADR-071, and ADR-085 mention `push-pr` | count | `grep -c push-pr` on each | VERIFIED: 5, 1, 2, 1 |
| 33 | `ship.SKILL.md.tmpl:6` grants `Bash(*)` | path | `sed -n 6p` | VERIFIED: `allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)` |
| 34 | The gstack figure is planned against actual with a driver present | quote | `sed -n 3p lib/ship-clock.ts` in the gstack clone | VERIFIED: "Measured conductors made 121-308 calls against the driver's 9 to 12, and 10 of 12 ran past its 100-minute stop". Row 1 verified the bytes; round 1 corrected the reading |
| 35 | 55 of 104 rendered `SKILL.md` files exceed 12 KiB | count | loop with `wc -c` against 12288 | VERIFIED: 55 of 104 |
| 36 | `scripts/validation/skill_size.py:72` sets a 12 KiB warning | path | `sed -n 72p` | VERIFIED: `SKILL_BYTE_WARNING: int = 12_288` |
| 37 | gstack caps a phase at 60 lines and a parts room at 32,000 bytes | path | `sed -n 24p lib/ship-phase.ts`; `sed -n 17p lib/ship-parts.ts` | VERIFIED: `MAX_LINES = 60`; `ROOM_DEFAULT = 32000` |
| 38 | ADR-111 rule 2 names at least 8 shared fixtures | quote | `sed -n 101,105p` on ADR-111 | VERIFIED: "at least 8 shared fixtures" |
| 39 | A scenario that fails on base cannot regress in the runner | behavior | read `is_base_unstable` docstring, `scripts/eval/eval-prompt-change.py:518-540` | VERIFIED: "it cannot regress" |
| 40 | All 8 `ship` scenarios test host detection, mode detection, or the marker check | count | print `id` and `expected_verdict` of each | VERIFIED: 4 host, 1 no-origin error, 2 mode, 1 marker |
| 41 | 17 templates have no `src/claude/skills/<name>/SKILL.md`; each has `.claude/skills/<name>/` | count | loop over templates | VERIFIED: 14 `ai-agents-*` and 3 `repository-*` |
| 42 | ADR-121 records Copilot CLI 1.0.109 UNAVAILABLE and Codex 0.167.0 NOT RUN | quote | `sed -n 56,57p` on ADR-121 | VERIFIED |
| 43 | ADR-110, ADR-112, ADR-114, ADR-121 are `status: proposed`; ADR-123 is accepted | quote | `sed -n 3p` on each | VERIFIED |
| 44 | ADR-057 says "Do not add a new blocking gate" | quote | `grep -n "Do not add a new blocking gate"` on ADR-057 | VERIFIED |
| 45 | The dry-run reports up to 24 resample calls for `ship` | behavior | dry-run output `"max_resample_api_calls": 24` | VERIFIED |
| 46 | gstack has a driver file in 2 of 48 sectioned skills | count | `ls -d */sections \| wc -l`; `ls */DRIVER.md` in the gstack clone | VERIFIED: 48; `autoplan`, `ship` |
| 47 | `check_adr_lifecycle.py` passes with ADR-127 present | behavior | `uv run python scripts/validation/check_adr_lifecycle.py` | VERIFIED after the prose review date was added: `[PASS] 153 violation(s) across 126 ADR record(s), none outside the baseline` |
| 48 | ADR-057 records 108 commits touching eval-scoped prompts against 1 with evidence | quote | `sed -n 273p` on ADR-057 | VERIFIED |
| 49 | ADR-112 puts force push and hook bypass in the consequential tier, enforced by `permissions.deny` | quote | `sed -n 85,104p` on ADR-112 | VERIFIED |
| 50 | The gstack files read give no call count from after the phase change | absence | read `lib/ship-phase.ts`, `lib/ship-clock.ts`, `ship/DRIVER.md`; a panel seat also searched `CHANGELOG.md` and one eval preregistration file | VERIFIED for those files only. Not a whole-repository search |
| 51 | ADR-103 is accepted and requires `--output-format` with `json`, `human`, `auto`; `auto` resolves to `json` when stdout is redirected | quote | `sed -n 3p`; `sed -n 92,100p` on ADR-103 | VERIFIED: decision items 2, 3, and 4 |
| 52 | The runner records the base as a ref name, not a commit | path | `sed -n 1031p scripts/eval/eval-prompt-change.py` | SUPERSEDED by row 58 at `26cb7876e8` (2026-11-25): the runner now also records `base_commit` |
| 53 | The runner excludes a scenario with an unstable base from regressions | path | `sed -n 769,772p scripts/eval/eval-prompt-change.py` | VERIFIED: `if is_base_unstable(...)` appends to `base_unstable_scenarios` and skips the regression branch |
| 54 | ADR-103 gives the envelope `Success`, `Data`, `Error`, and `Metadata`, and makes `Error.Code` the ADR-035 exit code | quote | `sed -n 92,93p`; `sed -n 103,104p` on ADR-103 | VERIFIED: decision items 1 and 6 |
| 55 | The runner treats three base shapes as unstable: a pass that is flaky, fewer than the required scored runs, and a resample that contradicts a clean first pass. ADR-127 decision 7 item 7 names the first two and points to the runner's list for the rest | behavior | read `is_base_unstable`, `scripts/eval/eval-prompt-change.py:518-540` | VERIFIED: three return paths |
| 56 | The decision 9 check is `scripts/validation/check_skill_rewrite_evidence.py` and runs in `pre_pr.py` | path | `grep -n check_skill_rewrite_evidence scripts/validation/checks_ci_parity.py` at `26cb7876e8` (2026-11-25) | VERIFIED: line 315 names the script; `pre_pr_sequence.py` registers the gate |
| 57 | The check runs in the `Validate PR` CI job | path | `grep -n "name: Validate PR\|check_skill_rewrite_evidence" .github/workflows/pr-validation.yml` | VERIFIED: job name at line 43, step at line 328, command at line 336 |
| 58 | The runner records all four identities in an `identity` block built by `run_identity` | behavior | read `scripts/eval/eval-prompt-change.py:1180-1206`, the call at line 1225, and the output key at line 1244 | VERIFIED: `prompt_surface_sha256`, `scenarios_sha256`, `base_commit`, `model` |
| 59 | The check recomputes the item 7 floor from the after results | behavior | read `_floor_findings`, `scripts/validation/skill_rewrite_evidence.py:229` | VERIFIED: `TestFloors` at `tests/validation/test_skill_rewrite_evidence.py:278` covers it |
| 60 | A brand-new skill is not gated; a new skill beside a deleted one is gated | behavior | read `_gate_or_skip` in `check_skill_rewrite_evidence.py`; `uv run pytest tests/validation -k skill_rewrite` | VERIFIED: 187 passed at `ddf10d447a` (2026-11-25) |
| 61 | The owner confirmed the new-skill reading on 2026-11-25 | quote | owner answer to decision brief D1 in the #7589 session, option "Amend ADR-127 here" | VERIFIED |

## Gate results

| Gate | Result |
|---|---|
| Claims ledger | VERIFIED: 55 rows. Rows 33 to 47 were added in the first debate's round 1 and rows 48 to 50 in its round 2. Rows 51 to 55 were added in and after the fourth debate |
| Documentation accuracy | Phase 4 ran once on 2026-11-25 (Sonnet, 11 tool uses, 61 s). 7 findings: 2 High, 2 Medium, 3 Low. All 7 fixed in the draft before the panel. High 1: the eval command pointed at the template, which feeds raw partial tags and skips `references/`. High 2: the draft called the grade deterministic and cited ADR-058. VERIFIED after the fixes by rows 28 to 31 |
| Self-consistency | FAILED on the first draft, as the panel showed: freeze against retire inside decision 7, the gate trigger in decision 7 against decision 9, and the unfunded-key row against the NOT RUN rule. Re-run on the round 1 revision: VERIFIED for decisions 1 to 13 against each other and Consequences |
| Refuting seat | Ran once on 2026-11-25 (`analyst`, Haiku, 52 tool uses, 126 s). 25 rows CONFIRMED. Row 6 not reproduced by the seat (no shell); row 14 not rerun by the seat. One finding outside the ledger: the ADR cited `SPEC-ship-driver.md`, which is not in this tree. Fixed by naming the unmerged branch instead. VERIFIED after the fix: `grep -c SPEC-ship-driver` on the ADR returns 0 |
