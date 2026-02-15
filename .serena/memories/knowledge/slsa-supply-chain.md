# SLSA (Supply-chain Levels for Software Artifacts)

**Created**: 2026-01-10
**Category**: Software Security

## Overview

Vendor-neutral security framework addressing supply chain vulnerabilities. "A checklist of standards and controls to prevent tampering, improve integrity, and secure packages and infrastructure."

## Purpose

Ensure artifact integrity across complex software ecosystems. Without proper safeguards, malicious actors can introduce vulnerabilities at any point in development and distribution.

## The Levels

Four compliance tiers of increasing assurance:

| Level | Focus |
|-------|-------|
| Lower levels | Easy, basic steps |
| Higher levels | Defense against advanced threats |

## Adoption Path

1. Start with generating provenance
2. Implement foundational protections
3. Progressively harden security

## Audiences

| Audience | Benefit |
|----------|---------|
| **Producers** | Protection against tampering and insider threats |
| **Consumers** | Verification of software security |
| **Infrastructure** | Guidance for hardening build platforms |

## Key Insight

"Having a common language and standard for objectively measuring our supply chain security is a must." Enables consistent communication across industries.

## Related

- [security-validation-chain](security-validation-chain.md): Validation patterns
- [ci-infrastructure-quality-gates](ci-infrastructure-quality-gates.md): Build security
- [foundational-knowledge-index](foundational-knowledge-index.md): Master index
