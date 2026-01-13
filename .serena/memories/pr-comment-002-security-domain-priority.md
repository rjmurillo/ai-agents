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

- [pr-comment-001-reviewer-signal-quality](pr-comment-001-reviewer-signal-quality.md)
- [pr-comment-003-path-containment-layers](pr-comment-003-path-containment-layers.md)
- [pr-comment-004-bot-response-templates](pr-comment-004-bot-response-templates.md)
- [pr-comment-005-branch-state-verification](pr-comment-005-branch-state-verification.md)
- [pr-comment-index](pr-comment-index.md)
