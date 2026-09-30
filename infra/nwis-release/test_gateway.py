"""Disposable real Nginx routing test. No host ports, release services, or tunnel."""
from pathlib import Path
import shlex
import subprocess
import tempfile

IMAGE = 'nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236'
ROUTES = {
    '/api/wells': '/api/wells',
    '/api/wells/ACTIVE-01/risk?lookahead_m=100': '/api/wells/ACTIVE-01/risk?lookahead_m=100',
    '/api/query': '/api/query',
    '/api/events?depth_basis=tvd': '/api/events?depth_basis=tvd',
    '/api/assessments/example': '/api/assessments/example',
    '/api/advisories/example/review': '/api/advisories/example/review',
    '/api/terms/accept': '/api/terms/accept',
    '/api/reports/OFF-04-DDR/source': '/api/reports/OFF-04-DDR/source',
    '/api/audit?limit=100': '/api/audit?limit=100',
    '/api/audit/verify': '/audit/verify',
    '/api/auth/login': '/auth/login',
    '/api/auth/me': '/auth/me',
    '/api/auth/sessions/example/revoke': '/auth/sessions/example/revoke',
    '/api/health': '/health',
    '/api/ready': '/ready',
}


def main():
    original = Path(__file__).with_name('nginx.conf').read_text(encoding='utf-8-sig')
    mock = '''
    server {
        listen 8000;
        add_header Set-Cookie "workbench_session=synthetic; Path=/; Secure; HttpOnly; SameSite=Lax" always;
        location / { return 200 "$request_uri|$http_origin|$http_cookie"; }
    }
}'''
    config = original.rsplit('}', 1)[0]+mock
    script = ['set -eu', 'nginx -t -c /preflight/nginx.conf', 'nginx -c /preflight/nginx.conf']
    for incoming, expected in ROUTES.items():
        url = shlex.quote('http://127.0.0.1:8080'+incoming)
        value = shlex.quote(expected+'|https://judge.example.org|workbench_session=synthetic')
        script += [f'body=$(wget -qO- --header="Origin: https://judge.example.org" --header="Cookie: workbench_session=synthetic" {url})',
                   f'test "$body" = {value}']
    for path in ('/docs', '/openapi.json', '/auth/login', '/admin/users', '/api/admin/users', '/api/ingest/report', '/api/audit/log', '/api/auth/signup'):
        script += [f'if wget -qO- http://127.0.0.1:8080{path}; then exit 1; fi']
    script += [
        'wget -S -O /dev/null http://127.0.0.1:8080/api/auth/me 2>/tmp/headers',
        "grep -qi 'Cache-Control: no-store' /tmp/headers",
        "grep -qi 'Set-Cookie: workbench_session=synthetic; Path=/; Secure; HttpOnly; SameSite=Lax' /tmp/headers",
        'nginx -s quit -c /preflight/nginx.conf',
        'echo "PASS: 15 routes, 8 denied routes, Origin/Cookie forwarding, Secure Set-Cookie and no-store."',
    ]
    with tempfile.TemporaryDirectory(prefix='nwis-d2-gateway-') as folder:
        Path(folder, 'nginx.conf').write_text(config, encoding='utf-8')
        subprocess.run(['docker', 'run', '--rm', '-i', '--network', 'none',
                        '--add-host', 'backend:127.0.0.1', '--user', '101:101', '--read-only',
                        '--tmpfs', '/tmp', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                        '--mount', f'type=bind,source={folder},target=/preflight,readonly',
                        '--entrypoint', 'sh', IMAGE, '-s'], input=('\n'.join(script)+'\n').encode('utf-8'), check=True)


if __name__ == '__main__':
    main()
