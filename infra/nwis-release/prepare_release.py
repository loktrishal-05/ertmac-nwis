"""Prepare frontend release files from an accepted D1 commit. Never deploys or links Vercel."""
import argparse
import io
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '579de878f5edf9d1e76545cc11e939750e751266'
BACKEND = 'e988cc36b3c7f3e9b14b5d7f2ace58335d34e705'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def vercel_config(origin):
    url = urlsplit(origin)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password or
            url.path not in ('', '/') or url.query or url.fragment or url.port not in (None, 443)):
        raise ValueError('Gateway must be an HTTPS origin without credentials, path, query or fragment')
    if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', url.hostname) or '.' not in url.hostname:
        raise ValueError('Use the reserved public gateway hostname')
    if url.hostname.endswith(('.invalid', '.test', '.local', '.internal', '.example')) or url.hostname == 'example.com':
        raise ValueError('Replace the placeholder with the assigned gateway hostname')
    try:
        ipaddress.ip_address(url.hostname)
    except ValueError:
        pass
    else:
        raise ValueError('Use a reserved DNS hostname with valid TLS, not an IP literal')
    template = Path(__file__).with_name('vercel.template.json').read_text(encoding='utf-8-sig')
    return json.loads(template.replace('__NWIS_GATEWAY_ORIGIN__', origin.rstrip('/')))


def frontend_sha(ref):
    if not re.fullmatch(r'[0-9a-f]{7,40}', ref):
        raise ValueError('Supply Claude D1 commit SHA, not a moving branch name')
    sha = git('rev-parse', '--verify', ref+'^{commit}').decode().strip()
    if sha == BASELINE:
        raise ValueError('D1 visual commit is still pending; baseline is not a release candidate')
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', BASELINE, sha], check=True)
    return sha


def export_frontend(sha, destination):
    destination.mkdir(parents=True, exist_ok=False)
    # Export committed frontend files only: never copy a working tree, tokens or .env files.
    with tarfile.open(fileobj=io.BytesIO(git('archive', '--format=tar', sha, 'frontend'))) as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != 'frontend':
                raise ValueError('Unsafe archive path')
            relative = Path(*path.parts[1:])
            if not path.parts[1:] or any(part.startswith(('.env', '.vercel')) for part in relative.parts):
                continue
            target = destination/relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source:
                    target.write_bytes(source.read())
            else:
                raise ValueError('Release archive must contain only regular files/directories')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-sha', required=True)
    parser.add_argument('--gateway-origin', required=True)
    args = parser.parse_args()
    sha = frontend_sha(args.frontend_sha)
    config = vercel_config(args.gateway_origin)
    # D2 may add deployment files, but must not alter the accepted backend or its image recipe.
    subprocess.run(['git', '-C', str(ROOT), 'diff', '--exit-code', BACKEND, '--',
                    'backend', 'infra/Dockerfile.backend', '.dockerignore'], check=True)
    destination = ROOT/'data'/'nwis-release'/sha/'frontend'
    export_frontend(sha, destination)
    (destination/'vercel.json').write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
    (destination/'.vercelignore').write_text('.env*\n.vercel\nnode_modules\ndist\n', encoding='utf-8')
    (destination.parent/'release.json').write_text(json.dumps({
        'backend_sha': BACKEND, 'frontend_sha': sha, 'frontend_baseline': BASELINE,
        'preflight_sha': git('rev-parse', 'HEAD').decode().strip(),
        'gateway_origin': args.gateway_origin.rstrip('/'), 'deployed': False,
    }, indent=2)+'\n', encoding='utf-8')
    print(f'Prepared only: {destination}\nNo build, upload, link, push, merge or deployment performed.')


if __name__ == '__main__':
    main()
