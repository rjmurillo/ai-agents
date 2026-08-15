---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-99916-b79742bf0-triage-resolve-5062-review-threads.json
qaCommit: 56237643c5951dc17e4a853b5e27f4c645061015
---

# QA: ADR-094 scoped re-review axes

## Scope

One added file: `.agents/architecture/ADR-095-scoped-re-review-axes.md` (drafted as ADR-094). A
proposed-status ADR draft. No code, no generated artifact, no shipped skill
change. The verifiable surface is the document's factual claims and its
conformance to repository text rules.

## What ran

| Check | Command | Result |
|---|---|---|
| Em-dash and en-dash prohibition (`.claude/rules/universal.md` MUST NOT 5) | byte count of U+2014 and U+2013 | 0 and 0 |
| Banned vocabulary (`.claude/rules/voice.md`) | regex over the 19-word list | 0 hits |
| ADR number collision | `ls .agents/architecture/ADR-*.md` | 94 existing files, highest ADR-093; 094 free |
| Prior-art search (`.claude/rules/search-before-building.md`) | `git grep -F -i` for `sub-loop`, `subloop`, `CI-feedback`, `scoped review`, `convergence` over `.agents/architecture/` | 2 hits, both unrelated uses of the word "convergence" (ADR-051:209, ADR-068:24). No ADR covers this ground. |
| Cited path resolution | `git ls-files` over all 13 paths the ADR names | 13 of 13 tracked |
| Quoted-line accuracy | scripted needle check within a 6-line window of each cited line number | 5 of 5 verified, table below |

## Quoted-line verification

Each load-bearing quote was checked against the file at the cited line, not
recalled from context.

| Citation | Quote checked | Result |
|---|---|---|
| `.claude/skills/review/SKILL.md:152` | `Reviewed-By: /review@<comma-separated-axis-list> on <reviewed-tip-sha>` | PASS |
| `.claude/skills/review/SKILL.md:164` | "the marker is valid only while" its parent is HEAD's parent | PASS |
| `.claude/commands/ship.md:109` | "Exit `1` means no marker, a stale marker, or new code landed after review" | PASS |
| `.agents/governance/CI-FEEDBACK-SUBLOOP.md:28` | "Re-run only the axes that flagged the original cluster, not all axes" | PASS |
| `.agents/governance/CI-FEEDBACK-SUBLOOP.md:11` | "PR #1965 (58 commits, 18 rounds) and PR #1979 (30 commits, 18 rounds)" | PASS |

## Correction found and applied

The task framing asserted that `pr-autofix` invokes `/review` per open PR at the
T3 and T4 tiers, making it the cost amplifier. That is false.
`git grep` over `.claude/commands/pr-autofix.md` returns no `/review`
invocation; the only matches are prose about review threads and a
`PR_REVIEW_CONFIG_PATH` variable. The T3 and T4 tiers walk the review-thread
lifecycle and do not run the axes.

The ADR states the corrected amplifier instead: `/ship` requires a SHA-bound
marker that any new code commit invalidates, so the full 15-axis run repeats per
fix round regardless of which tool drove the fix. That claim is supported by the
two quoted lines above.

## Not verified

- **The reduction figure is arithmetic on an assumed workload** (6 total
  rounds, 2 flagged axes), not a measurement. The original draft's 72% figure
  undercounted the proposed cost: it omitted the mandatory Stage-1 axis on
  every scoped round (contract change 7) and the initial full run needed to
  find what to scope in the first place. Corrected to 42 axis invocations
  against the unchanged 90-invocation baseline, a 53% reduction. The ADR
  labels this as arithmetic, not measurement. No scoped mode exists yet, so
  no empirical number is obtainable.
- **The 24% signal ratio** comes from 6 CI review agents in
  `.agents/analysis/009-phase1-agent-comment-baseline.md`, a different population
  from `/review`'s 15 axes. The ADR states this limitation inline and lists a
  per-axis signal measurement as an open item.
- **No behavioral testing**, because the ADR proposes rather than implements. The
  required tests are specified in the document for the implementing change.

## Verdict

PASS. Every factual claim in the document either resolves against a cited file
or is labeled as an estimate. The one inherited false premise was caught and
corrected.
