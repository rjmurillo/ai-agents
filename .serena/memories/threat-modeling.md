# Threat Modeling

**Created**: 2026-01-10
**Category**: Security Engineering

## Overview

Structured representation of all information affecting application security. Identifies, documents, and understands potential threats with mitigation strategies.

## Four-Question Framework (OWASP)

1. **What are we working on?** (Scope: sprints to entire systems)
2. **What can go wrong?** (Brainstorm or apply structured techniques)
3. **What are we going to do about it?** (Mitigate, accept, transfer, eliminate)
4. **Did we do a good job?** (Validate effectiveness)

## Methodologies

| Method | Approach |
|--------|----------|
| **STRIDE** | Spoofing, Tampering, Repudiation, Info Disclosure, DoS, Elevation |
| **Kill Chains** | Model attacker progression |
| **Attack Trees** | Hierarchical threat decomposition |

## Timing

Continuous activity throughout development:

- High-level models during planning
- Refine as details emerge
- Update after new features, incidents, or architecture changes

## Benefits

- Clear line of sight justifying security efforts
- Rational decisions with comprehensive information
- Generates assurance arguments
- Prioritized security improvements

## Related

- `security-principles-owasp`: OWASP Top 10
- `security-agent-vulnerability-detection-gaps`: Detection patterns
- `foundational-knowledge-index`: Master index
