"""Read-only HTTP startup validation. Exit nonzero if any dependency/proof fails."""
import argparse
import json
import sys
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    results = {}
    success = True
    with httpx.Client(base_url=args.backend_url, timeout=30, trust_env=False, follow_redirects=False) as client:
        for path in ('/health', '/ready', '/sovereignty/proof'):
            try:
                response = client.get(path)
                body = response.json()
                passed = response.status_code == 200
                if path == '/health':
                    passed &= body.get('status') == 'ok'
                elif path == '/ready':
                    passed &= body.get('status') == 'ready'
                else:
                    passed &= (body.get('status') == 'sovereign' and body.get('hosted_ai_configured') is False
                               and body.get('external_ai_calls') == 0 and body.get('network_egress_enforced') is False)
                results[path] = {'passed': passed, 'http_status': response.status_code, 'body': body}
            except (httpx.HTTPError, ValueError):
                passed = False
                results[path] = {'passed': False, 'error': 'unreachable or invalid JSON'}
            success &= passed
    print(json.dumps(results, indent=2))
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
