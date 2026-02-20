.PHONY: codegen dev test docker-up docker-down lint type-check clean

# --- Codegen ---
codegen: codegen-npm codegen-python

codegen-npm:
	npm run codegen

codegen-python:
	cd services/ml && \
	datamodel-codegen \
		--input-file-type jsonschema \
		--input ../../packages/schemas/ \
		--output app/schemas/generated/

# --- Development ---
dev:
	@echo "Starting Docker services..."
	docker compose up -d
	@echo "Starting Next.js + FastAPI..."
	npx concurrently \
		--names "web,api" \
		--prefix-colors "blue,green" \
		"npm run dev --workspace=@overplanned/web" \
		"cd services/ml && uvicorn app.main:app --reload --port 8000"

dev-web:
	npm run dev --workspace=@overplanned/web

dev-api:
	cd services/ml && uvicorn app.main:app --reload --port 8000

# --- Testing ---
test: test-web test-api

test-web:
	npm test --workspace=@overplanned/web --if-present

test-api:
	cd services/ml && python -m pytest

# --- Docker ---
docker-up:
	docker compose up -d

docker-down:
	docker compose down

# --- Quality ---
lint:
	npm run lint

type-check:
	npm run type-check

# --- Database ---
db-migrate:
	npm run db:migrate

db-seed:
	npm run db:seed

db-studio:
	npm run db:studio

# --- Cleanup ---
clean:
	rm -rf packages/shared-types/generated/*.ts
	rm -rf packages/schemas/*.json
	@echo "Cleaned generated files"
