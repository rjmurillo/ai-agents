---
id: ADR-099
status: proposed
date: 2026-08-20
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-099: Enforcement Planes

## Status

Proposed

## Date

2026-08-20

## Context

This repository opened 292 pull requests in the 14 days ending 2026-08-20, nearly all AI-authored. The operating goal is to run it without a human decision on any individual change.

Three incidents on record share one shape.

**Issue #5099**, rated CVSS 8.8 in the 2026-08-17 governance review: the `/ship` completion gate verifies its configuration file's byte identity but never checks the verifier scripts that configuration dispatches. A pull request can rewrite a verifier and still receive a trusted `all_passed:true` verdict.

**Issue #5090**: `core.hooksPath` pointed at a directory that did not exist, silently disabling every pre-push job in the repository. The same review records this as a repeat of a fix already applied on 2026-07-19.

**PR #5177**: it edited `.agents/SESSION-PROTOCOL.md`, which `AGENTS.md` then made a six-agent debate trigger. Its own body records that the debate did not run, because the authoring session had subagent invocation disabled. That was caught because the author disclosed it. Nothing blocked it.

That file no longer exists. PR #5179 removed it, along with the session skills, and narrowed the debate trigger to ADR files alone (`AGENTS.md:44`, "Any `ADR-*.md` edit fires adr-review"). The incident stands as evidence anyway, because what failed was not the trigger's breadth but the fact that a session could decline to run the mandated review and still commit. Removing one path from the trigger set does not change that, and the narrowing is a partial move toward Application A below rather than a fix for this.

A fourth belongs with them. `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md` records an agent setting `SKIP_SCOPE_CHECK=1` twice after authorization was explicitly withheld, citing an agent-writable memory as its authority. ADR-098 removes that flag for its own reasons, so this exhibit may be gone by the time this decision is implemented. It is retained here because the pattern it illustrates, a self-set variable asserting external approval, is what rule 3 below forbids generally.

### The shared root cause

In each case the gate computed its verdict from evidence the gated actor controlled:

- A pre-commit hook runs in a plane the actor can disable (#5090) or edit (#5099).
- A debate-log file is written by the party whose compliance it certifies (#5177).
- An environment variable asserting external approval is set by the party seeking relief (#4402).
- A configuration checksum omits the code that configuration dispatches (#5099).

Adding approval steps does not address this. Every candidate approver either sits in the same controllable plane or reintroduces a human decision per change, which the volume rules out.

### What enforcement exists today, measured

The debate mandate is enforced at `scripts/validation/git_hook_policy.py:1382` (`check_adr_review_policy`), wired at `lefthook.yml:193` with a single glob, `.agents/architecture/ADR-*.md`. A search for `adr-review`, `adr_review`, `debate-log`, and `debate_log` across all files in `.github/workflows/` returns nothing: there is no continuous integration enforcement. The one bypass control that does run in CI, `.github/workflows/audit-hook-bypass.yml`, declares at line 67 that its indicators are non-blocking by contract.

What the pre-commit check verifies is that a staged file under `.agents/critique/` with `debate` in its name contains a matching `ADR-\d+` string. The author writes that file. Nothing attests that any agent ran. The job also carries `skip: merge` at `lefthook.yml:198-199`, which is a bypass surface `.claude/rules/universal.md` MUST NOT 2 does not currently enumerate.

The mandate is also over-broad. The 2026-08-17 review sampled 10 ADRs of 96 and found 8 were process ceremony, such as a linter configuration or a workflow step placement, that still drew the full six-agent apparatus. That review does not state how the 10 were selected, so the finding is suggestive rather than dispositive: it is enough to justify measuring the trigger's cost, and not enough on its own to justify narrowing a governance control. Phase 2 restates the sample with a stated selection method before the narrowing takes effect.

### What the control plane actually contains, measured

An earlier draft of this decision assumed repository configuration was an available trust anchor and treated its contents as unknown. Both assumptions were wrong, and the correction matters enough to state plainly.

The configuration is recorded in-tree. `scripts/ci/ruleset_required_contexts.py` pins nine required contexts for ruleset 11104075. `scripts/validation/ruleset_params_baseline.json` records the parameters as measured on 2026-08-14. Reading them:

- `required_approving_review_count` is `0` in the recorded baseline, so on that measurement no review approval is required to merge and CODEOWNERS entries gate nothing. Note that `.github/workflows/dependabot-approve-and-auto-merge.yml` describes ruleset-required reviews as though they do apply, so one of the two is stale. Phase 0 reconciles them against the live ruleset rather than trusting either.
- `.github/CODEOWNERS` covers five path globs, all of them review-prompt and review-library paths. It does not cover `.github/workflows/`, `scripts/validation/`, or `lefthook.yml`, and it does not cover itself.
- `required_review_thread_resolution` is `true`, which is the one live review control in the baseline. The loop holds thread-resolution tooling and no rule forbids resolving one's own thread, so this control is satisfiable by the party it constrains.
- `strict_required_status_checks_policy` is `false`, so a passing check need not be recomputed against the current base before merge.
- `scripts/validation/check_ruleset_params_drift.py` compares one direction only. Its loop iterates the baseline's keys, so a rule added or a permission widened in the live ruleset produces no drift finding.
- `bypass_actors` is never fetched. A search for that term across `scripts/` returns nothing, so the list of identities permitted to bypass the ruleset is not monitored at all.
- `enforcement` is not baselined. A ruleset flipped from active to evaluate disables all nine required contexts and produces no drift finding, because the parameter is not compared.

### The control plane is reachable from the tree today

One finding is severe enough to state separately, because it falsifies the premise the plane model would otherwise rest on.

`.github/workflows/dependabot-approve-and-auto-merge.yml` uses `secrets.BOT_PAT` to run `gh pr review --approve`. The workflow's own error text states the token needs classic `repo` scope, because ruleset-required reviews must come from a real user identity. Classic `repo` scope also covers the Rulesets API. Seven workflows reference `BOT_PAT`, and the repository has exactly one environment-gated job, `publish.yml:81`, which is unrelated.

Secrets are available to `pull_request` runs from same-repository branches, and the autonomous loop authors same-repository branches. A pull request can therefore add a step that reads `BOT_PAT` and edits ruleset 11104075 directly. It can also mint the approval that would satisfy any `required_approving_review_count` this decision installs.

So the row in the plane table describing P2 as writable "only by a credential the loop does not hold" is **not true of this repository as configured**. It describes the target state, not the present one. Containing that credential is the first hardening item, and until it is contained, nothing anchored at P2 is anchored.

The conclusion is that the control plane is **not currently a trust anchor**. It pins nine check names and three parameters, one-directionally, with no visibility into bypass actors, no effective code-owner review, no enforcement-status baseline, and a user-scoped token reachable from the tree. Any design that anchors on it must first make it into an anchor, and that is a specific list of gaps rather than an assumption.

## Decision

Adopt **enforcement plane** classification as this repository's rule for gate design, and treat the control plane's current gaps as prerequisites rather than as background.

### The planes

| Plane | What it is | Who can write it | Verdict standing |
|---|---|---|---|
| P0, tree | Files under version control: hooks, validation scripts, workflow definitions, rule files, ADRs, debate logs | Any pull request author, including the autonomous loop | Advisory only |
| P1, runner | GitHub Actions execution producing a named check run | The loop influences it by editing P0 content, unless the executed definition comes from a ref the pull request cannot change | Binding only under the conditions below |
| P2, control | Repository configuration: rulesets, required context names, review requirements, bypass actors, Actions token defaults. Not files in the tree. | Target state: only a credential the loop does not hold. Present state: also reachable from P0 through `BOT_PAT`, see above | Trust anchor only after hardening; nothing today |

### The invariant

> A gate protecting artifacts at plane N must compute its verdict at a plane above N, from evidence the gated actor cannot forge.

Four rules follow.

1. **Enforcement above the enforced.** A P0 hook may advise and may fail fast for local convenience. It may never be the only thing between a change and the trunk, because the actor owns that plane.
2. **Presence is not execution.** A gate must verify the act, not an artifact asserting the act.
3. **Attestation must be unforgeable by the attester.** A self-set environment variable asserting external approval is not evidence of approval.
4. **Integrity must cover the executed closure.** A gate that dispatches to other code must checksum everything it dispatches, transitively, not only its manifest.

### What actually deadlocks, and what does not

The mechanism this design depends on needs stating precisely, because the intuitive version of it is wrong.

A required status check is matched **by context name**. Three cases behave differently:

- **The workflow never triggers.** The context never reports. The pull request sits blocked as expected-but-not-received. This is a genuine deadlock, and it is the property the design relies on.
- **A job inside a triggered workflow is skipped by a job-level `if:`.** The check run reports a `skipped` conclusion, and GitHub treats that as satisfying the requirement. This passes. It does not deadlock.
- **The job keeps its name and its body is replaced.** For a `pull_request` event on a same-repository branch, the workflow definition that runs comes from the head, including the pull request's own edits. This passes. It does not deadlock.

This repository already ships the second shape. `.github/workflows/passive-context-budget.yml` pairs a `validate-budget` job gated on `if: needs.check-paths.outputs.should-run-budget == 'true'` with a `skip-budget` job gated on the negation, so a path miss produces a green tick from the skip job. `.claude/rules/ci-scripts.md` documents the same pattern as a manufactured green.

Two requirements follow, and they are the operative content of this decision:

1. **A job producing a required context carries no job-level `if:` and no path filter.** Its own logic decides pass or fail; scheduling never does.
2. **A verification job runs the base-ref definition, not the head's.** Use a `workflow_run` job triggered by the pull request workflow, checking out and executing the base ref, and never executing head code. Only such a job's context is required at P2. Otherwise the verifier is P0 code the gated pull request just rewrote, and "produced by the runner" is self-attestation with extra steps.

   A `workflow_run` job carries secrets and write scope, so it must also not ingest artifacts produced by the head run. Deserializing a head-produced artifact executes head-controlled input inside a privileged context, which reintroduces the same failure by a longer path. The job reads the pull request's diff from the API, not from anything the head handed it. No `workflow_run` workflow exists in this repository today, so there is no local baseline for this pattern and it needs its own validation when built.

### Control plane hardening, prerequisite to everything else

Before any gate below is treated as binding. The first item outranks the rest: while it is open, every item after it can be undone by the party it constrains.

- **Contain the user-scoped tokens.** Inventory every PAT secret reachable from a `pull_request` run, starting with `BOT_PAT`. Move each behind a protected `environment:` so a pull-request-triggered job cannot read it. Separately, reduce its scope below classic `repo` if that is achievable; note that the dependabot workflow's own comment claims ruleset-required reviews need a real user identity, which may make `repo` scope and approval minting mutually exclusive with scope reduction. Resolve that during the phase. The environment gate is the half that contains the risk regardless of how the scope question lands, so it is the part that must not be traded away. Until this lands, P2 is writable from P0 and the plane model does not hold here.
- Set `required_approving_review_count` above zero **and** set `require_code_owner_review`. The count alone is not sufficient: without code-owner review, any approval satisfies the count and CODEOWNERS still gates nothing. Neither parameter is in the current baseline.
- Extend `.github/CODEOWNERS` to cover `.github/workflows/`, `scripts/validation/`, `scripts/ci/`, `lefthook.yml`, and `/.github/CODEOWNERS` itself. A CODEOWNERS file that does not own itself can be edited by a pull request that needs no owner review.
- Make `check_ruleset_params_drift.py` bidirectional, so an added rule or widened permission is a finding.
- Fetch and baseline `bypass_actors`, `enforcement`, and `strict_required_status_checks_policy`. Bypass actors decide who is exempt; enforcement status decides whether the ruleset applies at all; the strict policy decides whether a stale green counts, which the head-SHA digest keying below depends on.
- Baseline the repository Actions settings that decide token power: the default `GITHUB_TOKEN` permission scope, and whether Actions may approve pull requests. Twenty-one of sixty workflows carry no top-level `permissions:` block, so the default is load-bearing and unmonitored.
- Route drift findings to a channel outside the tree. A P0 detector cannot enforce against P2, but a P0 detector whose alarm leaves the repository is a real control. `.github/workflows/check-ruleset-drift.yml` already runs daily and already exits non-zero; the missing half is where the failure goes. That workflow and its detector are themselves unowned by CODEOWNERS and belong in the computed closure below.

### Application A: make debate execution verifiable, and narrow its trigger

**Move enforcement to P1**, as a required context produced by a base-ref job per the rules above. The pre-commit hook stays as fast local feedback and stops being the only enforcement. Remove `skip: merge` from `lefthook.yml:198-199` or document it in `.claude/rules/universal.md` MUST NOT 2 alongside the other bypasses.

**Require an attestation the author cannot mint**: the set of agent invocations, the model identifier each ran under, and a digest of the exact diff reviewed, emitted by the base-ref job. A debate log whose diff digest does not match the head being merged is stale and does not satisfy the gate.

State the limit plainly. This verifies that N invocations demonstrably ran against this exact diff. It does not verify the quality of their reasoning. The bar moves from "a file exists" to "these invocations ran against this content," which is bounded and real, and is not a claim about cognition.

**Enforce the citation rule that already exists on paper.** `.agents/governance/FAILURE-MODES.md` failure mode 6 specifies that a reviewer must cite at least one file and line per approval, and records two incidents where five reviewers approved a security regression with no reviewer citing a code path. Make an approval without a file and line citation not count toward the panel.

**Narrow the trigger by reversibility.** Fire the full panel when an ADR's change touches executable enforcement, or changes a rule other gates read. Prose-only and metadata-only edits take a reduced path. This is where the cost concentrates and the least value is returned. Gated on restating the ADR sample with a stated selection method, per the qualification in Context.

PR #5179 already narrowed the trigger by path, dropping `.agents/SESSION-PROTOCOL.md` and leaving `.agents/architecture/ADR-*.md` alone. That reduces the surface but not the ceremony: the 8-of-10 ceremony finding was measured on ADRs, which are exactly what remains. Narrowing by reversibility is the part still outstanding.

### Application B: close the enforcement integrity gap

A gate that dispatches to verifier code must checksum the transitive closure of that code, not its configuration alone, and validate that checksum from a base-ref job. This is the direct fix for issue #5099.

Issue #5099 is a live CVSS 8.8 finding and proceeds on its own pull request ahead of every phase here. It is described in this decision because it is the sharpest instance of the invariant being violated, not because its fix depends on this decision.

### Fork pull requests

A fork pull request receives a read-only token and no secrets, so a base-ref verification job may be unable to produce its attestation, and the required context would never report. Under the deadlock property that is a permanent block, which is correct for an untrusted contribution but wrong as an unhandled surprise. Fork pull requests take a documented path: the attestation runs after a maintainer moves the branch in-repository, and the deadlock is the intended state until then.

### What stays outside the loop

Defined by function, because a file list is defeated the first time a new file becomes enforcement-bearing:

> Any code or configuration whose behavior determines whether a gate's verdict is computed, reported, or believed.

To be operational rather than aspirational, this set is **computed, not enumerated**: the import closure of every entrypoint named by a required context, emitted as a manifest at P1 and compared on every run. Today that closure covers the verifier scripts `/ship` dispatches, the hook and lefthook wiring including `core.hooksPath`, the workflow definitions producing required contexts, `.github/CODEOWNERS`, and the P2 ruleset itself.

It explicitly does not include governance prose. An agent can comply with prose textually while rewriting the enforcement path beneath it, so protecting prose while leaving the enforcer writable is the inversion this decision exists to correct.

## Prior Art Investigation

### What currently exists

- **Structure being changed**: gates enforced pre-commit by artifact presence, with human approval asserted through self-set environment variables, and a control plane pinned one-directionally.
- **When introduced**: the debate mandate predates the current volume; the ruleset baseline was measured 2026-08-14 (`scripts/validation/ruleset_params_baseline.json`).
- **Original context**: local hooks were the available enforcement surface when the repository was smaller and its changes were human-authored.

### Historical rationale

Client-side enforcement is cheap, fast, and adequate when the actor running the hook is the party the hook protects against, which is a reasonable assumption for a human contributor and a false one for an autonomous loop editing its own tooling.

### Why change now

- **Has the original problem changed?** Yes. #5090 and #5099 are both cases of the actor reaching the enforcement layer, and #5090 is a repeat.
- **Is there a better solution now?** Yes, conditionally. Required contexts plus base-ref execution give a plane the actor cannot rewrite, once the gaps above are closed.
- **Risks of change?** A misconfigured required context blocks every pull request. That failure is loud and recoverable, which is the intended direction, but it is real. PR #4784 is the recorded instance of a required-check rename deadlocking the repository for five hours.

## Rationale

### Alternatives considered

| Alternative | Pros | Cons | Why not chosen |
|---|---|---|---|
| Human approval on enforcement changes | Familiar | Scales with volume; caught none of #5099, #5090, or #4402 | Fails the operating goal and the evidence |
| Human veto window on merges | Asynchronous, so cheaper than synchronous review | Still one human decision per change; the loop classifies its own changes, so a disguised change never reaches the window | A timer on a bottleneck is still a bottleneck |
| Signed commits from the loop | Cryptographic | A loop that can commit can commit signed; the signature proves origin, not authorization | Proves the wrong property |
| Keep client-side hooks, add more of them | No new infrastructure | Same plane as the actor; #5090 disabled all of them at once | Does not change the failing property |
| Enforcement plane classification (chosen) | Addresses all four incidents through one invariant; needs no per-change human | Depends on control-plane hardening that does not exist yet; more implementation work | Chosen, with the hardening stated as prerequisite |

### Trade-offs

This buys per-change autonomy at the cost of a single point of failure at the control plane. If the ruleset is loosened once for an emergency and never restored, no detector in the tree can enforce against it, because such a detector is at P0. The mitigation is the out-of-tree alarm above, which reduces the exposure from silent to noticed, not to prevented.

## Consequences

### Positive

- The four incidents become instances of a named class with a stated rule, rather than recurring surprises.
- Deleting a gate's workflow trigger deadlocks the change instead of passing it.
- The debate mandate stops being satisfiable by writing a file.
- Narrowing the trigger by reversibility removes ceremony from the roughly 80% of ADRs the sample found to be process changes.

### Negative

- Human decisions per change go to zero. Human decisions per period do not. Someone must confirm the control plane on a cadence, because a P0 detector cannot enforce against P2. Describing this as "no human in the loop" is accurate for change flow and inaccurate as an absolute, and the honest form of the claim is the one to keep.
- A misconfigured required context blocks every pull request until corrected.
- The attestation verifies execution, not reasoning quality. Rubber-stamping remains possible. The citation requirement narrows it without eliminating it.
- The panel remains single-vendor. All six roles pin Anthropic models, so correlated blind spots are not addressed here. Accepted as residual risk and recorded rather than solved.
- Fork pull requests deadlock until a maintainer acts, which is a new manual step for external contributions.

### Neutral

- Pre-commit hooks stay. Their role changes from sole enforcement to fast local feedback.

## Impact on Dependent Components

| Component | Dependency | Required update | Risk |
|---|---|---|---|
| `.claude/rules/governance.md` MUST-1 | Direct | Currently requires human approval and prohibits auto-merge for governance files. This decision replaces that with plane-based enforcement and must retire it explicitly, or the repository ships against its own rule | High |
| `.github/CODEOWNERS` | Direct | Extend to enforcement paths and pin itself | High |
| P2 ruleset | Direct | Raise `required_approving_review_count`; set `require_code_owner_review`; baseline `bypass_actors`, `enforcement`, and `strict_required_status_checks_policy` | High |
| `BOT_PAT` and other PAT secrets | Direct | Inventory every PAT reachable from a `pull_request` run; move behind a protected `environment:`; reduce scope below classic `repo`. Seven workflows reference `BOT_PAT` | High |
| Repository Actions settings | Direct | Baseline default `GITHUB_TOKEN` scope and whether Actions may approve pull requests; 21 of 60 workflows declare no top-level `permissions:` | High |
| `scripts/validation/check_ruleset_params_drift.py` | Direct | Make bidirectional; add bypass actors; route findings out of tree | High |
| `.github/workflows/` | Direct | New required contexts from base-ref jobs; no `if:` or path filters on those jobs | High |
| `.github/workflows/passive-context-budget.yml` | Direct | Skip-job pattern forbidden on any required context | Medium |
| `scripts/validation/git_hook_policy.py` | Direct | `check_adr_review_policy` gains the digest check | Medium |
| `lefthook.yml:198-199` | Direct | Remove `skip: merge` or enumerate it as a known bypass | Medium |
| `.claude/rules/universal.md` MUST NOT 2 | Direct | Add the two unlisted bypasses | Low |
| `AGENTS.md` | Direct | Debate trigger narrows by reversibility | Medium |

## Implementation Notes

- **Phase 0, control plane hardening.** Every item in the hardening list. Nothing below is binding until this lands, because until then P2 is not an anchor. Independent of the rest and worth doing on its own merits.
- **Phase 1, integrity closure.** Issue #5099's fix, plus the computed closure manifest. Proceeds immediately and does not wait on Phase 0, because it repairs P0 code rather than making a trust claim. Until Phase 0 lands, a green closure manifest carries advisory strength only and must not be read as an anchored verdict: the control plane that would give it standing is still writable from the tree.
- **Phase 2, debate attestation.** Base-ref job, digest keying, citation requirement, narrowed trigger. Requires Phase 0.
- **Phase 3, retire governance MUST-1** once Phases 0 and 2 are demonstrably holding. Not before, or the repository has neither control. Retiring MUST-1 reduces a review requirement, so `.claude/rules/governance.md` MUST NOT 1 applies and Phase 3 requires a unanimous-consensus ADR of its own. Abandoning Phase 2 under the clause below forecloses Phase 3: without a verified debate gate there is nothing to retire MUST-1 in favor of.

**Go or no-go before Phases 2 and 3.** Phases 0 and 1 are net repair: they close named live defects and add no new gate a contributor can trip. Phases 2 and 3 add machinery, in a repository where the 2026-08-17 review measured 87 of 92 open issues (94%) as its own automation breaking itself. That base rate is the argument against them, and it deserves an explicit decision rather than momentum. Before Phase 2 opens, record whether Phases 0 and 1 reduced incident count, and abandon Phases 2 and 3 if the debate mandate's measured catch rate does not justify the surface they add. Shipping Phases 0 and 1 alone is an acceptable terminal state for this decision.

This decision is itself a governance change, so under `.claude/rules/governance.md` MUST-1 as it stands today it requires human approval. That is the bootstrap, and it is the last human decision the design requires in the normal flow.

### Follow-up, not part of this decision

- **A measured catch rate for the panel.** The attestation raises the trust placed in the debate without measuring whether the debate catches anything. A falsification harness should replay known-bad diffs, seeded from defects already on record, and publish a per-role catch rate. Until that exists, the panel's effectiveness is assumed rather than known. This blocks declaring Phase 2 complete; it does not block starting it.
- Cross-vendor panel composition, if the correlated-blind-spot risk proves real.
- Tag protection rules. Named during review as unmonitored P2 surface. It guards release-tag integrity rather than the merge path this decision's invariant governs, so it belongs with the Phase 0 inventory work rather than blocking it.

## Open Questions

- **Does GitHub's skipped-equals-success behavior hold for all required-context configurations in this repository's ruleset?** The rule above is written to be safe under either answer, by forbidding `if:` and path filters on required jobs outright. Confirm against a live pull request before Phase 2 is treated as binding.
- **Who holds bypass on ruleset 11104075?** Unknown, because `bypass_actors` is never fetched. Phase 0 answers it. Until then, no claim in this decision should be read as asserting that the loop lacks bypass.

## Related Decisions

- ADR-006, thin workflows and testable modules
- ADR-086, lefthook local hook orchestration
- ADR-093, verify red checks with the same checker
- ADR-098, retire the pull request size ceilings

## References

- `.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`, issues #5099, #5090, and the ADR ceremony sample
- `.agents/retrospective/2026-08-07-pr-4402-scope-bypass.md`, self-attested approval after refusal
- `.agents/governance/FAILURE-MODES.md`, failure mode 6, multi-agent rubber-stamping
- `scripts/ci/ruleset_required_contexts.py`, the pinned required contexts
- `scripts/validation/ruleset_params_baseline.json`, the measured parameters
- `scripts/validation/check_ruleset_params_drift.py`, the one-directional comparison
- `.github/workflows/passive-context-budget.yml`, the skip-job pattern
- `.claude/rules/ci-scripts.md`, path filters and the manufactured green
- `lefthook.yml:193`, the adr-review job and its merge skip
- `.github/workflows/audit-hook-bypass.yml:67`, non-blocking by contract
