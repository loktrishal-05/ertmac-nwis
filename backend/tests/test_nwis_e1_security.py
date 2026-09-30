"""E1 security boundaries; synthetic fixtures only, no provider calls."""
from http.cookies import SimpleCookie
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.core.config import settings
from app.api.deps import get_optional_current_user
from app.main import app
import test_phase_f_auth
import test_nwis


class PublicSessionTests(unittest.TestCase):
    setUp = test_phase_f_auth.AccountsTests.setUp
    post = test_phase_f_auth.AccountsTests.post
    login = test_phase_f_auth.AccountsTests.login

    def test_secure_cookie_logout_and_disabled_google(self):
        with patch.object(settings, 'deployment_mode', 'public'), patch.object(settings, 'session_cookie_secure', True):
            self.client.base_url = 'https://testserver'
            response = self.login()
            cookies = SimpleCookie(response.headers['set-cookie'])
            cookie = cookies[settings.session_cookie_name]
            self.assertTrue(cookie['secure'] and cookie['httponly'])
            self.assertEqual(cookie['samesite'].lower(), 'lax')
            self.assertEqual(cookie['path'], '/')
            self.assertFalse(cookie['domain'])
            token = cookie.value
            self.assertEqual(self.client.get('/auth/me').status_code, 200)
            for path in ('/auth/google/start', '/auth/google/callback'):
                self.assertEqual(self.client.get(path).status_code, 404)
            self.assertEqual(self.post('/auth/logout').status_code, 200)
            self.client.cookies.set(settings.session_cookie_name, token)
            self.assertEqual(self.client.get('/auth/me').status_code, 401)


class NWISBoundaryTests(unittest.TestCase):
    setUp = test_nwis.NWISTests.setUp

    def test_anonymous_pdf_and_injection_filter_are_bounded(self):
        app.dependency_overrides[get_optional_current_user] = lambda: None
        self.assertEqual(self.client.get('/api/reports/OFF-04-DDR/source').status_code, 401)
        app.dependency_overrides[get_optional_current_user] = lambda: self.actor
        response = self.client.get('/api/events', params={'formation': "TIPAM_A' OR 1=1--"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'], [])
        response = self.client.get('/api/reports/../../.env/source')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('DATABASE_URL', response.text)

    def test_upload_type_and_stream_size_limit(self):
        self.actor.role = 'admin'
        self.db.commit()
        path = '/api/ingest/report?well_id=ACTIVE-01&type=DDR&dataset_origin=synthetic_demo'
        self.assertEqual(self.client.post(path, content=b'%PDF-', headers={'Content-Type': 'text/plain'}).status_code, 415)
        response = self.client.post(path, content=b'%PDF-'+b'x'*(20*1024*1024), headers={'Content-Type': 'application/pdf'})
        self.assertEqual(response.status_code, 413)


if __name__ == '__main__':
    unittest.main()
