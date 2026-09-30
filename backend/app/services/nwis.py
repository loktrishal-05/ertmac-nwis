"""Transparent offset and risk tools; no language model controls scores."""
import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from statistics import mean, median, pstdev
from sqlalchemy import select, text, func
from fastapi import HTTPException
from app.db.models.nwis import (Well, WellTrajectoryPoint, FormationInterval, DrillingEvent, TelemetrySample,
    OffsetWellMatch, RiskAssessment, RiskEvidence, DrillingAdvisory, DrillingReport, AlertState, HAZARDS)
from app.schemas.nwis import EventOut, HazardOut, MatchOut, RiskOut
from app.services.audit import append_event

VERSION = 'nwis-hybrid-v2'
DEFAULT_WEIGHTS = dict(geographic=.15, formation=.30, depth=.20, trajectory=.15, program=.10, data_quality=.10)

def now():
    return datetime.now(timezone.utc)

def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()

def audit(session, action, actor=None, **payload):
    append_event(session, event_type='PRODUCT_INTEGRATION_EVENT', actor_id=actor.id if actor else None,
                 actor_kind='user' if actor else 'system', payload=dict(product='SIH26121', action=action, **payload))

def visible(user):
    return ['internal', 'public'] + (['restricted'] if user.role == 'admin' else [])

def well(session, ident, user):
    row = session.get(Well, ident)
    if row is None or row.access_scope not in visible(user):
        raise HTTPException(404, 'Well unavailable')
    return row

def formation_at(session, w):
    if w.current_md is None:
        return None
    rows = session.scalars(select(FormationInterval).where(FormationInterval.well_id == w.id,
        FormationInterval.top_md <= w.current_md, FormationInterval.bottom_md > w.current_md)
        .order_by(FormationInterval.id).limit(2)).all()
    return rows[0] if len(rows) == 1 else None  # conflicting intervals are not resolved silently

def interpolate(session, well_id, md, attr='tvd'):
    if md is None:
        return None
    low = session.scalar(select(WellTrajectoryPoint).where(WellTrajectoryPoint.well_id == well_id,
        WellTrajectoryPoint.md <= md).order_by(WellTrajectoryPoint.md.desc()).limit(1))
    high = session.scalar(select(WellTrajectoryPoint).where(WellTrajectoryPoint.well_id == well_id,
        WellTrajectoryPoint.md >= md).order_by(WellTrajectoryPoint.md).limit(1))
    if low is None or high is None or getattr(low, attr) is None or getattr(high, attr) is None:
        return None  # never extrapolate missing trajectory
    if low.md == high.md:
        return getattr(low, attr)
    return getattr(low, attr) + (getattr(high, attr) - getattr(low, attr)) * (md-low.md)/(high.md-low.md)

def haversine(a, b):
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dl, dn = math.radians(b.latitude-a.latitude), math.radians(b.longitude-a.longitude)
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(math.sin(dl/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dn/2)**2)))

NEARBY_SQL = '''SELECT w.id, ST_Distance(a.location,w.location) AS distance_m
 FROM nwis_wells a JOIN nwis_wells w ON w.id <> a.id
 WHERE a.id=:active AND ST_DWithin(a.location,w.location,:radius)
 AND w.access_scope IN ('internal','public')
 ORDER BY distance_m,w.id LIMIT :limit OFFSET :offset'''

def nearby(session, active, radius_km, user, limit=101, offset=0):
    if not math.isfinite(radius_km) or not 0 < radius_km <= 100:
        raise ValueError('Radius must be between 0 and 100 km')
    if active.latitude is None or active.longitude is None:
        return []
    if session.bind.dialect.name == 'postgresql':
        sql = NEARBY_SQL
        if user.role == 'admin':
            sql = sql.replace("('internal','public')", "('internal','public','restricted')")
        rows = session.execute(text(sql), dict(active=active.id, radius=radius_km*1000, limit=limit, offset=offset)).all()
        return [(session.get(Well, ident), float(distance)) for ident, distance in rows]
    if session.bind.dialect.name != 'sqlite':
        raise RuntimeError('PostGIS is required outside isolated SQLite tests')
    # ponytail: O(n) spherical fallback for isolated SQLite tests only; PostGIS handles deployment.
    rows = session.scalars(select(Well).where(Well.id != active.id, Well.access_scope.in_(visible(user)),
        Well.latitude.is_not(None), Well.longitude.is_not(None))).all()
    matches = [(w, haversine(active, w)) for w in rows]
    return sorted((x for x in matches if x[1] <= radius_km*1000), key=lambda x:(x[1],x[0].id))[offset:offset+limit]

def weights():
    result = json.loads(os.getenv('NWIS_OFFSET_WEIGHTS', json.dumps(DEFAULT_WEIGHTS)))
    if set(result) != set(DEFAULT_WEIGHTS) or any(not isinstance(v,(float,int)) or not math.isfinite(v) or v < 0 for v in result.values()) or sum(result.values()) <= 0:
        raise ValueError('Invalid NWIS_OFFSET_WEIGHTS')
    return {k:v/sum(result.values()) for k,v in result.items()}

def score_offset(session, active, candidate, distance, radius_km, lookahead=100):
    af = formation_at(session, active)
    intervals = session.scalars(select(FormationInterval).where(FormationInterval.well_id == candidate.id)
        .order_by(FormationInterval.top_md, FormationInterval.id)).all()
    matches = [f for f in intervals if af and f.formation == af.formation]
    cf = matches[0] if len(matches) == 1 else None
    components = dict(geographic=math.exp(-distance/5000), formation=(1.0 if cf else 0.0) if af and intervals else None,
                      depth=None, trajectory=None, program=None, data_quality=0.0)
    basis = 'unavailable'
    if af and cf and active.current_md is not None:
        for b in ('tvdss','tvd','md'):
            start = active.current_md if b == 'md' else interpolate(session,active.id,active.current_md,b)
            end = active.current_md+lookahead if b == 'md' else interpolate(session,active.id,active.current_md+lookahead,b)
            top, bottom = getattr(cf,'top_'+b), getattr(cf,'bottom_'+b)
            if None not in (start,end,top,bottom) and end > start:
                components['depth'] = max(0, min(end,bottom)-max(start,top))/(end-start)
                basis=b
                break
    ai = interpolate(session,active.id,active.current_md,'inclination')
    ci = interpolate(session,candidate.id,(cf.top_md+cf.bottom_md)/2 if cf else active.current_md,'inclination')
    if ai is not None and ci is not None:
        components['trajectory'] = max(0,1-abs(ai-ci)/90)
    if active.program and candidate.program:
        keys = [k for k in ('mud_system','hole_size_in','casing_size_in') if active.program.get(k) is not None and candidate.program.get(k) is not None]
        if keys:
            components['program'] = sum(active.program[k] == candidate.program[k] for k in keys)/len(keys)
    known = sum(components[k] is not None for k in ('formation','depth','trajectory','program'))/4
    quality = known * (min(af.confidence,cf.confidence) if af and cf else .4)
    if basis in ('md','unavailable'):
        quality *= .65
    components['data_quality'] = quality
    ws = weights()
    total = sum(ws[k]*(v if v is not None else 0) for k,v in components.items())
    return MatchOut(offset_well_id=candidate.id,distance_m=distance,distance_km=distance/1000,
        **{k+'_score':v for k,v in components.items()},total_score=total,depth_basis=basis,weights=ws,
        algorithm_version=VERSION,dataset_origin=candidate.dataset_origin,
        explanation=explain(components,distance,basis,lookahead,af.formation if af else None))

def explain(c, distance, basis, lookahead, formation):
    """Deterministic reasons from the computed components only; unknowns are stated, never guessed."""
    reasons = [f'{distance/1000:.1f} km from the active well (geographic {c["geographic"]:.2f})']
    if c['formation'] is None: reasons.append('formation data unavailable')
    elif c['formation'] == 1: reasons.append(f'penetrated the active formation {formation}')
    else: reasons.append(f'active formation {formation} not matched at a single interval')
    reasons.append('depth overlap unavailable' if c['depth'] is None
        else f'{c["depth"]*100:.0f}% overlap with the next {lookahead} m on {basis.upper()}')
    reasons.append('trajectory comparison unavailable' if c['trajectory'] is None else f'trajectory similarity {c["trajectory"]:.2f}')
    reasons.append('program context unavailable' if c['program'] is None else f'program context similarity {c["program"]:.2f}')
    reasons.append(f'data quality {c["data_quality"]:.2f}')
    return reasons

def offsets(session, active, user, radius=10, lookahead=100):
    candidates = nearby(session,active,radius,user,limit=501)
    if len(candidates)>500:
        raise HTTPException(422,'More than 500 candidates; reduce radius')
    return sorted([score_offset(session,active,w,d,radius,lookahead) for w,d in candidates],key=lambda x:(-x.total_score,x.offset_well_id))

def event_query(user, well_id=None, formation=None, kind=None, depth_min=None, depth_max=None, basis='md'):
    if basis!='tvdss' and any(v is not None and v<0 for v in (depth_min,depth_max)):
        raise HTTPException(422,'Negative depth is supported only for TVDSS')
    if depth_min is not None and depth_max is not None and depth_min>depth_max:
        raise HTTPException(422,'depth_min exceeds depth_max')
    query=select(DrillingEvent).join(Well).where(Well.access_scope.in_(visible(user)))
    for col,value in ((DrillingEvent.well_id,well_id),(DrillingEvent.formation,formation),(DrillingEvent.event_type,kind)):
        if value is not None: query=query.where(col.in_(value) if isinstance(value,(list,tuple)) else col==value)
    lo = DrillingEvent.start_depth_md if basis=='md' else getattr(DrillingEvent,basis)
    hi = DrillingEvent.end_depth_md if basis=='md' else lo
    if depth_min is not None: query=query.where(hi>=depth_min)
    if depth_max is not None: query=query.where(lo<=depth_max)
    return query.order_by(DrillingEvent.well_id,DrillingEvent.start_depth_md,DrillingEvent.id)

def telemetry(session, active, channels=None, start=None, end=None, limit=1000, offset=0):
    end=utc(end or active.as_of or now())
    start=utc(start or end-timedelta(hours=1))
    if start>=end or end-start>timedelta(hours=24):
        raise HTTPException(422,'Telemetry window must be positive and at most 24 hours')
    query=select(TelemetrySample).where(TelemetrySample.well_id==active.id,
        TelemetrySample.timestamp>=start,TelemetrySample.timestamp<=end)
    if channels: query=query.where(TelemetrySample.channel.in_(channels))
    return session.scalars(query.order_by(TelemetrySample.timestamp,TelemetrySample.channel).offset(offset).limit(limit)).all()

def features(samples):
    good=[]
    for sample in samples:
        if sample.value is None or sample.quality!='good' or not math.isfinite(sample.value):
            good=[]
            continue
        if good and utc(sample.timestamp)-utc(good[-1].timestamp)>timedelta(minutes=5): good=[]
        good.append(sample)
    if len(good)<6: return None
    values=[s.value for s in good]
    baseline=values[:-3]
    center=median(baseline)
    scale=1.4826*median(abs(x-center) for x in baseline)
    if scale==0: scale=pstdev(baseline)
    # Flat baseline has no statistically estimable scale; don't invent a z-score.
    z=None if scale==0 else (values[-1]-center)/scale
    persistence=0 if not scale else sum(abs(v-center)/scale>=3 for v in values[-3:])
    seconds=(utc(good[-1].timestamp)-utc(good[0].timestamp)).total_seconds()
    dt=(utc(good[-1].timestamp)-utc(good[-2].timestamp)).total_seconds()
    return dict(mean=mean(values),std=pstdev(values),slope=(values[-1]-values[0])/seconds if seconds else None,
        rate_of_change=(values[-1]-values[-2])/dt if dt else None,robust_z=z,persistence=persistence,count=len(good))

def risk(session, active, user, lookahead=100, radius=10, as_of=None):
    at=utc(as_of or active.as_of or now())
    af=formation_at(session,active)
    ranked=offsets(session,active,user,radius,lookahead)
    relevant=[m for m in ranked if m.formation_score==1 and m.depth_score and m.total_score>=.5]
    samples=telemetry(session,active,start=at-timedelta(minutes=30),end=at,limit=1001)
    if len(samples)>1000: samples=[]  # insufficient bounded evidence, not a partial current window
    channel_features={}
    channel_fresh={}
    for channel in ('torque','standpipe_pressure','flow','hookload'):
        readings=[s for s in samples if s.channel==channel]
        last=max((utc(s.timestamp) for s in readings if s.quality=='good' and s.value is not None and math.isfinite(s.value)),default=None)
        channel_fresh[channel]=last is not None and at-last<=timedelta(minutes=5)
        channel_features[channel]=features(readings) if channel_fresh[channel] else None
    hazard_channels=dict(stuck_pipe='torque',torque_drag='torque',mud_loss='flow',kick_or_overpressure='standpipe_pressure')
    events=[]
    for match in relevant:
        candidate=session.get(Well,match.offset_well_id)
        basis=match.depth_basis
        low=active.current_md if basis=='md' else interpolate(session,active.id,active.current_md,basis)
        high=active.current_md+lookahead if basis=='md' else interpolate(session,active.id,active.current_md+lookahead,basis)
        query=event_query(user,candidate.id,af.formation,depth_min=low,depth_max=high,basis=basis)
        rows=session.scalars(query.limit(501)).all()
        if len(rows)>500: raise HTTPException(422,'Too many interval events; narrow the interval')
        events.extend((e,match) for e in rows if e.verification_state not in ('review_needed','rejected') and e.confidence>=.5)
    hazards=[]
    for hazard in HAZARDS:
        evidence=[(e,m) for e,m in events if e.event_type==hazard]
        supporting=sorted({e.well_id for e,m in evidence})
        denominator=sum(m.total_score for m in relevant)
        exposure=sum(m.total_score for m in relevant if m.offset_well_id in supporting)/denominator if denominator else None
        channel=hazard_channels.get(hazard)
        fresh=channel_fresh.get(channel,False)
        feat=channel_features.get(channel)
        anomaly=None if feat is None or feat['robust_z'] is None else (.15 if feat['persistence']==3 else 0.0)
        probability=None if exposure is None else min(.99,exposure+(1-exposure)*(anomaly or 0))
        quality=mean(m.data_quality_score for m in relevant) if relevant else 0
        evidence_quality=mean(e.confidence for e,m in evidence) if evidence else .35
        confidence=quality*min(1,len(relevant)/5)*evidence_quality*(1 if feat else .8)
        accounts={}
        for e,m in evidence:
            accounts.setdefault((e.well_id,e.start_depth_md),set()).add((e.outcome,e.mitigation))
        conflicting=any(len(v)>1 for v in accounts.values())
        if conflicting: confidence*=.5
        factors=['formation_match','historical_event_prevalence'] if supporting else []
        if anomaly: factors.append(hazard_channels[hazard]+'_persistent_deviation')
        data_quality=dict(analog_count=len(relevant),offset_quality=quality,evidence_quality=evidence_quality,
            telemetry_available=feat is not None,telemetry_fresh=fresh,telemetry_features=feat,
            telemetry_mode='replay' if active.dataset_origin=='synthetic_demo' else 'historical',freshness_basis='assessment_as_of',
            depth_bases=sorted({m.depth_basis for m in relevant}),contradictory_evidence=conflicting,calibration='unavailable',
            missing=['no_usable_offsets'] if not relevant else (['telemetry'] if feat is None else []))
        payload=dict(type=hazard, probability=probability,confidence=confidence,trend='rising' if anomaly else 'unavailable',
            historical_exposure=exposure,live_anomaly_contribution=anomaly,supporting_offset_wells=supporting,
            top_factors=factors,evidence_ids=[e.id for e,m in evidence],data_quality=data_quality)
        identity=digest(dict(well=active.id,at=at,md=active.current_md,lookahead=lookahead,radius=radius,version=VERSION,
            weights=weights(),payload=payload,evidence=[EventOut.model_validate(e).model_dump(mode='json') for e,m in evidence]))
        hazards.append(HazardOut(assessment_id=identity,**payload))
    return RiskOut(well_id=active.id,as_of=at,current_md_m=active.current_md,
        current_tvd_m=interpolate(session,active.id,active.current_md),formation=af.formation if af else None,
        lookahead_m=lookahead,hazards=hazards,dataset_origin=active.dataset_origin,model_version=VERSION),ranked

def alert_transition(state, hazard, at):
    at=utc(at)
    if state.last_as_of and at<=utc(state.last_as_of): return False
    if state.last_as_of and at-utc(state.last_as_of)>timedelta(minutes=5): state.consecutive=0
    state.last_as_of=at
    eligible=hazard.probability is not None and hazard.confidence>=.5 and len(hazard.supporting_offset_wells)>=2
    if not eligible or hazard.probability<.4:
        state.active=False; state.consecutive=0
        return False
    state.consecutive=state.consecutive+1 if hazard.probability>=.6 else 0
    if state.active or state.consecutive<3: return False
    if state.last_alert_at and at-utc(state.last_alert_at)<timedelta(minutes=30): return False
    state.active=True; state.last_alert_at=at
    return True

def persist_assessment(session, active, result, matches, user):
    # Serialize per well so repeated requests cannot create duplicate alerts/reviews.
    session.execute(select(Well).where(Well.id==active.id).with_for_update()).scalar_one()
    for m in matches:
        ident=digest([active.id,m.model_dump(),result.current_md_m,result.lookahead_m])
        if session.get(OffsetWellMatch,ident) is None:
            session.add(OffsetWellMatch(id=ident,active_well_id=active.id,**m.model_dump(exclude={'distance_m','distance_km','depth_basis','weights','explanation'})))
    created=[]
    for h in result.hazards:
        if session.get(RiskAssessment,h.assessment_id) is not None: continue
        session.add(RiskAssessment(id=h.assessment_id,well_id=active.id,as_of=result.as_of,current_md=result.current_md_m,
            formation=result.formation,lookahead_m=result.lookahead_m,hazard_type=h.type,probability=h.probability,
            confidence=h.confidence,trend=h.trend,model_version=VERSION,
            snapshot=h.model_dump(mode='json') | {
                'event_snapshots':{eid:EventOut.model_validate(session.get(DrillingEvent,eid)).model_dump(mode='json') for eid in h.evidence_ids},
                'source_hashes':{eid:session.get(DrillingReport,session.get(DrillingEvent,eid).source_report_id).file_hash for eid in h.evidence_ids}},
            dataset_origin=active.dataset_origin))
        session.flush()
        for eid in h.evidence_ids:
            e=session.get(DrillingEvent,eid)
            session.add(RiskEvidence(assessment_id=h.assessment_id,drilling_event_id=eid,offset_well_id=e.well_id,
                contribution=1/len(h.evidence_ids),reason='Formation/depth matched historical event; not a causal attribution',dataset_origin=e.dataset_origin))
        key=(active.id,h.type,int((active.current_md or 0)//100))
        state=session.get(AlertState,key)
        if state is None:
            state=AlertState(well_id=key[0],hazard=key[1],interval=key[2],consecutive=0,active=False)
            session.add(state)
        if alert_transition(state,h,result.as_of):
            advisory=DrillingAdvisory(id=digest([*key,result.as_of]),assessment_id=h.assessment_id,
                text=f'Historical {h.type} evidence in {", ".join(h.supporting_offset_wells)} overlaps the assessed interval. '
                     f'Review source events {", ".join(h.evidence_ids)} and current conditions with the drilling engineer. '
                     'This uncalibrated prototype assessment is advisory only; historical responses are not operating instructions.',
                dataset_origin=active.dataset_origin)
            session.add(advisory); created.append(advisory)
    audit(session,'risk_assessed',user,well_id=active.id,assessment_ids=[h.assessment_id for h in result.hazards])
    session.flush()
    return created


def depth_values(session, active, md):
    return dict(md=md,tvd=interpolate(session,active.id,md),tvdss=interpolate(session,active.id,md,'tvdss'))


def correlation_context(session, active, matches, formations, events, lookahead):
    """One explicit depth axis across tracks; missing markers stay null on that axis."""
    wells=[active]+[session.get(Well,m.offset_well_id) for m in matches]
    by_well={w.id:[f for f in formations if f.well_id==w.id] for w in wells}
    basis='md'
    for candidate in ('tvdss','tvd'):
        complete=lambda fs: bool(fs) and all(getattr(f,'top_'+candidate) is not None and getattr(f,'bottom_'+candidate) is not None for f in fs)
        if complete(by_well[active.id]) and any(complete(by_well[w.id]) for w in wells[1:]):
            basis=candidate
            break
    start=depth_values(session,active,active.current_md)
    end=depth_values(session,active,None if active.current_md is None else active.current_md+lookahead)
    tracks=[]
    for w in wells:
        intervals=[]
        for f in by_well[w.id]:
            top,base=getattr(f,'top_'+basis),getattr(f,'bottom_'+basis)
            intervals.append(dict(interval_id=f.id,formation=f.formation,top=top,base=base,
                confidence=f.confidence,source=f.source,alignment_available=top is not None and base is not None))
        tracks.append(dict(well=w,is_active=w.id==active.id,formations=intervals,
            events=[e for e in events if e.well_id==w.id],casing_points=(w.program or {}).get('casing_points')))
    return dict(alignment_basis=basis,current_bit_depth=start,
        lookahead_window=dict(lookahead_m=lookahead,start=start,end=end),tracks=tracks)


def telemetry_channel_states(session, active, channels, start, end):
    """Summarize the entire bounded window, independent of sample pagination."""
    from app.db.models.nwis import TelemetrySample as T
    names=session.scalars(select(T.channel).where(T.well_id==active.id).distinct().order_by(T.channel).limit(21)).all() if not channels else channels
    if len(names)>20: raise HTTPException(422,'Select at most 20 telemetry channels')
    output=[]
    for channel in names:
        base=select(T).where(T.well_id==active.id,T.channel==channel)
        known=session.scalar(base.order_by(T.timestamp.desc()).limit(1))
        window=base.where(T.timestamp>=start,T.timestamp<=end)
        counts=session.execute(select(func.count(),func.count(T.value)).select_from(T).where(
            T.well_id==active.id,T.channel==channel,T.timestamp>=start,T.timestamp<=end)).one()
        latest=session.scalar(window.order_by(T.timestamp.desc()).limit(1))
        valid=session.scalar(window.where(T.value.is_not(None),T.quality=='good').order_by(T.timestamp.desc()).limit(1))
        if valid is not None and not math.isfinite(valid.value): valid=None
        stamp=utc(valid.timestamp) if valid else None
        output.append(dict(channel=channel,known=known is not None,unit=known.unit if known else None,
            sample_count=counts[0],value_count=counts[1],latest_timestamp=latest.timestamp if latest else None,
            latest_valid_timestamp=stamp,state='unavailable' if stamp is None else ('fresh' if end-stamp<=timedelta(minutes=5) else 'stale')))
    return output
