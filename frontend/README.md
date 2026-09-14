# Frontend — Phase 1

React with Vite and JavaScript. Requires Node.js 22.12+ (or 20.19+).

From the repository root in Windows PowerShell:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open http://localhost:5173. Start the backend in a separate terminal using
the instructions in `../backend/README.md`.

`VITE_API_BASE_URL` configures the backend origin and defaults to
`http://localhost:8000`. Restart Vite after changing `.env`; rebuild for a
production bundle. Vite variables are public browser configuration: never put
secrets in them. There are no external fonts, hosted AI APIs, or CDN dependencies.

The header checks `GET /health` immediately and every 15 seconds after a check
completes. Requests time out after five seconds. Valid backend responses display
Connected; request failures, timeouts, and unexpected payloads display
Disconnected. Checking appears during initial startup. The existing backend CORS
settings already allow port 5173; Vite uses a strict port to avoid silently moving
to an origin that is not allowed.

Agent cards, zero metrics, and recent activity are foundation placeholders.
Navigation opens clearly labeled future-phase placeholders. No agent execution,
approval workflow, storage, authentication, document ingestion, or inference is
implemented. External AI Calls is an initial value, not an audit counter.

Validation and local production preview:

```powershell
npm run lint
npm run build
npm run preview
```

Preview also uses http://localhost:5173; stop the dev server before previewing.
To manually verify connectivity, start and stop the backend and wait for the
next health check. Check narrow and wide layouts and keyboard navigation.
