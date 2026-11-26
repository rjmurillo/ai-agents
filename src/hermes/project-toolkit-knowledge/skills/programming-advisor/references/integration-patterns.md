# Integration Patterns Reference

<!-- doc-accuracy: external-sdk NextAuth -- TypeScript examples use NextAuth, Prisma, and TanStack Query, not this repository -->

## Package Manager Detection

| File | Package Manager | Install Command |
|------|-----------------|-----------------|
| `package.json` + `package-lock.json` | npm | `npm install` |
| `package.json` + `yarn.lock` | yarn | `yarn add` |
| `package.json` + `pnpm-lock.yaml` | pnpm | `pnpm add` |
| `package.json` + `bun.lockb` | bun | `bun add` |
| `requirements.txt` | pip | `pip install` |
| `pyproject.toml` (poetry) | poetry | `poetry add` |
| `pyproject.toml` (uv) | uv | `uv add` |
| `Pipfile` | pipenv | `pipenv install` |
| `Cargo.toml` | cargo | `cargo add` |
| `go.mod` | go | `go get` |
| `Gemfile` | bundler | `bundle add` |
| `composer.json` | composer | `composer require` |

## Framework Detection

### JavaScript/TypeScript

| Indicator | Framework | Typical Structure |
|-----------|-----------|-------------------|
| `next.config.js` | Next.js | `app/` or `pages/`, `components/` |
| `nuxt.config.ts` | Nuxt | `pages/`, `components/`, `composables/` |
| `vite.config.ts` + React | Vite + React | `src/`, `src/components/` |
| `angular.json` | Angular | `src/app/`, `src/app/components/` |
| `svelte.config.js` | SvelteKit | `src/routes/`, `src/lib/` |
| `remix.config.js` | Remix | `app/routes/`, `app/components/` |
| `astro.config.mjs` | Astro | `src/pages/`, `src/components/` |

### Python

| Indicator | Framework | Typical Structure |
|-----------|-----------|-------------------|
| `manage.py` | Django | `app/`, `app/views.py`, `app/models.py` |
| `app.py` + Flask import | Flask | `app/`, `templates/`, `static/` |
| `main.py` + FastAPI import | FastAPI | `app/`, `app/routers/`, `app/models/` |

### Ruby

| Indicator | Framework | Typical Structure |
|-----------|-----------|-------------------|
| `Gemfile` + Rails gems | Rails | `app/models/`, `app/controllers/`, `app/views/` |
| `config.ru` + Sinatra | Sinatra | `app.rb`, `views/` |

## Common Integration Locations

### React/Next.js Projects

```
src/
├── components/     # Reusable UI components
├── hooks/          # Custom React hooks
├── lib/            # Utility functions, API clients
├── services/       # External service integrations
├── utils/          # Helper functions
├── types/          # TypeScript type definitions
└── schemas/        # Validation schemas (Zod, Yup)
```

### API/Backend Projects

```
src/
├── controllers/    # Request handlers
├── services/       # Business logic
├── models/         # Data models
├── middleware/     # Express/Fastify middleware
├── utils/          # Helpers
├── config/         # Configuration
└── types/          # Type definitions
```

## Starter Code Patterns

### Form Validation (Zod + React Hook Form)

```typescript
// src/schemas/user.ts
import { z } from 'zod'

export const userSchema = z.object({
  email: z.string().email('Invalid email'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
})

export type UserFormData = z.infer<typeof userSchema>
```

```typescript
// src/components/UserForm.tsx
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { userSchema, type UserFormData } from '@/schemas/user'

type UserFormProps = {
  createUser: (data: UserFormData) => Promise<void>
}

export function UserForm({ createUser }: UserFormProps) {
  const { register, handleSubmit, reset, setError, formState: { errors, isSubmitting } } = useForm<UserFormData>({
    resolver: zodResolver(userSchema),
  })

  const onSubmit = async (data: UserFormData) => {
    try {
      await createUser(data)
      reset()
    } catch {
      setError('root', { message: 'Could not create the account.' })
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <input {...register('email')} />
      {errors.email && <span>{errors.email.message}</span>}

      <input type="password" {...register('password')} />
      {errors.password && <span>{errors.password.message}</span>}

      {errors.root && <span role="alert">{errors.root.message}</span>}
      <button type="submit" disabled={isSubmitting}>Submit</button>
    </form>
  )
}
```

### Data Fetching (TanStack Query)

These hooks assume same-origin `/users` routes with JSON responses.

```typescript
// src/hooks/useUsers.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UserFormData } from '@/schemas/user'

type User = { id: string; email: string }

async function requestUsers<T>(init?: RequestInit): Promise<T> {
  const response = await fetch('/users', init)
  if (!response.ok) throw new Error(`User request failed (${response.status})`)
  return response.json()
}

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: ({ signal }) => requestUsers<User[]>({ signal }),
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: UserFormData) => requestUsers<User>({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })
}
```

### State Management (Zustand)

```typescript
// src/stores/userStore.ts
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// Persist display preferences only. The auth provider owns the session.
type User = { displayName: string }

interface UserState {
  user: User | null
  setUser: (user: User) => void
  clearUser: () => void
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      user: null,
      setUser: (user) => set({ user }),
      clearUser: () => set({ user: null }),
    }),
    { name: 'user-storage' }
  )
)
```

### Authentication (NextAuth.js)

This App Router handler uses NextAuth.js v4. Set `NEXTAUTH_SECRET` and the GitHub OAuth credentials on the server.

```typescript
// src/app/api/auth/[...nextauth]/route.ts
import NextAuth from 'next-auth'
import GitHubProvider from 'next-auth/providers/github'

const { GITHUB_ID, GITHUB_SECRET, NEXTAUTH_SECRET } = process.env
if (!GITHUB_ID || !GITHUB_SECRET || !NEXTAUTH_SECRET) {
  throw new Error('Missing server-side GitHub OAuth configuration')
}

const handler = NextAuth({
  secret: NEXTAUTH_SECRET,
  providers: [
    GitHubProvider({
      clientId: GITHUB_ID,
      clientSecret: GITHUB_SECRET,
    }),
  ],
})

export { handler as GET, handler as POST }
```

### Database (Prisma)

Generate the Prisma 5 client with `npx prisma generate` after saving the schema.

```prisma
// prisma/schema.prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

model User {
  id        String   @id @default(cuid())
  email     String   @unique
  name      String?
  createdAt DateTime @default(now())
}
```

```typescript
// src/lib/prisma.ts
import { PrismaClient } from '@prisma/client'

const globalForPrisma = globalThis as typeof globalThis & { prisma?: PrismaClient }

export const prisma = globalForPrisma.prisma ?? new PrismaClient()

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma
```

## Version Compatibility Notes

| Library | React Version | Node Version | Notes |
|---------|---------------|--------------|-------|
| React Query v5 | 18+ | 18+ | Major API changes from v4 |
| Next.js 14 | 18+ | 18.17+ | App Router is default |
| Zustand v4 | 16.8+ | - | Hooks-based API |
| Prisma 5 | - | 16.13+ | Rust-based engine |
| tRPC v11 | 18+ | 18+ | Requires TypeScript 5+ |
