# Foundation Track — Manifest

## Zones

### Zone: infra
Directory: infra
**SUPER**
- docker-compose.yml
- .env.example

### Zone: schema
Directory: schema
**SUPER**
- prisma/schema.prisma
- prisma/seed.ts
- prisma/migrations/

### Zone: codegen
Directory: codegen
- scripts/prisma-to-jsonschema.ts
- scripts/jsonschema-to-qdrant.ts
- packages/schemas/
- packages/shared-types/

### Zone: auth
Directory: auth
- apps/web/app/api/auth/
- apps/web/lib/auth/

### Zone: frontend
Directory: frontend
- apps/web/app/
- apps/web/components/
- tailwind.config.ts

### Zone: backend
Directory: backend
**SUPER**
- services/api/

### Zone: monorepo
Directory: monorepo
- package.json
- packages/
- Makefile

### Zone: deploy
Directory: deploy
- Dockerfile.*
- cloudbuild.yaml

### Zone: search
Directory: search
- services/api/search/

### Zone: embedding
Directory: embedding
- services/api/embedding/

### Zone: tests
Directory: tests
- tests/
- apps/web/__tests__/
- services/api/tests/
