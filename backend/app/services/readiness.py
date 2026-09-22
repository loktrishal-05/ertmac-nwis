"""Small dependency probes, never inference or plant actions."""
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.core.locality import require_private_resolution
from app.services.model_gateway.registry import get_runtime
from app.services.sovereignty_service import get_sovereignty_proof


def check_postgres():
    engine = create_engine(settings.database_url, poolclass=NullPool,
                           connect_args={'connect_timeout': 2, 'options': '-c statement_timeout=2000'})
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return True
    finally:
        engine.dispose()


def check_qdrant():
    require_private_resolution(settings.qdrant_url)
    with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as client:
        response = client.get(settings.qdrant_url.rstrip('/') + '/readyz')
        return response.status_code == 200


def check_model():
    bounded = settings.model_copy(update={'model_first_load_timeout_seconds': 2,
                                          'model_timeout_seconds': 2, 'model_max_retries': 0})
    runtime = get_runtime(settings.model_runtime, bounded)
    try:
        health = runtime.health()
        return health.reachable and health.configured_model_present
    finally:
        if getattr(runtime, '_client', None) is not None:
            runtime._client.close()


def runtime_readiness():
    proof = get_sovereignty_proof()
    checks = {'fastapi': True, 'configuration': proof.status == 'sovereign'}
    for name, check in (('postgresql', check_postgres), ('qdrant', check_qdrant), ('model', check_model)):
        try:
            checks[name] = bool(check()) if checks['configuration'] else False
        except Exception:
            # Never return connection strings, credentials, or remote error bodies.
            checks[name] = False
    return {'status': 'ready' if all(checks.values()) else 'not_ready', 'checks': checks,
            'model_check': 'runtime reachable and configured model installed; no inference performed'}
