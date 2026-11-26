# ADR-115 Debate Log 9

- **ADR**: `.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md`, Decision 6, proposed job layout (amendment 2026-11-25, not in force).
- **Issue**: #7591 (epic #7580).
- **Prior debate log**: `.project-toolkit/critique/ADR-115-debate-log-8.md` (closed by consensus; not edited).
- **Claims ledger**: `.project-toolkit/critique/ADR-115-claims-ledger.md`.
- **Analysis**: `.project-toolkit/analysis/hermes-pack-jobs-to-be-done-2026-11-25.md`.
- **Panel**: full (architect, critic, independent-thinker, security, analyst, high-level-advisor). The amendment sets the pack table the build will enforce, and logs 7 and 8 ran the full panel for the same kind of change.
- **Base**: `71ab5b15b3` (2026-11-25). Pilot `ship`: `3a619dabd6` (2026-11-25). Pinned guard: hermes-agent `63d0b94120`.

## Pre-review gates (adr-generator)

- Claims ledger: VERIFIED.
- doc-accuracy: NOT RUN. The script timed out at 300 s in Phase 1.
- Self-consistency: VERIFIED.
- Refuting seat (analyst, haiku): one finding on C9, a line-number mismatch. It came from reading the hermes-agent working tree, not the pinned commit. Not a factual error; C9 now names the revision.

## Round 1

Votes: architect D&C, critic Block, independent-thinker D&C, security D&C, analyst D&C, high-level-advisor Accept.

### P0

| ID | Seat | Finding | Disposition |
|---|---|---|---|
| R1-P0-1 | critic | Main's `ship` still hands PR creation to `push-pr` (`ship/SKILL.md:4`, `:159`). "As every other host does" is false today. Gating #7587 on the Hermes restore alone breaks `ship` everywhere. | Resolved. Decision 6 and the analysis state the order: pilot, then this layout, then #7587. The PR path text now says "after the pilot merges". |

### P1

| ID | Seat | Finding | Disposition |
|---|---|---|---|
| R1-P1-1 | architect | Log 9 is cited but missing. | Resolved. This file. |
| R1-P1-2 | architect, high-level-advisor | Nothing enforces the boundary for paths joined in code, or the `lib/github_core` rule. | Resolved. Decision 6 says no check enforces it today. Acceptance criterion 7 adds a check or records an accepted risk. Criterion 1 requires a six-pack smoke run. |
| R1-P1-3 | architect | No proof the `security-scan` rewording keeps detection the same. | Resolved. Acceptance criterion 4: a negative-control test on its fixtures. |
| R1-P1-4 | analyst, high-level-advisor | The pilot dependency is not stated in the ADR. | Resolved. Precondition bullet in Decision 6. |
| R1-P1-5 | analyst | `spec-generator` row misses line 3. | Resolved. Row reads 3, 158, 275-280. |
| R1-P1-6 | analyst | `api-doc-authoring` row names a generated file. | Resolved. Row names `templates/skills/api-doc-authoring.SKILL.md.tmpl:127`. |
| R1-P1-7 | critic | Growth assumptions unstated; no split trigger. | Resolved. Assumptions listed (no `lib/` growth, no P2, no new skills). Split trigger: under 20 files free. |
| R1-P1-8 | critic | Cross-pack name reads never run live. | Deferred to the implementation PR, criterion 3. Reason: this PR is design only and installs nothing; the pinned source was read (C9). |
| R1-P1-9 | critic | Migration omits the install guide, the README index, and the force list. | Resolved. Acceptance criteria 2 and 6. |
| R1-P1-10 | critic, security, high-level-advisor | Guard baseline drift: 13 vs 10 in delivery, 2 vs 1 in authoring; smoke NOT RUN. "No new high" hid the drift. | Resolved in text: the 4 unreviewed findings are listed by line, and the wording is "no `high` beyond main's". The smoke run is deferred to the implementation PR, criterion 1, because this PR changes no pack. |
| R1-P1-11 | independent-thinker | The five-skill `git` pack is a capacity cut. `merge-resolver` and `maintainer-review` serve PR jobs. | Accepted. `git` holds `takeover`, `modernize`, `git-advanced-workflows`. Delivery projects to 372 (28 free). Recorded as rejected alternative 4. |
| R1-P1-12 | independent-thinker | The rewording works around the guard; the CWE-22 section is out of scope for the skill. | Partly accepted. Alternative 8 records why moving the section does not help: the line flags in any packed skill. The `sudo` wording now points at `scan_bash_heredoc.py:62-65` (first written as `:62-63`, corrected after `/review`). The Negative bullet records the larger blast radius of a future `critical` line. |
| R1-P1-13 | security | Migration trains users to pass `--force`. | Resolved. Remove, then install without `--force`, then compare findings. |
| R1-P1-14 | security | Restored scripts run on Hermes with no capability review. | Resolved. Acceptance criterion 5 lists each script's subprocess, network, and credential use. |
| R1-P1-15 | high-level-advisor | The layout edits shipped files, which reverses the D10/D11 constraint without asking. | Resolved. Open question 3 asks the owner. ADR-115 already says a later change may reword. |
| R1-P1-16 | high-level-advisor | No build check stops a pack table with no PR-opening skill. | Resolved. Acceptance criterion 8. |

### P2

- Resolved: `stuck-detection` restore reason (architect); `review` loses its reading lists without `knowledge` and `quality` (architect); audit file cited for P0 and P1 (architect); still-excluded list in the ADR (analyst); staging kept one `excludedFiles` entry, now stated (analyst); C9 line 550 is the function, 552 the docstring (analyst); verdict tied to the pinned guard, and rewording limited to prose that does not run (security); placeholder for the traversal example (security); "22 files of room" removed (critic); security split and `research` placement explained (critic); "always install delivery" stated (independent-thinker); "six slots" corrected (independent-thinker); least-change fallback priced at 390 (independent-thinker, high-level-advisor).
- Not changed: moving `technical-writing` and `fix-markdown-fences` to `authoring`, which makes doc writers pass `--force` (independent-thinker). It keeps the J10 job whole. The owner may veto it.
- Not changed, pre-existing: frontmatter `status: proposed` with shipped trees, and Status entries out of date order (architect). Outside this amendment.

## Round 2

Votes: architect Accept, critic Accept, independent-thinker Disagree-and-Commit, security Accept, analyst Accept, high-level-advisor Accept. No P0 or P1 open.

Outcome: consensus in round 2, five Accept and one Disagree-and-Commit.

Dissent recorded (independent-thinker): the pinned guard runs in no build or CI job. A reintroduced `critical` line in delivery would block the whole base pack, and only a manual smoke run would catch it. The ADR names the risk in a Negative bullet. The independent-thinker also notes that deleting the CWE-22 section, which `security-scan` says it does not scan, was not weighed against moving it.

## After consensus

Applied 2026-11-25. These are the fixes two seats asked for; no rule changed, so no further round ran.

- Architect and high-level-advisor (P2): acceptance criteria lived only in the analysis. Decision 6 now points to them and names criteria 7 and 8 so they bind.
- Security (P2, for the implementation PR): the install guide's reviewed list must be updated (criteria 2 and 6) before users follow the remove-then-install steps.

Status stays `proposed`. The owner decides the layout under Decision 6.

## Factual corrections after consensus

Applied 2026-11-25 from a final check. Facts only; no rule or layout changed, so no further round ran.

- The fold-in alternative was priced from an early layout (398). With the three-skill `git` pack folded in, delivery projects to 384 of 400 (16 free). The analysis now offers the fold-in as an owner option.
- The pilot adds `ship_pr.py` but changes no `SKILL.md`; pilot `ship/SKILL.md:31,159` still hand off to `/push-pr`. The precondition now says the pilot must rewire `ship` before this layout lands.
- The restored chain is 56 files, not 60.
- `spec-generator` calls `adr-review` and `cva-analysis` by name; both stay excluded, now stated.
- The ADR frontmatter `date` stays 2026-11-24, so the generated index `.project-toolkit/architecture/README.md` does not change. PR #7629 edits that file.
- Two `security-scan` citations in Decision 6 now give the full repository path, so the citation-freshness gate resolves them.
- The `vulnerability-patterns.md:23` citation names its row, which the citation-freshness gate matches.
- The same citation now follows its anchor text, which the gate reads from before the citation.
- doc-accuracy, recorded as NOT RUN before review, later passed: the diff-scoped run (`--diff-base origin/main --format gate`) returned PASS with 0 findings.
- `/review` round 1 fixes (facts and wording only): a reversibility bullet, same-line anchors on three Decision 6 counts, `sudo_usage` named as a `high` finding that leaves a `caution` verdict, and the reader-list citation corrected to `scan_bash_heredoc.py:62-65`. Acceptance criteria 9 and 10 add step-by-step commits and a check that reworded lines do not run.
- The Decision 6 lead-in no longer says "six packs:" before an 18-item list, which the doc-accuracy cardinality rule flagged.
- `/review` round 2 (decision-rigor): acceptance criterion 9 ordered a restore commit that `hermes_pack_checks.py` would fail, because `review` names `decision-critic`, `observability`, and `codeql-scan` paths. It now puts the name-only references first, then the chain restore with `codeql-scan` and `golden-principles` in one commit.
