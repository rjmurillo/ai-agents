# Risk Rating Guide

Consistent risk rating ensures threats are prioritized appropriately.

## Risk Formula

```text
Risk = Likelihood x Impact
```

---

## Likelihood Scale

| Level | Score | Criteria | Examples |
|-------|-------|----------|----------|
| **High** | 3 | Easily exploitable, public tools available, no special access required | Public exploit, default credentials, no auth required |
| **Medium** | 2 | Requires some skill, tools, or limited access | Requires valid account, custom exploit, internal network |
| **Low** | 1 | Difficult to exploit, requires significant resources or insider access | Zero-day, physical access, nation-state level |

### Likelihood Factors

Consider these when rating likelihood:

| Factor | Increases Likelihood | Decreases Likelihood |
|--------|---------------------|---------------------|
| **Skill Required** | None / Script kiddie | Expert / Novel research |
| **Access Required** | Anonymous / Public | Authenticated / Internal / Physical |
| **Tools Available** | Public / Automated | Custom / Manual |
| **Detection** | Unlikely | Highly likely |
| **Motivation** | High value target | Low value target |

---

## Impact Scale

| Level | Score | Criteria | Examples |
|-------|-------|----------|----------|
| **High** | 3 | Significant harm, regulatory violation, major financial loss | Data breach, system compromise, ransomware, compliance violation |
| **Medium** | 2 | Limited harm, recoverable, moderate cost | Limited data exposure, service degradation, reputation damage |
| **Low** | 1 | Minor inconvenience, no sensitive data, easily recovered | Public info exposed, minor DoS, cosmetic defacement |

### Impact Factors

Consider these when rating impact:

| Factor | Increases Impact | Decreases Impact |
|--------|-----------------|-----------------|
| **Data Sensitivity** | PII, financial, health | Public, non-sensitive |
| **Data Volume** | All users affected | Single user affected |
| **System Criticality** | Core business function | Non-critical system |
| **Recovery Time** | Days/weeks | Minutes/hours |
| **Regulatory** | Reportable breach | No reporting required |
| **Reputation** | Public-facing, news-worthy | Internal, contained |

---

## Risk Matrix

|                          | Impact: Low (1) | Impact: Medium (2) | Impact: High (3) |
|--------------------------|-----------------|--------------------|--------------------|
| **Likelihood: High (3)** | Medium (3) | High (6) | Critical (9) |
| **Likelihood: Medium (2)** | Low (2) | Medium (4) | High (6) |
| **Likelihood: Low (1)** | Low (1) | Low (2) | Medium (3) |

### Risk Levels

| Risk Level | Score Range | Response |
|------------|-------------|----------|
| **Critical** | 9 | Fix immediately, stop deployment |
| **High** | 6 | Fix in current sprint |
| **Medium** | 3-4 | Fix in next release |
| **Low** | 1-2 | Fix opportunistically or accept |

---

## DREAD Alternative (Optional)

DREAD provides more granular rating but requires more effort:

| Factor | Description | Scale |
|--------|-------------|-------|
| **D**amage | How bad if exploited? | 0-10 |
| **R**eproducibility | How easy to reproduce? | 0-10 |
| **E**xploitability | How easy to exploit? | 0-10 |
| **A**ffected Users | How many affected? | 0-10 |
| **D**iscoverability | How easy to discover? | 0-10 |

```text
DREAD Score = (D + R + E + A + D) / 5
```

| Score | Risk Level |
|-------|------------|
| 9-10 | Critical |
| 7-8 | High |
| 4-6 | Medium |
| 1-3 | Low |

---

## Residual Risk

After applying mitigations, reassess:

```text
Residual Risk = Reduced Likelihood x Reduced Impact
```

### Example

| Stage | Likelihood | Impact | Risk |
|-------|------------|--------|------|
| **Initial** | High (3) | High (3) | Critical (9) |
| **After Mitigation** | Low (1) | High (3) | Medium (3) |

Document what changed and why.

---

## Common Pitfalls

| Pitfall | Problem | Solution |
|---------|---------|----------|
| Over-rating everything | No prioritization | Calibrate against real incidents |
| Under-rating likelihood | False security | Assume motivated attacker |
| Ignoring context | Wrong risk | Consider specific deployment |
| Static ratings | Drift from reality | Review quarterly |

---

## Calibration Questions

To ensure consistent ratings across the team:

1. What was the worst security incident we had?
2. How would we rate that incident?
3. Use that as a reference point for High impact.
4. What attacks do we see most often?
5. Use those as reference for High likelihood.

---

## References

- [OWASP Risk Rating Methodology](https://owasp.org/www-community/OWASP_Risk_Rating_Methodology)
- [CVSS Calculator](https://www.first.org/cvss/calculator/3.1)
- [FAIR Risk Quantification](https://www.fairinstitute.org/)
