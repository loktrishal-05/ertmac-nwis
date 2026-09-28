"""Selective drawing lookup and conservative OCR-only answers shared by existing agents."""
import re
from app.agents.enforcement import refuse
from app.agents.registry import invoke_tool
from app.schemas.agent_outputs import Citation, EquipmentTag, EquipmentTags

DRAWING_QUERY = re.compile(r'\b(?:p\s*&\s*id|pid|drawing|diagram|ocr|visual|line size)\b', re.I)
OCR_LIMITATION = ('OCR and visual candidates are uncertain supporting evidence, not a complete valve list, topology, '
                  'connectivity, flow direction, valve state, isolation, LOTO, permit status, startup/shutdown readiness or safe-to-operate state.')


def is_ocr(ref):
    return ref.kind == 'pid_region' or getattr(ref, 'ocr_derived', False)


def drawing_citations(refs):
    return [Citation(evidence_id=r.evidence_id, locator=r.locator,
                     claim=('Drawing region available as supporting evidence only.' if getattr(r, 'visual_candidates', []) and not getattr(r, 'text_items', []) else 'OCR region available as supporting evidence only.')) for r in refs if r.kind == 'pid_region']


def pid_evidence_lookup(query, refs, session):
    """Resolve versions from already-retrieved citations, not a scan of all drawings."""
    if not DRAWING_QUERY.search(query):
        return list(refs), []
    versions = dict.fromkeys(ref.document_version_id for ref in refs if is_ocr(ref))
    drawings, warnings = [], []
    for version in versions:
        payload, found = invoke_tool('get_pid_regions', session, {'document_version_id': version})
        warnings += payload.get('warnings', [])
        drawings += found
    return [ref for ref in refs if not is_ocr(ref)] + drawings, warnings


def drawing_refusal(query, refs):
    refusal = refuse(status='insufficient_evidence', reason=OCR_LIMITATION,
                      missing_evidence=[query],
                      safe_next_step='Obtain a readable drawing and authoritative procedure or verified field record.',
                      citations=[Citation(evidence_id=r.evidence_id, locator=r.locator,
                                          claim=('Drawing region available as supporting evidence only.' if getattr(r, 'visual_candidates', []) and not getattr(r, 'text_items', []) else 'OCR region available as supporting evidence only.')) for r in refs if is_ocr(r)])
    return {'agent_result': {'schema': 'S5', 'output': refusal.model_dump(mode='json')},
            'evidence': refs, 'warnings': [OCR_LIMITATION], 'human_approval_required': True}


def drawing_tags(query, refs):
    # Selection is policy metadata; bounded drawing responses do not call a reasoning model.
    from app.services.model_routing import select_model, RiskSignals
    from app.services.execution_observability import record_routing
    routing = select_model(query, signals=RiskSignals(pid_uncertainty=True), requested_path="EXISTING_AGENTIC_PATH")
    record_routing(routing)
    if re.search(r'\b(?:line size|diameter|topology|connect|upstream|downstream|flow direction|'
                 r'isolate|isolation|isolated|restart|startup|shutdown|loto|safe|operate|operating|start|stop|state|open|closed|permit|ready|readiness)\b', query, re.I):
        return drawing_refusal(query, refs)
    tags = [EquipmentTag(raw_text=item.text, normalized_tag=item.normalized_text,
                         equipment_type=None, evidence_id=ref.evidence_id,
                         confidence=item.confidence, status=item.status)
            for ref in refs if ref.kind == 'pid_region' for item in ref.text_items
            if item.category in {'equipment_tag', 'instrument_tag', 'valve_tag'}]
    if not tags and not any(getattr(r, 'visual_candidates', []) for r in refs):
        return drawing_refusal(query, refs)
    from app.services.visual_intelligence import observations
    visual = observations(refs)
    review = any(f.review_required for r in refs if r.kind == 'pid_region' for f in r.fusion)
    review = review or any(r.ocr_status == 'ambiguous' for r in refs if r.kind == 'pid_region')
    output = EquipmentTags(tags=tags, warnings=[OCR_LIMITATION])
    return {'agent_result': {'schema': 'S3', 'output': output.model_dump(mode='json'), 'visual_evidence': visual, 'model_routing': routing,
                'citations': [c.model_dump(mode='json') for c in drawing_citations(refs)],
                'multimodal_metadata': {
                    'regions_processed': len(visual),
                    'candidate_count': sum(len(r.fusion) for r in refs if r.kind == 'pid_region'),
                    'verified_count': sum(f.registry_status == 'VERIFIED' for r in refs if r.kind == 'pid_region' for f in r.fusion),
                    'conflict_count': sum(f.registry_status == 'CONFLICTING' for r in refs if r.kind == 'pid_region' for f in r.fusion)}},
            'human_approval_required': review,
            'operational_events': ['VISUAL_INTERPRETATION_REQUESTED'],
            'evidence': refs, 'warnings': [OCR_LIMITATION]}
