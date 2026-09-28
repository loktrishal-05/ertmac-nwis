# Government public-resource integration

These resources are optional references, never model authority or permission to operate equipment.
No concrete government API endpoint has been registered or called in Phase E. There is no plant-write integration.

| Resource | Role and status | Confidential-data eligibility | Deployment | Limitations |
|---|---|---|---|---|
| AIKosh | Operator-reviewed downloadable language/model resources; Phase D registry reused | Only a locally held artifact with source, licence, explicit approver and SHA-256 may be `LOCAL_APPROVED` | Local files and local runtime after provisioning | A catalogue listing is not approval. Release health verifies the actual local source file against its hash. Runtime adapter and licence fitness need operator review. |
| BHASHINI | Phase D public language service policy; external client remains unimplemented | Never eligible; confidential deployment rejects even explicitly public requests | `PUBLIC_EXTERNAL_OPTIONAL`, disabled by default | No hosted fallback for local voice. Public policy enablement does not mean an implemented speech integration. |
| data.gov.in | Optional public GET connector and registration schema implemented | Never receives confidential payloads; unavailable in confidential deployment | `PUBLIC_EXTERNAL_OPTIONAL`; separate public-mode installation | No resource endpoint shipped; operator must verify and register a resource and its terms. Public results are not plant evidence. |
| API Setu | **API Setu-ready** generic registered Government GET provider | Same denial as data.gov.in | `PUBLIC_EXTERNAL_OPTIONAL`, disabled by default | No concrete API Setu API claimed. OAuth exchange, mTLS, non-Government provider domains or non-GET protocols require separately reviewed adapters. |
| DigiLocker | Evaluated but not part of the core confidential inference workflow | No integration or confidential-data transfer | None | Future potential: verified personnel, training, certificate and document workflows. Identity, consent and authorization must be designed for that use case. |

## One policy

`app.services.language_resources` remains the classification and permission gate. It defines
`LOCAL_APPROVED`, `PUBLIC_EXTERNAL_OPTIONAL`, and `DISABLED_FOR_CONFIDENTIAL_DATA`.
Unreviewed language artifacts stay disabled. `WORKBENCH_DEPLOYMENT_MODE=confidential`
blocks public external resources regardless of a caller's classification. The existing model gateway
continues to deny hosted inference in every deployment mode. Public deployment mode does not enable hosted AI.

The new `government_resources` service accepts only a resource ID and an explicit `PUBLIC`
declaration. It accepts no query text, uploaded file, runtime parameters or request body.
It is not registered as an agent tool or exposed as a user-facing API. Configuration must be writable
only by operators: an operator could otherwise encode sensitive identifiers into static URLs or parameters.
This is a trust boundary, not automated classification of arbitrary text.

## Registering a public resource

Use a separate non-confidential installation, never the confidential production instance.
Obtain the actual resource URL and authentication contract from its Government publisher;
record the catalogue/source reference, licence and approver. No endpoint is inferred from a resource name.

Create a protected JSON list outside source control and validate each entry against
`app.services.government_resources.PublicResource`. Required fields are:

| Field | Value |
|---|---|
| `resource_id` | Local stable identifier, 1–100 letters/digits/underscore/hyphen |
| `name`, `provider` | Descriptive name; provider is `data.gov.in` or `API Setu` |
| `source`, `license`, `intended_use`, `approved_by` | Reviewed provenance and intended public use |
| `base_url` | Complete verified resource URL including its path; HTTPS on a `.gov.in` or `.nic.in` host, without credentials, query or fragment. data.gov.in uses its own domain. |
| `public_params` | Optional fixed, operator-reviewed public parameters; never plant identifiers or credentials |
| `secret_env` | Optional environment variable name beginning `WORKBENCH_GOV_`; never the key value |
| `auth_location`, `auth_name` | `header` or `query`, and the publisher's exact authentication field name |
| `timeout_seconds`, `retries` | Defaults 10 seconds per HTTP operation and one status retry; maxima 30 and two |

Set in the public installation's protected configuration:

```dotenv
WORKBENCH_DEPLOYMENT_MODE=public
WORKBENCH_GOVERNMENT_RESOURCES_ENABLED=true
WORKBENCH_GOVERNMENT_RESOURCE_REGISTRY=C:/workbench-config/public-resources.json
```

Inject any `WORKBENCH_GOV_*` secret into the service process environment from the site's secret manager.
These authentication variables are read from the process environment, not from the resource JSON or
the application's `.env` parsing. Header values must include the publisher's required scheme if applicable.
Do not put keys in logs, examples or command history. A trusted local caller uses:

```python
from app.services.government_resources import fetch_public_resource
result = fetch_public_resource("operator-registered-id", data_class="PUBLIC")
```

Only registered static GETs are supported. Redirects and environment proxies are disabled;
DNS must resolve to public addresses. Responses are capped at 2 MiB and must be JSON.
429/502/503/504 receive bounded backoff and retries; transport failures fail closed without replay.
The caller must schedule requests within the publisher's quota; there is no global distributed rate limiter.
Timeouts are HTTP operation limits, not a guaranteed end-to-end deadline against slow streaming.
Diagnostics omit raw URLs, authentication and upstream error bodies. Returned **data** is public upstream
content and must still be treated as untrusted. Provenance records provider, resource ID, source, licence,
retrieval time, public classification and the `public_reference_only_not_plant_evidence` limitation.

## Deployment enforcement

Application rejection is not a firewall. Enforce deny-by-default outbound access on confidential hosts,
containers and service accounts. A separate public-resource host may allow only reviewed destinations.
DNS checks have a DNS/network time-of-check limitation; an egress proxy/firewall must enforce actual routes.
There are no external calls in deterministic connector tests. No live Government API verification is claimed.
