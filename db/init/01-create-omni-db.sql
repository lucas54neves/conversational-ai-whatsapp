-- Provision Omni's database alongside the nutrition database. Both share
-- the `nutrition` superuser to keep credentials simple in dev.
-- Run once by postgres image's docker-entrypoint-initdb.d on first boot.
CREATE DATABASE omni OWNER nutrition;
