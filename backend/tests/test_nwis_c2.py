"""C2 checks use the existing isolated fixture; frozen B2 semantics stay unchanged."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import unittest
from app.db.models.nwis import DrillingEvent, AlertState
from app.services import nwis
from scripts.seed_nwis import AT
from scripts.provision_nwis_demo import provision
import test_nwis


class C2Tests(unittest.TestCase):
    setUp = test_nwis.NWISTests.setUp
    get = test_nwis.NWISTests.get

    def test_eligibility_snapshot_and_review_are_distinct(self):
        result = self.client.post('/api/wells/ACTIVE-01/assess').json()
        hazard = next(h for h in result['risk']['hazards'] if h['type'] == 'stuck_pipe')
        event = self.db.get(DrillingEvent, hazard['evidence_ids'][0])
        self.assertEqual(event.verification_state, 'unverified')
        self.assertGreaterEqual(event.confidence, .5)
        for state, confidence, eligible in (
            ('rejected', .9, False), ('review_needed', .9, False),
            ('unverified', .499, False), ('unverified', .5, True),
            ('validated', .499, False), ('validated', .9, True)):
            with self.subTest(state=state, confidence=confidence):
                event.verification_state, event.confidence = state, confidence
                self.db.commit()
                current = self.get('/api/wells/ACTIVE-01/risk')
                used = {eid for h in current['hazards'] for eid in h['evidence_ids']}
                self.assertEqual(event.id in used, eligible)
                detail = self.get('/api/assessments/'+hazard['assessment_id'])
                link = next(e for e in detail['evidence'] if e['event']['id'] == event.id)
                self.assertEqual(link['event']['verification_state'], state)
                self.assertEqual(link['event_at_assessment']['verification_state'], 'unverified')
                self.assertEqual(link['event_at_assessment']['confidence'], .9)
                self.assertEqual(link['source_sha256'], link['source_sha256_at_assessment'])
                self.assertIn('#page=', link['source_url'])
        event.verification_state, event.confidence = 'unverified', .9
        self.db.commit()
        response = self.client.post('/api/events/'+event.id+'/validate', json={'status': 'validated', 'reason': 'Human checked the synthetic source page'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['verification_state'], 'validated')
        audit = self.get('/api/audit')['items']
        entry = next(e for e in audit if e['payload']['action'] == 'drilling_lesson_validation')
        self.assertEqual(entry['actor_id'], str(self.actor.id))
        self.assertTrue(entry['occurred_at'])

    def test_requester_cannot_review_real_advisory(self):
        for minute in (58, 59, 60):
            self.client.post('/api/wells/ACTIVE-01/replay', json={'as_of': (AT-timedelta(minutes=60-minute)).isoformat()})
            self.client.post('/api/wells/ACTIVE-01/assess')
        advisory = self.get('/api/advisories')['items'][0]
        self.actor.role = 'requester'
        self.db.commit()
        response = self.client.post('/api/advisories/'+advisory['id']+'/review', json={'status': 'acknowledged', 'reason': 'Attempt by unauthorized requester'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.get('/api/advisories')['items'][0]['status'], 'pending_review')

    def test_missing_current_depth_is_explicit(self):
        self.active.current_md = None
        self.db.commit()
        risk = self.get('/api/wells/ACTIVE-01/risk')
        self.assertIsNone(risk['current_md_m'])
        self.assertIsNone(risk['current_tvd_m'])
        self.assertIsNone(risk['formation'])
        self.assertTrue(all(h['probability'] is None and not h['evidence_ids'] for h in risk['hazards']))
        correlation = self.get('/api/wells/ACTIVE-01/correlation')
        self.assertTrue(all(v is None for v in correlation['current_bit_depth'].values()))

    def test_transient_alert_resets_persistence(self):
        hazard = nwis.risk(self.db, self.active, self.actor)[0].hazards[1].model_copy(
            update={'probability': .8, 'confidence': .8, 'supporting_offset_wells': ['OFF-04', 'OFF-09']})
        state = AlertState(consecutive=0, active=False)
        self.assertFalse(nwis.alert_transition(state, hazard, AT))
        self.assertFalse(nwis.alert_transition(state, hazard.model_copy(update={'probability': .3}), AT+timedelta(minutes=1)))
        for minute in (2, 3):
            self.assertFalse(nwis.alert_transition(state, hazard, AT+timedelta(minutes=minute)))
        self.assertTrue(nwis.alert_transition(state, hazard, AT+timedelta(minutes=4)))
        self.assertFalse(nwis.alert_transition(state, hazard, AT+timedelta(minutes=4)))

    def test_provisioning_guards_and_idempotency(self):
        # Existing SQLite fixture is rejected unless the isolated-target guard is explicitly mocked.
        with self.assertRaises(ValueError):
            provision(self.db, 'demo', 'a-unique-test-password')
        with patch.object(self.engine, 'url', SimpleNamespace(database='nwis')):
            username = 'demo-'+uuid4().hex[:8]
            user = provision(self.db, username, 'a-unique-test-password')
            self.assertEqual(user.role, 'reviewer')
            self.assertEqual(provision(self.db, username, 'a-unique-test-password').id, user.id)
            with self.assertRaises(ValueError):
                provision(self.db, username, 'different-test-password')
            user.role = 'admin'
            self.db.commit()
            with self.assertRaises(ValueError):
                provision(self.db, username, 'a-unique-test-password')
            self.assertEqual(user.role, 'admin')
            with self.assertRaises(ValueError):
                provision(self.db, 'new', 'short')


if __name__ == '__main__':
    unittest.main()
