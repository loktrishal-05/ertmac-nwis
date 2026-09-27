"""Offline Stage-4 checkpoint checks using synthetic data, never BLIND answers."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from benchmark import stage4 as s
from benchmark.harness.test_evaluate import fixture, generated


class Stage4Tests(unittest.TestCase):
    def test_generic_binding_error_never_calls_model(self):
        case = {'evaluation_id': 'SYNTHETIC', 'split': 'blind', 'category': 'fixture', 'category_id': 'A'}
        row = s.initial(case, {'cases': {'SYNTHETIC': {'unresolved': 'No synthetic binding'}}})
        self.assertEqual(row['execution_status'], 'DATA_BINDING_ERROR')
        self.assertEqual(row['deterministic_result'], 'NOT_RUN')
        self.assertFalse(row['model_called'])
        self.assertIn(row['execution_status'], s.TERMINAL)
        with self.assertRaises(ValueError):
            s.initial({**case, 'split': 'development'}, {})

    def test_journal_replays_completed_calls_and_refuses_ambiguous_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'calls.jsonl'
            gateway = Mock()
            gateway.generate_text.return_value = generated({'fixture': True})
            first = s.JournalGateway(gateway, path).generate_text(messages=[], temperature=0)
            second = s.JournalGateway(gateway, path).generate_text(messages=[], temperature=0)
            self.assertEqual(first, second)
            gateway.generate_text.assert_called_once()
            with self.assertRaises(AssertionError):
                s.JournalGateway(gateway, path).generate_text(messages=[], temperature=1)
            events = path.read_text().splitlines()
            path.write_text(events[0] + '\n')
            with self.assertRaises(RuntimeError):
                s.JournalGateway(gateway, path).generate_text(messages=[], temperature=0)
            gateway.generate_text.assert_called_once()

    def test_frozen_evaluator_and_checkpoint_preserve_failed_outcome(self):
        cases, bundle, answer = fixture()
        case = {**cases[0], 'split': 'blind', 'category_id': 'A'}
        gateway = Mock()
        gateway.generate_text.side_effect = [generated({'route': 'knowledge', 'tools': ['qdrant_document_search']}), generated(answer)]
        with tempfile.TemporaryDirectory() as directory:
            row = s.initial(case, bundle)
            row.update(s.s.h.evaluate(case, bundle, s.JournalGateway(gateway, Path(directory) / 'calls.jsonl')))
            self.assertEqual(row['deterministic_result'], 'PASS')
            self.assertEqual(gateway.generate_text.call_count, 2)
            row.update(execution_status='STRUCTURAL_ERROR', deterministic_result='FAIL', model_called=True)
            self.assertIn(row['execution_status'], s.TERMINAL)
            with patch.object(s, 'RESULTS', Path(directory)):
                s.save([row])
                saved = json.loads((Path(directory) / 'qwen3_5_9b_blind.jsonl').read_text())
            self.assertEqual(saved['deterministic_result'], 'FAIL')
            self.assertTrue(saved['model_called'])


if __name__ == '__main__':
    unittest.main()
