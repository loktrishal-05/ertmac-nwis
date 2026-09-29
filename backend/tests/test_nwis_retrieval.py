"""NWIS retrieval integrity and extraction checks, plus opt-in real BGE/Qdrant smoke."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import select
from qdrant_client import QdrantClient
from app.services import nwis_knowledge as k, nwis
from app.schemas.nwis import QueryIn
from app.db.models.nwis import DrillingEvent, Well
from app.db.session import SessionLocal
from app.core.config import settings
import test_nwis

class FakeEmbeddings:
    def embed(self,texts,query=False): return [[1.0]+[0.0]*767 for _ in texts]
class FakeReranker:
    def score(self,query,texts): return [float('stuck_pipe' in t) for t in texts]

class RetrievalTests(test_nwis.NWISTests):
    # Reuse fixture only; this class's inherited tests are suppressed below.
    def test_hybrid_metadata_filters_and_stale_rejection(self):
        client=QdrantClient(':memory:'); self.addCleanup(client.close)
        count=k.index_events(self.db,client,FakeEmbeddings()); self.assertEqual(count,66)
        rows=self.db.scalars(select(DrillingEvent).where(DrillingEvent.well_id=='OFF-04',DrillingEvent.event_type=='stuck_pipe')).all()
        output=k.hybrid(rows,'stuck pipe',3,client,FakeEmbeddings(),FakeReranker())
        self.assertTrue(output); self.assertTrue(all(e.well_id=='OFF-04' for e in output))
        for e in rows: e.raw_phrase+=' altered'
        with self.assertRaises(ValueError): k.hybrid(rows,'stuck pipe',3,client,FakeEmbeddings(),FakeReranker())

    def test_contradiction_reduces_confidence(self):
        before=nwis.risk(self.db,self.active,self.actor)[0].hazards[1]
        original=self.db.get(DrillingEvent,before.evidence_ids[0])
        values={c.name:getattr(original,c.name) for c in DrillingEvent.__table__.columns}
        values.update(id='CONTRADICTION',outcome='Reported unresolved in conflicting account')
        self.db.add(DrillingEvent(**values)); self.db.commit()
        after=nwis.risk(self.db,self.active,self.actor)[0].hazards[1]
        self.assertLess(after.confidence,before.confidence)
        self.assertTrue(after.data_quality['contradictory_evidence'])

    def test_native_pdf_ingest_hash_page_date_idempotency(self):
        import pymupdf
        doc=pymupdf.open(); page=doc.new_page()
        text='Well: ACTIVE-01; Date: 2026-09-29; Event: stuck_pipe; MD: 2450 m; Formation: TIPAM_A; Observation: Synthetic incident'
        page.insert_textbox((40,40,550,400),text,fontsize=10)
        source=doc.tobytes(); doc.close()
        with tempfile.TemporaryDirectory() as folder,patch.object(settings,'data_root',Path(folder)):
            first=k.ingest_pdf(self.db,self.active,source,'DDR',self.actor,dataset_origin='synthetic_demo'); self.db.commit()
            second=k.ingest_pdf(self.db,self.active,source,'DDR',self.actor,dataset_origin='synthetic_demo')
            self.assertEqual(first['report_id'],second['report_id']); self.assertEqual(len(first['events']),1)
            self.assertEqual(first['events'][0].source_page,1)
            self.assertEqual(first['events'][0].start_depth_md,2450)
            self.assertTrue(list(Path(folder).rglob('*.pdf')))

    def test_ocr_number_review_gate(self):
        from app.services.extraction import Extraction
        block=SimpleNamespace(text='Event: stuck_pipe; MD: 2450 m',page=1,bbox=(0,0,100,100),confidence=.99)
        extraction=Extraction('ocr_required',[],'',{}, {'warnings':[]})
        with tempfile.TemporaryDirectory() as folder,patch.object(settings,'data_root',Path(folder)),\
             patch.object(k,'extract_pdf',return_value=extraction),\
             patch('app.services.pid_images.render_pages',return_value=[]),\
             patch('app.services.paddle_ocr.get_paddle_ocr',return_value=SimpleNamespace(recognize_pages=lambda p:[[block]])):
            result=k.ingest_pdf(self.db,self.active,b'%PDF-fake-test-source','DDR',self.actor,dataset_origin='synthetic_demo')
            self.assertEqual(result['status'],'review_needed')
            self.assertLess(result['events'][0].confidence,.5)

    def test_validation_role_and_audit(self):
        e=self.db.scalar(select(DrillingEvent).limit(1))
        response=self.client.post('/api/events/'+e.id+'/validate',json={'status':'validated','reason':'Checked synthetic source page'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['verification_state'],'validated')

# Only the five additional tests run here; the base suite runs separately.
for name in vars(test_nwis.NWISTests):
    if name.startswith('test_'): setattr(RetrievalTests,name,None)

@unittest.skipUnless(os.getenv('NWIS_TEST_RETRIEVAL')=='1','requires local model artifacts and NWIS Qdrant')
class RealRetrievalTests(unittest.TestCase):
    def test_bge_hybrid_rrf_reranker_citations(self):
        with SessionLocal() as session:
            k.index_events(session)
            rows=session.scalars(select(DrillingEvent).where(DrillingEvent.event_type=='stuck_pipe')).all()
            result=k.hybrid(rows,'stuck pipe in Tipam at 2470 m',6)
            self.assertTrue(result)
            self.assertTrue(all(e.event_type=='stuck_pipe' and e.source_page>0 for e in result))

if __name__=='__main__': unittest.main()
