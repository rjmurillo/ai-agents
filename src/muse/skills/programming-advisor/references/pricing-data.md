# Pricing Data Reference

Use this data to calculate total cost of ownership comparisons. Prices as of 2024.

## Cost Calculation Formula

```
Year N Cost = Setup Cost + (Monthly × 12 × N) + (Maintenance × N)

Where:
- Setup Cost (DIY) = Token Estimate × $0.015/1K tokens (blended rate)
- Maintenance (DIY) = 20% of Setup Cost annually
- Maintenance (SaaS) = $0 (handled by provider)
```

## Token Cost Estimates

| Model | Input (1K tokens) | Output (1K tokens) | Blended Estimate |
|-------|-------------------|--------------------| -----------------|
| Claude Sonnet | $0.003 | $0.015 | ~$0.015/1K |
| Claude Opus | $0.015 | $0.075 | ~$0.06/1K |
| GPT-4 | $0.01 | $0.03 | ~$0.025/1K |

**Rule of thumb:** Estimate $0.015/1K tokens for typical Claude Code usage.

---

## Authentication & Identity

| Service | Free Tier | Starter | Pro | Enterprise |
|---------|-----------|---------|-----|------------|
| **Auth0** | 7,500 MAU | $35/mo (500 MAU) | $240/mo | Custom |
| **Clerk** | 10,000 MAU | $25/mo | $99/mo | Custom |
| **Supabase Auth** | 50,000 MAU | Free w/ Supabase | - | - |
| **Firebase Auth** | Unlimited | Free | Free | Free |
| **WorkOS** | 1M MAU | Free | Enterprise | Custom |
| **Kinde** | 10,500 MAU | $25/mo | $99/mo | Custom |

**DIY Estimate:** 80-150K tokens (~$1.2K-$2.3K setup), 20% annual maintenance

---

## Email Services

| Service | Free Tier | Starter | Growth |
|---------|-----------|---------|--------|
| **Resend** | 3,000/mo | $20/mo (50K) | $80/mo (200K) |
| **SendGrid** | 100/day | $20/mo (50K) | $50/mo (100K) |
| **Postmark** | 100/mo | $15/mo (10K) | $50/mo (50K) |
| **AWS SES** | 62K/mo (w/ EC2) | $0.10/1K | $0.10/1K |
| **Mailgun** | 5,000/mo (3 mo) | $35/mo (50K) | $80/mo (100K) |

**DIY Estimate:** 15-30K tokens (~$225-$450 setup), SMTP config complexity

---

## Payments & Billing

| Service | Transaction Fee | Monthly | Notes |
|---------|-----------------|---------|-------|
| **Stripe** | 2.9% + $0.30 | $0 | Industry standard |
| **Paddle** | 5% + $0.50 | $0 | Handles tax/compliance |
| **LemonSqueezy** | 5% + $0.50 | $0 | Merchant of record |
| **PayPal** | 2.9% + $0.30 | $0 | Consumer familiarity |

**DIY Estimate:** Don't. PCI compliance alone costs $50K+/year.

---

## Database & Backend

| Service | Free Tier | Starter | Pro |
|---------|-----------|---------|-----|
| **Supabase** | 500MB, 2 projects | $25/mo | $599/mo |
| **PlanetScale** | 5GB, 1B reads | $39/mo | $99/mo |
| **Neon** | 512MB | $19/mo | $69/mo |
| **Railway** | $5 credit | Pay-as-you-go | ~$20/mo typical |
| **Vercel Postgres** | 256MB | $20/mo | Included in Pro |

**DIY (self-hosted):** VPS $5-20/mo + maintenance time

---

## File Storage & CDN

| Service | Free Tier | Starter | Notes |
|---------|-----------|---------|-------|
| **Cloudflare R2** | 10GB + 10M requests | $0.015/GB | No egress fees |
| **AWS S3** | 5GB (12 mo) | $0.023/GB | + egress costs |
| **Uploadthing** | 2GB | $10/mo (100GB) | Dev-friendly |
| **Cloudinary** | 25GB | $99/mo | Image transforms |

---

## Search

| Service | Free Tier | Starter | Notes |
|---------|-----------|---------|-------|
| **Algolia** | 10K records | $1/1K records | Fast, expensive at scale |
| **Typesense** | Self-host | $29/mo cloud | Open source |
| **Meilisearch** | Self-host | $30/mo cloud | Easy setup |
| **Elasticsearch** | Self-host | $95/mo cloud | Enterprise features |

**DIY (pg_trgm):** Free with PostgreSQL, good enough for most apps

---

## Monitoring & Error Tracking

| Service | Free Tier | Starter | Team |
|---------|-----------|---------|------|
| **Sentry** | 5K errors/mo | $26/mo | $80/mo |
| **LogRocket** | 1K sessions/mo | $99/mo | $250/mo |
| **Datadog** | 14-day trial | $15/host/mo | + features |
| **Better Stack** | 1 user | $24/mo | $85/mo |

---

## Analytics

| Service | Free Tier | Starter | Notes |
|---------|-----------|---------|-------|
| **Plausible** | 30-day trial | $9/mo (10K) | Privacy-focused |
| **Fathom** | - | $14/mo (100K) | Privacy-focused |
| **PostHog** | 1M events/mo | $0/mo | Product analytics |
| **Mixpanel** | 20M events/mo | $20/mo | Event tracking |
| **Google Analytics** | Unlimited | Free | Privacy concerns |

---

## AI & LLM Integration

| Service | Free Tier | Cost | Notes |
|---------|-----------|------|-------|
| **OpenAI API** | - | Pay-per-token | GPT-4, embeddings |
| **Anthropic API** | - | Pay-per-token | Claude models |
| **Vercel AI SDK** | - | Free (BYO keys) | React hooks |
| **LangChain** | - | Free (BYO keys) | Orchestration |
| **Pinecone** | 100K vectors | $70/mo | Vector DB |
| **Weaviate** | Self-host | $25/mo cloud | Vector DB |

---

## Cron & Background Jobs

| Service | Free Tier | Starter | Notes |
|---------|-----------|---------|-------|
| **Inngest** | 50K runs/mo | $50/mo | Event-driven |
| **Trigger.dev** | 10K runs/mo | $30/mo | Background jobs |
| **Quirrel** | Open source | Self-host | Simple cron |
| **Vercel Cron** | Included | With Vercel | Basic cron |

**DIY (node-cron):** Free, but needs always-on server

---

## Break-Even Analysis Guidelines

### When DIY Makes Sense

| Scenario | Break-even Point |
|----------|------------------|
| Auth (simple) | >100K MAU or custom requirements |
| Email (transactional) | >500K emails/mo |
| Search | >1M records or real-time requirements |
| Payments | Never (compliance costs too high) |
| Analytics | Privacy requirements or >10M events |

### Hidden Costs to Surface

1. **Security audits** - $5K-50K for custom auth
2. **Compliance** - SOC2, GDPR implementation time
3. **On-call burden** - DIY = you're the support
4. **Opportunity cost** - Time not spent on core product
5. **Technical debt** - Custom code needs maintenance forever

### Red Flags for DIY

- "It's just a simple [auth/payment/email] system"
- "We can build it in a weekend"
- "We'll add security later"
- "It's cheaper long-term" (usually false under 10K users)
