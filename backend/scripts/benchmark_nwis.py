"""Run the 40 development cases only. Reserved blind scenarios are never loaded."""
import hashlib
import json
import unittest
from pathlib import Path
from app.services.nwis_knowledge import extract_event

def main():
    root=Path(__file__).resolve().parents[2]/'benchmark'/'nwis'
    path=root/'development.json'
    manifest=json.loads((root/'manifest.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest[path.name]: raise ValueError('Benchmark integrity mismatch')
    cases=json.loads(path.read_text()); suite=unittest.TestSuite()
    for case in cases:
        if case['kind']=='unittest': suite.addTests(unittest.defaultTestLoader.loadTestsFromName(case['test']))
        else:
            def check(case=case):
                e=extract_event(case['source'],well_id='TEST',report_id='REPORT',page=1,origin='synthetic_demo')
                assert e is not None
                if case['expected_md'] is None: assert e.start_depth_md is None
                else: assert abs(e.start_depth_md-case['expected_md'])<1e-6
                assert e.verification_state==case['expected_state']
            suite.addTest(unittest.FunctionTestCase(check,description=case['id']))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    print(json.dumps(dict(cases=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),blind_run=False)))
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__=='__main__': main()
