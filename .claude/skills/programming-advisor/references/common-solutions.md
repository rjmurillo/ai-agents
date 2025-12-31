# Common Solutions - Don't Reinvent These

## Authentication & Authorization

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| User auth | Auth0, Clerk, Supabase Auth, Firebase Auth | Security critical, session mgmt, OAuth is complex |
| API auth | JWT libraries, Passport.js, jose | Crypto is easy to get wrong |
| RBAC/Permissions | CASL, Casbin, AccessControl | Edge cases everywhere |

## Data Handling

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| Form validation | Zod, Yup, Joi, Valibot | Schema evolution, error messages |
| Date/time | date-fns, dayjs, Luxon, Temporal | Timezones are nightmares |
| State management | Zustand, Redux Toolkit, Jotai, Valtio | Devtools, persistence, middleware |
| Data fetching | TanStack Query, SWR, RTK Query | Caching, deduplication, revalidation |

## UI Components

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| Component library | shadcn/ui, Radix, Headless UI, Mantine | Accessibility is hard |
| Data tables | TanStack Table, AG Grid, react-table | Sorting, filtering, virtual scroll |
| Forms | React Hook Form, Formik, Final Form | Validation, arrays, nested fields |
| Charts | Recharts, Chart.js, Nivo, Visx | Responsive, animations, accessibility |
| Rich text editor | Tiptap, Slate, Lexical, Quill | Collaborative editing, formats |

## Backend Infrastructure

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| ORM/Database | Prisma, Drizzle, TypeORM, Kysely | Migrations, types, query building |
| Job queues | BullMQ, Agenda, Graphile Worker | Retry logic, monitoring, scaling |
| Caching | Redis clients, node-cache, keyv | Invalidation strategies |
| Rate limiting | rate-limiter-flexible, bottleneck | Distributed systems complexity |
| File uploads | uploadthing, Multer, Filepond | Chunking, resumable, streaming |

## API & Networking

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| HTTP client | Axios, ky, ofetch, got | Interceptors, retry, timeout |
| WebSocket | Socket.io, ws, Sockette | Reconnection, rooms, namespaces |
| API framework | Express, Fastify, Hono, Elysia | Middleware, routing, validation |
| GraphQL | Apollo, URQL, graphql-request | Caching, optimistic updates |
| tRPC | tRPC | End-to-end type safety |

## CLI & DevTools

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| CLI framework | Commander, yargs, oclif, Cliffy | Help text, completions, plugins |
| Logging | Pino, Winston, Bunyan | Levels, transports, formatting |
| Config mgmt | dotenv, cosmiconfig, conf | Env vars, file formats, defaults |
| Process mgmt | PM2, nodemon, tsx | Watch mode, clustering, logs |

## Testing

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| Unit testing | Vitest, Jest, Mocha | Mocking, coverage, snapshots |
| E2E testing | Playwright, Cypress, Puppeteer | Browser automation is complex |
| API testing | Supertest, Pactum, msw | Mocking, fixtures |
| Load testing | k6, Artillery, autocannon | Distributed testing, metrics |

## PDF & Documents

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| PDF creation | pdf-lib, jsPDF, PDFKit | Fonts, images, page layout |
| PDF parsing | pdf-parse, pdfjs-dist | Encrypted PDFs, layouts |
| Excel/CSV | SheetJS, ExcelJS, Papa Parse | Formulas, large files, encoding |
| Word docs | docx, mammoth | Complex formatting |

## Email & Notifications

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| Email sending | Resend, SendGrid, Nodemailer, Postmark | Deliverability, templates, tracking |
| Email templates | React Email, MJML | Responsive email is painful |
| Push notifications | Firebase, OneSignal, web-push | Device management, scheduling |

## Payments & Commerce

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| Payments | Stripe, Paddle, LemonSqueezy | PCI compliance, fraud |
| Subscriptions | Stripe Billing, Paddle | Proration, dunning, tax |
| Tax calculation | TaxJar, Avalara, Stripe Tax | Jurisdiction rules change |

## AI & ML

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| LLM integration | LangChain, Vercel AI SDK, LlamaIndex | Streaming, tools, memory |
| Vector DB | Pinecone, Weaviate, ChromaDB, pgvector | Similarity search optimization |
| Embeddings | OpenAI, Cohere, Voyage | Model hosting is expensive |

## DevOps & Deployment

| Problem | Solutions | Why Not to Build |
|---------|-----------|------------------|
| Container orchestration | Docker Compose, Kubernetes | Networking, volumes, scaling |
| CI/CD | GitHub Actions, GitLab CI | Caching, artifacts, secrets |
| Infrastructure | Terraform, Pulumi, SST | State management, drift |
| Monitoring | Sentry, Datadog, Grafana | Alerting, dashboards, retention |

## Search Queries to Find More

When evaluating any task, search:
1. `best {task} library {language} {year}`
2. `{task} open source alternative`
3. `{task} vs alternatives comparison`
4. `awesome-{task}` (GitHub awesome lists)
5. `{task} npm` / `{task} pip` / `{task} crates`
