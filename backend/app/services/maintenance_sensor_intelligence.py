"""B2: deterministic maintenance & sensor intelligence over bounded windows.

Deepens Phase 3C's sensor features and Phase 4E's threshold loop without
replacing either: the same bounded reads (sensor_readings_query /
maintenance_history), the same caller-supplied thresholds
(SensorFeatureThresholds), and the same observation-language boundary
(app.agents.observation_language). What B2 adds is the cross-links:
per-channel rate of change, threshold-crossing transitions, anomaly
persistence and duration, multivariate trend correlation, and
maintenance-history temporal correlation -- assembled into evidence-backed
observations, clearly separated tentative hypotheses with contradicting
evidence, and recommended verification checks.

Safety boundaries enforced here in code:
- correlation != causation: every correlation observation says so, and no
  hypothesis is generated from a correlation alone
- a sensor anomaly is never a confirmed equipment failure
- maintenance history is temporal context, never proof of recurrence
- no autonomous work-order creation and no plant write/control capability
- a missing time-window, threshold, or maintenance record stays missing
- no threshold is invented: every threshold check requires a caller-supplied
  value, as in Phase 3C

Every observation string is passed through the existing Phase 4E
observation-language validator and every recommended check through the
existing authorization-language heuristic (validate_language below) -- a
deterministic fail-safe, since B2's own output must obey the same boundaries
it deepens."""
import math
from datetime import timedelta, timezone

from app.core.config import settings
from app.agents.evidence import csv_row_evidence, sensor_window_evidence
from app.agents.observation_language import find_observation_language_violations
from app.agents.safety_language import find_authorization_language
from app.schemas.agent_outputs import Citation, MaintenanceHypothesis
from app.schemas.maintenance_sensor_intelligence import (
    AnomalyExcursion,
    ChannelAnalysis,
    IntelligenceObservation,
    IntelligenceSufficiency,
    MaintenanceLink,
    SensorMaintenanceIntelligenceRequest,
    SensorMaintenanceIntelligenceResponse,
    SustainedRise,
    ThresholdCrossing,
    TrendCorrelation,
)
from app.services import evidence_sufficiency
from app.services.equipment_tags import normalize_equipment_tag
from app.services.sensor_features import compute_features
from app.services.structured_queries import maintenance_history, sensor_readings_query

CORRELATION_DISCLAIMER = "Correlation does not establish causation."
ADVISORY_BOUNDARY = ("Advisory observations only; plant-state actions require existing governance and "
                     "human approval. No autonomous work order is created and no plant control is performed.")


def _aware(stamp):
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _num(value):
    return f"{value:.4g}"


def _label(value, unit):
    return f"{_num(value)}{' ' + unit if unit else ''}"


def _duration_text(days):
    if days >= 1:
        return f"{days:.1f} days"
    if days * 24 >= 1:
        return f"{days * 24:.1f} hours"
    return f"{days * 24 * 60:.1f} minutes"


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    cov = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    if x_var == 0 or y_var == 0:
        return None
    return max(-1.0, min(1.0, cov / math.sqrt(x_var * y_var)))


def _channel_groups(readings):
    groups = {}
    for reading in readings:  # already chronologically ordered by the query service
        groups.setdefault(reading.sensor_tag, []).append(reading)
    return {tag: groups[tag] for tag in sorted(groups)}


def _crossings(rows, thresholds):
    if thresholds is None:
        return []
    crossings = []
    for previous, current in zip(rows, rows[1:]):
        if thresholds.maximum is not None and previous.value <= thresholds.maximum < current.value:
            crossings.append(ThresholdCrossing(
                direction="above_maximum", threshold=thresholds.maximum,
                previous_value=previous.value, crossing_value=current.value,
                crossed_at=_aware(current.timestamp)))
        if thresholds.minimum is not None and previous.value >= thresholds.minimum > current.value:
            crossings.append(ThresholdCrossing(
                direction="below_minimum", threshold=thresholds.minimum,
                previous_value=previous.value, crossing_value=current.value,
                crossed_at=_aware(current.timestamp)))
    return crossings


def _excursions(rows, thresholds):
    if thresholds is None:
        return []

    def runs(direction, threshold, predicate):
        found, run = [], []
        for reading in rows:
            if predicate(reading.value, threshold):
                run.append(reading)
                continue
            if run:
                found.append(run)
                run = []
        if run:
            found.append(run)
        return [AnomalyExcursion(
            direction=direction, threshold=threshold, start=_aware(item[0].timestamp),
            end=_aware(item[-1].timestamp), samples=len(item),
            duration_minutes=(_aware(item[-1].timestamp) - _aware(item[0].timestamp)).total_seconds() / 60,
            extreme_value=(max if direction == "above_maximum" else min)(r.value for r in item),
        ) for item in found]

    result = []
    if thresholds.maximum is not None:
        result += runs("above_maximum", thresholds.maximum, lambda value, limit: value > limit)
    if thresholds.minimum is not None:
        result += runs("below_minimum", thresholds.minimum, lambda value, limit: value < limit)
    return result


def _sustained_rise(rows):
    """Trailing run of strictly increasing readings. A rise trend needs at
    least two increases to be a trend (the same structural minimum as the
    existing rolling_window ge=2); a single up-step is not reported here --
    Phase 3C's relative_increase already covers it."""
    if len(rows) < 3:
        return None
    start_index = len(rows) - 1
    for index in range(len(rows) - 1, 0, -1):
        if rows[index].value > rows[index - 1].value:
            start_index = index - 1
        else:
            break
    consecutive_increases = len(rows) - 1 - start_index
    if consecutive_increases < 2:
        return None
    window = rows[start_index:]
    first, last = window[0], window[-1]
    return SustainedRise(
        consecutive_increases=consecutive_increases, samples=len(window),
        start=_aware(first.timestamp), end=_aware(last.timestamp),
        first_value=first.value, last_value=last.value,
        absolute_change=last.value - first.value,
        duration_minutes=(_aware(last.timestamp) - _aware(first.timestamp)).total_seconds() / 60,
    )


def _correlations(groups):
    tags = sorted(groups)
    correlations = []
    for index, tag_a in enumerate(tags):
        for tag_b in tags[index + 1:]:
            rows_a, rows_b = groups[tag_a], groups[tag_b]
            stamps_a = {_aware(reading.timestamp): reading for reading in rows_a}
            shared = [(stamps_a[_aware(reading.timestamp)], reading)
                      for reading in rows_b if _aware(reading.timestamp) in stamps_a]
            aligned = len(shared)
            if aligned < 2:
                correlations.append(TrendCorrelation(
                    sensor_tag_a=tag_a, sensor_tag_b=tag_b, aligned_samples=aligned,
                    pearson_r=None, not_computed_reason="fewer than 2 aligned samples"))
                continue
            coefficient = _pearson([a.value for a, _ in shared], [b.value for _, b in shared])
            if coefficient is None:
                correlations.append(TrendCorrelation(
                    sensor_tag_a=tag_a, sensor_tag_b=tag_b, aligned_samples=aligned,
                    pearson_r=None, not_computed_reason="zero variance in one or both channels"))
                continue
            correlations.append(TrendCorrelation(
                sensor_tag_a=tag_a, sensor_tag_b=tag_b, aligned_samples=aligned,
                pearson_r=coefficient, not_computed_reason=None))
    return correlations


def _onsets(channel_analyses):
    onsets, seen = [], set()
    for channel in channel_analyses:
        stamps = [crossing.crossed_at for crossing in channel.threshold_crossings]
        stamps += [excursion.start for excursion in channel.excursions]
        if channel.sustained_rise is not None:
            stamps.append(channel.sustained_rise.start)
        for stamp in stamps:
            key = (channel.sensor_tag, stamp)
            if key not in seen:
                seen.add(key)
                onsets.append((stamp, channel.sensor_tag))
    # One earliest observed onset per channel bounds maintenance cross-links.
    earliest = {}
    for stamp, channel in sorted(onsets):
        earliest.setdefault(channel, stamp)
    return sorted((stamp, channel) for channel, stamp in earliest.items())


def _maintenance_links(onsets, maintenance_rows, refs_by_record):
    links = []
    for record in maintenance_rows:
        if record.maintenance_date is None:
            continue  # an undated record cannot be temporally ordered; it stays context only
        ref = refs_by_record[record.id]
        event_at = _aware(record.maintenance_date)
        for onset_at, channel in onsets:
            links.append(MaintenanceLink(
                onset_channel=channel, onset_at=onset_at,
                work_order_id=record.work_order_id, maintenance_type=record.maintenance_type,
                maintenance_date=event_at,
                relation=("before_anomaly" if event_at < onset_at else
                          "after_anomaly" if event_at > onset_at else "at_anomaly"),
                interval_days=abs((onset_at - event_at).total_seconds()) / 86400,
                evidence_id=ref.evidence_id))
    return links


def validate_language(observations, contradicting_evidence, recommended_checks, metadata=()):
    """Deterministic fail-safe over B2's own output: raises if any observation
    or recommended check would violate the existing observation-language
    (app.agents.observation_language) or authorization-language
    (app.agents.safety_language) boundaries. Hypotheses are guarded
    structurally by MaintenanceHypothesis itself."""
    def prose(text):
        # Identifiers/units are source data, not diagnostic or authorization prose.
        for value in sorted(set(filter(None, metadata)), key=len, reverse=True):
            text = text.replace(value, "recorded identifier")
        return text

    for entry in [*observations, *contradicting_evidence]:
        violations = find_observation_language_violations(prose(entry.observation))
        if violations:
            raise ValueError(f"Observation-language guard failed for kind '{entry.kind}': {violations}")
    for check in recommended_checks:
        if find_authorization_language(prose(check)):
            raise ValueError(f"Recommended-check guard failed: authorization or control language in '{check}'")


def analyze(session, request) -> tuple[SensorMaintenanceIntelligenceResponse, list]:
    """Returns (response, evidence_refs): refs are the full EvidenceRef models
    behind every evidence_id in the response, for the citation validator and
    agent evidence tracking. All computation is deterministic; no model call."""
    request = SensorMaintenanceIntelligenceRequest.model_validate(request)
    tag = normalize_equipment_tag(request.equipment_tag)
    readings = sensor_readings_query(session, equipment_tag=tag, start=request.start, end=request.end,
                                     limit=settings.structured_query_max_limit)
    maintenance_start = request.start - timedelta(days=request.maintenance_lookback_days)
    maintenance_rows = maintenance_history(session, equipment_tag=tag, start=maintenance_start, end=request.end,
                                           limit=settings.structured_query_max_limit)
    warnings = []
    coverage_gaps = []
    if len(readings) >= settings.structured_query_max_limit or len(maintenance_rows) >= settings.structured_query_max_limit:
        coverage_gaps.append("possibly_truncated_window")
        warnings.append("A query reached its row cap; coverage may be incomplete. Narrow the requested window.")
    if not readings:
        warnings.append("No sensor readings were found for this equipment/window; no trend, "
                        "persistence, or correlation was computed.")

    groups = _channel_groups(readings)
    # ponytail: cap pairwise expansion at 16 channels; add channel selection for wider equipment.
    if len(groups) > 16:
        coverage_gaps.append("channel_limit")
        warnings.append("More than 16 channels matched; narrow the window. Cross-channel analysis was withheld.")
        groups = {}
    for sensor_tag, rows in list(groups.items()):
        stamps = [_aware(row.timestamp) for row in rows]
        if (len({(row.measurement, row.unit) for row in rows}) != 1
                or len(set(stamps)) != len(stamps)
                or any(not math.isfinite(row.value) or row.quality not in (None, "good") for row in rows)):
            del groups[sensor_tag]
            coverage_gaps.append("unusable_channel")
            warnings.append(f"Channel {sensor_tag} excluded: mixed measurement/units, duplicate timestamps, nonfinite values, or bad quality.")
    channels = []
    window_refs_by_channel = {}
    for sensor_tag, rows in groups.items():
        thresholds = request.thresholds.get(sensor_tag)
        values = [reading.value for reading in rows]
        features = compute_features(values, request.rolling_window)
        unit = rows[0].unit
        first_at, last_at = _aware(rows[0].timestamp), _aware(rows[-1].timestamp)
        if thresholds and thresholds.expected_interval_minutes is not None and any(
                (_aware(b.timestamp) - _aware(a.timestamp)).total_seconds() / 60 > thresholds.expected_interval_minutes * 2
                for a, b in zip(rows, rows[1:])):
            coverage_gaps.append("sampling_gaps")
            warnings.append(f"Channel {sensor_tag} has sampling gaps beyond twice the supplied expected interval; persistence between samples is unknown.")
        hours = (last_at - first_at).total_seconds() / 3600
        rate = (values[-1] - values[0]) / hours if len(rows) >= 2 and hours > 0 else None
        provenance = [{"source_filename": reading.citation.source_filename,
                       "source_sha256": reading.citation.source_sha256,
                       "source_row_number": reading.citation.source_row_number} for reading in rows]
        window_ref = sensor_window_evidence(
            source_filename=rows[0].citation.source_filename, source_sha256=rows[0].citation.source_sha256,
            citation_label=(f"{tag}/{sensor_tag} {rows[0].citation.source_filename} "
                            f"{request.start.isoformat()} to {request.end.isoformat()}"),
            provenance=provenance)
        channels.append(ChannelAnalysis(
            sensor_tag=sensor_tag, measurement=rows[0].measurement, unit=unit,
            reading_count=len(rows), first_timestamp=first_at, last_timestamp=last_at,
            features=features, rate_of_change_per_hour=rate,
            threshold_crossings=_crossings(rows, thresholds),
            excursions=_excursions(rows, thresholds),
            sustained_rise=_sustained_rise(rows),
            evidence_id=window_ref.evidence_id,
            warnings=([] if thresholds is not None and (thresholds.minimum is not None or thresholds.maximum is not None) else
                      ["No threshold was supplied for this channel; threshold crossing and persistence "
                       "checks were skipped."]),
        ))
        window_refs_by_channel[sensor_tag] = window_ref

    refs_by_record = {}
    maintenance_refs = []
    for record in maintenance_rows:
        ref = csv_row_evidence(source_filename=record.citation.source_filename,
                               source_sha256=record.citation.source_sha256,
                               source_row_number=record.citation.source_row_number)
        refs_by_record[record.id] = ref
        maintenance_refs.append(ref)
    undated = [record for record in maintenance_rows if record.maintenance_date is None]
    if undated:
        warnings.append(f"{len(undated)} maintenance record(s) had no usable date and were not temporally "
                        f"correlated.")

    onsets = _onsets(channels)
    links = _maintenance_links(onsets, maintenance_rows, refs_by_record)

    anomalous_tags = {channel.sensor_tag for channel in channels
                      if channel.threshold_crossings or channel.excursions or channel.sustained_rise is not None}
    stable_channels = [channel for channel in channels if channel.sensor_tag not in anomalous_tags
                       and channel.reading_count >= 2 and channel.features.minimum == channel.features.maximum
                       and request.thresholds.get(channel.sensor_tag) is not None
                       and (request.thresholds[channel.sensor_tag].minimum is not None
                            or request.thresholds[channel.sensor_tag].maximum is not None)]

    observations, contradicting, hypotheses = [], [], []
    for channel in channels:
        summary = (f"{channel.sensor_tag} recorded {channel.reading_count} readings from "
                   f"{channel.first_timestamp.isoformat()} to {channel.last_timestamp.isoformat()}; "
                   f"mean {_label(channel.features.mean, channel.unit)}, minimum "
                   f"{_label(channel.features.minimum, channel.unit)}, maximum "
                   f"{_label(channel.features.maximum, channel.unit)}, last recorded value "
                   f"{_label(channel.features.last_value, channel.unit)}")
        if channel.rate_of_change_per_hour is not None:
            summary += f"; average rate of change {channel.rate_of_change_per_hour:+.4g} per hour over the window"
        observations.append(IntelligenceObservation(
            kind="channel_window_summary", channel=channel.sensor_tag, observation=summary + ".",
            evidence_ids=[channel.evidence_id]))

        for crossing in channel.threshold_crossings:
            direction = "above" if crossing.direction == "above_maximum" else "below"
            limit_word = "maximum" if crossing.direction == "above_maximum" else "minimum"
            observations.append(IntelligenceObservation(
                kind="threshold_crossing", channel=channel.sensor_tag,
                observation=(f"{channel.sensor_tag} crossed {direction} the supplied {limit_word} threshold "
                             f"{_num(crossing.threshold)} at {crossing.crossed_at.isoformat()}: previous recorded "
                             f"value {_num(crossing.previous_value)}, crossing value "
                             f"{_num(crossing.crossing_value)}."),
                evidence_ids=[channel.evidence_id]))

        for excursion in channel.excursions:
            direction = "above" if excursion.direction == "above_maximum" else "below"
            limit_word = "maximum" if excursion.direction == "above_maximum" else "minimum"
            observations.append(IntelligenceObservation(
                kind="anomaly_persistence", channel=channel.sensor_tag,
                observation=(f"{channel.sensor_tag} was recorded {direction} the supplied {limit_word} threshold "
                             f"{_num(excursion.threshold)} for {excursion.samples} consecutive recorded samples "
                             f"({excursion.duration_minutes:.1f} minutes) from {excursion.start.isoformat()} to "
                             f"{excursion.end.isoformat()}; peak recorded value "
                             f"{_num(excursion.extreme_value)}. Duration spans recorded samples only; continuity between samples is unverified."),
                evidence_ids=[channel.evidence_id]))

        if channel.sustained_rise is not None:
            rise = channel.sustained_rise
            observations.append(IntelligenceObservation(
                kind="sustained_rise", channel=channel.sensor_tag,
                observation=(f"{channel.sensor_tag} recorded {rise.samples} consecutive increasing readings "
                             f"({rise.consecutive_increases} increases) from {rise.start.isoformat()} to "
                             f"{rise.end.isoformat()}: {_num(rise.first_value)} to {_num(rise.last_value)} "
                             f"({rise.absolute_change:+.4g} total over {rise.duration_minutes:.1f} minutes); a "
                             f"recorded monotonic rise is a measured trend only."),
                evidence_ids=[channel.evidence_id]))

        if channel.warnings:
            observations.append(IntelligenceObservation(
                kind="threshold_not_supplied", channel=channel.sensor_tag,
                observation=(f"No threshold was supplied for the recorded channel {channel.sensor_tag}; threshold "
                             f"crossing and persistence checks were skipped and this gap remains missing."),
                evidence_ids=[channel.evidence_id]))

    correlations = _correlations(groups)
    for correlation in correlations:
        evidence_ids = [window_refs_by_channel[correlation.sensor_tag_a].evidence_id,
                        window_refs_by_channel[correlation.sensor_tag_b].evidence_id]
        if correlation.pearson_r is not None:
            observations.append(IntelligenceObservation(
                kind="trend_correlation",
                observation=(f"{correlation.sensor_tag_a} and {correlation.sensor_tag_b} recorded "
                             f"{correlation.aligned_samples} aligned samples in the window; Pearson correlation "
                             f"coefficient r={correlation.pearson_r:.3f}. {CORRELATION_DISCLAIMER}"),
                evidence_ids=evidence_ids))
        else:
            observations.append(IntelligenceObservation(
                kind="trend_correlation",
                observation=(f"{correlation.sensor_tag_a} and {correlation.sensor_tag_b} recorded "
                             f"{correlation.aligned_samples} aligned samples; correlation was not computed "
                             f"({correlation.not_computed_reason})."),
                evidence_ids=evidence_ids))

    for link in links:
        direction = {"before_anomaly": "before", "after_anomaly": "after", "at_anomaly": "at"}[link.relation]
        text = (f"{(link.maintenance_type or 'Maintenance').capitalize()} event "
                f"{link.work_order_id or '(no work order id)'} was recorded "
                f"{_duration_text(link.interval_days)} {direction} the {link.onset_channel} anomaly onset at "
                f"{link.onset_at.isoformat()}")
        if link.relation == "before_anomaly":
            text += ". Temporal ordering only; history is not proof of recurrence and no causal link is established."
        elif link.relation == "after_anomaly":
            text += ". Temporal ordering only; the event postdates the onset."
        else:
            text += ". Recorded timestamps coincide; event order is unknown."
        observations.append(IntelligenceObservation(
            kind="maintenance_temporal_relation", channel=link.onset_channel,
            observation=text, evidence_ids=[link.evidence_id, window_refs_by_channel[link.onset_channel].evidence_id]))

    contradicting_by_channel = {sensor_tag: [] for sensor_tag in anomalous_tags}
    if anomalous_tags:
        for channel in stable_channels:
            for anomalous_tag in sorted(anomalous_tags):
                aligned = next(c.aligned_samples for c in correlations
                               if {c.sensor_tag_a, c.sensor_tag_b} == {channel.sensor_tag, anomalous_tag})
                if aligned < 2:
                    continue
                contradicting_by_channel[anomalous_tag].append(channel.evidence_id)
                contradicting.append(IntelligenceObservation(
                    kind="contradicting_indicator", channel=channel.sensor_tag,
                    observation=(f"{channel.sensor_tag} recorded no anomaly onset in the window while "
                                 f"{anomalous_tag} shows a detected change; this channel is recorded as "
                                 f"contradicting context for equipment-wide interpretations."),
                    evidence_ids=[channel.evidence_id, window_refs_by_channel[anomalous_tag].evidence_id]))

    for channel in channels:
        if channel.sustained_rise is None:
            continue
        hypotheses.append(MaintenanceHypothesis(
            text=(f"Possible sensor variation or equipment condition affecting the recorded {channel.sensor_tag} channel. "
                  f"These explanations remain unverified. Verification is required; correlation and "
                  f"maintenance history do not establish causation or recurrence."),
            supporting_evidence=[channel.evidence_id],
            contradicting_evidence=contradicting_by_channel[channel.sensor_tag],
            # Required legacy field: zero means unassessed, not a calibrated probability.
            confidence=0.0))

    usable_maintenance = [record for record in maintenance_rows if record.maintenance_date is not None]
    readings_present = bool(channels)
    analyzable = bool(channels) and all(channel.reading_count >= 2 for channel in channels)
    missing_categories = list(coverage_gaps)
    if not readings_present:
        missing_categories += ["sensor_window", "trend_window"]
    elif not analyzable:
        missing_categories.append("trend_window")
    if readings_present and len(channels) < 2:
        missing_categories.append("multi_channel_coverage")
    if not usable_maintenance:
        missing_categories.append("maintenance_history")
    if any(channel.warnings for channel in channels):
        missing_categories.append("supplied_thresholds")
    if any(correlation.aligned_samples < 2 for correlation in correlations):
        missing_categories.append("aligned_sensor_window")
    state = "INSUFFICIENT" if (not readings_present or not analyzable) else \
        ("PARTIAL" if missing_categories else "SUFFICIENT")
    sufficiency = IntelligenceSufficiency(state=state, missing_categories=sorted(set(missing_categories)),
        meaning="Evidence coverage only; never permission to execute. Correlation never establishes causation.")

    recommended = []
    if anomalous_tags:
        recommended.append(f"Have a qualified human inspector verify the detected change on {tag} with field "
                           f"instrumentation or a second independent sensor; this is an inspection "
                           f"recommendation, not an action.")
    if any(request.thresholds.get(channel.sensor_tag) is not None for channel in channels):
        recommended.append(f"Verify the supplied threshold values against the authoritative reviewed SOP for "
                           f"{tag} before interpreting any threshold comparison.")
    missing_threshold_channels = [channel.sensor_tag for channel in channels if channel.warnings]
    if missing_threshold_channels:
        recommended.append(f"Obtain the reviewed SOP threshold for {', '.join(missing_threshold_channels)}; "
                           f"none was supplied and none is invented here.")
    if any(correlation.pearson_r is not None for correlation in correlations):
        recommended.append("Cross-check correlated channels against independent field instrumentation before "
                           "any common-cause interpretation.")
    if links:
        recommended.append("Have a qualified reviewer confirm whether the recorded maintenance events relate "
                           "to the detected change; history alone is not proof of recurrence.")
    if not usable_maintenance:
        recommended.append(f"Obtain dated maintenance history for {tag} covering the analysis window; the gap "
                           f"remains missing.")
    if state == "INSUFFICIENT":
        recommended.append("Re-run the analysis with a window containing at least two recorded readings per "
                           "channel.")
    recommended.append(ADVISORY_BOUNDARY)

    all_refs = [window_refs_by_channel[channel.sensor_tag] for channel in channels] + maintenance_refs
    citations = [Citation(evidence_id=ref.evidence_id, locator=ref.locator,
                          claim="Recorded sensor window; measured facts only." if ref.kind == "sensor_window"
                          else "Recorded maintenance row; temporal context only.")
                 for ref in all_refs]
    measured = evidence_sufficiency.assess(
        "sensor maintenance history", all_refs, citations=citations,
        invalid_ids=[ref.evidence_id for ref in all_refs if not evidence_sufficiency.source_valid(session, ref)],
        categories={ref.evidence_id: ["maintenance"] for ref in maintenance_refs})
    rank = {"SUFFICIENT": 0, "PARTIAL": 1, "INSUFFICIENT": 2}
    sufficiency.state = max((sufficiency.state, measured["state"]), key=rank.get)
    sufficiency.missing_categories = sorted(set(sufficiency.missing_categories + measured["missing_categories"]))
    sufficiency.issues = measured["issues"]

    response = SensorMaintenanceIntelligenceResponse(
        equipment_tag=tag, window_start=_aware(request.start), window_end=_aware(request.end),
        maintenance_window_start=_aware(maintenance_start), maintenance_window_end=_aware(request.end),
        channels=channels, correlations=correlations, maintenance_links=links,
        observations=observations, contradicting_evidence=contradicting, hypotheses=hypotheses,
        recommended_checks=recommended, sufficiency=sufficiency, warnings=warnings,
        citations=citations, evidence_refs=all_refs, human_approval_required=True)
    validate_language(observations, contradicting, recommended,
                      metadata=[tag, *groups, *(c.unit for c in channels),
                                *(r.work_order_id for r in maintenance_rows),
                                *((r.maintenance_type or "Maintenance").capitalize() for r in maintenance_rows)])
    return response, all_refs
