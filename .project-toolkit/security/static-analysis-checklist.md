# Static Analysis Checklist

## Purpose

This checklist guides security agent static analysis for vulnerability detection. It focuses on common vulnerability patterns defined by CWE (Common Weakness Enumeration).

## Priority Vulnerabilities

### CWE-78: OS Command Injection

**Description**: Improper neutralization of special elements used in an OS command.

**Detection Patterns**:

```text
# Shell execution without proper quoting
$variable         # Unquoted variable in shell
$(command)        # Command substitution
`command`         # Backtick command substitution

# Dangerous functions
Runtime.exec()               # Java
os.system()                  # Python
exec()                       # Multiple languages
Process.Start()              # .NET
child_process.exec()         # Node.js
shell_exec()                 # PHP
```

**Remediation**:

- Use parameterized commands or APIs
- Quote all variables in shell scripts: `"${variable}"`
- Use arrays for command arguments in bash
- Validate and sanitize all input

**Evidence Example (CWE-78 Incident)**:

```bash
# VULNERABLE
git diff --name-only $MD_FILE_LIST

# FIXED
git diff --name-only "${MD_FILES[@]}"
```

### CWE-79: Cross-Site Scripting (XSS)

**Description**: Improper neutralization of user input in web output.

**Detection Patterns**:

```text
# Direct output without encoding
innerHTML =                  # JavaScript
@Html.Raw()                  # ASP.NET
{!! $variable !!}            # Laravel Blade
dangerouslySetInnerHTML      # React
v-html                       # Vue.js
[innerHTML]                  # Angular
```

**Remediation**:

- Use context-appropriate output encoding
- Use framework's built-in encoding (e.g., `@Html.Encode()`)
- Implement Content Security Policy (CSP)
- Validate and sanitize input

### CWE-89: SQL Injection

**Description**: Improper neutralization of SQL commands.

**Detection Patterns**:

```text
# String concatenation in queries
"SELECT * FROM users WHERE id = " + userInput
$"SELECT * FROM users WHERE id = {userId}"
f"SELECT * FROM users WHERE id = {user_id}"
query = "SELECT * FROM " + tableName

# Dangerous patterns
ExecuteNonQuery with string concat
ExecuteReader with string concat
FromSqlRaw with user input
```

**Remediation**:

- Use parameterized queries
- Use ORM with proper parameter binding
- Validate input against allowlist
- Apply least privilege to database accounts

### CWE-200: Exposure of Sensitive Information

**Description**: Unauthorized exposure of sensitive data.

**Detection Patterns**:

```text
# Logging sensitive data
logger.info(password)
console.log(token)
Debug.WriteLine(apiKey)

# Error messages with details
catch (Exception ex) { return ex.ToString(); }
res.send(err.stack)

# Hardcoded secrets
password = "secretvalue"
apiKey = "abc123"
connectionString = "...Password=..."
```

**Remediation**:

- Implement proper exception handling
- Use structured logging with PII filtering
- Store secrets in secure vault
- Mask sensitive data in logs

### CWE-287: Improper Authentication

**Description**: Failure to properly verify identity.

**Detection Patterns**:

```text
# Weak authentication
if (username == "admin")    # Hardcoded credentials
password.Equals(input)      # Case-sensitive comparison
md5(password)               # Weak hashing
sha1(password)              # Weak hashing

# Missing authentication
[AllowAnonymous] on sensitive endpoints
app.use('/admin', ...)      # No auth middleware
```

**Remediation**:

- Use strong password hashing (bcrypt, Argon2)
- Implement multi-factor authentication
- Use secure session management
- Apply authentication to all sensitive endpoints

### CWE-352: Cross-Site Request Forgery (CSRF)

**Description**: Missing verification of request origin.

**Detection Patterns**:

```text
# Missing CSRF tokens
<form action="/delete" method="POST">   # No token
[IgnoreAntiforgeryToken]                # Disabled protection
csrf: false                             # Disabled in framework

# State-changing GET requests
GET /api/delete/{id}
GET /api/transfer?amount=...
```

**Remediation**:

- Use anti-forgery tokens
- Verify request origin (SameSite cookies)
- Use POST/PUT/DELETE for state changes
- Implement double-submit cookie pattern

### CWE-611: XML External Entity (XXE)

**Description**: Processing external entities in XML.

**Detection Patterns**:

```text
# Dangerous XML parsing
XmlReader.Create() without settings
DocumentBuilderFactory without disabling DTD
lxml.etree.parse() without resolve_entities=False

# Vulnerable settings
XmlReaderSettings { DtdProcessing = DtdProcessing.Parse }
factory.setFeature("...external-general-entities", true)
```

**Remediation**:

- Disable DTD processing
- Disable external entity resolution
- Use safe XML parsing libraries
- Validate XML against schema

## Analysis Checklist

### Pre-Analysis

```markdown
- [ ] Identify file types and languages
- [ ] Determine trust boundaries
- [ ] Map data flow (input -> processing -> output)
- [ ] Identify external dependencies
```

### Core Analysis

```markdown
- [ ] CWE-78: Check shell/command execution
- [ ] CWE-79: Check output encoding
- [ ] CWE-89: Check database queries
- [ ] CWE-200: Check logging and error handling
- [ ] CWE-287: Check authentication mechanisms
- [ ] CWE-352: Check CSRF protection
- [ ] CWE-611: Check XML processing
```

### Post-Analysis

```markdown
- [ ] Prioritize findings by severity
- [ ] Document remediation steps
- [ ] Identify patterns for team training
- [ ] Update threat model if needed
```

## Severity Classification

| Severity | Definition | Examples |
|----------|------------|----------|
| Critical | Remote code execution, full system compromise | CWE-78, CWE-89 (with admin access) |
| High | Data breach, authentication bypass | CWE-287, CWE-200 (PII) |
| Medium | Limited data exposure, session issues | CWE-79, CWE-352 |
| Low | Information disclosure, minor issues | CWE-200 (non-sensitive) |

## Related Documents

- [Secret Detection Patterns](./secret-detection-patterns.md)
- [Security Best Practices](./security-best-practices.md)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

---

*Checklist Version: 1.0*
*Created: 2025-12-13*
*GitHub Issue: #10*
