-- A read-only account for Metabase (and for ad-hoc analysis).
--
-- Metabase must never be able to change application data. This user can only
-- SELECT, and only from the application schema.
--
-- The password is taken from the environment by the docker-compose file that
-- mounts this directory; the default is for local development only.
CREATE USER IF NOT EXISTS 'analytics_ro'@'%' IDENTIFIED BY 'change-me-analytics-readonly';
GRANT SELECT ON schemeping.* TO 'analytics_ro'@'%';
FLUSH PRIVILEGES;
