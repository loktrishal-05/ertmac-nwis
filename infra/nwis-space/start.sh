#!/bin/sh
# Boot the self-contained NWIS demo. Postgres/Qdrant listen on 127.0.0.1 only; nginx on :7860 is the sole public port.
set -eu
PG=/usr/lib/postgresql/15/bin
rnd() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
export NWIS_DB_PASSWORD="$(rnd)"
# Sessions die with the container anyway (DB is re-seeded), so a per-boot secret is fine unless one is supplied.
export WORKBENCH_AUTH_SECRET="${WORKBENCH_AUTH_SECRET:-$(rnd)}"

$PG/initdb -D /tmp/pg -U nwis_owner --auth=trust >/dev/null
$PG/pg_ctl -D /tmp/pg -o "-c listen_addresses=127.0.0.1 -k /tmp" -l /tmp/pg.log -w start
$PG/createdb -h 127.0.0.1 -U nwis_owner nwis

(cd /tmp && QDRANT__STORAGE__STORAGE_PATH=/tmp/qdrant QDRANT__STORAGE__SNAPSHOTS_PATH=/tmp/qdrant-snapshots \
  QDRANT__SERVICE__HOST=127.0.0.1 QDRANT__TELEMETRY_DISABLED=true exec qdrant >/tmp/qdrant.log 2>&1) &
i=0; until curl -sf http://127.0.0.1:6333/readyz >/dev/null; do
  i=$((i+1)); [ $i -gt 60 ] && { cat /tmp/qdrant.log; exit 1; }; sleep 1
done

cd /workbench
DATABASE_URL=postgresql+psycopg://nwis_owner@127.0.0.1:5432/nwis python -m alembic -c backend/alembic.ini upgrade head
$PG/psql -q -h 127.0.0.1 -U nwis_owner -d nwis -v ON_ERROR_STOP=1 -f infra/grant-app.sql
python -m scripts.seed_nwis --index
python backend/scripts/seed_demo_account.py

nginx -c /workbench/infra/nginx.conf -e stderr &
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
