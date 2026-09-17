"""The deterministic authorisation-language validator (Phase 4D brief item 1),
reused unchanged by Phase 4F (brief item 2 there: "Reuse 4D's
authorisation-language validator"). A pure function: no database access, no
model call, no state.

Permit, LOTO, isolation, and process-change language may cite what a
procedure or SOP says. It must never read as this system itself granting
clearance, permission, or authorisation to act -- that decision belongs to a
qualified human, every time, with no exception this phase or the next may
create. Phase 5 is where an actual approval workflow gets built; 4D/4F only
record `action_class`/`human_approval_required`, they do not gate on them
(docs/phase4-autonomous-continuation.md section 2's "No approval
enforcement... those are Phase 5" prohibition)."""
import re

_FORBIDDEN_PATTERNS: list[re.Pattern] = [
    re.compile(pattern, re.IGNORECASE) for pattern in (
        r"you(?:'re| are) (?:now |hereby )?cleared (?:to|for)",
        r"permission (?:is |has been )?(?:hereby )?granted",
        r"you may now (?:isolate|proceed|open|close|start|stop|shut ?down|begin|enter)",
        r"authoris(?:ed|ation) to (?!.{0,40}\b(?:request|obtain|seek)\b)",
        r"authoriz(?:ed|ation) to (?!.{0,40}\b(?:request|obtain|seek)\b)",
        r"you(?:'re| are) authoris",
        r"you(?:'re| are) authoriz",
        r"permit (?:is |has been )?(?:issued|approved)",
        r"consider (?:it|this) (?:approved|authorised|authorized|granted)",
        r"go ahead and (?:isolate|proceed|open|close|start|stop|shut ?down)",
        r"cleared for (?:isolation|entry|work|confined space)",
        r"you have (?:clearance|authorisation|authorization)",
    )
]


def find_authorization_language(text: str) -> list[str]:
    """Returns the list of matched pattern sources (empty if clean). Scans
    the literal text only -- callers decide which free-text fields of an
    S7/S6 output to concatenate and pass in (see nodes/safety.py,
    nodes/process_optimization.py)."""
    if not text:
        return []
    return [pattern.pattern for pattern in _FORBIDDEN_PATTERNS if pattern.search(text)]


def contains_authorization_language(text: str) -> bool:
    return bool(find_authorization_language(text))
