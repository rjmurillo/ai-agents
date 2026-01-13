# Skill: Security-Domain Priority Boost

## Statement

Process security-domain comments first, regardless of reviewer signal quality.

## Trigger

When PR comments contain security keywords (CWE, vulnerability, injection, bypass, hardening).

## Action

1. Scan comment text for security indicators
2. Boost priority above reviewer signal quality
3. Process security comments before general comments

## Benefit

Catches real vulnerabilities that might be deprioritized due to low-signal reviewer history.

## Evidence

- PR #488: Two bot comments on security fix PR, both 100% actionable
- gemini-code-assist: Caught case-sensitivity bypass (CWE-22 variant)
- Copilot: Caught path separator prefix bypass

## Anti-Pattern

Deprioritizing security comments from coderabbitai[bot] (50% signal) would miss real vulnerabilities.

## Atomicity

**Score**: 96%

**Justification**: Single concept (domain-based priority). Highly actionable.

## Category

pr-comment-responder

## Created

2025-12-29

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
