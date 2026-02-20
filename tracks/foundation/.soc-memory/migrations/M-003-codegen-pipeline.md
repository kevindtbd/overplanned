# M-003: Codegen Pipeline

## Description
Build the cross-stack contract system: Prisma → JSON Schema → Pydantic + TypeScript + Qdrant config. This ensures all stacks stay in sync with the Prisma schema as the single source of truth.

## Task
1. Write codegen specification doc FIRST: docs/codegen-spec.md
   - Map every Prisma type to JSON Schema output
   - Handle edge cases: Json fields → per-field schema override file, String[] → array, optionals, enums, @@unique/@@index (skip — no JSON Schema equivalent), default values (capture as default)

2. Implement scripts/prisma-to-jsonschema.ts (~100 LOC)
   - Parse Prisma schema using @mrleebo/prisma-ast
   - Output JSON Schema per model to packages/schemas/

3. Implement scripts/jsonschema-to-qdrant.ts (~50 LOC)
   - Read ActivityNode JSON Schema → generate Qdrant payload schema config

4. Wire datamodel-code-generator (pip install) → Pydantic output at services/api/models/generated.py

5. Wire json-schema-to-typescript (npm) → TS API types at packages/shared-types/api.ts

6. Create npm script: `npm run codegen` runs the full chain

7. CI guard: .github/workflows/codegen-check.yml
   - On PR: run codegen, diff generated files, fail if stale

Deliverable: change a Prisma model → `npm run codegen` → Pydantic + TS + Qdrant all update automatically.

## Output
scripts/prisma-to-jsonschema.ts

## Zone
codegen

## Dependencies
- M-002

## Priority
80

## Target Files
- docs/codegen-spec.md
- scripts/prisma-to-jsonschema.ts
- scripts/jsonschema-to-qdrant.ts
- packages/schemas/
- packages/shared-types/api.ts
- services/api/models/generated.py
- .github/workflows/codegen-check.yml

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
