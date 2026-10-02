---
title: eRTMAC-NWIS API
emoji: 🛢️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# eRTMAC-NWIS always-on demo backend

Backend for https://sovereign-ai-workbench-nine.vercel.app (Vercel rewrites `/api/*` here).
One container: PostGIS, Qdrant, FastAPI and the release nginx gateway. Only port 7860 is exposed.

- Synthetic demo dataset only; it is re-seeded on every boot and nothing is persisted.
- No LLM is used by the NWIS routes, so none is installed.
- Built from `infra/nwis-space/` in https://github.com/loktrishal-05/ertmac-nwis.
- `.github/workflows/keep-demo-awake.yml` pings the API every 6 h so the free Space never sleeps.

Optional Space secrets: `WORKBENCH_AUTH_SECRET` (32+ bytes) and `WORKBENCH_SMTP_*` for sign-up email codes.
