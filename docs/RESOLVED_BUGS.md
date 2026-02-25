# Resolved Bugs

## 2026-02-25: Beta gate login loop
- **Symptom**: Enter beta code -> Google OAuth -> redirects back to beta modal
- **Root cause**: `betaValidated` was `useState(false)` with no persistence. React re-mounts on OAuth redirect, state resets.
- **Fix**: Persist `beta_validated` in localStorage. Auto-redirect authenticated users from /auth/signin to /dashboard.
- **Files**: `apps/web/app/auth/signin/page.tsx`

## 2026-02-25: Dashboard 401s after re-login
- **Symptom**: All API routes return 401 after logout + login
- **Root cause**: Two issues: (1) JWT callback used `user.subscriptionTier` from PrismaAdapter which only passes standard OAuth fields — custom fields were undefined. (2) dev-login created DB sessions but app uses JWT strategy.
- **Fix**: (1) Fetch subscriptionTier + systemRole from DB in jwt callback. (2) Mint real JWT via `next-auth/jwt` encode() in dev-login.
- **Files**: `apps/web/lib/auth/config.ts`, `apps/web/app/api/auth/dev-login/route.ts`, `.eslintrc.json`

## 2026-02-25: Production Cloud SQL connection failure
- **Symptom**: `error=Callback` on Google OAuth, Prisma "empty host in database URL"
- **Root cause**: Three compounding issues: (1) `--add-cloudsql-instances` in cloudbuild.yaml had wrong instance name (`overplanned-db` vs `overplanned`). (2) Prisma 5.22 rejects empty host between `@/` in connection string — needs `localhost` placeholder. (3) `apps/web/.env` was baked into Docker image (`.dockerignore` only excluded root `.env`).
- **Fix**: (1) Fixed instance name in cloudbuild.yaml. (2) Added `localhost` to DATABASE_URL secret. (3) Changed `.dockerignore` to `**/.env` glob.
- **Files**: `cloudbuild.yaml`, `.dockerignore`, GCP Secret Manager

## 2026-02-25: User.image column missing in production DB
- **Symptom**: `The column User.image does not exist in the current database` after OAuth callback
- **Root cause**: Init migration was missing the `image` column that PrismaAdapter requires. Schema had drifted from DB.
- **Fix**: Manual `ALTER TABLE "User" ADD COLUMN IF NOT EXISTS "image" TEXT` + migration file + `_prisma_migrations` row.
- **Files**: `packages/db/prisma/migrations/20260226020000_add_user_image/migration.sql`
