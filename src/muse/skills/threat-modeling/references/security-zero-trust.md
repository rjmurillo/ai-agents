---
source: wiki/concepts/Design Principles/Zero Trust.md
created: 2026-04-11
review-by: 2026-07-11
---

# Zero Trust

No actor, system, network, or service is trusted by default. Every access request must be continuously validated.

Traditional security assumed everything inside the network perimeter was trusted. Zero Trust assumes breach and verifies every request as if it originates from an uncontrolled network.

## Evolution

| Era | Approach | Assumption |
|-----|----------|------------|
| Perimeter (2000s) | Firewalls, VPNs, network segmentation | Inside the network = trusted |
| Protocol (2010s) | SSL/TLS, DKIM, SPF, encryption | Verified sender = trusted |
| Zero Trust (2020s) | Context-based, continuous verification | Nothing is inherently trusted |

## Three Principles

1. **Verify explicitly**: Always authenticate and authorize based on all available data points.
2. **Least privilege access**: Limit access with just-in-time/just-enough-access (JIT/JEA).
3. **Assume breach**: Minimize blast radius, segment access, verify end-to-end encryption.

## Context-Based Decision Making

Zero Trust models use the context of an action at the touch point to allow or deny:

```text
Simple context (URL reputation)
    -> Enriched context (URL + sender + history)
        -> Full context (URL + sender + history + user behavior + device state + org graph)
```

### Two-Stage Models

1. **Stage 1**: Feature extraction into coarse buckets (fast classification)
2. **Stage 2**: Full ML modeling with enriched context (precise)

This enables shipping models impossible with single-stage approaches.

## Identity as the Perimeter

In Zero Trust, identity replaces the network as the security boundary:

| Component | Role |
|-----------|------|
| MFA | Prove identity with something you have/are |
| PIM | Just-in-time elevation, no permanent admin |
| Identity Protection | Risk-based sign-in classification |
| Conditional Access | Policy-based access decisions per request |
| RBAC | Least-privilege role assignments |

## Tier Model

| Tier | Contains | Example |
|------|----------|---------|
| Tier 0 | Identity infrastructure | Domain controllers, AD, Azure AD |
| Tier 1 | Enterprise servers/apps | Cloud services, enterprise apps |
| Tier 2 | User workstations/devices | Help desk, device management |

**Rule**: No entity may access or control a more privileged tier than the one it resides in.

## Applying to Threat Modeling

### Phase 1 (Scope and Decompose)

When mapping trust boundaries, apply Zero Trust thinking:

- Mark every service-to-service connection as a trust boundary (not just network edges)
- Identify where authentication/authorization decisions occur
- Flag any implicit trust assumptions (shared secrets, internal network trust)

### Phase 2 (Threat Identification)

For each trust boundary crossing, ask:

1. Is the caller identity verified at this point?
2. Is authorization checked per-request or assumed from prior auth?
3. What context is available for the access decision?
4. Can this boundary be bypassed through lateral movement?

### Phase 3 (Mitigation Strategy)

Zero Trust mitigations to consider:

- Replace shared secrets with workload identity
- Add per-request authorization (not session-based blanket trust)
- Implement conditional access policies
- Scope configuration access per environment
- Verify every deployment artifact independently

## Related

- [Defense in Depth](security-defense-in-depth.md): Complementary layered security pattern
- [Least Privilege](security-least-privilege.md): Foundation principle of Zero Trust
- [OWASP Top 10](security-owasp-top-10.md): Web security standards that complement Zero Trust
