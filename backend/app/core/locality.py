"""Configured locality, not firewall attestation."""
import ipaddress
import re
import socket
from urllib.parse import urlsplit

PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in
                         ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7'))


def classify_host(host):
    host = (host or '').lower()
    if host == 'localhost':
        return 'local'
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if re.fullmatch(r'[a-z][a-z0-9-]*(?:\.(?:[a-z0-9-]+))*', host) and (
                '.' not in host or host.endswith(('.local', '.internal', '.svc'))):
            return 'private'
        return 'invalid'
    if address.is_loopback:
        return 'local'
    return 'private' if any(address in net for net in PRIVATE_NETWORKS) else 'invalid'


def classify_http_url(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment or parsed.port == 0):
            return 'invalid'
        return classify_host(parsed.hostname)
    except ValueError:
        return 'invalid'


def require_private_resolution(url):
    """Check DNS before dispatch; not a defense against network/DNS TOCTOU or proxies."""
    parsed = urlsplit(url)
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80),
                                   type=socket.SOCK_STREAM)
    if not addresses or any(classify_host(row[4][0]) == 'invalid' for row in addresses):
        raise ValueError('Endpoint does not resolve exclusively to loopback/private addresses')


def classify_database(url):
    from sqlalchemy.engine import make_url
    try:
        parsed = make_url(url)
        if parsed.get_backend_name() != 'postgresql' or any(
                key in parsed.query for key in ('host', 'hostaddr', 'service', 'servicefile')):
            return 'invalid'
        return classify_host(parsed.host)
    except (ValueError, TypeError):
        return 'invalid'


def local_filesystem(path):
    value = str(path)
    return not (value.startswith(('\\\\', '//')) or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]+:', value))
