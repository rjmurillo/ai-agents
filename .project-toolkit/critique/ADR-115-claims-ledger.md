# ADR-115 Claims Ledger

Scope: the proposed Decision 6 amendment of 2026-11-25 (issue #7591). Base `71ab5b15b3` (2026-11-25). Pilot branch `refactor/adr-127-ship-driver-pilot` at `3a619dabd6` (2026-11-25). Pinned guard: hermes-agent `63d0b94120`.

| # | Claim | Kind | Command or read | Result |
|---|---|---|---|---|
| C1 | Main has four packs: delivery 299, knowledge 263, authoring 208, quality 166 files | count | `git ls-tree -r --name-only 71ab5b15b3 src/hermes/<pack> \| wc -l` | VERIFIED |
| C2 | Each pack's `lib/` is 57 files, so overhead with `plugin.json` is 58 | count | `git ls-files src/hermes/project-toolkit-delivery/lib \| wc -l` = 57 | VERIFIED |
| C3 | Pilot `_ship_common.py:380` joins sibling skill paths at run time | path | `git show 3a619dabd6:src/claude/skills/ship/scripts/_ship_common.py`, lines 380-382: `def skill_script(...)`, `parents[2].joinpath(skill, "scripts", *parts)` | VERIFIED |
| C4 | Pilot `ship_pr.py` runs `github`'s `new_pr.py`; `ship_preflight.py` runs `review`'s `validate_review_marker.py` | path | `ship_pr.py:97` `skill_script("github", "pr", "new_pr.py")`; `ship_preflight.py:116` `skill_script("review", "validate_review_marker.py")` | VERIFIED |
| C5 | Seven shipped skills run `github` scripts by path | count | `find_references` over `src/claude/skills`: `github-url-intercept`, `validate-pr-description`, `push-pr`, `pr-autofix`, `pr-review`, `pr-comment-responder`, `research`, plus pilot `ship` (C4). `merge-resolver`, `orphan-ref-validator`, and `review` hits are comments. | VERIFIED. See note N1. |
| C6 | `security-scan` rates `dangerous` from `references/vulnerability-patterns.md:23` and has a `high` at `SKILL.md:180` | behavior | `scan_plugin(..., source="local")` on a copy: `system_passwd_access` critical and `path_traversal_deep` high at line 23; `sudo_usage` high at line 180 | VERIFIED |
| C7 | Rewording both lines rates `security-scan` `safe` | behavior | Same scan on a copy with both lines reworded: `safe`, 0 high | VERIFIED |
| C8 | `review` and `ship` (main and pilot) rate `safe` alone | behavior | Same scan: `review` safe, main `ship` safe, pilot `ship` safe | VERIFIED |
| C9 | Hermes `skill_view(name, file_path)` reads a file inside another skill | behavior | `git -C <hermes-agent> show 63d0b94120:tools/skills_tool.py`, lines 550-555, docstring (the working tree at `2bd378ed1b` moves it to line 615): "View a skill (SKILL.md) or a file within its directory" | VERIFIED (read; not run in a live Hermes session) |
| C10 | Nine files name another pack's skill path under the layout (round 2 layout) | count | `find_references` under the proposed table, every hit per edge grepped | VERIFIED: `review` 6 files, `spec-generator` 1 (lines 3, 158, 275-280), `api-doc-authoring` 2 (template line 127, `example-verification.md:79`). `merge-resolver` stays in delivery, so its docstrings no longer cross. |
| C11 | Projected counts: delivery 372, git 70, azure-devops 68, knowledge 268, quality 125, authoring 253 | count | `skill_files` minus `excludedFiles`, plus 58, plus one file per script named in `skill-gap-audit-2026-11-25.md` for P0 and P1 | VERIFIED as arithmetic; growth is a projection |
| C12 | Staged delivery and authoring rate `caution` with no new `high`; other four `safe` | behavior | Pinned guard on staged copies. Delivery highs match the 13 on main; 2 extra hits came from `test/references/rule-testing.md`, an `excludedFiles` entry the staging kept. | VERIFIED |
| C13 | Folding the three-skill `git` pack into delivery projects to 384 (16 free) | count | Same method, 39-skill delivery table | VERIFIED |
| C14 | `pr-review` and `pr-autofix` run `github` scripts by path | path | `find_references`: `pr-review/SKILL.md` and `pr-autofix/SKILL.md` match `skills/github/scripts` | VERIFIED |
| C15 | Least change (today's table, plus `azure-devops`, chain restored, `codeql-scan` and `golden-principles` moved) projects delivery to 390 | count | Same method on today's table plus 5 restored skills | VERIFIED |
| C16 | The layout moves 13 skills and restores 7 | count | Moves: 3 to git (`takeover`, `modernize`, `git-advanced-workflows`), 2 to azure-devops, `benchmark-models`, `codeql-scan`, `golden-principles`, `style-enforcement`, `technical-writing`, `fix-markdown-fences`, `api-doc-authoring`, `prompt-engineer`. Restores: `ship`, `review`, `security-scan`, `pr-quality`, `security-detection`, `spec-generator`, `stuck-detection` | VERIFIED |
| C17 | One shared `lib/` file costs six slots | count | Six packs, one `lib/` copy each | VERIFIED |

N1: C5 by-path users are seven skills; with `ship` through code, eight. The ADR says "Seven shipped skills run `github` scripts by path", then names `ship` separately. The analysis doc says nine, and is corrected to seven in the same change.

## Gate results (adr-generator exit gates, 2026-11-25)

- Gate 1, claims ledger: VERIFIED (this file).
- Gate 2, doc-accuracy: VERIFIED after commit. `doc_accuracy.py --target . --diff-base origin/main --format gate` returned verdict PASS, 0 findings (2026-11-25). A first whole-repo run timed out at 300 s.
- Gate 3, self-consistency: VERIFIED. The Decision 6 bullets, the four new alternatives, and the Negative bullet agree on packs, moves, and counts.
- Gate 4, refuting seat (analyst, haiku, 86 s): one finding, on C9. It read the hermes-agent working tree at `2bd378ed1b`, where the docstring is at line 615. The ledger cites the pinned commit `63d0b94120`, where `git show 63d0b94120:tools/skills_tool.py` puts it at line 552. Not a factual error. C9 now names the revision. The seat could not check C1, C3, C4, C10, or C11 (no git access) or rerun guard claims.

## Round 1 revisions (2026-11-25)

- `git` shrinks to 3 skills; `merge-resolver` and `maintainer-review` stay in delivery. Recomputed: delivery 36 skills, 351 now, 372 after P0 and P1; git 64, 70, 70. Restaged guard: delivery `caution` (15 hits, 2 from the kept `rule-testing.md`), git `safe`, delivery 4.52 MB.
- C18: main's `ship` hands PR creation to `push-pr`. `src/claude/skills/ship/SKILL.md:4` and `:159`. VERIFIED. The layout therefore depends on the pilot merging first.
- C19: 4 `high` findings on main are not in `FORCE_ALLOWED_FINDINGS`: `code-qualities-assessment/references/calibration-examples.md:228,242,249` and `skill-bootstrap/scripts/adr_reason.py:184`. Pinned guard output compared with the security seat's count of 10 delivery and 1 authoring entries. VERIFIED.
- C20: `scan_bash_heredoc.py:62-65` says any command outside `_INERT_READERS` (for example `su`, `sudo -i`, `runuser`, `chroot`, `at`, `source`, a shell) may run a here-doc body. VERIFIED by read; corrected from `:62-63` after review.

## Post-consensus corrections (2026-11-25)

- C13 corrected: 398 came from an early single-pack run that also held `spec`, `spec-generator`, `api-doc-authoring`, and five git skills. The current fold-in is 384, from `check_layout.py` on the round-2 table with `git` merged.
- C21: the pilot adds 4 scripts under `ship/scripts/` and changes no `SKILL.md` (`git diff --stat main...3a619dabd6 -- src/claude/skills/ship templates/skills/ship.SKILL.md.tmpl`: 4 files). Pilot `ship/SKILL.md:31,159` still hand off to `/push-pr`. VERIFIED.
- C22: the chain adds 56 files (pilot `ship` 8, `review` 28, `security-scan` 17, `pr-quality` 1, `security-detection` 2). VERIFIED. The analysis said 60; corrected.

## PR #7634 follow-up (2026-11-25)

| ID | Claim | Evidence | Result |
|---|---|---|---|
| C23 | #7581 is blocked by #7587; #7586 is not | `get_issue_relationships.py --issue 7581` and `--issue 7586` | VERIFIED |
| C24 | #7586 may land with `push-pr` still shipped | Pilot owner confirmation; #7586 wiring criteria and #7587 conditional bundling clause | VERIFIED as a merge boundary, not as completed work |
| C25 | `spec-generator` calls excluded `cva-analysis` for Tier 3 to 5 and multi-use-case Tier 1 or 2 specs; Tier 4 and 5 also call blocking `adr-review` | `spec-prior-art-schema.md:195` (Step 5) and lines 234-239; `hermes.yaml` excludes both skills | VERIFIED |
| C26 | Current path validation allows same-pack targets | `check_references` in `build/scripts/hermes_pack_checks.py` | VERIFIED |
| C27 | An old table that names a removed skill fails validation | `check_assignment` in `build/scripts/hermes_pack_checks.py` | VERIFIED |
