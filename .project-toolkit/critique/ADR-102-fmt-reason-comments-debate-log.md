# ADR-102 Debate Log: reason comments on the formatter markers

## Date: 2026-10-11

## Scope

ADR-102 gains two HTML comment lines. Each states why a code excerpt sits
between the formatter off and on markers. Review thread PRRT_kwDOQoWRls6rPBmq
asked for a reason on every such block. No decision, status, contract, or
command changes.

## Participants

- architect agent
- critic agent

## Architect position

Verdict: needs-revision. Every added line is a comment, and no executable
enforcement is touched, so the reduced panel is enough. One clause was false:
the second excerpt is proposed replacement code, not a quote of validator
source. Suggested neutral wording: a function-body fragment whose indentation
must stay.

## Critic position

Verdict: accept. Block-level HTML comments render hidden. The lifecycle
validator blanks comment blocks before it reads the Status heading. The index
generator and line-count checks are unaffected.

## Outcome: Accepted

Decision: accepted after the architect's wording fix, which the author applied
before commit. The comment now reads: this excerpt is a function-body fragment,
so its indentation must stay.
