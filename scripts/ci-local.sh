#!/usr/bin/env bash
set -euo pipefail

# ── Local CI simulation ──────────────────────────────────────────────
# Mirrors cloudbuild.yaml steps so you catch failures before pushing.
#
# Usage:
#   ./scripts/ci-local.sh          # run tests + build
#   ./scripts/ci-local.sh test     # tests only
#   ./scripts/ci-local.sh build    # Docker build only
# ─────────────────────────────────────────────────────────────────────

cd "$(git rev-parse --show-toplevel)"

run_tests() {
  echo "── Running tests (mirrors CI test-web step) ──"
  docker run --rm \
    -v "$(pwd)":/app \
    -w /app \
    node:20 \
    bash -c "npm ci && cd apps/web && npx vitest run --reporter=dot --maxWorkers=2"
  echo "── Tests passed ──"
}

run_build() {
  echo "── Building Docker image (mirrors CI build-web step) ──"
  docker build -f Dockerfile.web -t overplanned-web .
  echo "── Build passed ──"
}

case "${1:-all}" in
  test)  run_tests ;;
  build) run_build ;;
  all)   run_tests && run_build ;;
  *)
    echo "Usage: $0 [test|build|all]"
    exit 1
    ;;
esac

echo "── Local CI passed ──"
