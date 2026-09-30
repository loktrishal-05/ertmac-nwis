"""Real migrations, geography and HTTP lifecycle in an isolated PostgreSQL schema.

Run only with NWIS_TEST_POSTGRES=1 against the dedicated NWIS Docker database.
"""
import os
import subprocess
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import User
from app.db.models.nwis import Well, DrillingEvent, DrillingAdvisory, RiskEvidence, RiskAssessment
from app.db.session import get_db
from app.main import app
from app.services import nwis
from app.services.audit import verify_chain
from scripts.seed_nwis import seed, AT, generate

@unittest.skipUnless(os.getenv('NWIS_TEST_POSTGRES')=='1','requires isolated PostGIS target')
class PostGISTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin_engine=create_engine(settings.database_url,isolation_level='AUTOCOMMIT')
        if cls.admin_engine.url.database!='nwis': raise RuntimeError('Dedicated nwis database required')
        cls.database='nwis_validation_'+uuid4().hex
        with cls.admin_engine.connect() as c: c.execute(text('CREATE DATABASE '+cls.database))
        cls.engine=create_engine(cls.admin_engine.url.set(database=cls.database))
        cls.migrate('upgrade','head')

    @classmethod
    def migrate(cls,operation,target):
        env=dict(os.environ,DATABASE_URL=cls.engine.url.render_as_string(hide_password=False))
        subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini',operation,target],env=env,check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin_engine.connect() as c: c.execute(text('DROP DATABASE '+cls.database+' WITH (FORCE)'))
        cls.admin_engine.dispose()

    def setUp(self):
        self.db=Session(self.engine,expire_on_commit=False)
        self.addCleanup(self.db.close)
        seed(self.db); self.db.commit()
        self.user=SimpleNamespace(role='reviewer')
        self.active=self.db.get(Well,'ACTIVE-01')

    def test_migration_head_and_geography(self):
        self.assertEqual(self.db.scalar(text('SELECT version_num FROM alembic_version')),'0018_nwis')
        self.assertIn('3.',self.db.scalar(text('SELECT postgis_lib_version()')))
        self.assertEqual(self.db.scalar(text("SELECT ST_SRID(location::geometry) FROM nwis_wells WHERE id='ACTIVE-01'")),4326)
        index=self.db.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_nwis_wells_location'"))
        self.assertIn('USING gist',index)
        self.assertEqual(self.db.scalar(text("SELECT to_regclass('users') IS NOT NULL")),True)

    def test_00_migration_roundtrip(self):
        self.db.close()
        self.migrate('downgrade','0017_accounts_recovery')
        with self.engine.connect() as c:
            self.assertIsNone(c.scalar(text("SELECT to_regclass('nwis_wells')")))
            self.assertIsNotNone(c.scalar(text("SELECT to_regclass('users')")))
        self.migrate('upgrade','head')

    def test_real_radius_boundary_and_index(self):
        rows=nwis.nearby(self.db,self.active,1,self.user)
        self.assertEqual([w.id for w,d in rows],['OFF-01','OFF-02'])
        exact=self.db.scalar(text("SELECT ST_Distance(a.location,b.location) FROM nwis_wells a,nwis_wells b WHERE a.id='ACTIVE-01' AND b.id='OFF-04'"))
        self.assertIn('OFF-04',[w.id for w,d in nwis.nearby(self.db,self.active,(exact+.01)/1000,self.user)])
        self.assertNotIn('OFF-04',[w.id for w,d in nwis.nearby(self.db,self.active,(exact-.01)/1000,self.user)])
        self.db.execute(text('SET LOCAL enable_seqscan=off'))
        plan=' '.join(self.db.scalars(text('EXPLAIN '+nwis.NEARBY_SQL),dict(active='ACTIVE-01',radius=1000,limit=100,offset=0)))
        self.assertIn('ix_nwis_wells_location',plan)

    def test_coordinate_trigger(self):
        self.db.execute(text("UPDATE nwis_wells SET latitude=27.9 WHERE id='OFF-11'"))
        self.assertAlmostEqual(self.db.scalar(text("SELECT ST_Y(location::geometry) FROM nwis_wells WHERE id='OFF-11'")),27.9)
        self.db.rollback()

    def test_http_login_replay_alert_review_and_audit(self):
        actor=User(username='nwis-'+uuid4().hex[:12],role='reviewer',password_hash=hash_password('Synthetic-NWIS-test-password!'),is_active=True,signup_pending=False)
        self.db.add(actor); self.db.commit()
        app.dependency_overrides[get_db]=lambda:self.db
        self.addCleanup(app.dependency_overrides.clear)
        with TestClient(app,base_url='https://testserver') as client:
            login=client.post('/auth/login',json={'username':actor.username,'password':'Synthetic-NWIS-test-password!'})
            self.assertEqual(login.status_code,200,login.text)
            self.assertEqual(client.get('/api/wells').status_code,403)
            self.assertEqual(client.post('/api/terms/accept',json={'version':'nwis-advisory-v1','accepted':True}).status_code,200)
            for minute in (58,59,60):
                stamp=AT-timedelta(minutes=60-minute)
                response=client.post('/api/wells/ACTIVE-01/replay',json={'as_of':stamp.isoformat()})
                self.assertEqual(response.status_code,200,response.text)
                response=client.post('/api/wells/ACTIVE-01/assess')
                self.assertEqual(response.status_code,200,response.text)
            rows=client.get('/api/advisories').json()['items']
            self.assertTrue(rows,'three sustained replay assessments should produce an advisory')
            selected=next(a for a in rows if a['status']=='pending_review')
            evidence=self.db.scalars(select(RiskEvidence).where(RiskEvidence.assessment_id==selected['assessment_id'])).all()
            self.assertGreaterEqual(len(evidence),2)
            review=client.post('/api/advisories/'+selected['id']+'/review',json={'status':'acknowledged','reason':'Reviewed synthetic source evidence with engineer'})
            self.assertEqual(review.status_code,200,review.text)
            self.assertEqual(client.post('/api/advisories/'+selected['id']+'/review',json={'status':'reviewed','reason':'Repeated review'}).status_code,409)
            self.assertEqual(str(actor.id),review.json()['reviewer'])
            request={'query':'show stuck-pipe incidents in Tipam between 2400-2700 m TVD','request_id':str(uuid4())}
            query=client.post('/api/query',json=request)
            self.assertEqual(query.status_code,200,query.text)
            self.assertTrue(query.json()['evidence'])
            self.assertTrue(client.get('/api/audit').json()['items'])
        self.assertTrue(verify_chain(self.db)['valid'])

    def test_seed_repeat_counts(self):
        before=self.db.scalar(select(func.count()).select_from(DrillingEvent))
        seed(self.db); self.db.commit()
        self.assertEqual(before,self.db.scalar(select(func.count()).select_from(DrillingEvent)))

if __name__=='__main__': unittest.main()
