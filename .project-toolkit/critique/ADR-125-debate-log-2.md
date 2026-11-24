# ADR-125 debate log 2

Prior debate log: [ADR-125 debate log](ADR-125-debate-log.md).
Claims ledger: [ADR-125 claims ledger](ADR-125-claims-ledger.md), section "Amendment 2026-11-24 claims".
Scope: the section "Amendment 2026-11-24" and its code in issue #7525.
The panel is the full six seats, because the change alters validator exit behavior.

## Round 1

Votes: architect, critic, independent-thinker, analyst, and high-level-advisor voted Disagree-and-Commit.
Security voted Block.

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Security | P0 | A branch could add a folder named like a third-party package, so `import yaml` read as first-party. | A root the scanner loads from site-packages is always third-party. First-party also needs a tracked `.py` file. A decoy test covers three shapes. |
| Security, architect, advisor, critic | P2 | Any folder counted as a package, so `import build` read as first-party. | A match needs a tracked `<root>.py` or `<root>/__init__.py`. Tested. |
| Independent-thinker | P2 | The check read the working tree, so untracked folders changed verdicts. | Matches come from `git ls-files`. An untracked module test covers it. |
| Independent-thinker, critic | P2 | Net duplicate counts let a new duplicate replace a removed one. | Each line's repeat count must not grow. A swap test covers it. |
| Architect, advisor | P1 | The non-redundancy admission is on for all consumers, and the ADR did not say so. | Change item 1 and Consequences now say so, and say how to reverse it. |
| Architect | P1 | The amendment did not relate itself to ADR-122's rejection of a generic exception framework. | New section "Relation to ADR-122". |
| Critic, independent-thinker | P1 | Unbounded first-party growth passes as WARN; same-root third-party growth too. | Kept as an accepted trade, now stated in Consequences, including namespace roots. A cap was rejected: it reintroduces a tolerance band. |
| Independent-thinker | P1 | A shipped file can import an upstream-only first-party module and pass. | Deferred: plugin self-containment gates own that defect, not this score. Recorded here. |
| Critic | P1 | No test proved Python-only coverage. | A TypeScript test now exits 10. The `ast` parse also rejects TypeScript, so the explicit language guard is not separately discriminated. |
| Analyst | P1 | The Alternatives row said every residual row imported a branch helper; one adds `yaml`. | Row corrected. |
| Analyst | P1 | The #7047 citation pointed at the wrong change. | Now cites PR #7051, which added the quoted text while fixing #7047. Ledger row shows `git log -S`. |
| Advisor, architect | P2 | The consolidation branch still needs one owner approval. | Stated in the Change section. Row-bound approval is listed as an alternative, tracked in #7525. |
| Architect, advisor | P2 | No reversibility statement or revisit trigger. | Added to Consequences. |
| Critic | P2 | A test was missing for one admitted file beside one unadmitted file. | Added; exit 10 and adapter FAIL. |
| Critic | P2 | The ledger mixed code lines with compared lines. | Ledger row now gives both measures. |
| Independent-thinker | P2 | Base imports resolve against the head tree. | Stated in Consequences as a known limit. |

Round 1 did not reach consensus because of the security Block.

## Round 2

The round 1 fixes landed in the code and the amendment text.
Votes: architect, critic, security, analyst, and high-level-advisor voted Accept.
Independent-thinker voted Disagree-and-Commit.

| Seat | Priority | Finding | Resolution |
| --- | --- | --- | --- |
| Architect | P2 | Item 3 overclaimed: an uninstalled dependency can be shadowed by a tracked package. | Item 3 now limits the claim to installed packages and names the residual case. |
| Critic, security | P2 | The adapter checks duplicate totals, not the per-line rule. | The ADR now says the assessor enforces the per-line rule. |
| Security | P2 | A committed `<name>/__init__.py` can shadow an uninstalled package. | Accepted risk; the decoy is a tracked Python package in the reviewed diff. |
| Advisor | P2 | A namespace package without `__init__.py` reads as third-party. | Accepted; it fails toward blocking. |
| Advisor | P2 | Results depend on the scanner's installed packages. | Accepted; the approval verifier uses its pinned environment. |
| Analyst | P2 | The 131-line and +36-line counts were not independently re-run by the seat. | Both rest on the author's AST and line-count replay in the ledger. |

Dissent (independent-thinker): a shipped lib file that adds `import scripts.x` is admitted here.
Of the three portability gates the seat searched, none parses import statements.
That gap has no owner gate today; it is recorded for the user's decision, not fixed here.

Consensus reached in round 2. The ADR status stays `accepted`; this debate covers only the amendment.

## Post-consensus wording edit

The doc-accuracy axis (rule R3) flagged Change item 4 against `assess.py`.
Item 4 now reads "Each admitted row's record is stored under `change_admissions`".
The local variable that fills the field is now `records`.
The meaning is unchanged, so no new round was opened.

## Post-review wording edits

The `/review` axes on head `44f7f2fa53` raised wording findings on the amendment.
The edits below change no decision, so no new round was opened.

- The #7512 and #7528 counts are now attributed to issue #7525 and the owner.
- Consequences now say a non-redundancy drop of any size passes when no line gained a copy.
- The revisit trigger names its record: a comment on issue #7525.
- Consequences now say the evidence base is one branch.

The same review fixed two adapter gaps in code: a record for an unadmittable quality, and non-string regression names.
Both now return UNKNOWN, with tests.

## Round 2 review wording edits

The `/review` round 2 decision-rigor axis on head `cf3d852f8e` raised four wording findings.
The edits below change no decision, so no new round was opened.

- The "Why" section now quotes the original revisit trigger and names both re-pin causes.
- The scope sentence now lists the config key and the JSON field, not only exit behavior.
- Alternatives now cover an opt-in non-redundancy admission and a ratio-score fix.
- Consequences now give the reason for the opt-in asymmetry and name the upstream-only import gap.
- The scope sentence now names the first decision in words, so the doc-accuracy count rule reads its three items correctly.

## PR #7535 review wording edit

Devin Review on PR #7535 found that a staged but uncommitted helper counted as first-party.
The assessor now reads the HEAD commit tree, not the index.
Change item 3 now says "the HEAD commit holds" in place of "the index tracks".
The rule is narrower and the decision is unchanged, so no new round was opened.

## Merge with PR #7523

PR #7523 landed on main with its own `changeAdmissions` records (ADR-122 item 10, issue #7493).
Those records use the JSON field `change_admissions`, which this amendment had also used.
This amendment's field is now `rule_admissions`, and its reference page is `rule-admissions.md`.
Change item 4 now names `rule_admissions`. The decision is unchanged, so no new round was opened.
