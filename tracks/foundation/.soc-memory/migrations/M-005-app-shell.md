# M-005: App Shell + Design System

## Description
Build the Next.js app shell with the locked design system. Mobile nav, desktop layout, fonts, design tokens, security headers.

## Task
1. Tailwind config with design tokens mapped to CSS custom properties:
   - Colors: terracotta (#C4694F), warm-background, warm-surface, warm-border + all token values
   - Reference: docs/overplanned-design-v4.html for exact values

2. Global CSS with :root variables (light mode default, dark mode support):
   - Font families, spacing scale, border radius, shadows

3. Font loading via next/font:
   - Sora (headings) — eager load
   - DM Mono (data/labels) — eager load
   - Lora (detail views/post-trip only) — lazy load via dynamic import

4. Mobile nav shell: Home / Trips / Explore / Profile (bottom tab bar)

5. Desktop layout: sidebar nav + main content area + context panel

6. Responsive breakpoint: mobile-first, desktop at 1024px

7. Env var validation: zod schema that validates all required env vars at build time
   - Crash with clear error messages if vars missing

8. Security headers middleware in next.config.js:
   - Content-Security-Policy (strict)
   - Strict-Transport-Security
   - X-Content-Type-Options: nosniff
   - X-Frame-Options: DENY
   - Referrer-Policy: strict-origin-when-cross-origin
   - Permissions-Policy (restrict camera, microphone, geolocation)

No emoji anywhere in the UI. SVG icons only, no icon libraries.

Deliverable: empty shell with nav, correct fonts/colors, responsive, security headers present in response.

## Output
apps/web/app/layout.tsx

## Zone
frontend

## Dependencies
- M-004

## Priority
70

## Target Files
- apps/web/app/layout.tsx
- apps/web/app/globals.css
- apps/web/tailwind.config.ts
- apps/web/components/nav/MobileNav.tsx
- apps/web/components/nav/DesktopSidebar.tsx
- apps/web/components/layout/AppShell.tsx
- apps/web/lib/env.ts
- apps/web/next.config.js

## Files
- docs/overplanned-design-v4.html
- docs/plans/vertical-plans-v2.md
