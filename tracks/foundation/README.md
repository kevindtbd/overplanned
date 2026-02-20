# Overplanned Foundation Track

## Contract System

This project uses a **cross-stack contract system** with Prisma as the single source of truth:

```
Prisma Schema → JSON Schema → Pydantic + TypeScript + Qdrant
```

### Quick Start

1. Install dependencies:
```bash
npm install
pip install datamodel-code-generator
```

2. Generate all contracts:
```bash
npm run codegen
```

### Codegen Pipeline

The `npm run codegen` command runs:

1. **`prisma-to-jsonschema.ts`** - Converts Prisma models to JSON Schema
2. **`datamodel-code-generator`** - Generates Pydantic models from JSON Schema
3. **`json-schema-to-typescript`** - Generates TypeScript types from JSON Schema
4. **`jsonschema-to-qdrant.ts`** - Generates Qdrant payload schema from ActivityNode

### Files Generated

- `packages/schemas/*.json` - JSON Schema for each Prisma model
- `services/api/models/generated.py` - Pydantic models for FastAPI
- `packages/shared-types/api.ts` - TypeScript types for Next.js
- `services/api/config/qdrant_schema.json` - Qdrant payload schema

### CI Validation

GitHub Actions workflow `.github/workflows/codegen-check.yml` ensures generated files stay in sync:
- Runs on PRs that modify schema files
- Fails if generated files are stale
- Prompts to run `npm run codegen` locally

### Specification

See `docs/codegen-spec.md` for full mapping rules and edge cases.

### Workflow

1. Modify `prisma/schema.prisma`
2. Run `npm run codegen`
3. Commit all generated files
4. CI validates on PR

**NEVER** edit generated files manually - they will be overwritten.
