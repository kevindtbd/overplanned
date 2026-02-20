# Overplanned Web App

Next.js 14 web application with NextAuth.js authentication.

## Authentication

- **Provider**: Google OAuth only
- **Session Strategy**: Database-backed (NOT JWT)
- **Session Duration**: 30 days max, 7 days idle timeout
- **Concurrent Sessions**: Max 5 active sessions per user (oldest deleted automatically)
- **Default Role**: New users get `subscriptionTier: beta` on first login

## Setup

1. Install dependencies:
```bash
npm install
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

3. Set up Google OAuth:
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create OAuth 2.0 credentials
   - Add authorized redirect URI: `http://localhost:3000/api/auth/callback/google`
   - Copy client ID and secret to `.env`

4. Generate NextAuth secret:
```bash
openssl rand -base64 32
```

5. Run Prisma migrations:
```bash
npx prisma migrate dev
```

6. Start development server:
```bash
npm run dev
```

## Access Control

During beta phase:
- All new signups get role: `beta`
- Access granted to: `beta`, `lifetime`, `pro` users
- Lifetime users are manually set via SQL
- Stripe is wired but NOT enforcing payment

## File Structure

```
apps/web/
├── app/
│   ├── api/auth/[...nextauth]/route.ts  # NextAuth route handler
│   ├── auth/
│   │   ├── signin/page.tsx              # Sign-in page
│   │   └── error/page.tsx               # Auth error page
│   ├── layout.tsx                        # Root layout with SessionProvider
│   └── page.tsx                          # Home page
├── components/
│   └── auth/
│       ├── ProtectedRoute.tsx            # Client-side route protection
│       └── SessionProvider.tsx           # NextAuth session provider wrapper
├── lib/
│   └── auth/
│       ├── config.ts                     # NextAuth configuration
│       ├── session.ts                    # Session utilities (concurrent limit, cleanup)
│       └── gates.ts                      # Feature gates and tier checks
├── middleware.ts                         # Auth middleware
└── types/
    └── next-auth.d.ts                    # NextAuth TypeScript declarations
```

## Key Features

### Concurrent Session Management
`lib/auth/session.ts` enforces max 5 sessions per user. On new session creation, oldest sessions are deleted if limit exceeded.

### Feature Gates
`lib/auth/gates.ts` defines feature access by tier:
- `hasAccess(tier)` - Check if user has basic access
- `hasFeatureAccess(tier, feature)` - Check specific feature access
- `FEATURE_GATES` - Map of all features and required tiers

### Protected Routes
Use `ProtectedRoute` component for client-side protection:
```tsx
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";

export default function DashboardPage() {
  return (
    <ProtectedRoute>
      <div>Protected content</div>
    </ProtectedRoute>
  );
}
```

Or use HOC:
```tsx
import { withProtectedRoute } from "@/components/auth/ProtectedRoute";

function DashboardPage() {
  return <div>Protected content</div>;
}

export default withProtectedRoute(DashboardPage);
```

## Database Schema

NextAuth uses these Prisma models:
- `User` - User accounts (custom fields: subscriptionTier, systemRole, lastActiveAt)
- `Session` - Active sessions (maxAge 30d, updateAge 7d)
- `Account` - OAuth provider accounts (Google)
- `VerificationToken` - Email verification tokens

See `packages/db/prisma/schema.prisma` for full schema.
