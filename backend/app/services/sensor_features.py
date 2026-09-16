"""Deterministic sensor-window features and factual anomaly observations.

These functions never diagnose equipment condition (no "bearing failure", no
"cavitation"). They report measured facts: thresholds, relative changes, gaps,
and quality flags. Interpretation belongs to a later reasoning layer."""
from statistics import mean, median, pstdev

from app.schemas.structured import AnomalyObservation, SensorFeatureSummary


def compute_features(values: list[float], rolling_window: int | None = None) -> SensorFeatureSummary:
    if not values:
        return SensorFeatureSummary(count=0)
    first, last = values[0], values[-1]
    absolute_change = last - first
    percentage_change = (absolute_change / first * 100) if first != 0 else None
    rolling = None
    if rolling_window and len(values) >= rolling_window:
        rolling = [mean(values[i:i + rolling_window]) for i in range(len(values) - rolling_window + 1)]
    slope = None
    if len(values) >= 2:
        xs = list(range(len(values)))
        x_mean = mean(xs)
        y_mean = mean(values)
        denominator = sum((x - x_mean) ** 2 for x in xs)
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values)) / denominator if denominator else 0.0
    return SensorFeatureSummary(
        count=len(values), minimum=min(values), maximum=max(values), mean=mean(values),
        median=median(values), stdev=pstdev(values) if len(values) >= 2 else 0.0,
        first_value=first, last_value=last, absolute_change=absolute_change,
        percentage_change=percentage_change, rolling_mean=rolling, slope=slope,
    )


def _label(value, unit):
    return f"{value}{' ' + unit if unit else ''}"


def detect_anomalies(readings: list[dict], thresholds, measurement: str, unit: str | None, as_of=None) -> list[AnomalyObservation]:
    """readings: chronologically ordered dicts with value/timestamp/quality keys.
    Every threshold-based check is skipped unless that threshold was explicitly supplied."""
    observations: list[AnomalyObservation] = []
    if not readings:
        return observations

    if thresholds.maximum is not None:
        for reading in readings:
            if reading["value"] > thresholds.maximum:
                observations.append(AnomalyObservation(
                    kind="threshold_exceeded",
                    observation=(f"{measurement} value {_label(reading['value'], unit)} exceeded configured "
                                 f"maximum {thresholds.maximum} at {reading['timestamp'].isoformat()}"),
                    evidence={"value": reading["value"], "threshold": thresholds.maximum,
                              "timestamp": reading["timestamp"].isoformat()},
                ))

    if thresholds.minimum is not None:
        for reading in readings:
            if reading["value"] < thresholds.minimum:
                observations.append(AnomalyObservation(
                    kind="threshold_below",
                    observation=(f"{measurement} value {_label(reading['value'], unit)} fell below configured "
                                 f"minimum {thresholds.minimum} at {reading['timestamp'].isoformat()}"),
                    evidence={"value": reading["value"], "threshold": thresholds.minimum,
                              "timestamp": reading["timestamp"].isoformat()},
                ))

    if thresholds.max_absolute_change is not None:
        for previous, current in zip(readings, readings[1:]):
            delta = current["value"] - previous["value"]
            if abs(delta) > thresholds.max_absolute_change:
                observations.append(AnomalyObservation(
                    kind="sudden_change",
                    observation=(f"{measurement} changed by {delta:+.4g} between {previous['timestamp'].isoformat()} "
                                 f"and {current['timestamp'].isoformat()}, exceeding the configured maximum change "
                                 f"of {thresholds.max_absolute_change}"),
                    evidence={"previous_value": previous["value"], "current_value": current["value"],
                              "delta": delta, "threshold": thresholds.max_absolute_change,
                              "timestamp": current["timestamp"].isoformat()},
                ))

    if thresholds.expected_interval_minutes is not None:
        for previous, current in zip(readings, readings[1:]):
            gap_minutes = (current["timestamp"] - previous["timestamp"]).total_seconds() / 60
            if gap_minutes > thresholds.expected_interval_minutes * 2:
                observations.append(AnomalyObservation(
                    kind="missing_samples",
                    observation=(f"Gap of {gap_minutes:.1f} minutes between samples exceeds twice the configured "
                                 f"expected interval of {thresholds.expected_interval_minutes} minutes"),
                    evidence={"gap_minutes": gap_minutes, "expected_interval_minutes": thresholds.expected_interval_minutes,
                              "from": previous["timestamp"].isoformat(), "to": current["timestamp"].isoformat()},
                ))

    if thresholds.stale_after_minutes is not None and as_of is not None:
        latest = readings[-1]
        age_minutes = (as_of - latest["timestamp"]).total_seconds() / 60
        if age_minutes > thresholds.stale_after_minutes:
            observations.append(AnomalyObservation(
                kind="stale_sensor",
                observation=(f"Latest {measurement} reading is {age_minutes:.1f} minutes old, exceeding the "
                             f"configured staleness limit of {thresholds.stale_after_minutes} minutes"),
                evidence={"age_minutes": age_minutes, "threshold_minutes": thresholds.stale_after_minutes,
                          "latest_timestamp": latest["timestamp"].isoformat()},
            ))

    for reading in readings:
        if reading.get("quality") and reading["quality"] not in ("good",):
            observations.append(AnomalyObservation(
                kind="bad_quality",
                observation=f"Reading at {reading['timestamp'].isoformat()} carries quality flag '{reading['quality']}'",
                evidence={"quality": reading["quality"], "timestamp": reading["timestamp"].isoformat()},
            ))

    if len(readings) >= 2:
        preceding = [reading["value"] for reading in readings[:-1]]
        latest = readings[-1]
        if latest["value"] > max(preceding):
            observations.append(AnomalyObservation(
                kind="relative_increase",
                observation="Latest value increased relative to preceding values in the window.",
                evidence={"latest_value": latest["value"], "preceding_maximum": max(preceding),
                          "timestamp": latest["timestamp"].isoformat()},
            ))
        elif latest["value"] < min(preceding):
            observations.append(AnomalyObservation(
                kind="relative_decrease",
                observation="Latest value decreased relative to preceding values in the window.",
                evidence={"latest_value": latest["value"], "preceding_minimum": min(preceding),
                          "timestamp": latest["timestamp"].isoformat()},
            ))

    return observations
