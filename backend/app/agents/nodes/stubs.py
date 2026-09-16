"""Typed not-implemented agent nodes. A stub node never produces prose that
could be mistaken for an answer, never calls the gateway, and never calls a
tool. Its only job is to prove the graph wiring is correct.

sub_phase is reported as "unassigned": no authoritative source in this
repository maps a specific route to a specific one of 4C/4D/4E/4F (the
"MUST NOT IMPLEMENT" list in this phase's own prompt attributes overlapping
concerns — threshold loops, observation/hypothesis validation — to 4E without
tying them to one route), so guessing a mapping here would repeat the exact
mistake the discovery discipline in this phase exists to prevent. This is
flagged explicitly rather than silently invented."""

SUB_PHASE = "unassigned"


def make_stub_node(route: str):
    def _stub(state) -> dict:
        return {"agent_result": {
            "status": "not_implemented", "route": route, "sub_phase": SUB_PHASE,
            "message": f"{route} agent is not implemented in Phase 4B.",
        }}
    _stub.__name__ = f"stub_{route}"
    return _stub
