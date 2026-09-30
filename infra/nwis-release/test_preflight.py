"""Offline checks for D2 release preparation; no deployment or network calls."""
import json
from pathlib import Path
import tempfile
import unittest
from prepare_release import BASELINE, export_frontend, frontend_sha, vercel_config


class ReleaseTests(unittest.TestCase):
    def test_gateway_origin_and_no_cache(self):
        config = vercel_config('https://nwis-judge.ngrok.app')
        self.assertEqual(config['rewrites'][0]['destination'], 'https://nwis-judge.ngrok.app/api/:path*')
        self.assertIn('(?!api', config['rewrites'][1]['source'])
        headers = {h['key']: h['value'] for h in config['headers'][0]['headers']}
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['x-vercel-enable-rewrite-caching'], '0')
        self.assertIn('VITE_API_BASE_URL=/api', config['buildCommand'])
        for origin in ('http://example.org', 'https://127.0.0.1', 'https://user:pass@gateway.org',
                       'https://example.invalid', 'https://gateway.org/api', 'https://gateway.org?secret=x'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                vercel_config(origin)

    def test_pending_d1_is_blocked(self):
        with self.assertRaisesRegex(ValueError, 'pending'):
            frontend_sha(BASELINE)
        with self.assertRaises(ValueError):
            frontend_sha('pivot/nwis-frontend')

    def test_clean_baseline_export_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'frontend'
            export_frontend(BASELINE, target)
            package = json.loads((target/'package.json').read_text())
            self.assertIn('verify:dist', package['scripts'])
            self.assertTrue((target/'src/services/apiRoutes.js').is_file())
            self.assertFalse(any(p.name.startswith(('.env', '.vercel')) for p in target.rglob('*')))
            self.assertFalse((target/'backend').exists())
            with self.assertRaises(FileExistsError):
                export_frontend(BASELINE, target)


if __name__ == '__main__':
    unittest.main()
