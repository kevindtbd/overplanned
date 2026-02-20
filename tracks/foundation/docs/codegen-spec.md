# Codegen Specification

## Overview
This document defines the transformation rules for the cross-stack contract system:
**Prisma Schema → JSON Schema → Pydantic + TypeScript + Qdrant**

Single source of truth: `prisma/schema.prisma`

## Prisma → JSON Schema Mapping

### Scalar Types
| Prisma Type | JSON Schema Type | Notes |
|-------------|------------------|-------|
| `String` | `{"type": "string"}` | |
| `Int` | `{"type": "integer"}` | |
| `Float` | `{"type": "number"}` | |
| `Boolean` | `{"type": "boolean"}` | |
| `DateTime` | `{"type": "string", "format": "date-time"}` | ISO 8601 string |
| `Json` | `{"type": "object"}` | See Json field override below |
| `String[]` | `{"type": "array", "items": {"type": "string"}}` | |
| `Int[]` | `{"type": "array", "items": {"type": "integer"}}` | |

### Enums
```prisma
enum TripMode {
  solo
  group
}
```
→
```json
{
  "type": "string",
  "enum": ["solo", "group"]
}
```

### Optionals
Prisma `String?` → JSON Schema `"type": ["string", "null"]` or use `required` array

### Default Values
Prisma `@default(beta)` → JSON Schema `"default": "beta"`

### Relations
**Skip all relation fields** (e.g., `user User @relation(...)`). Only include scalar fields.

### Prisma Decorators Ignored
- `@@unique` - No JSON Schema equivalent (validation, not type)
- `@@index` - No JSON Schema equivalent
- `@id` - Include as a string field
- `@unique` - No JSON Schema equivalent
- `@updatedAt`, `@default(now())` - Include in schema with default if applicable

### Json Field Override
For fields typed as `Json` in Prisma, create per-field schema override files:
- `packages/schemas/overrides/User.featureFlags.json`
- `packages/schemas/overrides/Trip.personaSeed.json`

Main codegen outputs `{"type": "object"}`, but override files provide specific structure.

## JSON Schema → Pydantic

Use `datamodel-code-generator`:
```bash
pip install datamodel-code-generator
datamodel-code-generator \
  --input packages/schemas/*.json \
  --output services/api/models/generated.py \
  --input-file-type jsonschema \
  --output-model-type pydantic_v2.BaseModel
```

## JSON Schema → TypeScript

Use `json-schema-to-typescript`:
```bash
npx json-schema-to-typescript \
  packages/schemas/*.json \
  -o packages/shared-types/api.ts
```

## JSON Schema → Qdrant Payload Schema

For `ActivityNode` only (the embedded model):
- Read `packages/schemas/ActivityNode.json`
- Generate Qdrant payload schema config
- Output to `services/api/config/qdrant_schema.json`

Format:
```json
{
  "name": {
    "type": "keyword"
  },
  "category": {
    "type": "keyword"
  },
  "latitude": {
    "type": "float"
  },
  "longitude": {
    "type": "float"
  }
}
```

## Output Files

| Target | Source | Generator |
|--------|--------|-----------|
| `packages/schemas/*.json` | `prisma/schema.prisma` | `scripts/prisma-to-jsonschema.ts` |
| `services/api/models/generated.py` | `packages/schemas/*.json` | `datamodel-code-generator` |
| `packages/shared-types/api.ts` | `packages/schemas/*.json` | `json-schema-to-typescript` |
| `services/api/config/qdrant_schema.json` | `packages/schemas/ActivityNode.json` | `scripts/jsonschema-to-qdrant.ts` |

## npm run codegen Pipeline

```bash
npm run codegen
```

Executes:
1. `tsx scripts/prisma-to-jsonschema.ts`
2. `datamodel-code-generator ...` (Pydantic)
3. `json-schema-to-typescript ...` (TypeScript)
4. `tsx scripts/jsonschema-to-qdrant.ts`

## CI Validation

`.github/workflows/codegen-check.yml`:
- On PR: run `npm run codegen`
- Diff generated files
- Fail if any generated file is stale

## Edge Cases

1. **Circular relations**: Skip all relation fields (only scalars)
2. **Composite IDs**: Treat each field individually
3. **Unsupported Prisma features**: Map to closest JSON Schema equivalent or skip
4. **Enums**: Always output as `{"type": "string", "enum": [...]}`
5. **Arrays**: Always output as `{"type": "array", "items": {...}}`
