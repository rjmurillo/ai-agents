# STRIDE Methodology Reference

STRIDE is a threat classification system developed by Microsoft. Each letter represents a category of security threat.

## Categories

### S - Spoofing Identity

**Definition**: Pretending to be something or someone other than yourself.

**Applies To**: External entities, data flows

**Examples**:

- Using stolen credentials
- Session hijacking
- IP address spoofing
- Certificate impersonation

**Questions to Ask**:

1. How do we verify user identity?
2. Can authentication be bypassed?
3. Are credentials transmitted securely?
4. Can sessions be stolen or replayed?

**Common Mitigations**:

- Multi-factor authentication
- Strong session management
- Certificate pinning
- IP validation

---

### T - Tampering with Data

**Definition**: Modifying data or code without proper authorization.

**Applies To**: Processes, data stores, data flows

**Examples**:

- SQL injection
- Cross-site scripting (XSS)
- Man-in-the-middle attacks
- File modification

**Questions to Ask**:

1. Can input be modified to change behavior?
2. Is data validated on both client and server?
3. Are communications encrypted?
4. How do we detect unauthorized changes?

**Common Mitigations**:

- Input validation
- Parameterized queries
- TLS/HTTPS
- Integrity checks (HMAC, signatures)

---

### R - Repudiation

**Definition**: Denying having performed an action when no one can prove otherwise.

**Applies To**: Processes

**Examples**:

- User denies making a purchase
- Admin denies changing configuration
- Attacker covers their tracks

**Questions to Ask**:

1. Do we log security-relevant actions?
2. Can logs be tampered with?
3. Is there a secure audit trail?
4. Can we prove who did what?

**Common Mitigations**:

- Comprehensive logging
- Secure log storage
- Digital signatures
- Timestamping

---

### I - Information Disclosure

**Definition**: Exposing information to someone not authorized to see it.

**Applies To**: Data stores, data flows

**Examples**:

- Stack traces in error messages
- Exposed API keys
- Unencrypted data transmission
- Database dumps

**Questions to Ask**:

1. What data is sensitive?
2. Is sensitive data encrypted at rest?
3. Is sensitive data encrypted in transit?
4. Who has access to what data?

**Common Mitigations**:

- Data classification
- Encryption at rest
- TLS/HTTPS
- Access controls
- Error message sanitization

---

### D - Denial of Service

**Definition**: Denying access to legitimate users by exhausting resources.

**Applies To**: Processes, data stores

**Examples**:

- DDoS attacks
- Resource exhaustion
- Algorithmic complexity attacks
- Lock-out attacks

**Questions to Ask**:

1. What resources can be exhausted?
2. Are there rate limits?
3. Can the system scale?
4. Are there single points of failure?

**Common Mitigations**:

- Rate limiting
- Auto-scaling
- CDN/DDoS protection
- Resource quotas
- Timeouts

---

### E - Elevation of Privilege

**Definition**: Gaining capabilities without proper authorization.

**Applies To**: Processes

**Examples**:

- Broken access control
- Privilege escalation
- IDOR (Insecure Direct Object Reference)
- Role bypass

**Questions to Ask**:

1. How are permissions checked?
2. Can users access other users' data?
3. Are admin functions properly protected?
4. Is the principle of least privilege followed?

**Common Mitigations**:

- Role-based access control
- Principle of least privilege
- Object-level authorization
- Security testing

---

## STRIDE per Element

| Element Type | S | T | R | I | D | E |
|--------------|---|---|---|---|---|---|
| External Entity | X | | | | | |
| Process | X | X | X | X | X | X |
| Data Store | | X | X | X | X | |
| Data Flow | | X | | X | X | |

**Legend**:

- X = This threat category applies to this element type
- Blank = Generally not applicable (but consider context)

---

## STRIDE-per-Interaction Variant

For each data flow crossing a trust boundary, ask:

1. **S**: Can the sender be spoofed?
2. **T**: Can the data be tampered with?
3. **R**: Can either party deny the interaction?
4. **I**: Can the data be disclosed?
5. **D**: Can the interaction be disrupted?
6. **E**: Can the receiver be tricked into elevating privileges?

---

## Risk Rating with STRIDE

| STRIDE Category | Typical Impact | Common Likelihood Factors |
|-----------------|----------------|---------------------------|
| Spoofing | High | Weak auth, public endpoints |
| Tampering | High | Missing validation, no encryption |
| Repudiation | Medium | Missing logs, log tampering |
| Info Disclosure | Medium-High | Misconfiguration, weak encryption |
| DoS | Medium-High | No rate limits, public-facing |
| Elevation | High | Complex permissions, legacy code |

---

## References

- [Microsoft STRIDE](https://docs.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats)
- [OWASP Threat Modeling](https://owasp.org/www-community/Threat_Modeling)
- [Adam Shostack - Threat Modeling](https://shostack.org/resources/threat-modeling)
