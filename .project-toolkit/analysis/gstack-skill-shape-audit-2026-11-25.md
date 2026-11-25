# gstack skill shape audit

Source: `github.com/garrytan/gstack` at commit `ec5d7e6fbd` (2026-11-25).
Method: read-only source read. No gstack code was run.
Every `path:line` below is a path inside that gstack commit, not this repository.
Three Sonnet readers produced the first pass. A second pass re-opened each cited line.
Claims marked INFERRED were not confirmed in code.
Rules D8 and D9 cite a manifest note and a directory count, not a code line.

## Rules extracted

### A. Skills hand fixed work to programs

| # | Rule | Evidence in gstack |
|---|---|---|
| A1 | The model keeps judgment. Programs do the fixed steps. | `ship/DRIVER.md:12` lists what the model keeps: judgment, fixes, CHANGELOG, PR prose, gates, the report. |
| A2 | One phase is one call. | `ship/DRIVER.md:10` gives the single form `gstack-ship-phase run --dir --phase --record -- <cmds>`. |
| A3 | A prose driver alone did not hold its call budget, so phases became single calls. | `lib/ship-phase.ts:2-3`: measured conductors made 121 to 308 calls where the driver plans 9 to 12. `lib/ship-clock.ts:3` adds that 10 of 12 ran past the 100 minute stop. gstack gives no count from after the change. |
| A4 | A driver states its call budget. | `ship/DRIVER.md:29`: one clean pass is 9 calls, at most 12. |
| A5 | A program is a thin shim over a pure function. | `bin/gstack-ship-preflight:12-13` writes `out.text` and exits `out.exit`. The function returns text and an exit code, so tests need no subprocess. |
| A6 | A phase run is journaled and resumable. | `lib/ship-phase.ts:6` keys each finished command by sha256. `lib/ship-phase.ts:37` reads `journal.json` with `schema_version`. |
| A7 | Phase order is not enforced in code. | INFERRED. The reader found no check that phase n-1 finished. `--phase` is a directory name. |

### B. Result lines, exit codes, caps

| # | Rule | Evidence in gstack |
|---|---|---|
| B1 | Programs print `KEY: value` lines. A parent keeps only lines that match one regex. | `lib/ship-phase.ts:25` defines `RESULT_RE`. |
| B2 | Output is bounded in code, not by request. | `lib/ship-phase.ts:24` caps a phase at 60 result lines. `lib/ship-parts.ts:17` sets a 32000 byte room. |
| B3 | `STOP:` means nothing after it ran. `NEXT:` names the next act. | `ship/DRIVER.md:13-14`. |
| B4 | Exit 3 means STOP or refused in the ship programs. | `lib/headless-artifacts.ts:161`: `EXIT = { ok: 0, fail: 1, usage: 2, refused: 3 }`. `lib/ship-preflight.ts:55` and `bin/gstack-ship-phase:16` repeat it. |
| B5 | Exit 3 is not uniform across gstack. | `bin/gstack-post:11` uses 1 and 2 for refusals. `bin/gstack-verify-gate:19-20` uses 0 and 2 as a hook. `bin/gstack-skill-gates:15` uses 2 for not armed. |
| B6 | A workflow ends on one machine-readable line. | `lib/headless-artifacts.ts:155` lists seven statuses. `lib/headless-artifacts.ts:166` documents the `GSTACK_RESULT:` terminal line. `ship/DRIVER.md:121` shows it. |
| B7 | Waits are capped in code. | `lib/ship-phase.ts:23` sets 200 seconds. `lib/ship-phase.ts:104` prints `WAITING:` then `NEXT: rerun`. |
| B8 | A run has a hard time limit that writes a stop file. | `lib/ship-clock.ts:17` sets 100 minutes. `lib/ship-clock.ts:18` names `stop.json`. |
| B9 | Error text comes from one table of codes. | `lib/result-codes.ts:31` defines `RESULT_CODES`. |

### C. What the model keeps and what it may not do

| # | Rule | Evidence in gstack |
|---|---|---|
| C1 | The parent owns advancement. Children return evidence, not permission. | `ship/SKILL.md:226`. |
| C2 | The parent never reads the full diff or the TODO file. A program writes them to a file. | `ship/DRIVER.md:72`. |
| C3 | Unattended runs take the recommended option and log it. Gate approvals stay pending. | `ship/DRIVER.md:16-17`. |
| C4 | Session kind is a program output, not a model guess. | `bin/gstack-session-kind:5` prints one of four kinds. |
| C5 | Skipping a stop needs a recorded class. Anything else is refused. | `bin/gstack-no-stop:12`. |
| C6 | A rerun is diagnostic. Only the final full run sets the verdict. | `ship/sections/measure.md:5-8`. That section also bans raising a budget or lowering a threshold to pass. |

### D. Sections on demand and the STOP table

| # | Rule | Evidence in gstack |
|---|---|---|
| D1 | Three layers: a skeleton, on-demand sections, and a short driver. | `ship/SKILL.md:251` calls itself a decision-tree skeleton. `ship/DRIVER.md:5` says to read the driver, not the skill. |
| D2 | A section is read only when a phase or a STOP sends the model there. | `ship/DRIVER.md:14-15`. |
| D3 | Each STOP string maps to one `file#anchor`. | `ship/DRIVER.md:123-148`, 24 rows. |
| D4 | A test proves every STOP anchor resolves to a real heading. | `test/ship-driver.test.ts:271-279`. |
| D5 | A test proves every program the driver names exists. | `test/ship-driver.test.ts:16` imports the STOP rows from the generator, so the test and the doc share one source. |
| D6 | The driver has a byte budget. | `test/ship-driver.test.ts:289`: at most 12 KiB. The measured file is 148 lines. |
| D7 | The driver holds no harness vocabulary. | `test/ship-driver.test.ts:290` bans `AskUserQuestion`, `Agent tool`, `PreToolUse`, and `~/.claude`. |
| D8 | The section manifest is passive. It holds no machine predicate. | `ship/sections/manifest.json:5`. |
| D9 | Adoption is uneven. | 48 skill directories have `sections/`. Only `ship/` and `autoplan/` have a `DRIVER.md`. Counted with `ls` at this commit. |

### E. Reviewer brief dispatch

| # | Rule | Evidence in gstack |
|---|---|---|
| E1 | Reviewers get their briefs byte for byte. | `bin/gstack-review-dispatch:3`. `ship/DRIVER.md:23-25` forbids shortening a brief. |
| E2 | A program renders the brief to a file and records its sha256. | `bin/gstack-review-dispatch:59`. |
| E3 | A program hashes what was sent. A mismatch voids that review. | `bin/gstack-review-dispatch:61` and `:603`. `lib/review-ledger.ts:40` reads the rendered hash. |
| E4 | A reply must name the tree it reviewed. A wrong tree merges nothing. | `bin/gstack-review-dispatch:65-67`. |
| E5 | The lead cannot drop or downgrade a finding. | `bin/gstack-review-dispatch:74` and `:658` print `JUDGMENT_REJECTED`. |
| E6 | A program picks the reviewers from the diff. The model dispatches exactly that list. | `bin/gstack-review-plan:96` sets depth by risk, not size. `ship/sections/review-army.md:27` says to dispatch exactly its `DISPATCH:` lines. |
| E7 | Missing outside coverage is unavailable, never clean. | `ship/DRIVER.md:92`. |
| E8 | The lead still judges findings, with stated grounds. | `ship/sections/review-army.md:490`. This sits beside E5: the lead may reason, the program checks the result. |

### F. Run records and receipts

| # | Rule | Evidence in gstack |
|---|---|---|
| F1 | A run keeps one record file with fixed headings. | `lib/ship-handoff.ts:35`: Release, Decisions, Reviews, Checks, Documentation, Next steps. `ship/DRIVER.md:17-21` says which phase fills which. |
| F2 | The run record is a small state machine. | `lib/ship-run-record.ts:8` names `RUN_TRANSITIONS`. |
| F3 | The receipt is bound to the pushed head and its tree. | `ship/DRIVER.md:119` passes the reviewed tree to `gstack-ship-receipt write`. `ship/DRIVER.md:109` passes `--reviewed-tree` to `finish`. |
| F4 | A parent reads the result line, never the PR body. | `ship/DRIVER.md:121`. |
| F5 | Every ship program logs its own call. | `bin/gstack-ship-preflight:9` calls `logShipCall`. `lib/ship-call-log.ts:44` defines it. |

### G. Templates and generated docs

| # | Rule | Evidence in gstack |
|---|---|---|
| G1 | The `.tmpl` file is the source. The rendered skill is committed. | `CLAUDE.md:115`. `package.json:26` defines `gen:skill-docs`. |
| G2 | CI regenerates and fails on any diff. | `.github/workflows/skill-docs.yml:43` runs `git diff --exit-code`. |
| G3 | Generated files carry a "do not edit" header. | `scripts/gen-skill-docs.ts:632`. |
| G4 | One template renders for many hosts. | `scripts/host-config.ts:116-118` declares per-host `pathRewrites` and `toolRewrites`. The `hosts/` directory holds 18 entries. How each host renders was not traced. |

### H. Evals and tests

| # | Rule | Evidence in gstack |
|---|---|---|
| H1 | Paid evals are chosen by diff through a touchfile map. | `package.json:60` defines `eval:select`. `test/helpers/touchfiles-data.ts:27` holds the map. |
| H2 | Each eval has a tier: gate, periodic, or marathon. | `test/helpers/touchfiles-data.ts:1176`. |
| H3 | A new prompt with no registered coverage fails planning. | `CONTRIBUTING.md:269`. |
| H4 | Results are stored and compared to the last run. | `test/helpers/eval-store.ts:24` sets a schema version. `package.json:55` defines `eval:compare`. |
| H5 | Programs are tested with fake binaries on `PATH`. | `test/aside-artifacts.test.ts:86`. |
| H6 | Every skill needs an evidence row or an explicit untested status. | `CONTRIBUTING.md:810`. |
| H7 | Long evals run detached, because a turn boundary kills a background task. | `CLAUDE.md:450-457`. |

## Parts that do not fit this repository

| gstack part | Fit | Why |
|---|---|---|
| "Do not edit" header on generated files (G3) | Reject | `universal.md` MUST NOT 5 bans generated headers. ADR-108 section 4 makes drift a gate instead. |
| Exit 3 reserved for STOP (B4) | Adapt | ADR-035 already assigns 3 to an external service error. A `STOP:` line pairs with any non-zero ADR-035 code. |
| Bash and TypeScript programs, 211 in one `bin/` | Reject | ADR-042 requires Python. Scripts live under each skill's `scripts/` and run through `lib/ptk_run.py` (ADR-121). |
| LLM judge as a gate tier | Reject | ADR-058 keeps a judge advisory. Graders here are deterministic and frozen before a scored run. |
| Results in the user's home directory (H4) | Adapt | This repo commits eval results under `evals/`. The baseline is the same eval run against `origin/main`. |
| Paid evals that block a PR in CI (H2) | Adapt | ADR-057 (amended 2026-07-22) keeps CI eval enforcement advisory. ADR-114 forbids agent workflows from blocking a merge. The gate is a deterministic evidence check, not a CI model run. |
| Version bump, CHANGELOG, and release steps in ship | Reject | ADR-092 omits manifest versions. The unmerged ship driver draft lists these as non-goals. |
| Budget ledger, credits, Capy and Greptile paths | Reject | They serve a host and vendors this repo does not use. |
| A separate `DRIVER.md` beside a 983-line `SKILL.md` | Adapt | gstack keeps both because the old skill still exists. A rewrite here makes `SKILL.md` the driver and moves the rest to `references/`. |
| Preamble program at skill load (`gstack-skill-start`) | Defer | Load-time injection is a harness feature. No skill here has a present use case. |
| Brief hashing and a findings ledger (E2 to E5) | Adopt for `review` | `review` and `adr-review` dispatch briefs as prose today. |
| Byte budget and anchor tests on the driver (D4 to D7) | Adopt | Both are deterministic pytest checks. They fit `tests/skills/<name>/`. |

## Limits of this audit

- Phase-order enforcement (A7) is INFERRED. Host rendering (G4) is cited but not traced.
- `lib/ship-receipt.ts`, `gstack-evidence`, `gstack-pregate`, and `gstack-ship-queue` were read by header only.
- gstack's own eval pass rates were not measured. No gstack eval was run.
