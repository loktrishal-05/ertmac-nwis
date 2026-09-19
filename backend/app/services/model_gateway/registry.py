"""Runtime selection and URL/host policy.

Two independent controls guard MODEL_BASE_URL: an allowlist (only these hosts
are permitted) and a denylist (these hosted-provider hosts are never permitted,
even if someone adds them to the allowlist by mistake). Deliberately redundant:
a one-line allowlist edit alone must not be enough to break sovereignty."""
import ipaddress
from urllib.parse import urlparse

from app.services.model_gateway.errors import ModelConfigurationError

DENYLISTED_HOSTS = frozenset({
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.cohere.ai",
    "api.mistral.ai",
    "api.together.xyz",
    "openrouter.ai",
    "api.groq.com",
})
DENYLISTED_HOST_SUFFIXES = (".azure.com",)
# bedrock*.amazonaws.com: AWS Bedrock hostnames vary by service/region
# (bedrock-runtime.<region>.amazonaws.com, bedrock.<region>.amazonaws.com, ...).
DENYLISTED_BEDROCK_PREFIX_SUFFIX = ("bedrock", ".amazonaws.com")


def _check_denylist(host: str) -> None:
    if host in DENYLISTED_HOSTS:
        raise ModelConfigurationError(f"Host '{host}' is a hosted AI provider endpoint and is never permitted")
    for suffix in DENYLISTED_HOST_SUFFIXES:
        if host.endswith(suffix):
            raise ModelConfigurationError(f"Host '{host}' matches denylisted suffix '{suffix}'")
    prefix, suffix = DENYLISTED_BEDROCK_PREFIX_SUFFIX
    if host.startswith(prefix) and host.endswith(suffix):
        raise ModelConfigurationError(f"Host '{host}' matches the denylisted AWS Bedrock pattern")


def validate_model_url(base_url: str, allowed_hosts: set[str]) -> str:
    """Raises ModelConfigurationError unless base_url is http(s), its host is in
    allowed_hosts, AND the host is not independently denylisted."""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ModelConfigurationError(f"MODEL_BASE_URL must be an http(s) URL with a host, got {base_url!r}")
    host = parsed.hostname.lower()
    if host not in {h.lower() for h in allowed_hosts}:
        raise ModelConfigurationError(f"Host '{host}' is not in MODEL_ALLOWED_HOSTS")
    _check_denylist(host)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not (address.is_loopback or address.is_private or address.is_link_local):
        raise ModelConfigurationError(f"Model runtime host '{host}' is public; use a loopback/private on-prem address")
    if address is None and "." in host and not host.endswith((".local", ".internal", ".svc")):
        raise ModelConfigurationError(f"Model runtime host '{host}' is not a local on-prem hostname")
    return base_url


def get_runtime(name: str, settings):
    """Lazily import and construct the selected runtime adapter."""
    if name == "ollama":
        from app.services.model_gateway.ollama_runtime import OllamaRuntime
        return OllamaRuntime(settings)
    if name == "vllm":
        from app.services.model_gateway.vllm_runtime import VLLMRuntime
        return VLLMRuntime(settings)
    raise ModelConfigurationError(f"Unknown MODEL_RUNTIME '{name}'; expected 'ollama' or 'vllm'")
