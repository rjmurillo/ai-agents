# ADR-095 debate log

Subject: `.agents/architecture/ADR-095-scoped-re-review-axes.md`
(`status: rejected`). Drafted and debated as ADR-094 and renumbered on merge,
because `ADR-094` is taken on `main` by
`.agents/architecture/ADR-094-govern-copilot-cli-compatibility.md` (accepted in
PR #5024), which also owns `.agents/critique/ADR-094-debate-log.md`. Findings
below cite `ADR-094:<line>` against the draft as debated; those line numbers
refer to the 317-line draft, not to the 139-line rejection record that replaced
it.

Skill: `.claude/skills/adr-review/SKILL.md`, 6-agent debate, one round.

## Outcome

The maintainer rejected the ADR after this debate, going further than the
debate's own verdict of "narrow and re-measure". The deciding finding was F1:
the proposal's motivating incidents predate the mechanism it proposed to
change, so its evidentiary basis is anachronistic. PR #5010 (`458028d2b`) had
meanwhile shipped risk-based axis selection, which addresses the same cost on a
sound key. `.agents/architecture/ADR-095-scoped-re-review-axes.md` records the
rejection. No role voted to reject; see the vote table below and the dissent
section.

Roles run: architect, critic, independent-thinker, security, analyst,
high-level-advisor. Each received the ADR, the repository, and the counter
evidence in the section below. Each was told the debate is a real gate and was
asked to engage the counter evidence directly rather than around it.

## Why this debate ran late

ADR-094 was authored, committed, and pushed while this repository's git hooks
were inert: `core.hooksPath` pointed at a nonexistent `.githooks` directory
(issue #5090). `AGENTS.md:44` fires `adr-review` on any `ADR-*.md` edit, so the
ADR skipped a gate it should have passed. The hooks are repaired and
`git_hook_policy.py adr-review` now blocks further commits until this log
exists. The debate below is the gate the ADR owed, run after the fact.

## Verdict

**NOT ACCEPTED. Narrow and re-measure before acceptance.**

Consensus was not reached. The skill requires all six roles at Accept or
Disagree-and-Commit. Two roles Block.

| Role | Vote | Headline |
|---|---|---|
| architect | ACCEPT WITH CHANGES | Right boundary, wired to the wrong files |
| critic | **BLOCK** | Cost measured on a different system |
| independent-thinker | ACCEPT WITH CHANGES | Every cost citation predates the mechanism |
| security | **BLOCK** | The safety property is unenforceable prose |
| analyst | ACCEPT WITH CHANGES | Central parameter k is unmeasured |
| high-level-advisor | DISAGREE AND COMMIT | Correct design, third-priority work |

The one thing all six agree on: **the marker prohibition is correct and must
not be traded away.** An axis that did not run has no verdict, so a subset run
must not refresh the ship gate. No role attacked that reasoning. The critic
recorded a standing dissent that if a re-measurement shrinks the cost win, the
right answer is to descope or defer, never to soften the marker rule to make
the numbers work.

What the debate rejects is the ADR's evidence base and the location of its
enforcement, not its central idea.

## Counter evidence the debate was required to weigh

Supplied to every role because it cuts against the ADR.

1. On PR #5059, the full review fan-out caught a defect nothing else did. A
   `pr-autofix` round-cap gate was wired behind
   `TIER=$(echo "$LIVE" | jq -r '.Data.tier // "UNKNOWN"')`, reading a field
   `check_pr_live_state.py` never emits, so the guard never opened and the gate
   never executed. 26 unit tests passed throughout because they exercised the
   script in isolation, never the wiring. Four axes (Architect, Reliability,
   Agent Safety, Spec Coverage) converged on it independently.
2. An earlier no-op in the same feature (wiring hand-edited into a generated
   file, stripped by the next build) was caught by a deterministic CI check,
   not by review.
3. A batch of 10 review threads on PR #5062 were 10 of 10 real defects, zero
   noise, against the 24% signal ratio the ADR cites.

### How the debate resolved it

The counter evidence **narrows** the ADR. It does not falsify the marker
prohibition and it does not support rejecting the ADR outright.

The gate reasoning survives intact. A #5059-class defect introduced by a fix
commit still cannot ship, because the final full run is the only honest marker
source and every later code commit invalidates it.

The cost model does not survive. Five of six roles reached the same conclusion
independently: **the scoping key is structurally wrong, not merely
error-prone.** The ADR scopes round N+1 to the axes that flagged in round N.
Round N+1's defects are created by round N's fix, in code that did not exist
when the flagged set was computed. On PR #5059 the four converging axes were
exactly the ones with nothing to say the round before, and two of them
(Reliability, Agent Safety) run on the general-purpose fallback and are not
axes an author fixing a `jq` field name would name. The ADR prices this at "one
late round" (`ADR-094:253-256`). The critic walked the arithmetic: four clean
scoped rounds, a failing final full run, a fix, and another full run makes the
ADR's own 6-round model 57 against 90 (37%, not 53%), and about 20% if it
happens twice.

On counter evidence 3, the debate went further than the counter evidence did.
See the P0 table.

## Findings

P0 blocks acceptance. P1 must be resolved or deferred with an issue. P2 is
documentation only.

| ID | Sev | Role | Finding |
|---|---|---|---|
| F1 | P0 | critic, independent-thinker, analyst | Every cost citation predates the mechanism. `/review` became a skill in `c3ddc571a` on 2026-05-24; the SHA-bound marker landed in `16c960418` on 2026-06-04. PR #1887 merged 2026-05-05, PRs #1965 and #1979 merged 2026-05-10. None of those rounds contained a marker-forced full re-review, because the marker did not exist. The `18 x 15 = 270` line sits under a heading that reads "What the cost is, measured" and is a projection onto a period that lacked the mechanism. |
| F2 | P0 | critic | The 24% signal figure is spliced from two rollups of one document, lower half chosen. `009-phase1-agent-comment-baseline.md:163` reports 182 comments over 120 runs at 52% aggregate signal. `:178` reports 24% over a different 173-unit first-pass rollup. `ADR-094:44` pairs the 182 count from the first with the 24% ratio from the second. Counter evidence 3 (10 of 10 on PR #5062) is therefore corroborated from inside the ADR's own source. |
| F3 | P0 | security | The load-bearing prohibition is unenforceable, and the ADR claims it is proven. No marker-writer script exists: `.claude/skills/review/scripts/` holds only `validate_findings_scope.py` and `validate_review_marker.py`, and the marker is written by prose at `review/SKILL.md:159-162` as `git commit --allow-empty --trailer`, executed by the same agent that chose the scoped mode to save work. `ADR-094:236-237` calls its unit tests "the negative controls that prove a scoped run cannot become ship evidence"; no test over `validate_review_marker.py` can observe whether a model followed an instruction. CWE-693. |
| F4 | P0 | architect | Every validator change is aimed at a mirror. Three byte-identical copies exist; the canonical one is `scripts/validation/validate_review_marker.py`, registered in `scripts/sync_plugin_lib.py:44-45` and pinned by `tests/validation/test_review_marker_packaging.py:18-22`. `ADR-094:272` names only the `.claude/` mirror, which fails the packaging test and is overwritten on the next sync. |
| F5 | P0 | architect | Two push-blocking consumers are absent from the impact table. `scripts/validation/git_hook_policy.py` `_check_review_marker` fires pre-push on any `Reviewed-By: /review@` trailer and returns the validator's exit code as the hook's. `scripts/validation/checks_coverage.py` wraps the same validator inside `pre_pr.py`. The ADR rates `/ship` as the only consumer at "Low". A new exit-1 condition lands on every contributor's pre-push hook. |
| F6 | P1 | security | `ship.md:110` contributor mode says not to run the marker validator and accepts "a `/review` run logged in the ship report", which a scoped run satisfies verbatim. `ADR-094:274` asserts `ship.md` needs no change. The marker prohibition provides zero protection on that path. |
| F7 | P1 | security | Contract change 7 excludes SKIPPED axes from `merge_verdicts`, and `ADR-094:234` requires "an all-PASS scoped run yields PASS". A run with 12 unevaluated axes then prints `PASS`. `.claude/rules/security.md` MUST-7 forbids exactly that shape. `review/SKILL.md:92` already has `PARTIAL`. CWE-390. |
| F8 | P1 | architect, security, independent-thinker, critic | The scoping key is wrong (see the counter-evidence resolution above). Recommended fix, costed on the ADR's own arithmetic: flagged axes plus a fixed safety core of `security` alongside the always-on `spec-compliance`, giving `15 + 4x(1+1+2) + 15 = 46` against 90, a 49% reduction instead of 53%. Four extra axis invocations buys the defect class scoping is worst at. |
| F9 | P1 | architect | The DRY seam does not exist where the ADR puts it. `resolve_axis_set.py` is placed at `.claude/skills/review/scripts/` (a mirror) while the canonical validator at `scripts/validation/` has no sibling `references/` directory. The axis set gets computed in one file and re-derived in another, which is the drift the set-equality rule exists to catch. |
| F10 | P1 | analyst, high-level-advisor | The cost model's central parameter is unmeasured. No source records how many axes flag per fix round. `ADR-094:297-300` concedes the related gap and then ships a rounded "53% reduction" headline built on the unmeasured parameter. |
| F11 | P1 | analyst, independent-thinker, high-level-advisor | Parallel axis execution is dismissed at `ADR-094:150` because it "does not reduce token spend, which is the reported driver". No measurement of `/review` token spend exists in this repository. The dimension the cited incidents actually measure is wall clock and round count, which is what parallelization attacks. The ADR dismisses the only alternative that hits the measured dimension on the authority of an unmeasured one. |
| F12 | P1 | architect, analyst | `decision-makers: []` (`ADR-094:5`). The template requires it. `ADR-094:295` acknowledges the gap; acknowledging does not clear it. No reversibility assessment is present either, and the change is highly reversible, which makes the section cheap and its absence a template regression. |
| F13 | P2 | critic | "Axis invocation" is not a cost unit. The 15 are 12 subagent tasks plus 3 chained skills, and two of the three are deterministic Python runs (`review/SKILL.md:88-89`). The always-on `+1` is `spec-compliance`, a full subagent task. The 53% is a ratio over unlike things. |
| F14 | P2 | critic | The set-equality rule discovers its axis set from `references/*.md` at validation time, so the day a twelfth Stage-2 axis file lands, every unmerged branch's previously valid marker fails `/ship` with no code change on those branches. |
| F15 | P2 | architect, independent-thinker | Internal contradiction. `ADR-094:168-170` rejects the sub-loop doctrine because "prose cannot be gated", then answers its own Negative 3 with a `(scoped:)` suffix and a 15-row table, which is prose. Contract changes 4 and 9 also put `--axes` parsing and the marker prohibition in an LLM-executed `SKILL.md`. |
| F16 | P2 | critic, independent-thinker | Two unsourced claims. "The plugin keeps losing installs" (`ADR-094:151`) has no citation anywhere. `ADR-094:193` cites `review/SKILL.md:47-49` for three chained-skill names; those lines name only two, and `code-qualities-assessment` is invoked at `:87` with no path-resolution bullet. |
| F17 | P2 | architect | Test-tree split. Existing validator tests live at `tests/validation/test_validate_review_marker.py` and `tests/validation_pre_pr/test_review_marker.py`. `ADR-094:223` puts the new marker tests under `tests/skills/review/`. |

## Verification of the debate's own claims

Two roles produced quantitative findings that the orchestrator re-measured
before recording, per `.claude/rules/canonical-source-mirror.md`. One did not
reproduce.

**Not reproduced.** The critic reported "32 merged PRs carry a `Reviewed-By:
/review@` trailer on `origin/main`, mean 2.22, median 1, max 8" and built its
P0-1 on that distribution. Measured on this branch after `git fetch origin
main`: `origin/main` carries **zero** commits with that trailer, by
`%(trailers:key=Reviewed-By,valueonly)` and by `git merge-base --is-ancestor`
on individual marker commits. All 14 marker commits in the clone sit on
unmerged branch refs (for example `origin/fix/4880-root-context-v2`,
`origin/chore/ruff-e501-wrap-2993`). This repository squash-merges, so the
empty marker commit is discarded at merge and never reaches `main`. The
critic's mean, median, and adoption percentages are therefore not usable and
are not carried into F1.

**The finding survives in a stronger, reproducible form.** 14 marker commits
exist across all refs; none merged. There is no observed instance of the
18-round marker-forced full-re-review workload the ADR prices, on any ref.
That is a sharper statement of F1 than the critic's version, and it is
checkable with one command.

**Reproduced, with corrections.** The independent-thinker's marker census was
directionally right and off in two counts. Measured: 14 trailer commits, of
which **3** name the full 15-axis set (not 4) and **11** name a subset (not
10). **4** name a `code-review` axis for which no `references/code-review.md`
exists; the directory holds 12 files and that is not one of them. The
consequence the independent-thinker drew stands and is the more important half:
`ADR-094:246` claims "`/ship` gate strength is unchanged: a full run is still
the only marker source", and `validate_review_marker.py` parses the axis list
without ever checking membership or completeness, so subset markers already
pass today. That strengthens the case for the validator hardening and weakens
the ADR's "no new risk" framing.

**Reproduced exactly.** The date precedence in F1 (`c3ddc571a` 2026-05-24,
`16c960418` 2026-06-04). The 009 splice in F2 (`:163` 52% over 182 comments,
`:178` 24% over 173 units). The absence of a marker-writer script in F3. The
`references/` inventory: 12 files, 11 Stage-2 axes plus `spec-compliance`, and
the three chained skill names at `review/SKILL.md:87-89`.

## Zimmermann anti-pattern check

No role produced a Pass Through: all six returned substantive architectural
findings with file and line citations. No role produced a Copy Edit: no
finding in the P0 or P1 set is editorial. One Groundhog Day risk was avoided
because the debate ran a single round. The critic's Self Promotion risk was
checked by re-measuring its central number, which is what caught the
non-reproducing distribution above.

## Recommendations to the maintainer

The ADR keeps `status: proposed`. This log is the evidence for the acceptance
decision, not an acceptance.

Blocking before any acceptance:

1. Re-cite or relabel the cost section (F1). The three incidents predate the
   mechanism. Move `18 x 15 = 270` out of a heading that says "measured" and
   mark it a projection, or replace it with a measurement of the current
   system.
2. Fix the 24% splice (F2). The same source reports 52% over the count the ADR
   quotes. Drop the row or cite it correctly.
3. Make the marker prohibition a code path (F3). Add a marker-writer script
   that refuses to write unless the axis set that ran equals the discovered
   set, and have `review/SKILL.md` call it instead of raw
   `git commit --allow-empty`. Delete or rewrite `ADR-094:236-237`, which tells
   the approving maintainer a claim is proven when the named test cannot reach
   it.
4. Retarget every validator change to `scripts/validation/` and record the
   three copies, the `SYNC_FILE_PAIRS` entry, and the packaging test (F4).
5. Add `git_hook_policy.py` and `checks_coverage.py` to the impact table with
   their real blast radius (F5).

Strongly recommended before implementation:

6. Adopt flagged axes plus a `security` safety core, or reject it in writing
   with reasoning (F8). Cost is 4 axis invocations.
7. Sequence the `validate_review_marker.py` hardening as its own change,
   landing before the flag (independent-thinker). It closes a hole that is live
   now: 11 of 14 markers would be rejected today, 4 of them naming an axis that
   does not exist. Its rejection log then produces the per-axis dataset that
   `ADR-094:297-300` says does not exist, which makes the flag's cost case
   falsifiable instead of asserted.
8. Weigh parallel axis execution against this ADR rather than beside it (F11).
   It attacks the only dimension anyone has measured, needs no contract change,
   and loses no coverage.

## Recorded dissent

**high-level-advisor, Disagree and Commit.** The priority is wrong. The ADR
targets cost-per-round while the measured pain is rounds and hours. The ADR
itself names two higher-value levers, parallel execution at `:150` and
per-axis signal measurement at `:297-300`, and defers both to ship the third.
On evidence where the full fan-out caught a defect that 26 unit tests and every
scoped signal missed, the correct direction is to make the full run faster and
universal, not optional and narrower. Also: a hardened marker validator that
requires exact set equality on an LLM-emitted 15-name list, on the critical
ship path, is the single change this role would refuse. It should warn, not
exit 1.

**critic, standing dissent.** If re-measurement shrinks the win to a tail
optimization, descope or defer. Never soften the marker rule to make the
numbers look better.

**independent-thinker, recorded prediction with its falsifier.** Per-axis
signal, not per-round scope, is the real lever, and the right move is dropping
two or three axes rather than scoping fifteen. This is wrong if a rejection log
shows scoped-run demand above roughly one per PR with a stable axis cluster,
which would mean callers know their scope and the flag earns its two
invocation modes.

**architect, recorded sequencing preference.** Measure first, scope second. Not
a block, because the flag is cheap to delete and the measurement does not exist
yet.

## What the debate did not do

It did not evaluate the `--axes` implementation, which was never built. It did
not rewrite the ADR: the maintainer took the findings and rejected the proposal
instead, and the ADR was renumbered to 095 and rewritten as a rejection record
in that same decision.

## What outlived the rejection

Two items here are not about ADR-095 and should not be discarded with it.

1. `validate_review_marker.py` accepts a subset axis list today. 14
   `Reviewed-By: /review@` marker commits exist across all refs; 3 name the
   full 15-axis set, 11 name a subset, and 4 of those name a `code-review` axis
   for which no `references/code-review.md` exists. The validator parses the
   list and never checks membership or completeness. This is a gap in the
   shipped gate, independent of the rejected proposal, and wants its own issue.
2. The re-measurement discipline in the verification section above. One role's
   headline number did not reproduce and was caught only because it was
   re-measured before it entered a committed artifact.
