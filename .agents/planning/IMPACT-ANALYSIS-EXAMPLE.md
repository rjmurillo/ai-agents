# Impact Analysis Framework - Example Workflow

This document provides a concrete example of using the Multi-Agent Impact Analysis Framework during the planning phase.

## Scenario: Implement OAuth 2.0 Authentication

A user requests: "Plan implementation of OAuth 2.0 authentication for the application"

## Step 1: Planner Analyzes Scope

The planner identifies this as a **multi-domain change** affecting:

- **Code**: New authentication modules, refactoring existing auth
- **Architecture**: New authentication pattern, security boundaries
- **Security**: Critical - new attack surface, sensitive data handling
- **Operations**: Secrets management, environment configuration
- **Quality**: Comprehensive security testing required

**Decision**: Trigger Multi-Agent Impact Analysis

## Step 2: Planner Orchestrates Consultations

The planner invokes each specialist agent with structured prompts:

### 2.1 Implementer Consultation

```text
Task(subagent_type="implementer", prompt="""
Impact Analysis Request: OAuth 2.0 Authentication Implementation

**Context**: Add OAuth 2.0 authentication to replace current basic auth system

**Scope**: 
- New OAuth client library integration
- Refactor existing authentication middleware
- Token storage and refresh logic
- User session management updates

**Analysis Required**:
1. Identify impacts in code structure and maintainability
2. List affected files/modules
3. Identify code quality risks
4. Recommend implementation patterns
5. Estimate complexity (Low/Medium/High)

**Deliverable**: Save findings to `.agents/planning/impact-analysis-oauth-code.md`
""")
```

**Result**: Implementer creates impact-analysis-oauth-code.md

- **Complexity**: Medium
- **Affected modules**: 12 files across auth, middleware, session layers
- **Key risks**: Thread-safety in token refresh, existing auth pattern incompatibility
- **Recommendation**: Use factory pattern for OAuth clients, refactor auth middleware first

### 2.2 Architect Consultation

```text
Task(subagent_type="architect", prompt="""
Impact Analysis Request: OAuth 2.0 Authentication Implementation

**Context**: Add OAuth 2.0 authentication to replace current basic auth system

**Scope**: Architectural changes to support OAuth flow

**Analysis Required**:
1. Verify alignment with existing ADRs
2. Identify required architectural patterns
3. Detect potential design conflicts
4. Assess long-term implications
5. Determine if new ADR needed

**Deliverable**: Save findings to `.agents/planning/impact-analysis-oauth-architecture.md`
""")
```

**Result**: Architect creates impact-analysis-oauth-architecture.md

- **Complexity**: Low
- **ADR alignment**: Aligns with ADR-015 (stateless authentication)
- **New pattern**: OAuth 2.0 Authorization Code Flow
- **Recommendation**: Create ADR-027 for OAuth integration strategy

### 2.3 Security Consultation

```text
Task(subagent_type="security", prompt="""
Impact Analysis Request: OAuth 2.0 Authentication Implementation

**Context**: Add OAuth 2.0 authentication, handling sensitive tokens

**Scope**: Security implications of OAuth implementation

**Analysis Required**:
1. Assess attack surface changes
2. Identify new threat vectors
3. Determine required security controls
4. Evaluate compliance implications
5. Estimate security testing needs

**Deliverable**: Save findings to `.agents/planning/impact-analysis-oauth-security.md`
""")
```

**Result**: Security creates impact-analysis-oauth-security.md

- **Complexity**: High
- **Attack surface**: New token endpoints, redirect URIs, token storage
- **Critical threats**: 
  - Token leakage via logs/errors (STRIDE: Information Disclosure)
  - CSRF on OAuth callback (STRIDE: Spoofing)
  - Open redirect vulnerabilities (STRIDE: Spoofing)
- **Required controls**:
  - P0: Secure token storage (encrypted at rest)
  - P0: PKCE (Proof Key for Code Exchange)
  - P0: State parameter validation
  - P1: Token rotation policy
- **Recommendation**: Full penetration testing required

### 2.4 DevOps Consultation

```text
Task(subagent_type="devops", prompt="""
Impact Analysis Request: OAuth 2.0 Authentication Implementation

**Context**: OAuth requires client secrets, redirect URIs in configuration

**Scope**: Build, deployment, and infrastructure changes

**Analysis Required**:
1. Assess build pipeline impact
2. Identify deployment changes needed
3. Determine infrastructure requirements
4. Evaluate secrets management needs
5. Identify configuration changes

**Deliverable**: Save findings to `.agents/planning/impact-analysis-oauth-devops.md`
""")
```

**Result**: DevOps creates impact-analysis-oauth-devops.md

- **Complexity**: Medium
- **Infrastructure**: 
  - New secrets: `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_REDIRECT_URI`
  - Environment-specific OAuth provider URLs
- **Build changes**: 
  - Add OAuth library to dependencies
  - Update integration tests (need OAuth mock server)
- **Deployment**: 
  - Zero downtime requirement - feature flag needed
  - Rollback strategy: Keep basic auth as fallback for 1 release cycle
- **Recommendation**: Use Azure Key Vault for secrets, not environment variables

### 2.5 QA Consultation

```text
Task(subagent_type="qa", prompt="""
Impact Analysis Request: OAuth 2.0 Authentication Implementation

**Context**: OAuth 2.0 authentication with security-critical flows

**Scope**: Testing requirements and quality assurance

**Analysis Required**:
1. Identify required test types
2. Determine coverage targets
3. Assess hard-to-test scenarios
4. Identify quality risks
5. Estimate testing effort

**Deliverable**: Save findings to `.agents/planning/impact-analysis-oauth-qa.md`
""")
```

**Result**: QA creates impact-analysis-oauth-qa.md

- **Complexity**: High
- **Required test types**:
  - Unit: OAuth client wrapper, token handlers (90% coverage target)
  - Integration: Full OAuth flow with mock provider (all flows)
  - Security: OWASP security test cases (comprehensive)
  - E2E: User authentication journeys (5 critical paths)
  - Performance: Token refresh under load (baseline established)
- **Hard-to-test scenarios**:
  - OAuth provider downtime handling
  - Token expiration edge cases
  - Concurrent token refresh requests
- **Recommendation**: Set up WireMock for OAuth provider simulation

## Step 3: Planner Aggregates Findings

The planner synthesizes all consultation results into the comprehensive plan:

### Aggregated Impact Summary

**Consultations Completed**:

- [x] Implementer - Complexity: Medium
- [x] Architect - Complexity: Low
- [x] Security - Complexity: High
- [x] DevOps - Complexity: Medium
- [x] QA - Complexity: High

### Cross-Domain Risks

| Risk | Affected Domains | Priority | Mitigation |
|------|------------------|----------|------------|
| Token leakage in logs | Code, Security | P0 | Implement token sanitization in logging layer |
| OAuth provider outage | Code, Operations, Quality | P1 | Implement circuit breaker pattern + fallback |
| Secret rotation complexity | Security, Operations | P1 | Automate via Key Vault integration |
| Testing OAuth flows | Code, Quality | P1 | Deploy WireMock in CI pipeline |

### Integrated Recommendations

Based on specialist consultations:

1. **Phase implementation**: Start with ADR creation, then refactor auth middleware, finally add OAuth
2. **Security-first approach**: Complete security controls before feature flag enabled
3. **Infrastructure ready**: Set up Key Vault integration in Dev/Staging before code changes
4. **Testing infrastructure**: Deploy OAuth mock server in CI before implementation begins
5. **Gradual rollout**: Feature flag → 10% users → 50% → 100% over 2 weeks

### Overall Complexity Assessment

- **Code**: Medium
- **Architecture**: Low
- **Security**: High
- **Operations**: Medium
- **Quality**: High
- **Overall**: **High** - Security-critical change requiring careful implementation

### Recommendation

**Proceed with caution**. This is a high-complexity, security-critical change requiring:

- 3-4 week implementation timeline
- Security review at design and implementation phases
- Phased rollout with monitoring
- Comprehensive security testing before production

## Step 4: Route to Critic

The planner completes the plan with all impact analyses integrated and routes to the critic agent for validation.

The critic reviews:

- ✅ All specialist consultations completed
- ✅ Cross-domain risks identified and mitigated
- ✅ Implementation sequence logical (infrastructure → code → testing)
- ✅ Security concerns appropriately prioritized
- ✅ Rollback strategy defined

**Critic verdict**: Plan approved with recommendations integrated

## Step 5: Implementation Begins

With critic approval, the plan proceeds to implementation with:

- Clear understanding of all impacts across domains
- Risks identified and mitigation strategies in place
- Realistic complexity assessment
- Coordinated approach across code, architecture, security, operations, and quality

## Benefits Realized

The Multi-Agent Impact Analysis Framework ensured:

1. **No surprises**: Security risks identified before coding began
2. **Coordinated approach**: DevOps prepared Key Vault before implementation needed it
3. **Quality built-in**: Testing infrastructure ready when tests written
4. **Realistic estimates**: 3-4 week timeline vs. initial 1-week estimate
5. **Risk mitigation**: All P0/P1 risks addressed in plan before implementation

## Files Created

Impact analysis artifacts saved for future reference:

```text
.agents/planning/
├── impact-analysis-oauth-code.md
├── impact-analysis-oauth-architecture.md
├── impact-analysis-oauth-security.md
├── impact-analysis-oauth-devops.md
├── impact-analysis-oauth-qa.md
└── oauth-2-implementation-plan.md (final plan)
```

These artifacts serve as:

- Documentation of decision rationale
- Reference for similar future changes
- Audit trail for compliance
- Knowledge base for team learning
