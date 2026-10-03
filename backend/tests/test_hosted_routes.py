"""The Vercel route map must match the release Nginx gateway exactly (same cases as infra/nwis-release/test_gateway.py)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


routes = load("api/_routes.py", "hosted_routes")
gateway = load("infra/nwis-release/test_gateway.py", "release_gateway_cases")
DENIED = ("/docs", "/openapi.json", "/auth/login", "/admin/users", "/api/admin/users", "/api/ingest/report", "/api/audit/log",
          "/api/auth/google/start", "/api/auth/google/callback", "/api/auth/password/reset/extra", "/api/auth/email/verify/extra")


class HostedRoutesTest(unittest.TestCase):
    def test_allowed_routes_match_gateway(self):
        for incoming, expected in gateway.ROUTES.items():
            with self.subTest(incoming):
                self.assertEqual(routes.upstream(incoming.split("?")[0]), expected.split("?")[0])

    def test_everything_else_is_refused(self):
        for path in DENIED:
            with self.subTest(path):
                self.assertIsNone(routes.upstream(path))


if __name__ == "__main__":
    unittest.main()
