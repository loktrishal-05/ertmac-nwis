"""Selective drawing lookup and conservative OCR-only answers shared by existing agents."""
import re
from app.agents.enforcement import refuse
from app.agents.registry import invoke_tool
from app.schemas.agent_outputs import Citation, EquipmentTag, EquipmentTags

DRAWING_QUERY = re.compile(r'\b(?:p\s*&\s*id|pid|drawing|diagram|ocr|visual|line size)\b', re.I)
OCR_LIMITATION = ('OCR labels are uncertain supporting evidence, not a complete valve list, topology, '
                  'connectivity, flow direction, valve state, isolation, permit status, or equipment readiness.')


def is_ocr(ref):
    return ref.kind == 'pid_region' or getattr(ref, 'ocr_derived', False)


def drawing_citations(refs):
    return [Citation(evidence_id=r.evidence_id, locator=r.locator,
                     claim='OCR region available as supporting evidence only.') for r in refs if r.kind == 'pid_region']


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
                                          claim='OCR region available as supporting evidence only.') for r in refs if is_ocr(r)])
    return {'agent_result': {'schema': 'S5', 'output': refusal.model_dump(mode='json')},
            'evidence': refs, 'warnings': [OCR_LIMITATION]}


def drawing_tags(query, refs):
    # This minimum path extracts labels only; it does not interpret diagram geometry.
    if re.search(r'\b(?:line size|diameter|topology|connect|upstream|downstream|flow direction|'
                 r'isolate|isolation|isolated|restart|start|stop|state|open|closed|permit|ready|readiness)\b', query, re.I):
        return drawing_refusal(query, refs)
    tags = [EquipmentTag(raw_text=item.text, normalized_tag=item.normalized_text,
                         equipment_type=None, evidence_id=ref.evidence_id,
                         confidence=item.confidence, status=item.status)
            for ref in refs if ref.kind == 'pid_region' for item in ref.text_items
            if item.category in {'equipment_tag', 'instrument_tag', 'valve_tag'}]
    if not tags:
        return drawing_refusal(query, refs)
    output = EquipmentTags(tags=tags, warnings=[OCR_LIMITATION])
    return {'agent_result': {'schema': 'S3', 'output': output.model_dump(mode='json')},
            'evidence': refs, 'warnings': [OCR_LIMITATION]}
