# Secret Detection Patterns

## Purpose

This document defines patterns for detecting hardcoded secrets, credentials, and sensitive data in code. Use these patterns to identify potential security risks before code reaches production.

## Detection Categories

### 1. API Keys and Tokens

#### Generic API Key Patterns

```regex
# Generic API key patterns
(?i)(api[_-]?key|apikey)\s*[:=]\s*['"][a-zA-Z0-9-_]{20,}['"]
(?i)(api[_-]?secret|apisecret)\s*[:=]\s*['"][a-zA-Z0-9-_]{20,}['"]
```

#### Cloud Provider Keys

```regex
# AWS Access Keys
AKIA[0-9A-Z]{16}
(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*['"][a-zA-Z0-9/+=]{40}['"]

# Azure
(?i)DefaultEndpointsProtocol=https;AccountName=.+;AccountKey=.+
(?i)azure[_-]?storage[_-]?key\s*[:=]\s*['"][a-zA-Z0-9/+=]{88}['"]

# GCP
(?i)type\s*[:=]\s*['"]service_account['"]
(?i)private[_-]?key[_-]?id\s*[:=]\s*['"][a-zA-Z0-9-_]{20,}['"]

# Stripe
(?i)sk_live_[a-zA-Z0-9]{24,}
(?i)rk_live_[a-zA-Z0-9]{24,}

# SendGrid
(?i)SG\.[a-zA-Z0-9-_]{22}\.[a-zA-Z0-9-_]{43}

# Twilio
(?i)SK[a-z0-9]{32}
(?i)twilio[_-]?auth[_-]?token\s*[:=]\s*['"][a-zA-Z0-9]{32}['"]
```

### 2. Authentication Credentials

#### Passwords

```regex
# Password in code
(?i)(password|passwd|pwd)\s*[:=]\s*['"][^'"]{4,}['"]
(?i)(password|passwd|pwd)\s*[:=]\s*[a-zA-Z0-9!@#$%^&*]{4,}\s*[;,]

# Connection strings with password
(?i)Password\s*=\s*[^;]+
(?i)pwd\s*=\s*[^;]+
```

#### Private Keys

```regex
# RSA Private Key
-----BEGIN RSA PRIVATE KEY-----
-----BEGIN PRIVATE KEY-----
-----BEGIN EC PRIVATE KEY-----
-----BEGIN OPENSSH PRIVATE KEY-----
-----BEGIN PGP PRIVATE KEY BLOCK-----
```

#### SSH Keys

```regex
# SSH private key
ssh-rsa AAAA[a-zA-Z0-9+/=]{100,}
```

### 3. Tokens and Sessions

#### JWT Tokens

```regex
# JWT tokens (don't commit valid tokens)
eyJ[a-zA-Z0-9-_]+\.eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+
```

#### Bearer Tokens

```regex
(?i)bearer\s+[a-zA-Z0-9-_.]{20,}
(?i)(access[_-]?token|auth[_-]?token)\s*[:=]\s*['"][a-zA-Z0-9-_.]{20,}['"]
```

#### OAuth

```regex
(?i)client[_-]?secret\s*[:=]\s*['"][a-zA-Z0-9-_]{20,}['"]
(?i)refresh[_-]?token\s*[:=]\s*['"][a-zA-Z0-9-_]{20,}['"]
```

### 4. Database Credentials

#### Connection Strings

```regex
# SQL Server
(?i)Server=.+;Database=.+;User Id=.+;Password=.+
(?i)Data Source=.+;Initial Catalog=.+;User ID=.+;Password=.+

# PostgreSQL
(?i)postgresql://[^:]+:[^@]+@[^/]+/[^?]+
(?i)postgres://[^:]+:[^@]+@[^/]+/[^?]+

# MySQL
(?i)mysql://[^:]+:[^@]+@[^/]+/[^?]+

# MongoDB
(?i)mongodb(\+srv)?://[^:]+:[^@]+@[^/]+
```

### 5. Encryption Keys

```regex
# Encryption/signing keys
(?i)(encryption[_-]?key|signing[_-]?key)\s*[:=]\s*['"][a-zA-Z0-9-_/+=]{16,}['"]
(?i)(secret[_-]?key|master[_-]?key)\s*[:=]\s*['"][a-zA-Z0-9-_/+=]{16,}['"]
(?i)AES[_-]?KEY\s*[:=]\s*['"][a-zA-Z0-9-_/+=]{16,}['"]
```

### 6. Environment Variables (Leaks)

```regex
# Environment variable exposure
(?i)process\.env\.([A-Z_]+[_]?(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL))
(?i)os\.environ\[['"]([A-Z_]+[_]?(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL))['"]\]
(?i)Environment\.GetEnvironmentVariable\(['"]([A-Z_]+[_]?(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL))['"]\)
```

## High-Risk Files

### Always Scan These Patterns

| Pattern | Risk | Reason |
|---------|------|--------|
| `*.env*` | Critical | Environment files often contain secrets |
| `*.pem` | Critical | Certificate private keys |
| `*.key` | Critical | Private keys |
| `*.p12` | Critical | PKCS12 certificate stores |
| `*.pfx` | Critical | PKCS12 certificate stores |
| `appsettings*.json` | High | .NET configuration files |
| `config.json` | High | Generic config with secrets |
| `credentials*` | Critical | Credential files |
| `secrets*` | Critical | Secret files |
| `.npmrc` | High | npm registry tokens |
| `.pypirc` | High | PyPI credentials |
| `nuget.config` | High | NuGet credentials |

### Never Commit These

| File | Reason |
|------|--------|
| `.env.local` | Local environment overrides |
| `.env.production` | Production secrets |
| `id_rsa` | SSH private key |
| `*.pem` | Private keys |
| `service-account.json` | GCP service account |
| `credentials.json` | Cloud credentials |

## Detection Workflow

### Step 1: Identify Candidate Files

```bash
# Find files likely to contain secrets
find . -name "*.env*" -o -name "*.pem" -o -name "appsettings*.json" \
       -o -name "config*.json" -o -name "*secret*" -o -name "*credential*"
```

### Step 2: Apply Pattern Matching

```bash
# Search for common secret patterns
grep -rE "(api[_-]?key|password|secret|token|credential)" --include="*.cs" --include="*.js" --include="*.py" --include="*.json"
```

### Step 3: Validate Findings

For each match:

1. Is this a placeholder/example value?
2. Is this a test/mock credential?
3. Is this loading from environment variables?
4. Is the value base64/encrypted?

### Step 4: Report and Remediate

```markdown
## Finding: Hardcoded API Key
- **Location**: src/config/api.ts:23
- **Pattern**: AWS access key (AKIA...)
- **Severity**: Critical
- **Remediation**: Move to environment variable or secret manager
```

## False Positive Indicators

These patterns suggest the secret might be a placeholder:

| Pattern | Likely False Positive |
|---------|----------------------|
| `your-api-key-here` | Placeholder |
| `xxx...xxx` | Masked example |
| `<API_KEY>` | Template variable |
| `${ENV_VAR}` | Environment reference |
| `process.env.` | Env var access |
| In `/test/` path | Test fixture |
| In `/mock/` path | Mock data |
| In `*.example` file | Example file |

## Remediation Patterns

### Instead of Hardcoding

```csharp
// BAD: Hardcoded
var apiKey = "sk_live_abc123...";

// GOOD: Environment variable
var apiKey = Environment.GetEnvironmentVariable("API_KEY");

// GOOD: Secret manager
var apiKey = await secretManager.GetSecretAsync("api-key");

// GOOD: Configuration with user secrets (development)
var apiKey = configuration["ApiKey"];
```

### Commit Prevention

Add to `.gitignore`:

```gitignore
# Secrets
*.env.local
*.env.production
secrets.json
credentials.json
*.pem
*.key
*.p12
```

Add pre-commit hook secret detection (see Issue #9).

## Related Documents

- [Static Analysis Checklist](./static-analysis-checklist.md)
- [Security Best Practices](./security-best-practices.md)
- [Infrastructure File Patterns](./infrastructure-file-patterns.md)

---

*Document Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #10*
