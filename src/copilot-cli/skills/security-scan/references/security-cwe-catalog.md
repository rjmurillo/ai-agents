# CWE-699 Categories and High-Priority CWEs

Loaded by the `security` agent when it scans for CWEs and needs a name or description. The agent body keeps the category list with CWE numbers.

**[Injection and Code Execution]** (OWASP A03:2021)

- CWE-22: Path Traversal - Improper limitation of pathname to restricted directory
- CWE-23: Relative Path Traversal - Use of ../ sequences to escape directory
- CWE-36: Absolute Path Traversal - Use of absolute paths to access arbitrary files
- CWE-73: External Control of File Name - User input controls file path or name
- CWE-77: Command Injection - Improper neutralization of special elements in command
- CWE-78: OS Command Injection - Improper neutralization of special elements in OS commands
- CWE-89: SQL Injection - Improper neutralization of SQL command elements
- CWE-91: XML Injection - Improper neutralization of XML elements
- CWE-94: Code Injection - Improper control of generation of code using untrusted input
- CWE-95: Eval Injection - Improper neutralization of directives in dynamically evaluated code
- CWE-99: Resource Injection - External control of resource identifiers

**[Authentication and Session Management]** (OWASP A07:2021)

- CWE-287: Improper Authentication - Failure to properly verify identity
- CWE-798: Hard-coded Credentials - Credentials embedded in source code (inbound auth or outbound connections)
- CWE-640: Weak Password Recovery - Password reset without proper verification
- CWE-384: Session Fixation - Reusing session identifiers across authentication
- CWE-613: Insufficient Session Expiration - Sessions remain valid too long

**[Authorization and Access Control]** (OWASP A01:2021)

- CWE-285: Improper Authorization - Failure to restrict operations to authorized users
- CWE-863: Incorrect Authorization - Authorization check has incorrect logic
- CWE-269: Improper Privilege Management - Running with unnecessary privileges
- CWE-284: Improper Access Control - Missing or incorrect access restrictions

**[Cryptography]** (OWASP A02:2021)

- CWE-327: Broken or Risky Cryptographic Algorithm - Weak encryption/hashing
- CWE-759: One-Way Hash without Salt - Enables rainbow table attacks
- CWE-326: Inadequate Encryption Strength - Key size too small
- CWE-295: Improper Certificate Validation - Missing or incorrect TLS verification

**[Input Validation and Representation]** (OWASP A03:2021)

- CWE-20: Improper Input Validation - Failure to validate or incorrectly validate input
- CWE-79: Cross-site Scripting (XSS) - Improper neutralization of script in web output
- CWE-129: Improper Validation of Array Index - Out-of-bounds read/write
- CWE-1333: Inefficient Regular Expression - ReDoS via catastrophic backtracking

**[Resource Management]** (OWASP A04:2021)

- CWE-400: Uncontrolled Resource Consumption - Missing limits on memory/CPU/disk
- CWE-770: Allocation Without Limits - No rate limiting or resource quotas
- CWE-772: Missing Release of Resource - Memory/handle leaks
- CWE-404: Improper Resource Shutdown - Resources not properly closed

**[Error Handling and Logging]** (OWASP A09:2021)

- CWE-209: Error Message Information Exposure - Stack traces in error responses
- CWE-532: Sensitive Information in Log File - Passwords/tokens/PII in logs
- CWE-117: Improper Output Neutralization for Logs - Log injection attacks

**[API and Function Abuse]** (OWASP A08:2021)

- CWE-306: Missing Authentication for Critical Function - API without credentials
- CWE-862: Missing Authorization - Authenticated but not authorized
- CWE-426: Untrusted Search Path - Loading resources from untrusted locations
- CWE-502: Deserialization of Untrusted Data - Object injection attacks

**[Race Conditions and Concurrency]**

- CWE-362: Race Condition - Concurrent access to shared resource
- CWE-367: TOCTOU Race Condition - Time-of-check time-of-use vulnerability

**[Code Quality and Maintainability]**

- CWE-484: Omitted Break Statement - Unintended switch fallthrough
- CWE-665: Improper Initialization - Variables used before assignment
- CWE-1321: Prototype Pollution - Modification of object prototypes

**[Agentic Security]** (OWASP Agentic Top 10:2026)

- ASI01/CWE-94: Agent Goal Hijack - Untrusted input in system prompts
- ASI02/CWE-22: Tool Misuse - MCP tool parameter validation failures
- ASI03/CWE-522: Identity Abuse - Credentials exposed in agent context
- ASI04/CWE-426: Supply Chain - Unvalidated MCP server loading
- ASI05/CWE-94: Code Execution - ExpandString or Invoke-Expression with input
- ASI06/CWE-502: Memory Poisoning - Malicious data in agent memory systems
- ASI07: Inter-Agent Communication - Unsigned or unvalidated agent-to-agent messages
- ASI08/CWE-703: Cascading Failures - Error propagation across agent workflows
- ASI09/CWE-346: Trust Exploitation - Origin validation errors, UI misrepresentation
- ASI10/CWE-284: Rogue Agents - Unauthorized agent execution or scope expansion
