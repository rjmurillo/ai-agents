---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-01-fix-4813.json
qaCommit: 8c2ffaad25a11c2bb5b40a721c5e3440d7e59a70
---
# QA Report: Exclude references/ from agent classifier

## Verdict: PASS

## Test Results

| Suite | Tests | Result |
|-------|-------|--------|
| tests/validation/test_check_agent_skill_discriminator.py | 33 | PASS |

## Verification

Reproduction from issue now outputs "No changed agent definitions to score".

## Coverage

- 2 affected reference files tested
- Edge case: arbitrary references/ subdir tested
- Negative: real agent in subdir still correctly detected
