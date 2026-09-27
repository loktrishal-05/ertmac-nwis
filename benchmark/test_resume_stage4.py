"""Synthetic recovery check; no benchmark answers or inference."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from benchmark.resume_stage4 import OriginalJournal, RecoveryJournal
from benchmark.harness.test_evaluate import generated


class RecoveryTest(unittest.TestCase):
    def test_one_retry_preserves_history_and_refuses_second_failed_retry(self):
        for failure in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'synthetic.requests.jsonl'
                broken = Mock()
                broken.generate_text.side_effect = RuntimeError('interrupted')
                with self.assertRaises(RuntimeError):
                    OriginalJournal(broken, path).generate_text(messages=[])
                # Synthetic crash after start, before either response or error persistence.
                path.write_text(path.read_text().splitlines()[0] + '\n')
                j = OriginalJournal(None, path)
                j.append({'event': 'reconciliation', 'index': 0, 'retry_authorized': True, 'retry_number': 1})
                original = path.read_bytes()
                gateway = Mock()
                if failure:
                    gateway.generate_text.side_effect = RuntimeError('retry interrupted')
                    for _ in range(2):
                        with self.assertRaises(RuntimeError):
                            RecoveryJournal(gateway, path).generate_text(messages=[])
                else:
                    gateway.generate_text.return_value = generated({'synthetic': True})
                    for _ in range(2):
                        RecoveryJournal(gateway, path).generate_text(messages=[])
                gateway.generate_text.assert_called_once()
                self.assertTrue(path.read_bytes().startswith(original))
                self.assertEqual(sum(json.loads(x)['event'] == 'started' for x in path.with_suffix('.retry1.jsonl').read_text().splitlines()), 1)


if __name__ == '__main__':
    unittest.main()
