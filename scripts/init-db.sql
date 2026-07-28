-- Runs once on first postgres container boot.
CREATE EXTENSION IF NOT EXISTS vector;

-- Separate database for pytest (integration tests truncate between tests).
CREATE DATABASE citation_test OWNER dev;
\connect citation_test
CREATE EXTENSION IF NOT EXISTS vector;
