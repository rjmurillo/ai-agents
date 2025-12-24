# PR Review: Application Checklist

## Phase 1-2: Context and Acknowledgment

- [ ] Enumerate ALL reviewers (Skill-PR-001)
- [ ] Prioritize cursor[bot] first (Skill-PR-006)
- [ ] Parse each comment independently (Skill-PR-002)
- [ ] **BLOCKING**: Add eyes reaction to EACH comment
- [ ] **BLOCKING**: Verify eyes_count == comment_count via API

## Phase 3-5: Analysis and Response

- [ ] Track 'NEW this session' vs 'DONE prior sessions'
- [ ] For atomic bugs, use Quick Fix path
- [ ] Use correct API (REST vs GraphQL)
- [ ] Reply then resolve each thread

## Phase 6-8: Verification

- [ ] Check for Copilot follow-up PRs
- [ ] Verify addressed_count == total_comment_count
- [ ] Update HANDOFF.md with session summary

## Cumulative Metrics (as of 2025-12-22)

| Reviewer | Total Comments | Signal Rate | Trend |
|----------|----------------|-------------|-------|
| cursor[bot] | 45 | **100%** | Stable |
| Copilot | 459 | ~34% | Declining |
| coderabbitai[bot] | 164 | ~49% | Stable |
| gemini-code-assist[bot] | 49 | ~25% | Stable |
