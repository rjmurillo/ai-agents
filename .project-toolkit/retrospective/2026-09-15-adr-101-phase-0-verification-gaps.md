# Retrospective: three verification gaps while landing ADR-101 Phase 0

**Date**: 2026-09-15
**Scope**: PRs #5742 (ADR-072 and ADR-101 accepted), #5757 (Phase 0 item 5), #5759 (Phase 0 items 1 and 2), issue #5244
**Failure mode classification**: #10 Silent defaults and guard-clause suppression, #9 Confident-incorrectness recurrence, and #4 False completion markers (`.agents/governance/FAILURE-MODES.md` lines 28, 27 and 22)

## What happened

Three records reached `accepted` and three PRs were opened. The work itself held up. Three separate verification steps did not, and all three share one shape: the thing I checked was narrower than the claim I made about it.

1. **Pipe-masked exit codes, twice.** Running the new ruleset drift checker against live negative controls, I printed `exit=$?` after piping its output through `grep`, so the shell reported grep's status. All three drift cases printed `exit=0` while actually exiting 1. Later, a backgrounded `git push` was reported to me as "exit code 0" because the command ended in `tail`; the push had in fact been rejected by the `retrospective-policy` pre-push gate. The first was caught by re-running without a pipe, the second by comparing `git rev-parse HEAD` against `git ls-remote`. Neither was caught by reading the exit code, which was the thing I had written the check to read.

2. **An incomplete migration inventory.** PR #5759 adds `environment: bot-secrets` to every job reaching `secrets.BOT_PAT`, so those jobs keep working once the secret moves into an environment. I had also told the repository owner to move `COPILOT_GITHUB_TOKEN` into the same environment, but I never enumerated that token's consumers. `nightly-cli-smoke.yml` reads it at lines 143 and 159 and had no stanza, so all three matrix legs would have run the real-CLI tests unauthenticated the moment the repository-level copy was deleted. Devin Review found it. No gate in this repository would have.

3. **A confident claim about a tool that does not run here.** I wrote in the PR description that workflow-schema validation "gets its first real exercise in CI on this PR" because `actionlint` was not installable locally. `actionlint` does not run in CI either. `pr-validation.yml` lines 209 to 213 record that as a deliberate supply-chain decision under issue #3330, and `scripts/validate_workflows.py` is the replacement. I asserted the absence of coverage without searching for what replaced it.

Separately, and not a failure: `Validate Spec Coverage` was found returning `CRITICAL_FAIL` on both sub-checks across #5742, #5757 and #5759 while its check run concluded `success` every time, because `.github/scripts/check_spec_failures.py` lines 84 to 97 treat an infrastructure-flagged failure as a skip. It was one of nine pinned required contexts. That discovery is what motivated unpinning it from ruleset 11104075.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Nightly smoke | High if unfixed | Three matrix legs would have run unauthenticated after the secret migration, failing as a broken smoke rather than a missing secret |
| Merge gating | Medium | A required context returned no signal on three consecutive PRs while reporting green |
| Own verification | Medium | Two exit-code reads reported the opposite of the truth; one shipped in a PR description as a false coverage claim |
| Delivered code | None | No defect reached `main`; #5742 and #5757 merged green and the nightly gap was fixed before #5759 merged |

## Root cause (five whys)

1. Why did the exit codes read wrong? The status came from the last command in a pipeline, not from the program under test.
2. Why was that not noticed? The printed number was plausible, and a plausible number reads as a measurement rather than as an artifact of how it was captured.
3. Why was the inventory incomplete? It was scoped to the secret named in the task (`BOT_PAT`) rather than to the set of secrets the migration actually moves, which I had myself widened to two a few messages earlier.
4. Why was the actionlint claim wrong? I verified that the tool was unavailable locally and inferred the consequence for CI instead of searching for how the repository covers that concern.
5. Why do all three look alike? Each verified the narrow thing in front of me and then reported a wider claim. The gap between the two was never itself checked.

Root cause: **the scope of the check was set by the artifact I was touching, while the scope of the claim was set by the consequence I was describing, and nothing reconciled the two.**

## Remediation

- [x] Exit codes on every gate in this session are now read without a pipe, and both PR descriptions state that explicitly so a reader can tell which method produced the number.
- [x] `nightly-cli-smoke.yml` gated in `6807d8f06`. Coverage is now computed by a script that walks every workflow job reaching either secret, directly or through a workflow-level `env` block, rather than hand-listed: 12 jobs across 7 workflows, zero uncovered.
- [x] The `actionlint` claim was corrected in the #5759 description before merge, naming `pr-validation.yml:209-213` and `scripts/validate_workflows.py`, and the replacement gate was run locally with a negative control (a duplicate `environment:` key makes it exit 1).
- [ ] Candidate rule addition: when a change describes a consequence for a set (every consumer of X, every caller of Y), compute the set and paste the computation, rather than enumerating members by hand. Owner: this session's operator; candidate for `.claude/rules/ci-scripts.md`, which already carries the related "diff violations on (file, rule) identity" item.
- [ ] `.project-toolkit/architecture/ADR-101-enforcement-planes.md` lines 408 and 425 say "six of the nine pinned required contexts" and are now six of eight. Left alone deliberately: any ADR edit fires the mandatory review panel.

## Learning

The 2026-09-11 retrospective recorded a chained command masking a red test, and remediation item three there proposed never chaining a gate into `tail` before acting on it. That item was still unchecked, and the same shape recurred twice in this session, once in a hand-written verification and once in tooling output I did not author. A remediation that lives only as an unchecked box in a retrospective is not a control.

The more useful signal is where the real bug came from. Every gate in this repository passed on #5759, including the full 7730-test suite, `build_all --check`, `pre_pr.py`, and the workflow validator. The defect was found by an external reviewer reading the diff for intent. Three review surfaces had been dark for days (Codex and Cursor Bugbot on usage limits, spec validation fail-opening), and the first PR that got a real review produced a real finding within three minutes. Green checks measured what they were built to measure; they could not measure a set I had failed to enumerate.
