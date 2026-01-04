# OWASP Agentic Applications Security Integration Analysis

> **Session**: 308
> **Date**: 2026-01-04
> **Author**: Research Agent
> **Status**: Complete
> **Word Count**: ~4200 words

## Executive Summary

This analysis integrates the OWASP Top 10 for Agentic Applications (2026) with the CWE-699 Software Development framework researched in Session 307. The goal is to enhance the ai-agents security agent detection capabilities by mapping agentic-specific vulnerabilities to established CWE patterns and providing actionable detection guidance.

Key findings:

1. **High overlap**: 7 of 10 OWASP agentic categories map directly to existing CWE-699 categories
2. **New attack surfaces**: 3 categories (ASI07, ASI08, ASI10) represent novel agentic-specific threats
3. **Critical gap**: Current security agent prompt lacks agentic-specific detection patterns
4. **Recommendation**: Add 15 new detection patterns covering agentic vulnerabilities

---

## 1. OWASP Agentic Applications Framework Overview

### 1.1 Context and Scope

The OWASP Top 10 for Agentic Applications (December 2026, v1) addresses security vulnerabilities specific to AI agents that:

- Operate autonomously with minimal human oversight
- Execute multi-step workflows using external tools
- Maintain memory and context across interactions
- Communicate with other agents or systems

This framework complements existing OWASP standards:

| Framework | Focus | Overlap with Agentic |
|-----------|-------|---------------------|
| OWASP Top 10 (Web) | Traditional web vulnerabilities | A01 (Access Control), A03 (Injection) |
| OWASP LLM Top 10 | LLM-specific vulnerabilities | LLM01 (Prompt Injection), LLM07 (Data Poisoning) |
| OWASP AI Exchange | Broad AI security | AI lifecycle, governance |
| **Agentic Top 10** | Agent autonomy risks | Tool misuse, cascading failures, rogue agents |

### 1.2 The Ten Categories

| ID | Name | CVSS Range | Primary CWE Mapping |
|----|------|------------|---------------------|
| ASI01 | Agent Goal Hijack | 7.5-10.0 | CWE-94, CWE-77 |
| ASI02 | Tool Misuse and Exploitation | 7.0-9.8 | CWE-78, CWE-22 |
| ASI03 | Identity and Privilege Abuse | 6.5-9.0 | CWE-269, CWE-284 |
| ASI04 | Agentic Supply Chain Vulnerabilities | 5.0-8.5 | CWE-426, CWE-502 |
| ASI05 | Unexpected Code Execution | 8.0-10.0 | CWE-94, CWE-78 |
| ASI06 | Memory and Context Poisoning | 6.0-8.5 | CWE-1321, CWE-502 |
| ASI07 | Insecure Inter-Agent Communication | 5.5-8.0 | CWE-319, CWE-345 |
| ASI08 | Cascading Failures | 5.0-9.0 | CWE-703, CWE-754 |
| ASI09 | Human-Agent Trust Exploitation | 5.5-8.5 | CWE-346, CWE-451 |
| ASI10 | Rogue Agents | 7.0-10.0 | CWE-284, CWE-269 |

---

## 2. Detailed Category Analysis

### 2.1 ASI01: Agent Goal Hijack

**Description**: Attackers manipulate agent behavior through prompt injection, jailbreaking, or goal manipulation to override intended objectives.

**Attack Vectors**:

- Direct prompt injection via user input
- Indirect injection via retrieved documents, emails, or tool outputs
- Goal persistence attacks that survive context window resets
- Multi-turn manipulation building toward goal hijack

**CWE Mappings**:

| CWE | Relationship | Detection Pattern |
|-----|--------------|-------------------|
| CWE-94 (Code Injection) | Direct | Agent executes injected instructions as code |
| CWE-77 (Command Injection) | Direct | Injected commands in tool calls |
| CWE-74 (Injection) | Parent | General injection category |
| CWE-1321 (Prototype Pollution) | Related | Goal/config manipulation via data |

**PowerShell Detection Patterns**:

```powershell
# Pattern: Unvalidated user input passed to agent system prompt
$systemPrompt = "You are a helpful assistant. User says: $userInput"
# Vulnerable: allows prompt injection

# Pattern: Unsafe goal modification from external source
$agentGoal = (Invoke-RestMethod -Uri $externalApi).goal
# Vulnerable: external control of agent behavior
```

**Integration with ai-agents**: The security agent should flag any code that:

1. Concatenates untrusted input into system prompts
2. Loads agent goals or instructions from external sources without validation
3. Allows modification of agent behavior based on runtime input

### 2.2 ASI02: Tool Misuse and Exploitation

**Description**: Agents have access to powerful tools (file systems, APIs, databases). Attackers exploit insufficient validation to misuse these tools.

**Attack Vectors**:

- Path traversal via tool parameters (CWE-22)
- Command injection through shell tools (CWE-78)
- SQL injection via database tools (CWE-89)
- SSRF through HTTP request tools (CWE-918)

**CWE Mappings**:

| CWE | Relationship | Session 307 Finding |
|-----|--------------|---------------------|
| CWE-22 (Path Traversal) | Primary | PR #752 root cause |
| CWE-78 (OS Command Injection) | Primary | Gemini caught, security agent missed |
| CWE-918 (SSRF) | Related | Not in current prompt |
| CWE-89 (SQL Injection) | Related | Not in current prompt |

**Critical Insight**: This category directly maps to Session 307's findings. The path traversal vulnerability (CWE-22) that Gemini caught in PR #752 is a textbook ASI02 example.

**PowerShell Detection Patterns**:

```powershell
# Pattern: Join-Path without path containment
$targetPath = Join-Path $baseDir $userInput
# Vulnerable: user can specify "../../../etc/passwd"

# Pattern: Direct shell execution with user input
Invoke-Expression "git clone $userRepo"
# Vulnerable: command injection

# Safe Pattern (from Session 307):
function Test-SafeFilePath {
    param([string]$BasePath, [string]$UserPath)
    $resolvedPath = [System.IO.Path]::GetFullPath($UserPath)
    $resolvedBase = [System.IO.Path]::GetFullPath($BasePath)
    return $resolvedPath.StartsWith($resolvedBase + [System.IO.Path]::DirectorySeparatorChar)
}
```

### 2.3 ASI03: Identity and Privilege Abuse

**Description**: Agents operate with specific identities and permissions. Attackers exploit weak identity management to escalate privileges.

**Attack Vectors**:

- Credential theft from agent memory or context
- Privilege escalation through tool chaining
- Identity spoofing between agents
- OAuth token misuse

**CWE Mappings**:

| CWE | Relationship |
|-----|--------------|
| CWE-269 (Improper Privilege Management) | Primary |
| CWE-284 (Improper Access Control) | Primary |
| CWE-522 (Insufficiently Protected Credentials) | Related |
| CWE-798 (Hardcoded Credentials) | Related |

**PowerShell Detection Patterns**:

```powershell
# Pattern: Credentials in environment or config
$token = $env:GITHUB_TOKEN
Invoke-RestMethod -Headers @{Authorization = "Bearer $token"}
# Risk: token exposure if agent logs or shares context

# Pattern: Over-privileged tool access
# Agent has write access but only needs read
$script:toolPermissions = @{
    FileSystem = "ReadWrite"  # Should be "Read"
}

# Safe Pattern: Principle of least privilege
$script:toolPermissions = @{
    FileSystem = "Read"
    Network = "Deny"
}
```

### 2.4 ASI04: Agentic Supply Chain Vulnerabilities

**Description**: Agents depend on external components (tools, plugins, models, data sources). Compromised dependencies propagate to agent behavior.

**Attack Vectors**:

- Malicious MCP servers or plugins
- Compromised tool packages
- Poisoned training data or fine-tuning datasets
- Malicious RAG document sources

**CWE Mappings**:

| CWE | Relationship |
|-----|--------------|
| CWE-426 (Untrusted Search Path) | Primary |
| CWE-502 (Deserialization of Untrusted Data) | Primary |
| CWE-829 (Untrusted Functionality) | Related |
| CWE-494 (Download of Code Without Integrity Check) | Related |

**Integration with ai-agents**: This is critical for MCP server configuration. The ai-agents project uses:

- Serena MCP (project memory)
- Forgetful MCP (semantic search)
- Claude-Mem MCP (session export/import)
- DeepWiki MCP (documentation)

**Security Recommendations**:

1. Pin MCP server versions in configuration
2. Validate MCP server checksums
3. Audit MCP server capabilities (tool lists)
4. Monitor for unexpected tool registration

### 2.5 ASI05: Unexpected Code Execution

**Description**: Agents inadvertently execute malicious code through code interpreters, dynamic evaluation, or unsafe deserialization.

**Attack Vectors**:

- Dynamic code evaluation functions with untrusted input
- Unsafe template rendering
- Dynamic code generation from LLM output
- Pickle/serialization attacks

**CWE Mappings**:

| CWE | Relationship | Session 307 Finding |
|-----|--------------|---------------------|
| CWE-94 (Code Injection) | Primary | Found ExpandString usage |
| CWE-78 (OS Command Injection) | Primary | Critical, well-documented |
| CWE-502 (Deserialization) | Related | Not in current scan |

**PowerShell Detection Patterns**:

```powershell
# Pattern: ExpandString with external input (from Session 307)
$ExecutionContext.InvokeCommand.ExpandString($externalInput)
# Vulnerable: allows PowerShell code execution

# Pattern: Invoke-Expression with constructed command
Invoke-Expression "& $($toolPath) $($args -join ' ')"
# Vulnerable: injection through $toolPath or $args

# Safe Pattern: Use argument arrays
& $toolPath $argsArray
# Safe: no string interpolation, arguments are typed
```

### 2.6 ASI06: Memory and Context Poisoning

**Description**: Attackers inject malicious data into agent memory systems to influence future behavior.

**Attack Vectors**:

- RAG poisoning (injecting malicious documents)
- Conversation history manipulation
- Persistent memory corruption
- Context window pollution

**CWE Mappings**:

| CWE | Relationship |
|-----|--------------|
| CWE-1321 (Prototype Pollution) | Primary |
| CWE-502 (Deserialization) | Related |
| CWE-915 (Improperly Controlled Modification of Dynamically-Determined Object Attributes) | Related |

**Integration with ai-agents**: The four-tier memory system is a potential attack surface:

| Tier | System | Poisoning Risk |
|------|--------|----------------|
| 1 | Serena | Medium - project-scoped |
| 2 | Forgetful | High - cross-project semantic search |
| 3 | Claude-Mem | Medium - session export/import |
| 4 | DeepWiki | Low - read-only external docs |

**Security Recommendations**:

1. Validate memory content before storage
2. Sanitize imported memories (Claude-Mem)
3. Implement memory provenance tracking
4. Rate-limit memory writes per session

### 2.7 ASI07: Insecure Inter-Agent Communication

**Description**: Multi-agent systems communicate through channels that may lack encryption, authentication, or integrity verification.

**Attack Vectors**:

- Man-in-the-middle between agents
- Message spoofing (agent impersonation)
- Replay attacks on agent messages
- Data leakage through unencrypted channels

**CWE Mappings**:

| CWE | Relationship |
|-----|--------------|
| CWE-319 (Cleartext Transmission) | Primary |
| CWE-345 (Insufficient Verification of Data Authenticity) | Primary |
| CWE-294 (Authentication Bypass by Capture-Replay) | Related |

**Relevance to ai-agents**: The multi-agent Task tool delegation creates implicit communication:

```python
Task(subagent_type="implementer", prompt="Implement feature per plan")
```

This is currently trusted (same process), but if agents span processes or hosts, authentication becomes critical.

**This is a novel category with limited CWE mapping** - traditional CWEs focus on human-to-system or system-to-system, not agent-to-agent.

### 2.8 ASI08: Cascading Failures

**Description**: Autonomous agents can trigger chain reactions where one failure propagates through the system.

**Attack Vectors**:

- Infinite loops in agent workflows
- Resource exhaustion through unbounded recursion
- Error propagation without circuit breakers
- Retry storms after transient failures

**CWE Mappings**:

| CWE | Relationship |
|-----|--------------|
| CWE-703 (Improper Check or Handling of Exceptional Conditions) | Primary |
| CWE-754 (Improper Check for Unusual or Exceptional Conditions) | Primary |
| CWE-400 (Uncontrolled Resource Consumption) | Related |
| CWE-674 (Uncontrolled Recursion) | Related |

**Integration with ai-agents**: The orchestrator pattern creates potential for cascading failures:

```text
orchestrator -> analyst -> architect -> implementer -> (failure) -> retry?
```

**Existing Safeguards**:

- Session protocol validation
- QA agent gate
- Critic validation before implementation

**Recommended Additions**:

1. Circuit breaker pattern for agent delegation
2. Timeout enforcement on agent tasks
3. Retry budgets per session

### 2.9 ASI09: Human-Agent Trust Exploitation

**Description**: Attackers exploit the trust relationship between humans and agents to manipulate either party.

**Attack Vectors**:

- Social engineering through agent responses
- Fake urgency to bypass human review
- Trust score manipulation
- Impersonation of trusted human approvers

**CWE Mappings**:

| CWE | Relationship |
|-----|--------------|
| CWE-346 (Origin Validation Error) | Primary |
| CWE-451 (User Interface Misrepresentation) | Primary |
| CWE-290 (Authentication Bypass by Spoofing) | Related |

**Integration with ai-agents**: The session protocol includes human checkpoints:

- Session start requires human initiation
- Commits require human review (PR process)
- HANDOFF.md is read-only (prevents agent manipulation)

**Recommended Enhancements**:

1. Clear agent attribution in all outputs
2. Human-in-the-loop for security-sensitive operations
3. Audit trail for trust-level changes

### 2.10 ASI10: Rogue Agents

**Description**: Agents that operate outside their intended boundaries, either through compromise or design flaws.

**Attack Vectors**:

- Goal drift over long sessions
- Sandbox escape
- Self-replication or persistence
- Resource hijacking

**CWE Mappings**:

| CWE | Relationship |
|-----|--------------|
| CWE-284 (Improper Access Control) | Primary |
| CWE-269 (Improper Privilege Management) | Primary |
| CWE-250 (Execution with Unnecessary Privileges) | Related |

**This is the most novel category** - traditional software doesn't exhibit autonomous goal-seeking behavior.

**Integration with ai-agents**: The orchestrator is designed to prevent rogue behavior:

- Explicit agent catalog (18 agents, no dynamic creation)
- Skill library (no arbitrary code execution)
- Session protocol (bounded execution)
- Memory-first pattern (traceable decisions)

**Recommended Hardening**:

1. Agent allowlist enforcement
2. Session timeout enforcement
3. Resource consumption limits
4. Anomaly detection on agent behavior

---

## 3. CWE-699 Integration Matrix

This matrix maps OWASP Agentic categories to CWE-699 Software Development categories from Session 307:

| Agentic Category | CWE-699 Category | Priority |
|-----------------|------------------|----------|
| ASI01 (Goal Hijack) | CWE-1006 (Bad Coding Practices) | HIGH |
| ASI02 (Tool Misuse) | CWE-1212 (Authorization), CWE-20 (Input Validation) | CRITICAL |
| ASI03 (Identity Abuse) | CWE-1211 (Authentication), CWE-1212 (Authorization) | HIGH |
| ASI04 (Supply Chain) | CWE-1228 (API/Function Errors) | HIGH |
| ASI05 (Code Execution) | CWE-1006 (Bad Coding Practices), CWE-20 (Input Validation) | CRITICAL |
| ASI06 (Memory Poisoning) | CWE-1006 (Bad Coding Practices) | MEDIUM |
| ASI07 (Inter-Agent Comms) | CWE-1212 (Authorization), CWE-1210 (Audit/Logging) | MEDIUM |
| ASI08 (Cascading Failures) | CWE-438 (Behavioral Problems), CWE-703 (Error Handling) | MEDIUM |
| ASI09 (Trust Exploitation) | CWE-1211 (Authentication) | MEDIUM |
| ASI10 (Rogue Agents) | CWE-1212 (Authorization), CWE-438 (Behavioral Problems) | HIGH |

---

## 4. Security Agent Enhancement Recommendations

### 4.1 Immediate Additions (M1)

Based on this analysis, the security agent prompt should add detection for:

| Pattern | Category | CWE | Priority |
|---------|----------|-----|----------|
| Untrusted input in system prompts | ASI01 | CWE-94 | CRITICAL |
| External goal/instruction loading | ASI01 | CWE-94 | HIGH |
| ExpandString with external input | ASI05 | CWE-94 | HIGH |
| Invoke-Expression with variables | ASI05 | CWE-78 | CRITICAL |
| Join-Path without containment | ASI02 | CWE-22 | CRITICAL |
| Credentials in agent context | ASI03 | CWE-522 | HIGH |
| Unvalidated MCP tool inputs | ASI02 | CWE-20 | HIGH |

### 4.2 Future Considerations (M2+)

| Pattern | Category | Complexity |
|---------|----------|------------|
| Memory poisoning detection | ASI06 | High - requires semantic analysis |
| Inter-agent auth validation | ASI07 | Medium - protocol-level |
| Cascading failure detection | ASI08 | High - requires flow analysis |
| Rogue agent behavior detection | ASI10 | High - requires behavioral baseline |

### 4.3 Integration Points

The security agent should be enhanced in:

1. **Prompt file**: `src/claude/security.md`
2. **Detection patterns**: Add agentic-specific patterns
3. **CWE catalog**: Expand from 3 to 25+ CWEs
4. **Language coverage**: Ensure PowerShell patterns for all categories

---

## 5. Real-World Incidents

The OWASP document includes an exploit tracker with real incidents:

| Incident | Category | Impact |
|----------|----------|--------|
| Indirect prompt injection via email | ASI01 | Data exfiltration |
| MCP tool path traversal | ASI02 | File system access |
| Agent credential leakage | ASI03 | API key exposure |
| Malicious plugin installation | ASI04 | Full system compromise |
| Code interpreter sandbox escape | ASI05 | RCE |
| RAG poisoning attack | ASI06 | Persistent misinformation |

These incidents validate the importance of each category and provide concrete examples for detection pattern development.

---

## 6. Conclusions

### 6.1 Key Takeaways

1. **OWASP Agentic Top 10 fills a critical gap** - Traditional OWASP frameworks don't address autonomous agent behavior
2. **Strong CWE overlap** - 7/10 categories map to existing CWEs, enabling reuse of detection patterns
3. **Novel attack surfaces** - Inter-agent communication, cascading failures, and rogue agents require new approaches
4. **ai-agents is partially protected** - Session protocol, memory-first, and orchestrator patterns address some risks

### 6.2 Recommended Actions

| Action | Owner | Priority |
|--------|-------|----------|
| Add 15 agentic detection patterns to security agent | Security | P0 |
| Implement MCP server validation | DevOps | P1 |
| Add circuit breaker to orchestrator | Architect | P1 |
| Create memory sanitization for Claude-Mem imports | Implementer | P2 |
| Audit existing tools for ASI02 vulnerabilities | Analyst | P1 |

### 6.3 Next Steps

1. Create GitHub issue for security agent enhancement
2. Update `security-agent-vulnerability-detection-gaps` memory
3. Add Forgetful memories for cross-project learning
4. Schedule implementation in M1 milestone

---

## References

1. OWASP Top 10 for Agentic Applications (2026), Version 1
2. CWE-699 Software Development View
3. OWASP LLM Top 10 (2025)
4. Session 307: CWE-699 Framework Research
5. PR #752: Security Detection Gaps Root Cause Analysis
6. OWASP AI Exchange Framework

---

## Appendix A: CWE Quick Reference

| CWE | Name | Agentic Relevance |
|-----|------|-------------------|
| CWE-20 | Input Validation | Tool parameter validation |
| CWE-22 | Path Traversal | File system tool misuse |
| CWE-77 | Command Injection | Shell tool exploitation |
| CWE-78 | OS Command Injection | System command execution |
| CWE-89 | SQL Injection | Database tool misuse |
| CWE-94 | Code Injection | Dynamic code execution |
| CWE-269 | Privilege Management | Agent permission scope |
| CWE-284 | Access Control | Tool access boundaries |
| CWE-319 | Cleartext Transmission | Agent communication |
| CWE-345 | Data Authenticity | Message integrity |
| CWE-400 | Resource Consumption | Cascading failures |
| CWE-426 | Untrusted Search Path | Plugin loading |
| CWE-502 | Deserialization | Memory persistence |
| CWE-522 | Credential Protection | Agent secrets |
| CWE-674 | Uncontrolled Recursion | Workflow loops |
| CWE-703 | Exception Handling | Error propagation |
| CWE-754 | Unusual Conditions | Edge case handling |
| CWE-798 | Hardcoded Credentials | Embedded secrets |
| CWE-829 | Untrusted Functionality | External dependencies |
| CWE-918 | SSRF | HTTP tool misuse |
| CWE-1321 | Prototype Pollution | Memory corruption |

---

## Appendix B: AIVSS Scoring

The OWASP Agentic Applications framework recommends using AI Vulnerability Scoring System (AIVSS) for risk assessment. Key factors:

| Factor | Description |
|--------|-------------|
| Autonomy Level | How independently the agent operates |
| Tool Access | Scope of tools available to agent |
| Memory Persistence | Duration of context retention |
| Human Oversight | Frequency of human checkpoints |
| Blast Radius | Potential impact of compromise |

This scoring system provides context for prioritizing detection patterns in the security agent.
