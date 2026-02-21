#!/usr/bin/env bash
set -euo pipefail

# Overplanned — Local Development Bootstrap
# Usage: ./dev-setup.sh

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[x]${NC} $1"; exit 1; }

# ─── Prerequisites ──────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || error "Docker is required. Install it first."
command -v node >/dev/null 2>&1   || error "Node.js is required (v18+). Install it first."
command -v npm >/dev/null 2>&1    || error "npm is required. Install it first."

# ─── .env setup ─────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  info "Creating .env from .env.example..."
  cp .env.example .env
  # Generate dev-friendly defaults
  sed -i 's/your_secure_postgres_password_here/overplanned_dev/g' .env
  sed -i 's/your_secure_redis_password_here/overplanned_dev/g' .env
  sed -i 's/your_secure_qdrant_api_key_here/overplanned_dev/g' .env
  sed -i "s/your_nextauth_secret_min_32_chars_here/$(openssl rand -base64 32)/g" .env
  warn "Created .env with dev defaults. Add your Google OAuth + Anthropic keys manually."
else
  info ".env already exists, skipping."
fi

if [ ! -f apps/web/.env.local ]; then
  info "Creating apps/web/.env.local from apps/web/.env.example..."
  cp apps/web/.env.example apps/web/.env.local
  # Point to PgBouncer with dev password
  sed -i 's/your_secure_postgres_password_here/overplanned_dev/g' apps/web/.env.local
  warn "Created apps/web/.env.local. Add your Google OAuth keys manually."
else
  info "apps/web/.env.local already exists, skipping."
fi

# ─── Docker services ────────────────────────────────────────────────────────
info "Starting Docker services (Postgres, PgBouncer, Redis, Qdrant, API)..."
docker compose up -d

info "Waiting for services to be healthy..."
timeout=60
elapsed=0
while [ $elapsed -lt $timeout ]; do
  healthy=$(docker compose ps --format json 2>/dev/null | grep -c '"healthy"' || true)
  total=$(docker compose ps --format json 2>/dev/null | grep -c '"running"\|"healthy"' || true)
  if [ "$healthy" -ge 4 ]; then
    break
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done

if [ $elapsed -ge $timeout ]; then
  warn "Some services may not be healthy yet. Check: docker compose ps"
else
  info "All data services healthy."
fi

# ─── Node dependencies ──────────────────────────────────────────────────────
info "Installing Node.js dependencies..."
npm install

# ─── Prisma setup ───────────────────────────────────────────────────────────
info "Generating Prisma client..."
npx prisma generate

info "Running database migrations..."
npx prisma migrate dev --name init 2>/dev/null || npx prisma db push

info "Seeding database..."
npx prisma db seed

# ─── Summary ────────────────────────────────────────────────────────────────
echo ""
info "Setup complete!"
echo ""
echo "  Services running:"
echo "    Postgres     → localhost:15432"
echo "    PgBouncer    → localhost:16432"
echo "    Redis        → localhost:16379"
echo "    Qdrant       → localhost:6333"
echo "    FastAPI      → localhost:8000  (docs: localhost:8000/docs)"
echo ""
echo "  To start the frontend:"
echo "    npm run dev"
echo ""
echo "  Then open: http://localhost:3000"
echo ""
warn "Remember to add your Google OAuth and Anthropic API keys to .env"
