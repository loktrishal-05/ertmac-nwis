"""Focused release scan. Prints file/kind only, never credential values."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = {
    'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'google_secret': r'GOCSPX-[A-Za-z0-9_-]{20,}',
    'google_api_key': r'AIza[0-9A-Za-z_-]{30,}',
    'github_token': r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
    'aws_key': r'AKIA[0-9A-Z]{16}',
    'slack_token': r'xox[baprs]-[0-9A-Za-z-]{20,}',
    'openai_key': r'sk-(?:proj-)?[A-Za-z0-9_-]{40,}',
    'jwt': r'eyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{20,}',
}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare-private-env', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'data/final_security.json')
    args = parser.parse_args()
    names = git('ls-files', '-z').decode().split('\0')
    findings = []
    patterns = {kind: re.compile(pattern) for kind, pattern in PATTERNS.items()}
    # Compare actual configured secret values without exposing them or copying the source environment.
    private = []
    if args.compare_private_env and args.compare_private_env.is_file():
        for line in args.compare_private_env.read_text(encoding='utf-8-sig').splitlines():
            key, _, value = line.partition('=')
            if key.strip() in {'NWIS_AUTH_SECRET', 'NWIS_SMTP_PASSWORD', 'NWIS_GOOGLE_CLIENT_SECRET'}:
                value = value.strip().strip('\"\'')
                if len(value) >= 8:
                    private.append(value)
    scanned = 0
    for name in filter(None, names):
        path = ROOT/name
        if path.name.startswith('.env') and not path.name.endswith('.example'):
            findings.append({'file': name, 'kind': 'tracked_environment'})
        if path.suffix.lower() in {'.pem', '.key', '.p12', '.pfx'}:
            findings.append({'file': name, 'kind': 'tracked_certificate'})
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if b'\0' in raw:
            continue
        value = raw.decode('utf-8', errors='replace')
        scanned += 1
        findings.extend({'file': name, 'kind': kind} for kind, pattern in patterns.items() if pattern.search(value))
        if any(secret in value for secret in private):
            findings.append({'file': name, 'kind': 'configured_private_secret'})
    history = git('log', '--all', '--format=', '--name-only', '--', '.env', '**/.env', '**/.env.local').decode().strip()
    if history:
        findings.append({'kind': 'environment_in_history'})
    result = dict(tracked_text_files=scanned, compared_private_values=len(private),
                  findings=findings, scope='current tracked text, known live-secret comparison, exact env history paths')
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(findings))


if __name__ == '__main__':
    main()
