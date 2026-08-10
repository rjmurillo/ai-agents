---
id: ADR-093
status: proposed
date: 2026-08-07
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-093: A local run clears a red remote check only when it is the same checker

## Status

Proposed

## Date

2026-08-07

## Context

On PR #4701, the customer-facing fix for issue #4672, the
`semgrep-cloud-platform/scan` check was red. I ran semgrep locally, saw zero
findings, and published a comment on the pull request stating that the red was
unrelated pre-existing noise in a file the branch merely touched, and that it
could be disregarded.

That was wrong in a way that took a user challenge to surface.

The local invocation was `semgrep --config=auto`. The CI check is the Semgrep
Cloud App running a server-side rule set, and this repository ships no semgrep
configuration file for a CLI to read. The two runs therefore evaluated
different rule sets, and a clean result from one said nothing about the other.

Both findings were real:

- A taint reaching a `subprocess.CompletedProcess` constructor. Fixing it
  surfaced an adjacent defect: a URL parse that derived `github.com/owner` from
  a remote naming no repository, which would have queried the wrong repository.
- A `compile()` call on file content, which produced an executable code object
  from a path taken as a parameter.

The failure mode is what makes this worth a rule rather than a memory. The
output of the wrong tool is indistinguishable from the output of the right one:
both say zero findings, in the same format, with the same exit code. Nothing in
the local run announces that it evaluated a different contract. And the
consequence is not a private mistake. It is a published instruction to a human
reader to ignore a live security finding, which is strictly worse than saying
nothing.

## Decision

Add one MUST to `.claude/rules/universal.md`, which is always-on:

> **Verify a red remote check with equivalent evidence, or report it
> unreproduced.** MUST NOT claim a red remote check is cleared by a local run
> unless the checker, ruleset, flags, and version are demonstrably identical.
> State the command and
> why it is the same check; if you cannot, say the check is red and you could
> not reproduce it. A different tool produces evidence about a different check,
> and calling that "resolved" tells the reader to disregard a live finding.

The repository-specific semgrep facts go to `.agents/governance/GOTCHAS.md`
rather than into the rule: which rule set CI actually runs, that findings
arrive as pull request review comments while the check run itself carries no
annotations or output text, that `p/security-audit` gets closer than `auto` but
remains a guess, and that the `security-suppressions-staged` hook forbids the
obvious escape.

## Alternatives Considered

**Three rules rather than one.** The first draft added two more: that when one
pull request is red and its siblings are green the cause is in your own diff,
and that GitHub list endpoints must be paginated with duplicate check names
reduced by best outcome. Adversarial review recommended cutting both, and was
right on both counts.

The sibling-comparison rule was a general debugging heuristic any competent
reader already applies, so it failed the admission test for always-on bytes.
Worse, its own cited evidence was false. I wrote that a sibling pull request
modified "the same file at the same lines" and passed, and the hunk headers
show #4723 touching lines 542, 904, and 928 while #4701 touched 721. I had
published an unverified claim inside the rule written to stop me publishing
unverified claims, which is a stronger argument for cutting it than any
byte-budget argument.

The pagination rule is a fact you look up while doing the thing rather than
judgment that must bind every turn. It lives in the Serena memory
`git/github-api-lists-truncate-at-per-page-and-dedup-must-take-best`.

**A CI-side fix, so the check becomes locally reproducible.** Raised in review
and not considered in the first draft, which was a real gap: an alternative
that removes a failure mode beats one that documents it, and it costs zero
always-on bytes.

Checking it changed the advice. `semgrep ci`, when logged in, runs the rules
configured on Semgrep App rather than a pack named on the command line, so
`SEMGREP_APP_TOKEN=<token> semgrep ci` is an exact reproduction. The check is
locally reproducible after all, and the GOTCHAS entry now says so instead of
claiming it cannot be.

That weakens the case for this rule on semgrep specifically and does not remove
it. A token is required, so the reproduction is unavailable to anyone without
one, and the rule governs every remote checker rather than this one. The
narrower reading is that the rule now has a documented way to be satisfied
rather than only a way to be admitted, which is a better rule than the one
first proposed.

**A memory instead of a rule.** Rejected for the surviving item. A memory is
retrieved when someone thinks to look, and the failure here is precisely that
the agent does not know it needs to look: the local run appears to have
answered the question. The rule has to be present at the moment the claim is
written.

**Nothing, on the grounds that the model should know better.** Rejected on
evidence. The model in question was me, the reasoning felt sound at the time,
and it took a user saying "I don't buy it" to reopen it.

## Consequences

### Positive

- A published "this is resolved" claim now carries a stated basis, or an
  explicit admission that the check was not reproduced.
- The semgrep specifics are recorded where someone staring at a red scan will
  find them, including the API path that returns the findings and the two that
  return nothing.

### Negative

- Always-on corpus grows by 472 bytes, from 71,033 to 71,505, roughly 0.6
  percent. IFScale (arXiv:2507.11538) measures instruction-following degrading
  steadily with simultaneous instruction count, and the failure mode is silent
  omission, so every marginal rule makes the others slightly less reliable.
  This is a real cost, not a rounding error, which is why the draft went from
  three rules to one.
- 1,765 bytes of ceiling headroom remain. The next always-on addition will be
  tighter.

### Neutral

- Three documents pin the measured corpus figures and a test asserts each
  against a live measurement, so this change moved all three. That coupling is
  working as intended: it is what caught the byte growth in the first place.

## Prior Art Investigation

### What Currently Exists

- **Structure being changed**: `.claude/rules/universal.md`, the always-on MUST
  list, plus its two generated mirrors under `.github/instructions/` and
  `src/copilot-cli/instructions/`.
- **Closest existing rule**: `.claude/rules/testing.md` MUST 10 states that a
  scope measurement must be reported together with the size of the scope,
  because the filter under evaluation is also the filter applied to the
  evidence. That is the same family of error, one layer down.
- **Why testing.md is the wrong home**: its `paths:` frontmatter scopes it to
  `tests/**`. The failure here occurred while investigating a CI result on
  non-test files, so the rule would not have loaded.

### Why It Is Not Being Removed

Nothing is removed. This adds one item and leaves testing.md MUST 10 in place;
the two are complementary rather than duplicative.

## Compliance

- `.claude/rules/governance.md` MUST 2 requires an ADR for a new rule. This
  document.
- `.claude/rules/governance.md` MUST 4 requires the rule change to cite the
  failure mode that motivated it. PR #4701, and the review comment on it that
  told a reader to disregard a live finding.
- `.claude/rules/knowledge-persistence.md` requires the generated mirrors to be
  regenerated in the same change. Done with `build/scripts/generate_rules.py`.

## References

- Issue #4672, the customer-facing plugin denial this was found while fixing.
- PR #4701, where the incorrect comment was published.
- Review of this ADR by the architect and critic agents, 2026-08-07. The
  architect returned accept with a wording change; the critic returned revise,
  arguing the rule would not fire for an agent who believed the tools already
  matched, and that the CI-side fix was not evaluated. Both are addressed above:
  the wording now requires the equivalence to be demonstrable, which is the
  clause that cannot be satisfied by belief, and the CI-side alternative is
  evaluated and changed the GOTCHAS advice.
- Issue #4725, the separate semgrep python36 false positives. Distinct incident;
  its conclusion does not transfer to the taint findings.
- IFScale, arXiv:2507.11538, on instruction-following degradation with rule
  count.
