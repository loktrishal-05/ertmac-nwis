"""Disposable PostGIS grant check. No network, host ports, or persistent release volume."""
from pathlib import Path
import subprocess


def main():
    sql = Path(__file__).with_name('grant-app.sql').resolve()
    script = r'''
set -eu
docker-entrypoint.sh postgres >/tmp/postgres.log 2>&1 &
pg_pid=$!
trap 'kill "$pg_pid" 2>/dev/null || true' EXIT
ready=0
for i in $(seq 1 60); do
  if pg_isready -h 127.0.0.1 -U nwis_owner -d nwis >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1
psql -U nwis_owner -d nwis -v ON_ERROR_STOP=1 -c 'CREATE TABLE d2_probe(id serial PRIMARY KEY, value text);'
psql -U nwis_owner -d nwis -v ON_ERROR_STOP=1 -f /release/grant-app.sql
psql -U nwis_owner -d nwis -v ON_ERROR_STOP=1 -f /release/grant-app.sql
flags=$(psql -U nwis_owner -d nwis -Atc "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname='nwis_app'")
test "$flags" = 'f|f|f'
PGPASSWORD="$NWIS_DB_PASSWORD" psql -h 127.0.0.1 -U nwis_app -d nwis -v ON_ERROR_STOP=1 -c "SELECT PostGIS_Version(); INSERT INTO d2_probe(value) VALUES ('synthetic_demo'); UPDATE d2_probe SET value='synthetic_demo'; SELECT * FROM d2_probe; DELETE FROM d2_probe;"
if PGPASSWORD="$NWIS_DB_PASSWORD" psql -h 127.0.0.1 -U nwis_app -d nwis -v ON_ERROR_STOP=1 -c 'CREATE TABLE forbidden(id int);' 2>/tmp/denied; then exit 1; fi
grep -q 'permission denied' /tmp/denied
echo 'PASS: PostGIS, idempotent role grants, application DML/sequence access, no superuser/createdb/createrole/schema DDL.'
'''
    subprocess.run(['docker', 'run', '--rm', '-i', '--network', 'none',
                    '-e', 'POSTGRES_USER=nwis_owner', '-e', 'POSTGRES_DB=nwis',
                    '-e', 'POSTGRES_PASSWORD=disposable-owner-test-only',
                    '-e', 'NWIS_DB_PASSWORD=disposable-app-test-only',
                    '--mount', f'type=bind,source={sql},target=/release/grant-app.sql,readonly',
                    '--entrypoint', 'bash', 'postgis/postgis:17-3.5', '-s'],
                   input=script.encode('utf-8'), check=True)


if __name__ == '__main__':
    main()
