"""Focused B2 contracts and complete evidence-chain checks."""
import unittest
from datetime import timedelta
from uuid import UUID, uuid4
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import select, update, func
from qdrant_client import QdrantClient
from app.db.models.nwis import FormationInterval, WellTrajectoryPoint, TelemetrySample, RiskAssessment, DrillingAdvisory, DrillingEvent, Well, AlertState
from app.db.models.durable_execution import DurableExecution
from app.schemas.nwis import QueryIn
from app.services import nwis, nwis_knowledge as knowledge
from app.services.audit import verify_chain
from app.agents.nwis import graph
from scripts.seed_nwis import AT
import test_nwis
from test_nwis_retrieval import FakeEmbeddings, FakeReranker

class B2Tests(unittest.TestCase):
    setUp=test_nwis.NWISTests.setUp
    get=test_nwis.NWISTests.get
    request=test_nwis.NWISTests.request

    def test_correlation_tracks_align_tvd_not_md(self):
        active=self.db.get(FormationInterval,'ACTIVE-01-F2')
        offset=self.db.get(FormationInterval,'OFF-02-F2')
        offset.top_tvd=active.top_tvd; offset.bottom_tvd=active.bottom_tvd
        self.active.program=self.active.program | {'casing_points':[{'md':2300,'tvd':2300,'source':'synthetic casing record','confidence':.8}]}
        self.db.commit()
        result=self.get('/api/wells/ACTIVE-01/correlation',lookahead_m=150)
        self.assertEqual(result['alignment_basis'],'tvd')
        a=next(t for t in result['tracks'] if t['well']['id']=='ACTIVE-01')
        b=next(t for t in result['tracks'] if t['well']['id']=='OFF-02')
        af=next(f for f in a['formations'] if f['formation']=='TIPAM_A')
        bf=next(f for f in b['formations'] if f['formation']=='TIPAM_A')
        self.assertEqual((af['top'],af['base']),(bf['top'],bf['base']))
        self.assertNotEqual(active.top_md,offset.top_md)
        self.assertEqual(result['current_bit_depth'],{'md':2450,'tvd':2450,'tvdss':None})
        self.assertEqual(result['lookahead_window']['end']['md'],2600)
        self.assertEqual(a['casing_points'][0]['md'],2300)
        self.assertIsNone(b['casing_points'])
        self.assertIn('do not establish',result['warning'])

    def test_missing_markers_and_tvdss_are_explicit(self):
        self.db.execute(update(FormationInterval).values(top_tvdss=FormationInterval.top_tvd-100,bottom_tvdss=FormationInterval.bottom_tvd-100))
        self.db.execute(update(WellTrajectoryPoint).values(tvdss=WellTrajectoryPoint.tvd-100))
        f=self.db.get(FormationInterval,'OFF-02-F2'); f.top_tvdss=None; f.confidence=.2
        self.db.commit()
        result=self.get('/api/wells/ACTIVE-01/correlation')
        self.assertEqual(result['alignment_basis'],'tvdss')
        marker=next(f for t in result['tracks'] if t['well']['id']=='OFF-02' for f in t['formations'] if f['formation']=='TIPAM_A')
        self.assertIsNone(marker['top']); self.assertFalse(marker['alignment_available'])
        self.assertEqual(marker['confidence'],.2)
        self.assertEqual(result['current_bit_depth']['tvdss'],2350)
        self.assertEqual(self.get('/api/events',depth_basis='tvdss',depth_min=0)['items'],[])

    def test_telemetry_channel_freshness_is_not_page_dependent(self):
        first=self.get('/api/wells/ACTIVE-01/telemetry',channels='torque',limit=1)
        last=self.get('/api/wells/ACTIVE-01/telemetry',channels='torque',limit=1,offset=60)
        self.assertEqual(first['channels'],last['channels'])
        self.assertEqual(first['source_mode'],'replay')
        self.assertEqual(first['channels'][0]['state'],'fresh')
        stale=self.get('/api/wells/ACTIVE-01/telemetry',channels='torque',**{'to':(AT+timedelta(minutes=6)).isoformat()})
        self.assertEqual(stale['channels'][0]['state'],'stale')
        self.db.execute(update(TelemetrySample).where(TelemetrySample.channel=='torque').values(value=None)); self.db.commit()
        empty=self.get('/api/wells/ACTIVE-01/telemetry',channels='torque,absent')
        self.assertEqual([c['state'] for c in empty['channels']],['unavailable','unavailable'])
        self.assertTrue(empty['channels'][0]['known']); self.assertFalse(empty['channels'][1]['known'])
        self.assertEqual(empty['channels'][0]['value_count'],0)
        self.assertTrue(all(s['value'] is None for s in empty['items']))
        self.assertEqual(self.client.get('/api/wells/ACTIVE-01/telemetry?channels=,').status_code,422)

    def test_signed_tvdss_filters_and_extraction(self):
        event=self.db.scalar(select(DrillingEvent).where(DrillingEvent.well_id=='OFF-04'))
        event.tvdss=-20; self.db.commit()
        rows=self.get('/api/events',well_id='OFF-04',depth_basis='tvdss',depth_min=-30,depth_max=-10)
        self.assertEqual([e['id'] for e in rows['items']],[event.id])
        self.assertEqual(self.client.get('/api/events?depth_basis=md&depth_min=-1').status_code,422)
        extracted=knowledge.extract_event('Event: mud_loss; MD: 20 m; TVDSS: -20 m',well_id='OFF-04',report_id='TEST',page=1,origin='synthetic_demo')
        self.assertEqual(extracted.tvdss,-20)
        self.assertEqual(extracted.verification_state,'unverified')

    def test_bad_sample_and_time_gap_break_anomaly_persistence(self):
        rows=[SimpleNamespace(value=v,quality='good',timestamp=AT+timedelta(minutes=i)) for i,v in enumerate([10,11,9,10,11,9,30,30,30])]
        self.assertEqual(nwis.features(rows)['persistence'],3)
        rows[-2].quality='bad'
        self.assertIsNone(nwis.features(rows))
        rows[-2].quality='good'; rows[-1].timestamp+=timedelta(minutes=6)
        self.assertIsNone(nwis.features(rows))

    def test_explicit_query_mode_citations_and_legacy_separation(self):
        body=self.request().model_dump(mode='json')
        result=self.client.post('/api/query',json=body)
        self.assertEqual(result.status_code,200,result.text)
        answer=result.json(); self.assertEqual(answer['mode'],'nwis_evidence')
        for event in answer['evidence']:
            for field in ('well_id','source_report_id','source_page','formation','start_depth_md','raw_phrase'):
                self.assertIsNotNone(event[field])
            self.assertIn(event['id'],answer['answer'])
        # B1 persisted requests did not contain the two new optional keys.
        record=self.db.get(DurableExecution,UUID(body['request_id']))
        record.request={k:v for k,v in record.request.items() if k not in ('mode','offset_limit')}; self.db.commit()
        self.assertEqual(self.client.post('/api/query',json=body).json(),answer)
        self.assertEqual(self.client.post('/api/query',json=body | {'mode':'legacy'}).status_code,422)
        self.assertEqual(self.client.post('/query',json=body).status_code,422)
        nodes=graph(self.db,QueryIn(**body),self.actor).get_graph().nodes
        self.assertTrue({'WellKnowledgeAgent','OffsetWellAgent','DrillingRiskAgent','AdvisoryAgent'}.issubset(nodes))
        refused=self.client.post('/api/query',json=body | {'request_id':str(uuid4()),'query':'Set RPM to 150 and change mud weight'})
        self.assertEqual(refused.status_code,200); self.assertEqual(refused.json()['status'],'refused')

    def test_compare_top_three_and_mud_loss_queries(self):
        body=self.request().model_dump(mode='json')
        result=self.client.post('/api/query',json=body | {'query':'compare events in the three most relevant offsets'}).json()
        expected={m.offset_well_id for m in nwis.offsets(self.db,self.active,self.actor)[:3]}
        self.assertEqual({e['well_id'] for e in result['evidence']},expected)
        result=self.client.post('/api/query',json=body | {'request_id':str(uuid4()),'query':'what mitigations worked for mud losses near this active well?'}).json()
        self.assertTrue(result['evidence'])
        self.assertEqual({e['event_type'] for e in result['evidence']},{'mud_loss'})
        self.assertTrue(all(e['mitigation'] and e['outcome'] for e in result['evidence']))

    def test_explicit_mode_hybrid_uses_qdrant_citations(self):
        client=QdrantClient(':memory:'); self.addCleanup(client.close)
        embeddings=FakeEmbeddings(); reranker=FakeReranker()
        knowledge.index_events(self.db,client,embeddings)
        store=knowledge.vector_store(client)
        with patch.object(knowledge,'vector_store',return_value=store),patch.object(knowledge,'get_embeddings',return_value=embeddings),patch.object(knowledge,'get_reranker',return_value=reranker):
            result=self.client.post('/api/query',json=self.request(retrieval='hybrid').model_dump(mode='json'))
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(result.json()['evidence'])
        self.assertTrue(all(e['source_page']>0 for e in result.json()['evidence']))

    def test_complete_assessment_evidence_advisory_audit_chain(self):
        for minute in (58,59,60):
            stamp=AT-timedelta(minutes=60-minute)
            self.assertEqual(self.client.post('/api/wells/ACTIVE-01/replay',json={'as_of':stamp.isoformat()}).status_code,200)
            result=self.client.post('/api/wells/ACTIVE-01/assess?lookahead_m=100')
            self.assertEqual(result.status_code,200,result.text)
        advisory=next(a for a in self.get('/api/advisories')['items'] if self.db.get(RiskAssessment,a['assessment_id']).hazard_type=='stuck_pipe')
        detail=self.get('/api/assessments/'+advisory['assessment_id'])
        self.assertGreaterEqual(len(detail['evidence']),2)
        self.assertEqual(set(detail['hazard']['evidence_ids']),{e['event']['id'] for e in detail['evidence']})
        for link in detail['evidence']:
            self.assertEqual(link['event'],link['event_at_assessment'])
            self.assertEqual(link['source_sha256'],link['source_sha256_at_assessment'])
            self.assertIn('#page=',link['source_url'])
            self.assertEqual(self.client.get(link['source_url'].split('#')[0]).status_code,200)
        count=self.db.scalar(select(func.count()).select_from(DrillingAdvisory))
        self.assertEqual(self.client.post('/api/wells/ACTIVE-01/assess?lookahead_m=150').status_code,200)
        self.assertEqual(count,self.db.scalar(select(func.count()).select_from(DrillingAdvisory)))
        response=self.client.post('/api/advisories/'+advisory['id']+'/review',json={'status':'acknowledged','reason':'Checked synthetic source evidence'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(verify_chain(self.db)['valid'])
        self.assertTrue(any(e['payload']['action']=='advisory_review' for e in self.get('/api/audit')['items']))
        event=self.db.get(DrillingEvent,detail['evidence'][0]['event']['id']); event.verification_state='rejected'; self.db.commit()
        preserved=self.get('/api/assessments/'+advisory['assessment_id'])
        link=next(e for e in preserved['evidence'] if e['event']['id']==event.id)
        self.assertEqual(link['event_at_assessment']['verification_state'],'unverified')
        self.assertEqual(link['event']['verification_state'],'rejected')
        self.db.get(Well,event.well_id).access_scope='restricted'; self.db.commit()
        self.assertEqual(self.client.get('/api/assessments/'+advisory['assessment_id']).status_code,404)

    def test_low_confidence_event_cannot_be_promoted(self):
        event=self.db.scalar(select(DrillingEvent).where(DrillingEvent.event_type=='stuck_pipe'))
        event.confidence=.35; event.verification_state='review_needed'; event.start_depth_md=None; self.db.commit()
        response=self.client.post('/api/events/'+event.id+'/validate',json={'status':'validated','reason':'Checked OCR value'})
        self.assertEqual(response.status_code,409)
        risk=self.get('/api/wells/ACTIVE-01/risk')
        self.assertFalse(any(event.id in h['evidence_ids'] for h in risk['hazards']))

    def test_offset_explanations_are_deterministic_and_justify_ranking(self):
        first=self.get('/api/wells/ACTIVE-01/nearby',radius_km=10)['items']
        self.assertEqual(first,self.get('/api/wells/ACTIVE-01/nearby',radius_km=10)['items'])
        closest=min(first,key=lambda m:m['distance_m'])
        best=first[0]
        self.assertNotEqual(closest['offset_well_id'],best['offset_well_id'])
        self.assertIn('penetrated the active formation',' '.join(best['explanation']))
        self.assertIn('overlap with the next 100 m',' '.join(best['explanation']))
        # The closer well loses on non-geographic components, visible in its own scores.
        weaker=[k for k in ('formation','depth','trajectory','program') if (closest[k+'_score'] or 0)<(best[k+'_score'] or 0)]
        self.assertTrue(weaker)
        for match in first:
            self.assertEqual(len(match['explanation']),6)
            self.assertTrue(match['explanation'][0].startswith(f"{match['distance_km']:.1f} km"))
            if match['depth_score'] is None: self.assertIn('depth overlap unavailable',match['explanation'])

    def test_equal_scores_break_ties_by_well_id(self):
        weights='{"geographic":0,"formation":0,"depth":0,"trajectory":0,"program":1,"data_quality":0}'
        for well in self.db.scalars(select(Well)).all(): well.program=None
        self.db.commit()
        with patch.dict('os.environ',{'NWIS_OFFSET_WEIGHTS':weights}):
            ranked=nwis.offsets(self.db,self.active,self.actor)
        self.assertTrue(ranked and all(m.total_score==0 for m in ranked))
        ids=[m.offset_well_id for m in ranked]
        self.assertEqual(ids,sorted(ids))

if __name__=='__main__': unittest.main()
