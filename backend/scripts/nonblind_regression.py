"""Explicit live local-model regression; immutable inputs, fresh outputs outside benchmark/."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from scripts.frozen_integrity import ROOT, verify


def selected_inputs():
    from benchmark.harness import evaluate as h
    from benchmark.stage2 import select_cases
    source = ROOT / "benchmark/cases/benchmark_cases_final.jsonl"
    cases = h.load_cases(source)
    manifest = json.loads(source.with_name("benchmark_split_manifest.json").read_text(encoding="utf-8"))
    selected = select_cases(cases, manifest)
    if any(c["split"] not in {"development", "validation"} for c in selected):
        raise ValueError("Only non-BLIND cases may execute")
    return selected, h.load_mapping(ROOT / "benchmark/mappings/benchmark_corpus_mapping_final.json", source, cases)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    verify()
    selected, bundle = selected_inputs()
    if not args.execute:
        print(f"NON-BLIND PLAN PASS: {len(selected)} development/validation cases; no model calls")
        return 0
    if os.environ.get("WORKBENCH_LIVE_REGRESSION") != "1":
        parser.error("Explicit WORKBENCH_LIVE_REGRESSION=1 is required")
    from benchmark.harness import evaluate as h
    from benchmark.stage2 import CONFIG, execute_case, metrics
    from app.core.config import settings
    folder = ROOT / "data/regression" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True, exist_ok=False)
    reports = {}
    try:
        for tag in (settings.primary_model, settings.fast_model):
            gateway = h.ModelGateway(settings.model_copy(update={**CONFIG, "model_name": tag}))
            health = gateway.health()
            if not health.reachable or not health.configured_model_present:
                raise RuntimeError("Required local regression model is unavailable")
            rows = []
            with (folder / (tag.replace(":", "-") + ".jsonl")).open("x", encoding="utf-8") as output:
                for case in selected:
                    row = execute_case(case, bundle, tag, gateway)
                    rows.append(row)
                    output.write(json.dumps(row) + "\n")
                    output.flush()
            reports[tag] = metrics(rows)
            reports[tag]["all_pass"] = all(row.get("deterministic_result") == "PASS" for row in rows)
        (folder / "summary.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
        return int(not all(report["all_pass"] for report in reports.values()))
    finally:
        verify()


if __name__ == "__main__":
    raise SystemExit(main())
