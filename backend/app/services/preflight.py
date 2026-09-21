"""Phase 5E -- deterministic pre-routing guardrails.

Runs BEFORE the LangGraph router, in plain Python, with no model call. The
LLM never decides authorization/safety here -- exactly the same posture
Phase 5A/5B/5C/5D already hold for governance/approval/audit/evidence
(docs/phase5a.md: "The existing router remains model-assisted; 5A does not
claim it is deterministic or implement pre-routing Phase 5E guardrails.").

Four independent, composed checks, each able to end the request before any
gateway call:

1. Access-scope validity (`_check_scope`) -- reuses the request's own
   `access_scope` field (Phase 3A/4D: metadata/filtering only, never
   authorization by itself); an unsupported value fails closed.
2. Prompt-injection preflight (`_detect_injection`) -- reuses
   `app.agents.safety_language.strip_quoted_spans` so a quoted example of an
   injection phrase (e.g. inside an incident report) is never itself treated
   as an attempt.
3. Unsafe plant-action preflight (`_detect_unsafe_action`) -- catches a
   request asking the AI to PERFORM or AUTHORIZE a plant action, as opposed
   to asking an INFORMATIONAL question about one; the system has no
   plant-write tool at all (app.agents.registry is read-only-only), so this
   only ever prevents mis-routing a request that could never be honoured
   safely as a normal informational answer.
4. Company-domain classification (`classify_domain`) -- IN_SCOPE /
   OUT_OF_SCOPE / UNCERTAIN, composed from the existing Phase 3B1 tag
   vocabulary (`app.services.tags`), a bounded known-intent phrase list, and
   a bounded out-of-domain marker list. Deliberately conservative: a query
   with no recognizable signal either way is UNCERTAIN (ask), never a guess
   in either direction.

D-010 (`app.agents.safety_language`) is UNCHANGED and remains a supplemental
signal applied to SPECIALIST OUTPUT only (docs/phase4-decisions.md D-010);
none of this module's checks feed it, and it never gates this module.
"""
import re
from dataclasses import dataclass, field

from app.agents.enforcement import refuse
from app.agents.safety_language import strip_quoted_spans
from app.schemas.agent_outputs import Refusal
from app.services.tags import extract_tags

# The only access_scope values this deployment's retrieval layer actually
# recognizes today (docs/phase3a.md: "access_scope is metadata/filtering
# only, not authorization"). A client requesting anything else cannot be
# silently widened or narrowed by this gate -- it fails closed. Extend this
# set only alongside real ingested/retrieval support for a new scope value,
# the same way app.services.tags.DEFAULT_PATTERNS is a plain, hand-maintained
# constant rather than a database-driven list.
SUPPORTED_ACCESS_SCOPES = frozenset({"internal"})

_INJECTION_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"ignore\s+(?:all\s+|any\s+)?(?:previous\s+|prior\s+|above\s+|earlier\s+|the\s+|your\s+)?instructions",
    r"disregard\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier|your)\s+(?:instructions|rules|policy|policies|guardrails)",
    r"forget\s+(?:all\s+|any\s+)?(?:previous|prior|your)\s+instructions",
    r"reveal\s+(?:the\s+|your\s+)?(?:system\s+)?prompt",
    r"(?:show|print|output)\s+(?:me\s+)?(?:the\s+|your\s+)?system\s+prompt",
    r"bypass\s+(?:the\s+)?approval",
    r"pretend\s+(?:that\s+)?(?:you\s*(?:'re|\s+are)|i\s*(?:'m|\s+am))\s+(?:an?\s+)?admin",
    r"act\s+as\s+(?:if\s+you\s+(?:are|were)\s+)?(?:an?\s+)?admin",
    r"disable\s+(?:the\s+)?safety\s+checks?",
    r"you\s+are\s+now\s+in\s+(?:developer|admin|unrestricted)\s+mode",
))

_INFORMATIONAL_MARKER = re.compile(
    r"\b(?:what|which|when|who|why|describe|describes|describing|explain|explains|explained|"
    r"summari[sz]e|tell\s+me\s+about|how\s+(?:do|does|would|should|can)\s+(?:i|we|one|you)|"
    r"is\s+it\s+safe|steps?\s+(?:to|for)|procedure\s+(?:for|to)|\bsop\b|standard\s+operating\s+procedure|"
    r"history\s+of|who\s+approved|documentation\s+(?:for|on)|says?\s+about)\b", re.IGNORECASE,
)
_ACTION_VERB = r"(?:start|stop|restart|shut\s*down|open|close|isolate|bypass|override|suppress|defeat|energize|de-energize)"
_UNSAFE_ACTION_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    rf"^\s*(?:please\s+)?{_ACTION_VERB}\b",
    rf"\b(?:can|could|would|will)\s+you\s+{_ACTION_VERB}\b",
    rf"\b(?:issue|complete|approve|authorize|authorise)\s+(?:the\s+)?(?:permit|loto|lock[- ]?out[- ]?tag[- ]?out|isolation)\b",
    r"\bclaim\s+(?:physical\s+)?isolation\b",
    r"\b(?:operate|control|access)\s+(?:the\s+)?(?:scada|dcs)\b",
))

# Strong, bounded signals of an industrial/company-scoped task. Composed with
# the Phase 3B1 tag regex below -- never keyword matching alone.
_STRONG_INTENT_PHRASES = (
    "maintenance history", "work order", "incident report", "pending approval", "pending approvals",
    "vibration trend", "sensor reading", "sensor trend", "audit log", "governance status",
    "approval status", "evidence manifest", "p&id", "pid drawing", "process optimization",
    "downtime", "failure mode", "root cause", "shutdown procedure", "isolation procedure",
    "permit to work", "loto procedure", "interlock", "alarm history", "asset health",
    "reliability", "standard operating procedure",
)
_EQUIPMENT_NOUNS = re.compile(
    r"\b(?:pump|valve|compressor|motor|tank|vessel|exchanger|turbine|boiler|reactor|sensor|"
    r"instrument|equipment|asset|actuator|pipeline|manifold)s?\b", re.IGNORECASE,
)
_SOP_REFERENCE = re.compile(r"\bsop[- ]?\d+\b", re.IGNORECASE)

# Generic physical-quantity/property nouns: real industrial vocabulary, but
# with no equipment/procedure/tag context too ambiguous to route -- exactly
# the brief's own "Tell me about pressure" example.
_WEAK_INDUSTRIAL_NOUNS = re.compile(
    r"\b(?:pressure|temperature|flow|level|speed|efficiency|corrosion|noise|leak)\b", re.IGNORECASE,
)

# A bounded, deliberately non-exhaustive list of clearly non-industrial
# general-chat topics (same honesty as D-010's own "necessarily incomplete"
# framing, docs/phase4-decisions.md D-010). Composed with the strong-signal
# check above so a company name or brand mention next to one of these does
# not itself grant scope.
_OUT_OF_DOMAIN_MARKER = re.compile(
    r"\b(?:movie|film|tv\s+show|song|poem|novel|celebrity|actor|actress|joke|"
    r"football|soccer|cricket|basketball|baseball|championship|tournament|olympics|"
    r"bitcoin|cryptocurrency|crypto|forex|stock\s+market|"
    r"weather\s+forecast|horoscope|recipe|restaurant\s+recommendation|dating\s+advice|"
    r"capital\s+of|who\s+is\s+the\s+president|your\s+favorite)\b", re.IGNORECASE,
)


@dataclass
class PreflightResult:
    decision: str  # ALLOW / CLARIFY / REFUSE
    domain_status: str  # IN_SCOPE / OUT_OF_SCOPE / UNCERTAIN
    reason_code: str
    detected_risks: list[str] = field(default_factory=list)
    refusal: Refusal | None = None


def _check_scope(access_scope: str) -> str | None:
    if access_scope not in SUPPORTED_ACCESS_SCOPES:
        return "unsupported_access_scope"
    return None


def _detect_injection(query: str) -> list[str]:
    scanned = strip_quoted_spans(query or "")
    return [pattern.pattern for pattern in _INJECTION_PATTERNS if pattern.search(scanned)]


def _detect_unsafe_action(query: str) -> bool:
    scanned = strip_quoted_spans(query or "")
    for sentence in re.split(r"(?<=[.!?])\s+|[;\n]+", scanned):
        if not sentence.strip() or _INFORMATIONAL_MARKER.search(sentence):
            continue
        if any(pattern.search(sentence) for pattern in _UNSAFE_ACTION_PATTERNS):
            return True
    return False


def classify_domain(query: str) -> tuple[str, list[str]]:
    """Deterministic composition, never naive single-keyword matching: a tag
    hit, a known operational phrase, or an equipment noun is a strong signal;
    an out-of-domain marker only wins when no strong signal is also present
    (so a company/brand mention next to an unrelated request cannot bypass
    the gate -- see test_company_name_does_not_bypass_domain_gate)."""
    text = query or ""
    tags = extract_tags(text)
    has_tag = any(tags.values())
    strong = has_tag or bool(_SOP_REFERENCE.search(text)) or bool(_EQUIPMENT_NOUNS.search(text)) or any(
        phrase in text.lower() for phrase in _STRONG_INTENT_PHRASES
    )
    signals = []
    if has_tag:
        signals.append("equipment_or_instrument_tag")
    if _SOP_REFERENCE.search(text):
        signals.append("sop_reference")
    if _EQUIPMENT_NOUNS.search(text):
        signals.append("equipment_noun")
    if strong:
        return "IN_SCOPE", signals or ["known_intent_phrase"]
    if _OUT_OF_DOMAIN_MARKER.search(text):
        return "OUT_OF_SCOPE", ["out_of_domain_marker"]
    if _WEAK_INDUSTRIAL_NOUNS.search(text):
        return "UNCERTAIN", ["weak_industrial_noun"]
    return "UNCERTAIN", []


def run_preflight(query: str, access_scope: str) -> PreflightResult:
    """The single deterministic gate. Order: scope -> injection -> unsafe
    action -> domain. The first three are absolute security concerns and
    short-circuit regardless of domain (an in-scope-looking "Start P-204" is
    still refused); domain classification only runs once nothing else has
    already ended the request."""
    scope_reason = _check_scope(access_scope)
    if scope_reason:
        return PreflightResult(
            decision="REFUSE", domain_status="UNCERTAIN", reason_code=scope_reason,
            detected_risks=["unsupported_access_scope"],
            refusal=refuse(
                status="refused",
                reason="The requested access scope is not supported by this workbench.",
                safe_next_step="Retry without an access_scope override, or contact an administrator "
                               "to provision a supported scope.",
            ),
        )

    injection_hits = _detect_injection(query)
    if injection_hits:
        return PreflightResult(
            decision="REFUSE", domain_status="UNCERTAIN", reason_code="prompt_injection_detected",
            detected_risks=["prompt_injection_attempt"],
            refusal=refuse(
                status="refused",
                reason="The request was blocked by a deterministic prompt-injection guardrail.",
                safe_next_step="Rephrase the request as a plain question about company data, equipment, "
                               "or procedures, without instructions directed at this system itself.",
            ),
        )

    if _detect_unsafe_action(query):
        return PreflightResult(
            decision="REFUSE", domain_status="UNCERTAIN", reason_code="unsafe_action_request",
            detected_risks=["unsafe_plant_action_request"],
            refusal=refuse(
                status="refused",
                reason="This workbench has no plant-control capability and cannot perform, authorize, "
                       "isolate, or clear equipment for the requested action.",
                safe_next_step="Ask an informational question instead (e.g. which SOP describes this "
                               "procedure), or contact a supervisor/control-room operator to perform it.",
            ),
        )

    domain_status, signals = classify_domain(query)
    if domain_status == "OUT_OF_SCOPE":
        return PreflightResult(
            decision="REFUSE", domain_status=domain_status, reason_code="out_of_scope",
            detected_risks=signals,
            refusal=refuse(
                status="refused",
                reason="This workbench is restricted to authorized organizational and industrial tasks.",
                safe_next_step="Ask a question about company equipment, procedures, maintenance, safety, "
                               "or approvals.",
            ),
        )
    if domain_status == "UNCERTAIN":
        return PreflightResult(
            decision="CLARIFY", domain_status=domain_status, reason_code="ambiguous_domain",
            detected_risks=signals,
            refusal=refuse(
                status="clarification_required",
                reason="This request needs a specific equipment tag, document/SOP reference, or "
                       "operational context before it can be treated as an organizational task.",
                missing_evidence=["equipment tag, SOP/document reference, or other company context"],
                safe_next_step="Add the missing identifier or context and ask again.",
            ),
        )
    return PreflightResult(decision="ALLOW", domain_status="IN_SCOPE", reason_code="ok", detected_risks=signals)
