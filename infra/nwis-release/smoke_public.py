"""Run AFTER deployment authorization. Tests HTTPS proxy/cookie boundaries, not fixture mode."""
import argparse
from getpass import getpass
from http.cookiejar import CookieJar
from http.cookies import SimpleCookie
import json
from statistics import median
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4
from prepare_release import vercel_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--browser-origin', help='Exact frontend CORS origin when probing gateway directly')
    parser.add_argument('--username', default='nwis_demo_reviewer')
    args = parser.parse_args()
    vercel_config(args.origin)
    origin = args.origin.rstrip('/')
    browser_origin = (args.browser_origin or origin).rstrip('/')
    vercel_config(browser_origin)
    client = build_opener(HTTPCookieProcessor(CookieJar()))

    def call(path, body=None, expected=200, request_origin=browser_origin, pdf=False):
        payload = json.dumps(body).encode() if body is not None else None
        request = Request(origin+path, data=payload, headers={'Origin': request_origin, 'Accept': 'application/json',
                          'Content-Type': 'application/json'})
        try:
            response = client.open(request, timeout=180)
        except HTTPError as error:
            response = error
        with response:
            assert response.status == expected, (path, response.status)
            assert response.geturl() == origin+path, 'Unexpected redirect'
            content = response.read()
            if pdf:
                assert content.startswith(b'%PDF-') and 'application/pdf' in response.headers.get('Content-Type', '')
                return content
            assert 'no-store' in response.headers.get('Cache-Control', ''), path
            data = json.loads(content)
            if path == '/api/auth/login':
                cookie = SimpleCookie()
                cookie.load(response.headers.get('Set-Cookie', ''))
                session = cookie['workbench_session']
                assert session['secure'] and session['httponly'] and session['samesite'].lower() == 'lax'
                assert session['path'] == '/' and not session['domain']
            return data

    ready = call('/api/ready')
    assert ready['status'] == 'ready' and all(ready['checks'].values())
    assert call('/api/health')['status'] == 'ok'
    call('/api/wells', expected=401)
    capabilities = call('/api/auth/capabilities')
    assert not any(capabilities[k] for k in ('signup','google','password_recovery','email_recovery'))
    actor = call('/api/auth/login', {'username': args.username, 'password': getpass('Demo reviewer password: ')})
    assert actor['role'] == 'reviewer'
    assert call('/api/auth/me')['id'] == actor['id']
    terms = {'version': 'nwis-advisory-v1', 'accepted': True}
    call('/api/terms/accept', terms, expected=403, request_origin='https://untrusted.invalid')
    assert call('/api/terms/accept', terms)['accepted']
    assert call('/api/wells')['items']
    assert call('/api/wells/ACTIVE-01/nearby')['items'][0]['offset_well_id'] == 'OFF-04'
    risk = call('/api/wells/ACTIVE-01/risk?lookahead_m=100')
    assert risk['dataset_origin'] == 'synthetic_demo' and not risk['calibrated']
    call('/api/reports/OFF-04-DDR/source', pdf=True)
    timings = []
    for _ in range(4):
        start = perf_counter()
        result = call('/api/query', {'mode': 'nwis_evidence', 'request_id': str(uuid4()),
            'well_id': 'ACTIVE-01', 'query': 'OFF-04 TIPAM_A stuck pipe 2470 m', 'retrieval': 'hybrid',
            'formation': 'TIPAM_A', 'type': 'stuck_pipe', 'offset_limit': 1})
        assert result['evidence'] and all(e['id'] in result['answer'] for e in result['evidence'])
        timings.append(round(perf_counter()-start, 3))
    assert median(timings[1:]) < 30, 'Warm hybrid queries exceed frontend timeout'
    assert call('/api/audit/verify')['valid']
    assert all(e['actor_id'] == actor['id'] for e in call('/api/audit')['items'])
    call('/api/admin/users', expected=404)
    call('/api/auth/signup', {}, expected=404)
    call('/api/auth/logout', {})
    call('/api/wells', expected=401)
    print(json.dumps({'https_routing_cookie_origin_checks': 'passed', 'hybrid_query_seconds': timings,
                      'warm_median_seconds': median(timings[1:])}, indent=2))


if __name__ == '__main__':
    main()
