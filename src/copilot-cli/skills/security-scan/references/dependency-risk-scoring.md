# Dependency Risk Scoring

Assess risk for all external dependencies using this scoring matrix:

| Factor | Weight | Score 1 (Low) | Score 3 (Medium) | Score 5 (High) |
|--------|--------|---------------|------------------|----------------|
| **Maintenance** | 25% | Active (commits <30d) | Moderate (commits <90d) | Stale (>90d) |
| **Popularity** | 15% | >10k stars/downloads | 1k-10k | <1k |
| **Security History** | 30% | No CVEs | Patched CVEs | Unpatched CVEs |
| **Lock-in Risk** | 20% | Easy to replace | Moderate coupling | Deep integration |
| **License** | 10% | MIT/Apache | LGPL | GPL/Proprietary |

**Risk Score** = Sum(Weight x Score)

| Total Score | Risk Level | Action |
|-------------|------------|--------|
| <2.0 | Low | Approve |
| 2.0-3.5 | Medium | Document mitigation |
| >3.5 | High | Require ADR approval |

Include dependency risk assessment in security reviews for any new external packages.
