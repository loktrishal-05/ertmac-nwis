# Frontend

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

In development the browser calls same-origin `/api`, which Vite proxies to the
backend (`WORKBENCH_API_PROXY`, default `http://localhost:8000`), so the session
cookie works whether you open `localhost` or `127.0.0.1`. Leave
`VITE_API_BASE_URL` unset for development; set it to the site's HTTPS API origin
for production builds. Restart Vite after changing `.env`. Vite variables are
public browser configuration: never put secrets in them. There are no external
fonts, hosted AI APIs, or CDN dependencies.

The header checks `GET /health` immediately and every 15 seconds after a check
completes. Requests time out after five seconds. Valid backend responses display
Connected; request failures, timeouts, and unexpected payloads display
Disconnected. Checking appears during initial startup. The existing backend CORS
settings already allow port 5173; Vite uses a strict port to avoid silently moving
to an origin that is not allowed.

Routes use real URLs: the public landing page at `/`, sign-in and account pages
under `/login` and friends, and the authenticated workbench under `/app/*`.
Areas the backend does not provide yet show an explicit "Not yet available"
state; self-service sign-up, recovery and Google sign-in stay disabled until the
backend reports those capabilities.

Validation and local production preview:

```powershell
npm run lint
npm test
npm run build
npm run preview
```

Preview also uses http://localhost:5173; stop the dev server before previewing.
To manually verify connectivity, start and stop the backend and wait for the
next health check. Check narrow and wide layouts and keyboard navigation.
