# Backend — Phase 0

Requires Python 3.10 or newer. Run these commands in Windows PowerShell, starting
at the repository root:

```powershell
Copy-Item .env.example .env
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If the `py` launcher is unavailable, use `python -m venv .venv` instead.
The commands use the virtual environment interpreter directly, so PowerShell
activation or execution-policy changes are unnecessary. `--reload` is for local
development only. Stop the server with Ctrl+C.

In a second PowerShell terminal, verify the endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json
```

Expected response:

```json
{
  "status": "ok",
  "service": "sovereign-agentic-workbench-backend"
}
```

Interactive API documentation: <http://127.0.0.1:8000/docs>.

## Configuration

Settings use `pydantic-settings`. The optional `.env` is loaded from the repository
root regardless of the working directory. System environment variables take
precedence. `.env` is ignored by Git; `.env.example` contains no secrets.

`WORKBENCH_CORS_ORIGINS` is a JSON array of allowed origins. Defaults allow
`localhost` and `127.0.0.1` on ports 5173 and 3000 for a future React frontend.
Only GET is currently permitted through CORS, with credentials disabled.

Only FastAPI, Uvicorn, and pydantic-settings are direct dependencies. No agents,
database connections, authentication, or model inference run in Phase 0.
