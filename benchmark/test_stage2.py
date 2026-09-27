"""Deterministic orchestration checks; no live model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from benchmark import stage2 as s
from benchmark.harness.test_evaluate import fixture, generated


class Stage2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selected, cls.bundle, cls.hashes = s.prepare()

    def test_real_coverage_is_identical_and_ref005_never_calls_or_scores(self):
        gateway = Mock()
        runnable = []
        for model in s.MODELS:
            rows = [s.initial_row(c, self.bundle, model) for c in self.selected]
            runnable.append([r['evaluation_id'] for r in rows if r['execution_status'] != 'DATA_BINDING_ERROR'])
            case = next(c for c in self.selected if c['evaluation_id'] == 'REF-005')
            with patch.object(s.h, 'evaluate', side_effect=AssertionError('must not evaluate')):
                row = s.execute_case(case, self.bundle, model, gateway)
            self.assertEqual(row['execution_status'], 'DATA_BINDING_ERROR')
            self.assertEqual(row['deterministic_result'], 'NOT_RUN')
            self.assertFalse(row['model_called'])
            self.assertNotIn('checks', row)
            self.assertNotIn('expected_route', row)
            self.assertEqual((s.metrics(rows)['selected'], s.metrics(rows)['runnable'], s.metrics(rows)['data_binding_errors']), (30, 29, 1))
        self.assertEqual(runnable[0], runnable[1])
        self.assertEqual(len(runnable[0]), 29)
        gateway.generate_text.assert_not_called()

    def test_binding_error_is_generic_and_unexpected_bug_is_not_hidden(self):
        case = {'evaluation_id': 'SYNTHETIC-UNRESOLVED', 'split': 'validation', 'category': 'fixture'}
        bundle = {'cases': {case['evaluation_id']: {'unresolved': 'Synthetic missing binding'}}}
        with patch.object(s.h, 'evaluate', side_effect=AssertionError('must not evaluate')):
            row = s.execute_case(case, bundle, 'fixture-model', Mock())
        self.assertEqual(row['binding_error'], 'Synthetic missing binding')
        self.assertEqual(row['model'], 'fixture-model')
        self.assertFalse(row['model_called'])
        with self.assertRaises(KeyError):
            s.initial_row(case, {'cases': {}}, 'fixture-model')

    def test_blind_cannot_reach_evaluation(self):
        manifest = json.loads((s.ROOT / 'benchmark/cases/benchmark_split_manifest.json').read_text())
        self.assertFalse({c['evaluation_id'] for c in self.selected} & set(manifest['splits']['blind']))
        case = {**self.selected[0], 'split': 'blind'}
        with patch.object(s.h, 'evaluate') as evaluate:
            with self.assertRaises(ValueError):
                s.execute_case(case, self.bundle, s.MODELS[0], Mock())
            evaluate.assert_not_called()
        altered = copy.deepcopy(manifest)
        altered['splits']['development'][0] = manifest['splits']['blind'][0]
        with self.assertRaises(ValueError):
            s.select_cases(self.selected, altered)

    def test_frozen_fixture_uses_same_prompts_and_counts_two_requests_per_case(self):
        cases, bundle, answer = fixture()
        case = {**cases[0], 'split': 'development'}
        calls = []
        for model in s.MODELS:
            gateway = Mock()
            gateway.generate_text.side_effect = [generated({'route': 'knowledge', 'tools': ['qdrant_document_search']}), generated(answer)]
            row = s.execute_case(case, bundle, model, gateway)
            self.assertEqual(row['model'], model)
            self.assertEqual(row['deterministic_result'], 'PASS')
            self.assertEqual(row['pass_fail'], 'REVIEW_REQUIRED')
            self.assertTrue(row['model_called'])
            summary = s.metrics([row])
            self.assertEqual(summary['model_requests'], 2)
            self.assertEqual(summary['review_required_count'], 1)
            calls.append(gateway.generate_text.call_args_list)
        self.assertEqual(calls[0], calls[1])

    def test_metrics_exclude_data_errors_and_keep_failures_and_unknowns_visible(self):
        rows = [s.initial_row(c, self.bundle, s.MODELS[0]) for c in self.selected]
        rows[0].update(model_called=True, execution_status='STRUCTURAL_ERROR', deterministic_result='FAIL',
                       schema_valid=False, error='ModelTimeoutError: fixture', requests=[{}],
                       critical_failures=['invented_evidence_reference'], review_required=['claim_entailment'],
                       latency_seconds=2, input_tokens=None, output_tokens=None)
        m = s.metrics(rows)
        self.assertEqual((m['runnable'], m['executed'], m['data_binding_errors']), (29, 1, 1))
        self.assertEqual(m['deterministic_failures'], 1)
        self.assertEqual(m['deterministic_passes'], 0)
        self.assertEqual(m['fabricated_reference_cases'], 1)
        self.assertEqual(m['runtime_failure_cases'], [rows[0]['evaluation_id']])
        self.assertEqual(m['dimensions']['schema']['confirmed_failures'], 1)
        self.assertEqual(m['input_tokens']['unknown_cases'], 1)
        self.assertTrue(all(d['denominator'] == 29 for d in m['dimensions'].values()))

    def test_missing_or_unhealthy_4b_blocks_all_inference_even_with_execute(self):
        model = s.MODELS[0]
        runtime = {'version': {'version': 'fixture'}, 'tags': {'models': [{'name': model, 'digest': 'nine'}]}}
        readiness = {'runtime': {'version': runtime['version'], 'models': [
            {'inventory': {'name': model, 'digest': 'nine'}, 'health': {'passed': True}}]}}
        gate = s.candidate_gate(runtime, readiness)
        self.assertTrue(gate[0]['health_passed'])
        self.assertFalse(gate[1]['health_passed'])
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(s, 'RESULTS', Path(folder) / 'must-not-exist'), \
                 patch.object(s, 'prepare', return_value=(self.selected, self.bundle, self.hashes)), \
                 patch.object(s, 'snapshot', return_value=runtime), \
                 patch.object(s, 'candidate_gate', return_value=gate), \
                 patch.object(s, 'report') as report, patch.object(s.h, 'ModelGateway') as gateway, \
                 patch('sys.argv', ['stage2', '--execute']):
                s.main()
                gateway.assert_not_called()
                self.assertFalse(s.RESULTS.exists())
                self.assertIn('WAITING FOR 4B', report.call_args.args[0])
        runtime['tags']['models'].append({'name': s.MODELS[1], 'digest': 'four'})
        self.assertEqual(s.candidate_gate(runtime, readiness)[1]['reason'], 'HEALTH_CHECK_REQUIRED')


if __name__ == '__main__':
    unittest.main()
