"""Mirror of the release gateway map (infra/nwis-release/nginx.conf): NWIS routes keep /api, approved shared
routes are stripped exactly once, everything else is refused. Underscore prefix: not a Vercel function."""
import re

EXACT = {"/api/audit": "/api/audit", "/api/health": "/health", "/api/ready": "/ready", "/api/audit/verify": "/audit/verify"}
KEEP = re.compile(r"^/api/(wells|events|query|assessments|advisories|terms|reports)(/|$)")
STRIP = (re.compile(r"^/api/(auth/(capabilities|login|logout|me|sessions)(/|$).*)$"),
         re.compile(r"^/api/(auth/(signup|email/(request-verification|verify)|password/(forgot|verify-otp|reset)))$"))


def upstream(path):
    if path in EXACT:
        return EXACT[path]
    if KEEP.match(path):
        return path
    for rule in STRIP:
        if match := rule.match(path):
            return "/" + match.group(1)
    return None
