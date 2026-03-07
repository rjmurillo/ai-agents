# Advanced Analysis Techniques

Optional techniques for complex threat analysis. Use when basic STRIDE is insufficient.

## Attack Trees

Decompose complex threats into attack paths:

```text
              [Steal User Data]
                    |
        +-----------+-----------+
        |                       |
   [SQL Injection]      [Compromised API Key]
        |                       |
   +----+----+             +----+----+
   |         |             |         |
[Error]  [Blind]      [Phishing]  [Git Leak]
```

### When to Use

- Multi-step attack scenarios
- Identifying weakest attack paths
- Comparing mitigation effectiveness

## Kill Chains

Map attacker progression for sophisticated threats:

| Phase | Attacker Action | Detection Opportunity |
|-------|-----------------|----------------------|
| Recon | Port scanning | Network monitoring |
| Weaponize | Craft exploit | Threat intelligence |
| Deliver | Send phishing email | Email filtering |
| Exploit | Execute payload | Endpoint detection |
| Install | Persist access | File integrity monitoring |
| Command | Establish C2 | Network anomaly detection |
| Action | Exfiltrate data | DLP, egress monitoring |

### When to Use

- APT-style threats
- Identifying detection gaps
- Building defense-in-depth strategy
