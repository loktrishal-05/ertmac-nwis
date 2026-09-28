"""Opt-in, operator-registered public GETs. No query, file, or plant payload API."""
import ipaddress
import json
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import Field, model_validator

from app.core.config import settings
from app.services.language_resources import LanguageResource, PolicyDenied, permitted


class PublicResource(LanguageResource):
    provider: Literal["data.gov.in", "API Setu"]
    resource_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    deployment: Literal["external_api"] = "external_api"
    classification: Literal["PUBLIC_EXTERNAL_OPTIONAL"] = "PUBLIC_EXTERNAL_OPTIONAL"
    base_url: str
    # Entire reviewed resource URL, including any resource path. No guessed endpoints.
    public_params: dict[str, str] = Field(default_factory=dict)
    secret_env: str = Field(default="", pattern=r"^(?:WORKBENCH_GOV_[A-Z0-9_]+)?$")
    auth_location: Literal["header", "query"] = "header"
    auth_name: str = Field(default="Authorization", pattern=r"^[A-Za-z0-9_-]{1,60}$")
    timeout_seconds: float = Field(default=10, gt=0, le=30)
    retries: int = Field(default=1, ge=0, le=2)

    @model_validator(mode="after")
    def reviewed_public_endpoint(self):
        p = urlsplit(self.base_url)
        if (p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment
                or p.port not in (None, 443) or not p.hostname.endswith((".gov.in", ".nic.in"))):
            raise ValueError("Resource requires a credential-free Government HTTPS URL")
        if self.provider == "data.gov.in" and not (p.hostname == "data.gov.in" or p.hostname.endswith(".data.gov.in")):
            raise ValueError("data.gov.in resource must use its own domain")
        if not self.approved_by:
            raise ValueError("Public resource registration requires operator review")
        if any(k.lower() in {"api-key", "api_key", "apikey", "authorization", "token", "password"}
               for k in self.public_params):
            raise ValueError("Credentials must come from secret_env")
        return self


def registry(config=settings):
    if not config.government_resource_registry:
        return {}
    rows = [PublicResource.model_validate(r) for r in
            json.loads(Path(config.government_resource_registry).read_text(encoding="utf-8"))]
    if len({r.resource_id for r in rows}) != len(rows):
        raise ValueError("Duplicate government resource ID")
    return {r.resource_id: r for r in rows}


def fetch_public_resource(resource_id, *, data_class="CONFIDENTIAL", config=settings):
    """Only a registered static request can leave the host; caller must explicitly declare PUBLIC.

    Operator registry and environment are trusted configuration. Never register plant identifiers.
    This module is intentionally not an agent tool or an HTTP route.
    """
    if config.deployment_mode != "public" or not config.government_resources_enabled or data_class != "PUBLIC":
        raise PolicyDenied("Government resources require enabled public deployment and PUBLIC request")
    resource = registry(config).get(resource_id)
    if resource is None or not permitted(resource, data_class, config, external_enabled=True):
        raise PolicyDenied("Government resource is not registered or permitted")
    params, headers = dict(resource.public_params), {}
    if resource.secret_env:
        secret = os.environ.get(resource.secret_env)
        if not secret:
            raise PolicyDenied("Government resource authentication is not configured")
        (headers if resource.auth_location == "header" else params)[resource.auth_name] = secret
    try:
        host = urlsplit(resource.base_url).hostname
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise PolicyDenied("Government endpoint must resolve to public addresses")
        with httpx.Client(timeout=resource.timeout_seconds, trust_env=False, follow_redirects=False) as client:
            for attempt in range(resource.retries + 1):
                with client.stream("GET", resource.base_url, params=params, headers=headers) as response:
                    if response.status_code in (429, 502, 503, 504) and attempt < resource.retries:
                        # Bounded backoff; never obey an unbounded Retry-After.
                        time.sleep(min(attempt + 1, 2))
                        continue
                    if response.status_code != 200:
                        raise PolicyDenied("Government resource unavailable or rate limited")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 2 * 1024 * 1024:
                            raise PolicyDenied("Government response exceeds 2 MiB")
                    data = json.loads(body)
                    return {"data": data, "provenance": {
                        "provider": resource.provider, "resource_id": resource.resource_id,
                        "source": resource.source, "license": resource.license,
                        "classification": resource.classification, "data_classification": "PUBLIC",
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "authority": "public_reference_only_not_plant_evidence"}}
    except (httpx.HTTPError, OSError, ValueError) as error:
        # Never propagate request URLs (query API keys), response bodies or raw exception text.
        raise PolicyDenied("Government resource request failed") from None
