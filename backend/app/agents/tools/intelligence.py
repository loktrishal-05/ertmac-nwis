"""analyze_sensor_maintenance -- B2 read-only deterministic intelligence tool.

Wraps app.services.maintenance_sensor_intelligence.analyze, which reuses
Phase 3C's own bounded reads and caller-supplied thresholds. The tool adds no
inference of its own: every observation, hypothesis, and recommendation in the
payload is deterministic Python output, and no threshold is ever invented."""
from app.agents.registry import register
from app.schemas.maintenance_sensor_intelligence import (
    SensorMaintenanceIntelligenceRequest,
)
from app.services.maintenance_sensor_intelligence import analyze
from app.services.model_gateway.types import ToolSpec


AnalyzeSensorMaintenanceArguments = SensorMaintenanceIntelligenceRequest


def analyze_sensor_maintenance(session, arguments: AnalyzeSensorMaintenanceArguments):
    response, refs = analyze(session, arguments)
    return response.model_dump(mode="json"), refs


register(
    ToolSpec(
        name="analyze_sensor_maintenance",
        description="Read-only deterministic maintenance & sensor intelligence over a bounded time window: "
                     "per-channel window features and rate of change, threshold crossings (caller-supplied "
                     "thresholds only), anomaly persistence, multivariate trend correlation, and "
                     "maintenance-history temporal correlation. Observations are measured facts; hypotheses "
                     "are tentative and clearly separated; correlation never establishes causation.",
        parameters=AnalyzeSensorMaintenanceArguments.model_json_schema(),
    ),
    AnalyzeSensorMaintenanceArguments, analyze_sensor_maintenance,
)
