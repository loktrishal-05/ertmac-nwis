"""One-time functional held-out evaluation. Never changes application code or case oracles."""
import argparse
from contextlib import closing
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
from qdrant_client import QdrantClient
from sqlalchemy import select, update
from app.db.models.nwis import AlertState, DrillingEvent, Well
from app.db.session import SessionLocal
from app.services import nwis, nwis_knowledge as knowledge
from scripts.seed_nwis import AT
from test_nwis import NWISTests
from test_nwis_retrieval import FakeEmbeddings, FakeReranker

ROOT = Path(__file__).resolve().parents[2]


def evaluate(case, fixture):
    data, oracle = case['input'], case['oracle']
    category = case['category']
    if category == 'extraction':
        event = knowledge.extract_event(data['source'], well_id='BLIND-WELL', report_id='BLIND-REPORT',
                                       page=data['page'], origin=case['dataset_origin'])
        return {key: getattr(event, key) for key in oracle}
    if category == 'radius':
        # Transaction rolls back: exercise real PostGIS without changing the demo universe.
        with SessionLocal() as db:
            active, offset = db.get(Well, 'ACTIVE-01'), db.get(Well, 'OFF-01')
            assert active.id != offset.id and data['different_well_ids']
            active.latitude, active.longitude = data['active']
            offset.latitude, offset.longitude = data['offset']
            db.flush()
            found = {well.id: distance for well, distance in nwis.nearby(db, active, data['radius_km'], fixture.actor)}
            return dict(included=offset.id in found, distance_m=found.get(offset.id))
    if category == 'risk':
        assert data['remove_all_coordinates']
        fixture.db.execute(update(Well).values(latitude=None, longitude=None))
        fixture.db.expire_all()
        result = nwis.risk(fixture.db, fixture.db.get(Well, data['well_id']), fixture.actor, lookahead=data['lookahead_m'])[0]
        assert all(h.probability is None for h in result.hazards)
        assert all(h.confidence == oracle['confidence'] for h in result.hazards)
        return dict(all_hazard_probabilities=None, confidence=0)
    if category == 'alert':
        hazard = nwis.risk(fixture.db, fixture.active, fixture.actor)[0].hazards[1]
        state = AlertState(consecutive=0, active=False)
        count = 0
        for index, probability in enumerate(data['probabilities']):
            sample = hazard.model_copy(update=dict(probability=probability, confidence=data['confidence'],
                supporting_offset_wells=['BLIND-OFF-'+str(i) for i in range(data['supporting_wells'])]))
            count += nwis.alert_transition(state, sample, AT+timedelta(seconds=index*data['sample_spacing_seconds']))
        return dict(alerts=count)
    if category == 'authorization':
        assert data['terms_accepted']
        fixture.actor.role = data['role']
        fixture.db.commit()
        response = fixture.client.request(data['method'], data['path'], json=data['body'])
        return dict(http_status=response.status_code)
    if category == 'safety':
        from uuid import uuid4
        response = fixture.client.post('/api/query', json={**data, 'mode': 'nwis_evidence', 'request_id': str(uuid4())})
        assert response.status_code == 200
        return {key: response.json()[key] for key in oracle}
    if category == 'evidence':
        assert data['retrieval'] == 'hybrid'
        event = fixture.db.scalar(select(DrillingEvent).where(DrillingEvent.well_id == data['well_id']).order_by(DrillingEvent.id).limit(1))
        event.source_page = data['indexed_event_page']
        fixture.db.commit()
        with closing(QdrantClient(':memory:')) as client:
            knowledge.index_events(fixture.db, client, FakeEmbeddings())
            event.source_page = data['stored_event_page']
            fixture.db.flush()
            try:
                knowledge.hybrid([event], event.raw_phrase, 1, client, FakeEmbeddings(), FakeReranker())
            except ValueError as error:
                return dict(stale_evidence_rejected='stale or inconsistent' in str(error))
            return dict(stale_evidence_rejected=False)
    raise ValueError('Unsupported held-out category')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-sha', required=True)
    args = parser.parse_args()
    target = ROOT/'data/final_held_out.json'
    # Exclusive durable marker prevents an accidental second invocation, including after interruption.
    with target.open('x', encoding='utf-8') as output:
        json.dump(dict(status='started', backend_sha=args.backend_sha), output)
    path = ROOT/'benchmark/nwis/blind.json'
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == json.loads((path.parent/'manifest.json').read_text())[path.name]
    cases = json.loads(path.read_text())
    assert len(cases) == 8 and len({c['id'] for c in cases}) == 8
    result = dict(backend_sha=args.backend_sha, blind_sha256=digest, attempts=1, cases=[], passed=0, total=8)
    for case in cases:
        fixture = NWISTests()
        try:
            fixture.setUp()
            actual = evaluate(case, fixture)
            for key, expected in case['oracle'].items():
                assert math.isclose(actual[key], expected, abs_tol=1e-9) if isinstance(expected, float) else actual[key] == expected, key
            result['passed'] += 1
            result['cases'].append(dict(id=case['id'], passed=True, actual=actual))
        except Exception as error:
            result['cases'].append(dict(id=case['id'], passed=False, error_type=type(error).__name__, detail=str(error)[:300]))
        finally:
            fixture.doCleanups()
        target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    result['status'] = 'completed'
    target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(result['passed'] != result['total'])


if __name__ == '__main__':
    main()
