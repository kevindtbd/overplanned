# Cloud Deployment Plan — Overplanned Beta

**Date:** 2026-02-24
**Goal:** Deploy Overplanned to GCP Cloud Run for beta launch
**Domain:** www.overplanned.app
**Budget:** ~$7-15/mo

---

## Architecture

```
              www.overplanned.app
                      |
               [Cloud Run: web]     <- public, custom domain, beta-gated
              Next.js 14 standalone
                      |
                Cloud SQL
                (Postgres 16)
                via Auth Proxy
```

**What's deployed:** 1 Cloud Run service (Next.js) + Cloud SQL
**What's NOT deployed:** FastAPI, Redis, Qdrant, scrapers (run locally when needed)
**Qdrant:** Stubbed secrets for now. Self-hosted on Cloud Run when two-tower model goes live (~Month 9). NOT Qdrant Cloud managed tier.
**Rollback strategy:** Git revert bad commit, push to main, Cloud Build redeploys

## Decisions Made (Brainstorm + Deepening)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Environment count | Single prod | Beta, hand-picked users, add staging later |
| Managed services | Cloud SQL only | Self-host nothing else; Qdrant self-hosted on Cloud Run when needed |
| Redis | Not deployed | Cache-only use case, not needed at beta scale |
| FastAPI/scrapers | Not deployed | Run locally to seed data, no 24/7 spend |
| DB connection | Cloud SQL Auth Proxy | Built into Cloud Run, handles auth + encryption |
| Session strategy | JWT (switching from database) | Eliminates 3 DB queries per page load |
| Beta gate | One-time code at signup | Code validates once, user gets `beta` role, never asked again |
| OAuth providers | Google only | Apple/Facebook buttons commented out, not configured |
| Rollback | Git revert + push | Simple, auditable, works with Cloud Build flow |

## GCP State (Already Provisioned)

- GCP Project: `overplanned-app`
- APIs enabled: Cloud Run, Cloud SQL, Secret Manager, Cloud Build, Artifact Registry
- Cloud SQL: Postgres 16 instance, `overplanned` database + user
- Secrets in Secret Manager: Anthropic, Google OAuth, NextAuth, Stripe (test), Resend, Sentry, Database URL
- Google OAuth: app created, redirect URI set for localhost (needs prod URI added)
- Sentry: project created, DSN saved

## GCP State (Still Needed)

- Artifact Registry repository (`overplanned` in `us-central1`)
- Cloud Build trigger (push to `main`)
- Cloud Run service (`overplanned-web`)
- Custom domain mapping on Cloud Run
- DNS CNAME record
- Qdrant Cloud free cluster
- Prisma migration against Cloud SQL
- Prod OAuth redirect URI
- `BETA_CODE` secret
- Updated `DATABASE_URL` (Unix socket format for Auth Proxy)
- Updated `NEXTAUTH_URL` (`https://www.overplanned.app`)

---

## Phase 0: Pre-Flight Code Changes

### 0.1 — Create `/api/health` route (MUST)
Dockerfile.web healthcheck expects `GET /api/health` to return 200.
No route exists. Create `apps/web/app/api/health/route.ts`.

```typescript
// Return 200 + basic status
export async function GET() {
  return Response.json({ status: "ok", timestamp: new Date().toISOString() });
}
```

### 0.2 — Beta code gate on signup (MUST)
One-time code entry before Google OAuth. Flow:
1. User clicks "Continue with Google" on `/auth/signin`
2. If no `beta_validated` cookie, show beta code input first
3. Code validates against `BETA_CODE` env var (from Secret Manager)
4. If valid, set `beta_validated` cookie, proceed with OAuth
5. Cookie persists — returning users skip the gate

Alternative: add a beta code field directly on the signin page, validate before `signIn("google")` fires.

### 0.3 — Switch session strategy: database -> JWT (MUST)
In `apps/web/lib/auth/config.ts`:
- Change `strategy: "database"` to `strategy: "jwt"`
- Add `jwt` callback to encode `subscriptionTier` + `systemRole` into token
- Update `session` callback to read from `token` instead of `user`
- Remove `enforceConcurrentSessionLimit` call (not possible with JWT)
- Update middleware cookie name check (JWT uses different cookie)

### 0.4 — Comment out Apple + Facebook OAuth buttons (MUST)
In `apps/web/app/auth/signin/page.tsx`:
- Comment out Apple and Facebook button JSX (both desktop and mobile variants)
- Keep code intact for future re-enablement

### 0.5 — Gate `/dev/tokens` from production (MUST)
Design token swatch page at `apps/web/app/dev/tokens/page.tsx` has no auth guard.
Options:
- Add env check at top of component: if NODE_ENV !== development, redirect
- Or add `/dev/` to middleware blocked paths in production

### 0.6 — Update `cloudbuild.yaml` (MUST)
- Remove `build-api`, `push-api`, `deploy-api` steps
- Remove API image from `images` list
- Add `--add-cloudsql-instances=overplanned-app:us-central1:INSTANCE_NAME` to deploy-web
- Add `--set-secrets` for: `BETA_CODE`, Qdrant Cloud URL/key
- Consider adding a test step (npm test) before build

### 0.7 — Update middleware for JWT (MUST)
In `apps/web/middleware.ts`:
- Session cookie check: JWT sessions use `next-auth.session-token` (no `__Secure-` prefix change needed, NextAuth handles this)
- Verify the cookie check still works with JWT strategy
- Comment on lines 44-46 about server-side checks no longer applies — JWT carries claims

### 0.8 — Verify `.gitignore` (MUST)
Confirm `.env`, `.env.local`, `.env.production` are all gitignored.

**Phase 0 Checkpoint:**
- `docker build -f Dockerfile.web .` succeeds locally
- Health endpoint returns 200
- Beta gate blocks without code, allows with code
- JWT sessions work (login, session persists, user.subscriptionTier populated)
- Apple/Facebook buttons hidden
- `/dev/tokens` blocked in production mode

---

## Phase 1: GCP Wiring

### 1.1 — Artifact Registry
```bash
gcloud artifacts repositories create overplanned \
  --repository-format=docker \
  --location=us-central1
```

### 1.2 — Update secrets in Secret Manager
- `DATABASE_URL` -> Unix socket format: `postgresql://overplanned:PASSWORD@/overplanned?host=/cloudsql/overplanned-app:us-central1:INSTANCE_NAME`
- `NEXTAUTH_URL` -> `https://www.overplanned.app`
- Create `BETA_CODE` secret with chosen beta code
- Create `qdrant-url` and `qdrant-api-key` secrets (from Qdrant Cloud)

### 1.3 — Google OAuth
Add authorized redirect URI: `https://www.overplanned.app/api/auth/callback/google`

### 1.4 — Qdrant (DEFERRED)
Qdrant is not needed for beta launch — vector search powers the two-tower model (~Month 9).
Stub `qdrant-url` and `qdrant-api-key` secrets with placeholder values.
When ready: deploy self-hosted Qdrant as a Cloud Run service (not Qdrant Cloud managed tier).

### 1.5 — Cloud Build trigger
```bash
gcloud builds triggers create github \
  --repo-name=overplanned \
  --repo-owner=YOUR_GITHUB_ORG \
  --branch-pattern=^main$ \
  --build-config=cloudbuild.yaml
```

### 1.6 — Run Prisma migration
Connect to Cloud SQL via proxy locally, then:
```bash
DATABASE_URL="postgresql://overplanned:PASSWORD@/overplanned?host=/cloudsql/overplanned-app:us-central1:INSTANCE_NAME" \
  npx prisma migrate deploy --schema=packages/db/prisma/schema.prisma
```

**Phase 1 Checkpoint:**
- `gcloud sql connect` works
- All secrets present and correctly formatted
- Qdrant secrets stubbed with placeholders
- Artifact Registry repo exists
- Cloud Build trigger created
- Prisma migration applied, tables exist

---

## Phase 2: First Deploy

### 2.1 — Manual first deploy
Trigger Cloud Build manually or push to main.
Watch the build in Cloud Build console.

### 2.2 — Verify at *.run.app URL
- Health endpoint returns 200
- Landing page loads
- Beta gate appears on signin

### 2.3 — Map custom domain
```bash
gcloud run domain-mappings create \
  --service=overplanned-web \
  --domain=www.overplanned.app \
  --region=us-central1
```

### 2.4 — DNS
Add CNAME record: `www.overplanned.app` -> `ghs.googlehosted.com`
SSL auto-provisions via Let's Encrypt (may take 15-30 min).

### 2.5 — End-to-end test
1. Visit `https://www.overplanned.app`
2. Landing page loads
3. Click sign in -> beta code gate appears
4. Enter beta code -> Google OAuth flow
5. Create account -> lands on dashboard with `subscriptionTier: beta`
6. Create a trip -> verify Prisma writes to Cloud SQL
7. Check Sentry for any errors

**Phase 2 Checkpoint:**
- Custom domain resolves with valid SSL
- Full signup flow works end-to-end
- No errors in Sentry
- Trip creation writes to Cloud SQL successfully

---

## Phase 3: Monitoring + Hardening

### 3.1 — Sentry -> Discord
Sentry project settings -> Integrations -> Discord.
Authorize server, pick channel, set alert rules (new issue, regression).

### 3.2 — Cloud Monitoring uptime check
Create uptime check on `https://www.overplanned.app/api/health`.
Alert on 2 consecutive failures.

### 3.3 — Cloud SQL backups (MOVED to Phase 1.6)
Already enabled before migration. Verify:
```bash
gcloud sql instances patch INSTANCE_NAME \
  --backup-start-time=04:00 \
  --enable-point-in-time-recovery
```

### 3.4 — Budget alert
Set billing budget alert at $25/mo.

### 3.5 — Review Cloud Run settings
- Confirm `min-instances: 0` (cost) vs `min-instances: 1` (no cold starts, ~$5-10/mo extra)
- Confirm `max-instances: 10` is reasonable
- Confirm memory (512Mi) is sufficient for Next.js standalone

**Phase 3 Checkpoint:**
- Sentry errors appear in Discord
- Uptime check is green
- Backup schedule confirmed
- Budget alert set

---

## Issues Found During Deepening

| Issue | Severity | Status |
|-------|----------|--------|
| No `/api/health` route | Critical | Phase 0.1 |
| Session strategy (database) causes 3 DB queries/page | Critical | Phase 0.3 |
| Apple/Facebook OAuth buttons wired but not configured | Critical | Phase 0.4 |
| `/dev/tokens` page has no prod guard | Important | Phase 0.5 |
| `DATABASE_URL` format wrong for Cloud SQL Auth Proxy | Important | Phase 1.2 |
| Google OAuth missing prod redirect URI | Important | Phase 1.3 |
| Dev-login route properly guarded (3 layers) | OK | No action needed |
| Admin pages protected by `requireAdmin()` | OK | No action needed |
| Middleware needs JWT cookie update | Important | Phase 0.7 |

---

## Agent Review Findings (2026-02-24)

**Reviewers:** Cloud Architect, Security Auditor, Test Engineer
**Verdict:** REVISE then ship — plan is fundamentally sound, no architectural changes needed

### Blockers (Must Fix Before Deploy)

| # | Issue | Source | Impact |
|---|-------|--------|--------|
| 1 | JWT session callback will crash — `user` undefined in `{ session, token }`, `lastActiveAt` + `enforceConcurrentSessionLimit` throw | Architect | App unusable on every auth'd request |
| 2 | Cloud Build `E2_HIGHCPU_8` is NOT free tier — costs $30-60/mo | Architect | Blows $7-15 budget 4x |
| 3 | Dev-login route ships to prod container — one env var from auth bypass | Security | Auth bypass risk |
| 4 | No `/api/health` route — Cloud Run marks service unhealthy | All | Service won't start |
| 5 | No beta gate implemented yet | Security | App fully open |
| 6 | Apple/Facebook OAuth buttons still live, providers not configured | Security | Broken auth flows |
| 7 | `NEXTAUTH_URL` set to prod domain but Phase 2.1 tests at `.run.app` URL | Architect | OAuth fails during first deploy test |
| 8 | DB connection limit: 10 instances x 3 = 30 > db-f1-micro's 25 limit | Architect | Connection exhaustion |

### Important (Fix Same PR)

| # | Issue | Source |
|---|-------|--------|
| 9 | `/dev/tokens` needs server-side `notFound()`, not client-side guard | Security |
| 10 | Beta code: use `crypto.timingSafeEqual` + rate limiting | Security |
| 11 | Add `connect_timeout=10` to DATABASE_URL for cold starts | Architect |
| 12 | Set `--concurrency=40` and `--timeout=30s` on Cloud Run | Architect |
| 13 | Enable Cloud SQL backups BEFORE first migration | Architect |
| 14 | Apex domain redirect (`overplanned.app` -> `www.overplanned.app`) | Architect |
| 15 | Add `.env.production` to `.gitignore` | Security |
| 16 | Remove API `images:` block from cloudbuild.yaml | Architect |
| 17 | Remove orphaned session functions after JWT switch | Test Engineer |

### Test Gaps

| Test | Blocking | Effort |
|------|----------|--------|
| `/api/health` route + test | YES | 15 min |
| Middleware tests (zero today) | YES | 30-45 min |
| Beta code gate tests | YES | 30-45 min |
| Cloud Build test step | No (but should) | 15 min |

### Confirmed Good (No Action)
- Existing 850 Vitest tests won't break from JWT switch (all mock getServerSession at boundary)
- Security headers (CSP, HSTS, X-Frame-Options) already solid in next.config.js
- Container runs non-root, no secrets baked in
- Admin routes server-side protected via `requireAdmin()`
- OAuth redirect validation prevents open redirects
- Dev-login has 3 defense layers (but should still exclude from prod build)

### Plan Revisions Required

**Phase 0.3 (JWT switch)** — expand to include:
- Remove `enforceConcurrentSessionLimit` call and `lastActiveAt` write from session callback
- Move `lastActiveAt` to a debounced API call on app mount
- Remove orphaned functions in `lib/auth/session.ts`
- Add `connection_limit=2&connect_timeout=10` to DATABASE_URL

**Phase 0.5 (dev routes)** — strengthen:
- Add hard `throw` at module scope in dev-login route OR exclude from prod build
- Use server-side `notFound()` layout wrapper for `/dev/*`, not client-side guard
- Block `/dev/*` in middleware for production

**Phase 0.6 (cloudbuild)** — add:
- Change `machineType` to `E2_MEDIUM` (free tier)
- Remove `images:` block for API service
- Add `--concurrency=40 --timeout=30s` to deploy-web
- Add `--add-cloudsql-instances` flag
- Add test step before build

**Phase 1 (GCP wiring)** — reorder:
- Enable Cloud SQL backups BEFORE running migration (was Phase 3.3, move to Phase 1.1)
- Add apex domain redirect via DNS provider

**Phase 2 (first deploy)** — fix sequence:
- Test at `.run.app` URL with temporary NEXTAUTH_URL, OR skip OAuth test until custom domain is mapped

---

## Cost Estimate

| Service | Monthly Cost |
|---------|-------------|
| Cloud Run (web, free tier) | $0 |
| Cloud SQL (Postgres 16, small) | $7-10 |
| Qdrant (deferred, not deployed) | $0 |
| Secret Manager | ~$0.06 |
| Cloud Build (free tier, 120 min/day) | $0 |
| Artifact Registry (storage) | ~$0.10 |
| Custom domain SSL | $0 (auto) |
| **Total** | **~$7-11/mo** |

---

## Out of Scope (Deferred)

- FastAPI service deployment (run locally for seeding)
- Redis (not needed at beta scale)
- Staging environment (add when needed)
- PgBouncer (Cloud SQL Auth Proxy handles connections)
- Qdrant deployment (stub secrets, deploy self-hosted on Cloud Run when two-tower model is ready)
- Apple/Facebook OAuth (buttons commented out)
- Rate limiting (in-memory acceptable for beta)
- CDN / Cloud CDN (Cloud Run handles it fine)
- CI test step in Cloud Build (optional, add if builds are fast enough)
