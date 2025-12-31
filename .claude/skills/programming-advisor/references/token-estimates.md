# Token Burn Estimation Guide

## Understanding Token Economics

### Token Cost Factors

1. **Input Tokens**: Your prompts, code context, error messages
2. **Output Tokens**: Generated code, explanations, iterations
3. **Iteration Multiplier**: Rarely works first try - multiply by 2-5x

### Estimation Formula

```
Total Tokens ≈ (Initial Prompt + Code Context) × Iterations + Output Tokens × Iterations
```

**Rule of thumb**: `LOC × 50-100 tokens` for simple code, `LOC × 100-200` for complex logic

## Detailed Estimates by Category

### Scripts & Utilities

| Task | LOC Est. | Tokens (Optimistic) | Tokens (Realistic) | Notes |
|------|----------|---------------------|--------------------| ------|
| File renamer | 20-50 | 2-5K | 8-15K | Edge cases add iterations |
| CSV processor | 50-100 | 5-10K | 15-30K | Data format issues |
| API wrapper | 100-200 | 10-20K | 30-60K | Auth, error handling |
| CLI tool | 150-300 | 15-30K | 40-80K | Arg parsing, help text |
| Web scraper | 200-400 | 20-40K | 60-120K | Site changes, anti-bot |

### Frontend Components

| Task | LOC Est. | Tokens (Optimistic) | Tokens (Realistic) | Notes |
|------|----------|---------------------|--------------------| ------|
| Button component | 30-60 | 3-6K | 10-20K | Variants, states |
| Form with validation | 100-200 | 10-20K | 40-80K | Edge cases, UX |
| Data table | 200-400 | 20-40K | 80-150K | Sorting, filtering, pagination |
| Dashboard page | 300-600 | 30-60K | 100-200K | Multiple components |
| Full SPA | 1000+ | 100K+ | 300K+ | Routing, state, API |

### Backend Services

| Task | LOC Est. | Tokens (Optimistic) | Tokens (Realistic) | Notes |
|------|----------|---------------------|--------------------| ------|
| REST endpoint | 50-100 | 5-10K | 20-40K | Validation, errors |
| Auth system | 300-500 | 30-50K | 100-200K | Security critical |
| CRUD API | 200-400 | 20-40K | 60-120K | Relations, validation |
| Background jobs | 150-300 | 15-30K | 50-100K | Retry logic, monitoring |
| Full API service | 1000+ | 100K+ | 300-500K | Multiple endpoints |

### DevOps & Infrastructure

| Task | LOC Est. | Tokens (Optimistic) | Tokens (Realistic) | Notes |
|------|----------|---------------------|--------------------| ------|
| Dockerfile | 20-50 | 2-5K | 10-20K | Multi-stage, optimization |
| CI/CD pipeline | 50-150 | 5-15K | 20-50K | Platform-specific |
| Terraform module | 100-300 | 10-30K | 40-100K | State, dependencies |
| K8s manifests | 100-200 | 10-20K | 30-80K | Resources, networking |

## Iteration Multipliers

| Scenario | Multiplier | Why |
|----------|------------|-----|
| Happy path only | 1-2x | Best case |
| Edge cases needed | 2-3x | Error handling |
| Integration issues | 3-5x | External dependencies |
| Performance tuning | 2-4x | Optimization cycles |
| Security review | 2-3x | Vulnerabilities found |
| UI/UX polish | 3-5x | Design iterations |

## Hidden Token Costs

Often overlooked:
- **Debugging sessions**: 10-50K per bug hunt
- **Refactoring**: 50-100% of original cost
- **Documentation**: 20-50% of code tokens
- **Test writing**: 50-100% of code tokens
- **Code review fixes**: 10-30% additional

## Cost Translation (Approximate)

At typical API rates (~$3/1M input, ~$15/1M output):

| Token Range | Approx. Cost |
|-------------|--------------|
| 10K | $0.05-0.15 |
| 50K | $0.25-0.75 |
| 100K | $0.50-1.50 |
| 500K | $2.50-7.50 |
| 1M+ | $5.00-15.00+ |

## Red Flags: When Vibe Coding Gets Expensive

🚨 **High token burn indicators:**
- "Can you also add..." (scope creep)
- Complex state management
- Multiple external API integrations  
- Real-time features (WebSocket, SSE)
- File uploads/processing
- Payment/billing systems
- Multi-tenant architecture
- Offline-first capabilities

## When Vibe Coding Makes Sense

✅ **Efficient use cases:**
- Glue code between existing libraries
- One-off data transformation scripts
- Prototyping to validate ideas (throw away after)
- Learning exercises (explicit goal)
- Highly domain-specific logic
- No existing solution found after searching
