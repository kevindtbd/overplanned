# Cross-Stack Contract System (B+A)

## Problem
5 representations of the same entities across stacks:
- Prisma (PostgreSQL) — DB source of truth
- Qdrant — vector search with payload fields
- FastAPI Pydantic — Python API models
- Next.js TypeScript — frontend types
- Pipeline — scraper write targets

Manual sync = drift. Drift = silent breakage.

## Solution: Prisma → JSON Schema → Everything

```
Prisma Schema → codegen → JSON Schema (intermediate)
                              ├→ prisma generate (TS types, built-in)
                              ├→ datamodel-code-generator (Pydantic)
                              ├→ json-schema-to-typescript (API TS types)
                              └→ custom script (Qdrant payload config)
```

## Toolchain
| Step | Tool | Maturity |
|---|---|---|
| Prisma → TS | `prisma generate` | Built-in |
| Prisma → JSON Schema | Custom script (~100 LOC) | Write ourselves |
| JSON Schema → Pydantic | `datamodel-code-generator` | Mature pip package |
| JSON Schema → TS API shapes | `json-schema-to-typescript` | Mature npm package |
| JSON Schema → Qdrant | Custom script (~50 LOC) | Write ourselves |

## CI Guard
On any PR touching schema.prisma:
1. Run prisma generate
2. Run prisma→json-schema codegen
3. Run json-schema→pydantic codegen
4. Run json-schema→ts codegen
5. Diff check: generated files changed but not committed → FAIL

## Why JSON Schema (not Protobuf)
- REST stack (not gRPC) — Protobuf adds complexity for no transport benefit
- Mature generators for both Python and TS
- Human-readable diffs in PR review
- Qdrant payloads are JSON — natural fit
- datamodel-code-generator handles nested objects, enums, optionals, arrays

## Key Files
```
packages/schemas/activity-node.json
packages/schemas/trip.json
packages/schemas/user.json
packages/schemas/behavioral-signal.json
packages/schemas/vibe-tags.json        ← 42 locked tags, enum
packages/schemas/quality-signal.json
packages/shared-types/api.ts           ← generated
services/api/models/generated.py       ← generated
scripts/prisma-to-jsonschema.ts
scripts/jsonschema-to-qdrant.ts
```
