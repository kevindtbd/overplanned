# Test Type Error Cleanup — Design

## Problem
667 TypeScript errors in `apps/web/__tests__/` prevent a clean `tsc --noEmit`.
Production code has zero errors. The pre-push hook filters test errors as a
workaround, but this also hides new test-file regressions.

## Goal
Zero errors from `cd apps/web && npx tsc --noEmit`, enabling a strict
pre-push hook with no filtering.

## Error Breakdown

| Code | Count | Description | Fix Strategy |
|------|-------|-------------|-------------|
| TS2339 | 505 | `.mockResolvedValueOnce` etc. not on Prisma types | Fix mock typing |
| TS7031 | 56 | Binding element `{ page }` implicitly `any` | Add `: { page: Page }` |
| TS7006 | 40 | Parameter implicitly `any` | Add type annotations |
| TS2345 | 18 | Argument not assignable (mock shape) | Add missing mock fields |
| TS2307 | 13 | Module not found (`@playwright/test`, `vitest-mock-extended`) | Install devDeps |
| TS2352 | 11 | Conversion may be mistake | Fix `as` casts |
| TS2769 | 8 | No overload matches | Fix mock call signatures |
| TS2322 | 6 | Type not assignable | Fix assignments |
| TS2741 | 3 | Missing properties | Add missing props |
| TS2353 | 3 | Object literal unknown props | Remove extra props |
| Other | 4 | Misc | Case-by-case |

## Spike Result (VALIDATED)
Tested `vi.mocked(prisma, true)` on `expenses.test.ts`:
- Before: 28 errors
- After: 4 errors (unrelated strict-typing issues, not mock-related)
- **Track 1 approach confirmed viable**

Note: deep mocking surfaces NEW strict-typing errors (~4 per file estimate).
After Track 1's mechanical replace, expect ~50-100 new minor errors
(optional chaining on mock call args, etc). These fold into Track 5.

## Fix Strategy

### Step 0: Install Missing DevDeps
```bash
npm install --save-dev @playwright/test vitest-mock-extended
```
Both are imported in test files but not installed. Resolves all 13 TS2307 errors.

### Track 1: Prisma Mock Typing (505 errors)
All 27 API test files use:
```ts
const mockPrisma = vi.mocked(prisma);
```
This returns `Mocked<PrismaClient>` — shallow mock. Methods like
`mockPrisma.tripMember.findUnique` retain their Prisma type, so
`.mockResolvedValueOnce` doesn't exist on them.

**Fix**: Change to deep mocking:
```ts
const mockPrisma = vi.mocked(prisma, true);
```
The `true` flag makes vitest wrap all nested properties as `Mock`, adding
`.mockResolvedValueOnce` etc.

### Track 2: Playwright Types (56 TS7031 + remaining TS7006)
E2E spec files use `({ page }) =>` callbacks without typing.
After Step 0 installs `@playwright/test`, add type annotations:
```ts
test("...", async ({ page }: { page: Page }) => {
```

### Track 3: Implicit Any in Test Callbacks (remaining TS7006)
Non-Playwright test callbacks with untyped parameters. Add explicit types.

### Track 4: Mock Shape Mismatches (TS2345, TS2741, TS2769)
Test mocks missing properties that were added to TripContext or API types.
Add the missing fields (e.g., `myUserId`, `hasReflected`, `reflectionSummary`).

### Track 5: Misc + Track 1 Cascade (TS2352, TS2322, TS2353, new strict errors)
Case-by-case fixes. Includes ~50-100 new errors surfaced by deep mocking.

## Execution Plan
1. Step 0: Install `@playwright/test` + `vitest-mock-extended`
2. Track 1: `vi.mocked(prisma, true)` across 27 files (find-and-replace)
3. Run `tsc --noEmit`, recount — expect ~150-200 remaining
4. Track 2: Playwright type annotations in E2E specs
5. Track 4: Mock shape mismatches
6. Track 5: All remaining (including cascade from Track 1)
7. Run `tsc --noEmit` — expect 0
8. Run full test suite — expect all 1027+ pass
9. Remove pre-push `|| true` filter, commit clean hook

## Verification
- Run tests once at the end (not after each track) — these are type-only
  changes, runtime behavior unchanged.
- If any tests fail, bisect by track.

## Risk
- Deep mocking may surface more cascade errors than estimated (~50-100).
  Manageable — they're all mechanical fixes.
- Mock shape fixes could expose tests asserting the wrong thing. Low
  probability since tests currently pass at runtime.
