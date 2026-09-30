-- Run after migrations as nwis_owner. Never grant the application superuser/DDL rights.
\getenv app_password NWIS_DB_PASSWORD
SELECT format('CREATE ROLE nwis_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nwis_app')
\gexec
GRANT CONNECT ON DATABASE nwis TO nwis_app;
GRANT USAGE ON SCHEMA public TO nwis_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nwis_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nwis_app;
ALTER DEFAULT PRIVILEGES FOR ROLE nwis_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nwis_app;
ALTER DEFAULT PRIVILEGES FOR ROLE nwis_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO nwis_app;
