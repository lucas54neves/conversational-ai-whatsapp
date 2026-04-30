-- Provision Omni's database alongside the nutrition database.
-- Both share the `nutrition` superuser to keep credentials simple in dev.
-- This file is run once by the postgres image's docker-entrypoint-initdb.d
-- on the very first boot of an empty data directory.
CREATE DATABASE omni OWNER nutrition;
