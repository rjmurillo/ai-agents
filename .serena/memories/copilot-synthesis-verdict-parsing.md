# Copilot Synthesis Verdict Parsing Fix

**Date**: 2025-12-23
**PR**: #296
**Related Issue**: #237

## Problem

The Copilot Context Synthesis workflow was failing to post synthesis comments even when AI generated valid output.

## Root Cause

1. **Prompt Issue**: The `copilot-synthesis.md` prompt had `VERDICT: PASS` at the end of the file, but:
   - It was outside the expected output format code block
   - AI wasn't clearly instructed to include this token in its response

2. **Workflow Issue**: The condition `if: steps.synthesize.outputs.verdict == 'PASS'` was too strict. If AI generated valid content but verdict parsing failed, comment was never posted.

## Solution

1. **Prompt Fix**: Added explicit instruction for AI to output `VERDICT: PASS` at the end of its response
2. **Workflow Fix**: Added fallback condition:
   ```yaml
   verdict == 'PASS' || (findings != '' && copilot-exit-code == '0')
   ```

## Key Insight

When building AI-powered workflows:
- Prompts must explicitly specify ALL required output tokens, not just example them
- Workflow conditions should have fallbacks for parsing failures
- Exit code 0 + non-empty output = successful AI invocation (even if structured parsing fails)

## Debug Pattern

When Copilot synthesis fails to post:
1. Check workflow logs for "Could not parse verdict" error
2. Verify AI exit code (0 = success, 124 = timeout)
3. Check stdout length (0 chars = likely auth issue, >0 = parsing issue)
4. Compare against verdict regex: `VERDICT:[[:space:]]*\([A-Z_]*\)`
