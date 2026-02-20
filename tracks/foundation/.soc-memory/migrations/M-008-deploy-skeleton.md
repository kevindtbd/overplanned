# M-008: Deploy Skeleton

## Description
Docker images and GCP Cloud Run configuration for both services. Multi-stage builds, non-root users, production-ready.

## Task
1. Dockerfile.web (Next.js):
   - Multi-stage: deps → build → production
   - Pinned base image (node:20-alpine with specific digest)
   - Non-root user (nextjs:nodejs)
   - Standalone output mode
   - Health check: HEALTHCHECK CMD wget --spider http://localhost:3000/api/health

2. Dockerfile.api (FastAPI):
   - Multi-stage: deps → production
   - Pinned base image (python:3.11-slim with specific digest)
   - Non-root user
   - Health check: HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

3. GCP Cloud Run config (cloudbuild.yaml):
   - Build both images
   - Push to Artifact Registry
   - Deploy web as public service
   - Deploy api as internal-only service (no public ingress, IAM-authenticated by web service)

4. Env management:
   - GCP Secret Manager references for all API keys in prod
   - Document which env vars come from Secret Manager vs Cloud Run env

5. .dockerignore for both services (exclude node_modules, .env, .git, tests)

Deliverable: both services build as Docker images, health checks pass, non-root verified with `docker run --user` check.

## Output
Dockerfile.web

## Zone
deploy

## Dependencies
- M-006

## Priority
50

## Target Files
- Dockerfile.web
- Dockerfile.api
- cloudbuild.yaml
- .dockerignore

## Files
- services/api/main.py
- apps/web/next.config.js
- docs/plans/vertical-plans-v2.md
