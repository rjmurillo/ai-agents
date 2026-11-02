---
source: wiki/concepts/Design Principles/Principle of Least Privilege.md
created: 2026-04-11
review-by: 2026-07-11
---

# Principle of Least Privilege

Every program and user should operate using the minimum set of privileges necessary to complete their task.

**Origin**: Jerome Saltzer, MULTICS operating system (1974)

## Core Insight

If a component only has permissions for what it needs, a compromise limits the blast radius. Attackers can only access what that component could access.

## Application Areas

| Area | Application |
|------|-------------|
| User accounts | Role-based access, not admin by default |
| Service accounts | Scoped to specific resources |
| API keys | Limited to required operations |
| Database access | Read-only where writes unnecessary |
| File systems | Minimal directory access |
| Network | Firewall rules, network segmentation |

## Benefits

| Benefit | Explanation |
|---------|-------------|
| Reduced attack surface | Fewer permissions = fewer attack vectors |
| Blast radius containment | Compromised component cannot pivot easily |
| Audit clarity | Clear what each identity should access |
| Compliance | Required by most security frameworks |

## Implementation Examples

### Service Accounts

```yaml
# Over-privileged
serviceAccount:
  role: cluster-admin

# Least privilege
serviceAccount:
  role: pod-reader
  namespace: my-app
```

### Database Access

```sql
-- Over-privileged
GRANT ALL PRIVILEGES ON database.* TO 'app_user'@'%';

-- Least privilege
GRANT SELECT, INSERT ON database.orders TO 'order_service'@'10.0.1.0/255.255.255.0';
GRANT SELECT ON database.products TO 'order_service'@'10.0.1.0/255.255.255.0';
```

### API Scopes

```csharp
// Over-privileged
var scopes = new[] { "https://graph.microsoft.com/.default" };

// Least privilege
var scopes = new[] { "User.Read", "Calendars.Read" };
```

### Azure Managed Identity

```csharp
// Service gets only permissions assigned to its managed identity
var credential = new DefaultAzureCredential();
var client = new BlobServiceClient(
    new Uri("https://storage.blob.core.windows.net"),
    credential
);
// Identity only has access to specific containers, not entire account
```

## Common Violations

| Violation | Problem |
|-----------|---------|
| Admin by default | All users start with full access |
| Shared service accounts | Multiple services use same credentials |
| Wildcard permissions | `*` grants everything |
| Permanent credentials | Long-lived tokens instead of short-lived |
| No permission reviews | Permissions accumulate, never removed |

## Applying to Threat Modeling

### Phase 2 (Threat Identification)

For each component in the DFD, ask:

1. What permissions does this component have?
2. Are any permissions broader than required?
3. If compromised, what can an attacker reach from here?
4. Are credentials shared between components?

### Phase 3 (Mitigation Strategy)

Least privilege mitigations to recommend:

- Scope service accounts to specific resources and namespaces
- Use managed identities instead of shared secrets
- Grant minimum database permissions per service
- Request only needed API scopes
- Implement short-lived tokens with rotation
- Schedule regular permission audits

### Validation Checklist

For each service/component in the threat model:

- [ ] Service accounts have scoped permissions, not admin
- [ ] Database users have minimum required grants
- [ ] API keys limited to required operations
- [ ] Managed identities used instead of shared secrets
- [ ] Regular permission audits scheduled
- [ ] Production has stricter permissions than dev
- [ ] Network access limited by firewall rules

## Relationship to Zero Trust

| Principle | Focus |
|-----------|-------|
| Least Privilege | What can they access? |
| Zero Trust | Should we trust them at all? |

Zero Trust assumes breach. Least Privilege limits damage when breach occurs. They are complementary.

## Related

- [Zero Trust](security-zero-trust.md): Complementary verification model
- [Defense in Depth](security-defense-in-depth.md): Least privilege is one layer
- [OWASP Top 10](security-owasp-top-10.md): A01 Broken Access Control mitigation
