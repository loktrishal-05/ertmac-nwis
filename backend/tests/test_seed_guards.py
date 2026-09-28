"""Known-password seeds must fail before any side effects outside development."""
import unittest
from unittest.mock import patch

from scripts import seed_dev_users, seed_phase9


class SeedGuardTests(unittest.TestCase):
    def test_non_development_refuses_before_side_effects(self):
        for module in (seed_dev_users, seed_phase9):
            for mode in ("confidential", "public", "production"):
                with self.subTest(script=module.__name__, mode=mode), \
                        patch.object(module.settings, "deployment_mode", mode), \
                        patch.object(module, "SessionLocal") as database, \
                        patch.object(seed_phase9, "prepare_sources") as files:
                    with self.assertRaisesRegex(RuntimeError, "development"):
                        module.main()
                    database.assert_not_called()
                    files.assert_not_called()

    def test_development_reaches_seed_operations(self):
        for module, operation in ((seed_dev_users, "SessionLocal"), (seed_phase9, "prepare_sources")):
            with self.subTest(script=module.__name__), \
                    patch.object(module.settings, "deployment_mode", "development"), \
                    patch.object(module, operation, side_effect=LookupError("seed reached")):
                with self.assertRaisesRegex(LookupError, "seed reached"):
                    module.main()
