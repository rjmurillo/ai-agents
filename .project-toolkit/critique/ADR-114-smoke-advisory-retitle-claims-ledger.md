# ADR-114 Claims Ledger: Smoke Advisory Retitle (2026-11-26)

Factual claims behind the 2026-11-26 retitle and dated notes in ADR-114.
Rows were read at `origin/main` `67899d52d` (2026-11-26) unless a row says otherwise.

| # | Claim | Kind | Command | Result |
|---|-------|------|---------|--------|
| 1 | `plugin-cli-smoke.yml` is listed in `advisory_agent_workflows` | quote | `git show origin/main:src/claude/skills/pr-review/pr-review-config.yaml`, read the list | VERIFIED: entry 7 of 7 is `path: ".github/workflows/plugin-cli-smoke.yml"` |
| 2 | The readiness check loads that list, including the smoke | behavior | `_load_advisory_agent_workflows()` from `.claude/skills/github/scripts/pr/test_pr_merge_ready.py` | VERIFIED: returns 7 paths, `.github/workflows/plugin-cli-smoke.yml` among them, no warning |
| 3 | `CLI Smoke Result` is not a required context on `main` | absence | `get_branch_protection.py --owner rjmurillo --repo ai-agents --branch main --output-format json` (2026-11-26T07:16:17Z) | VERIFIED: 9 ruleset contexts, none is `CLI Smoke Result`; no classic protection |
| 4 | The workflow still runs on pull requests and still reports `CLI Smoke Result` | behavior | `git show origin/main:.github/workflows/plugin-cli-smoke.yml`, lines 89-92 and 673 | VERIFIED: `on: pull_request` and `workflow_dispatch`; job `name: CLI Smoke Result` |
| 5 | The legs still wait in `agent-${{ matrix.cli }}` | quote | same file, line 201 | VERIFIED: `environment: agent-${{ matrix.cli }}` |
| 6 | The 2026-11-05 amendment names the title, Decision 5 sentence, Decision 13 heading and lead, item 5, and the Consequences lines as superseded | quote | `sed -n 180p` on ADR-114 | VERIFIED |
| 7 | The 2026-11-05 amendment withdraws Decision 11 item 8 and says the Decision 13 rollback row no longer applies | quote | `sed -n 182,183p` on ADR-114 | VERIFIED |
| 8 | No other file quotes the old title except the index and one claims ledger | absence | `git grep -n -i "Except the Plugin CLI Smoke"` (whole tree), before the edit | VERIFIED before the edit: ADR-114 lines 13 and 180, `README.md:170`, `ADR-127-claims-ledger.md:28`. After the edit: ADR-114 line 180 (amendment history), the new 2026-11-26 amendment, and `ADR-127-claims-ledger.md:28` |
| 9 | Lines above the new amendment keep their numbers | count | `wc -l` before the edit, and a diff of line positions | VERIFIED: 217 lines before; every edit above line 201 appends to an existing line. The new amendment adds lines after line 200 only |
| 10 | The readiness check drops a listed check from both non-required buckets | behavior | read `test_pr_merge_ready.py:1126` (`_exempt_advisory_checks`) and its caller at `:1301` | VERIFIED by code read |

## Inbound references left unchanged

- `ADR-127-claims-ledger.md:28` records the old title as read on 2026-11-25 at `792f6febd3`. It is a point-in-time verification, so it stays.
- `ADR-071` line 628 says `CLI Smoke Result` blocks merge, and line 640 says auto-merge waits once the owner adds it to the ruleset (ADR-114 Decision 11 item 8, now withdrawn). ADR-114's 2026-11-05 amendment already says to read that note with the amendment. The pointer runs one way only. Editing ADR-071 needs its own debate log, so it is out of scope and is flagged in the pull request body.
