-- Enable PostGIS extension
-- This runs on first database initialization only

-- Create PostGIS extension if it doesn't exist
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Verify PostGIS is installed
DO $$
DECLARE
    postgis_version TEXT;
BEGIN
    SELECT PostGIS_version() INTO postgis_version;
    RAISE NOTICE 'PostGIS version: %', postgis_version;
END $$;

-- Create application schema (optional, can be managed by Prisma)
-- Uncomment if you want to pre-create schemas
-- CREATE SCHEMA IF NOT EXISTS public;

-- Grant necessary permissions
GRANT ALL PRIVILEGES ON DATABASE overplanned TO overplanned;
GRANT ALL PRIVILEGES ON SCHEMA public TO overplanned;

-- Enable UUID extension for primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Set timezone to UTC
SET timezone = 'UTC';

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialized successfully with PostGIS support';
END $$;
