# Skill-security-013: No Blind Suppression

**Statement**: Never use alert suppression (lgtm, nosec, etc) until root cause understood and documented.

**Context**: When security scanner flags issue, suppression is last resort after understanding why alert exists. Suppression without understanding leaves vulnerabilities in place.

**Evidence**: PR #760 commit ddf7052 removed `# lgtm[py/path-injection]` suppression comments after proper fix applied. User feedback: "WANTING TO SUPPRESS LEGITIMATE SECURITY ISSUES WHEN THERE WERE PATCHES PROVIDED". Suppression attempt damaged trust before root cause was addressed.

**Atomicity**: 94% | **Impact**: 9/10

## Pattern

When CodeQL, SAST, or security scanner flags vulnerability:

1. STOP - Do not suppress yet
2. Understand - What is the vulnerability? Why does scanner flag it?
3. Research - Look for examples of correct fixes for this issue type
4. Test - Verify your understanding with adversarial inputs
5. Fix - Apply proper fix that eliminates root cause
6. Document - Add code comments explaining why the fix works
7. THEN suppress - Only suppress if fix proves ineffective AND documented reason exists

Suppression is valid when:
- Root cause confirmed understood
- Fix attempted and tested
- Documented rationale (CWE number, external link, decision)

## Anti-Pattern

Never suppress security alerts to:
- Make CI green faster
- Avoid "extra" work
- Hide alerts without understanding them

This leaves vulnerabilities in production code and damages user trust.
