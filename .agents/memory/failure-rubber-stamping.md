# Failure Pattern: Multi-Agent Rubber-Stamping

**Last Updated**: 2026-04-21
**Status**: active
**Severity**: High

## Summary

Parallel reviewers converge on approval when asked to evaluate the same artifact with the same framing. Reviews become correlated, not independent. The apparent multi-agent confidence is an illusion produced by shared priors and shared prompts.

## What Failed

- `2025-12-24-parallel-pr-review-session.md`: Five agents approved a PR that a single adversarial pass would have flagged.
- Reviews framed as "confirm the plan" produced ratification; reviews framed as "find the fault" produced findings.

## What Worked

- Adversarial framing per agent (critic, independent-thinker, security) with differentiated goals.
- Consensus protocol requiring at least one explicit dissent acknowledgement before approval.
- Evidence-bearing reviews: each agent cites a file, line, or tool output, not just a verdict.

## Current Recommendation

Diverge before converging. Assign each reviewer a distinct failure mode to hunt. Require evidence citations. Treat unanimous approval without dissent as a smell, not a signal.

## References

- `.agents/governance/FAILURE-MODES.md` Section 6
- `.agents/governance/CONSENSUS.md`
- ADR-010 Quality Gates: Evaluator-Optimizer
- Retrospective: `.agents/retrospective/2025-12-24-parallel-pr-review-session.md`
