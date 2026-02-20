## Summary

<!-- What does this PR do? Why? -->

## Schema Changes

<!-- If this PR modifies schema.prisma, fill out this section. Otherwise, delete it. -->

### Affected Models

<!-- List every model touched by this PR -->

-

### New Fields

<!-- List new fields with types and purpose -->

| Model | Field | Type | Purpose |
|-------|-------|------|---------|
|       |       |      |         |

### New Indexes

<!-- List new indexes and the queries they optimize -->

-

### Migration Name

<!-- The migration name from `prisma migrate dev --name <name>` -->

`prisma/migrations/<timestamp>_<name>`

## Checklist

### All PRs

- [ ] Tests pass locally
- [ ] No unrelated changes included

### Schema Change PRs (REQUIRED if schema.prisma is modified)

- [ ] Ran `npx prisma generate` — no errors
- [ ] Ran `npx prisma migrate dev` — migration created cleanly
- [ ] Generated client files are committed
- [ ] Contract tests pass (`npm run test:contracts`)
- [ ] No breaking changes to other tracks' interfaces
- [ ] Affected models, new fields, and new indexes listed above
- [ ] Reviewer assigned from a different track
- [ ] Commit messages use `schema:` prefix

## Testing

<!-- How was this tested? What test cases were added? -->

## Track

<!-- Which track does this belong to? -->

- [ ] Foundation (Track 1)
- [ ] Pipeline (Track 2)
- [ ] Admin (Track 3)
- [ ] Solo Trip (Track 4)
- [ ] Group Trip (Track 5)
- [ ] Mid-Trip (Track 6)
- [ ] Post-Trip (Track 7)
- [ ] Cross-track / Infrastructure
