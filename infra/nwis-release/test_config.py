"""Offline final-release Compose checks; captures only disposable placeholder credentials."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
VALUES = dict(NWIS_DB_OWNER_PASSWORD='test-owner-only', NWIS_DB_PASSWORD='test-app-only',
              NWIS_BACKEND_IMAGE='ertmac-nwis-release:test', NWIS_MODEL_DIR=str(ROOT/'models'),
              NWIS_PUBLIC_ORIGIN='https://judge.example.org', NWIS_AUTH_SECRET='a'*48,
              NWIS_SMTP_HOST='smtp.example.org', NWIS_SMTP_SENDER='nwis@example.org')


def config(values):
    env = {key: value for key, value in os.environ.items() if not key.startswith('NWIS_')}
    return subprocess.run(['docker', 'compose', '--profile', 'operator', '--env-file', os.devnull, '-f',
                           str(ROOT/'infra/nwis-release/compose.yml'), 'config', '--format', 'json'],
                          env={**env, **values}, capture_output=True, text=True)


class ConfigTests(unittest.TestCase):
    def test_auth_and_private_storage_topology(self):
        result = config(VALUES)
        self.assertEqual(result.returncode, 0)
        services = json.loads(result.stdout)['services']
        env = services['backend']['environment']
        self.assertEqual(env['WORKBENCH_SIGNUP_MODE'], 'open')
        self.assertEqual(env['WORKBENCH_SMTP_TLS'], 'starttls')
        self.assertEqual(env['WORKBENCH_DEPLOYMENT_MODE'], 'public')
        self.assertEqual(env['WORKBENCH_GOOGLE_ENABLED'], 'false')
        self.assertEqual(env['SESSION_COOKIE_SECURE'], 'true')
        for name in ('backend', 'postgres', 'qdrant', 'migrate'):
            self.assertFalse(services[name].get('ports'))
        self.assertEqual(services['gateway']['ports'][0]['host_ip'], '127.0.0.1')
        self.assertTrue(json.loads(result.stdout)['networks']['storage']['internal'])

    def test_missing_mail_auth_and_storage_requirements_fail_closed(self):
        for key in ('NWIS_AUTH_SECRET', 'NWIS_SMTP_HOST', 'NWIS_SMTP_SENDER',
                    'NWIS_DB_OWNER_PASSWORD', 'NWIS_DB_PASSWORD', 'NWIS_BACKEND_IMAGE',
                    'NWIS_MODEL_DIR', 'NWIS_PUBLIC_ORIGIN'):
            with self.subTest(key=key):
                result = config({k: v for k, v in VALUES.items() if k != key})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key, result.stderr)


if __name__ == '__main__':
    unittest.main()
