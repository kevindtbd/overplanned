FROM python:3.11-slim

WORKDIR /app

# Install system deps for asyncpg and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.txt /app/services/api/requirements.txt
RUN pip install --no-cache-dir -r services/api/requirements.txt

COPY services/ /app/services/
COPY prisma/ /app/prisma/

# Generate Prisma Python client from schema
RUN python -m prisma generate --schema=/app/prisma/schema.prisma

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
