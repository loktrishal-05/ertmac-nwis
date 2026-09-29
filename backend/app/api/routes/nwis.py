"""Authenticated SIH26121 API, isolated from legacy product semantics."""
from datetime import datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import AuditEvent, User
from app.db.models.nwis import Well, FormationInterval, DrillingEvent, DrillingAdvisory, RiskAssessment, TermsAcceptance, DrillingReport, RiskEvidence
from app.schemas.nwis import (Page, WellOut, EventOut, MatchOut, CorrelationOut, FormationOut, RiskOut, TelemetryOut,
    QueryIn, QueryOut, ReviewIn, AdvisoryOut, TermsIn, TermsOut, AssessmentOut, IngestOut, Schema, Hazard, TelemetryPage, AssessmentDetail, HazardOut)
from app.schemas.audit import AuditEventResponse
from app.services import nwis as service
from app.services import nwis_knowledge

router=APIRouter(prefix='/api',tags=['NWIS'])
TERMS='nwis-advisory-v1'

def access(user: User=Depends(get_current_user),session: Session=Depends(get_db)):
    if user.role not in ('requester','reviewer','admin'): raise HTTPException(403,'Role not permitted')
    if session.get(TermsAcceptance,(user.id,TERMS)) is None: raise HTTPException(403,'Accept NWIS advisory terms first')
    return user

def reviewer(user=Depends(access)):
    if user.role not in ('reviewer','admin'): raise HTTPException(403,'Reviewer role required')
    return user

def admin(user=Depends(access)):
    if user.role!='admin': raise HTTPException(403,'Administrator role required')
    return user

def page(rows,limit,offset):
    return dict(items=rows[:limit],limit=limit,offset=offset,has_more=len(rows)>limit,as_of=service.now())

@router.get('/terms',response_model=TermsOut)
def terms(user=Depends(get_current_user),session: Session=Depends(get_db)):
    return TermsOut(accepted=session.get(TermsAcceptance,(user.id,TERMS)) is not None)

@router.post('/terms/accept',response_model=TermsOut)
def accept_terms(body: TermsIn,user=Depends(get_current_user),session: Session=Depends(get_db)):
    session.execute(select(User).where(User.id==user.id).with_for_update()).scalar_one()
    if session.get(TermsAcceptance,(user.id,TERMS)) is None:
        session.add(TermsAcceptance(user_id=user.id,version=TERMS,accepted_at=service.now()))
        service.audit(session,'terms_accepted',user,version=TERMS); session.commit()
    return TermsOut(accepted=True)

@router.get('/wells',response_model=Page[WellOut])
def wells(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),user=Depends(access),session:Session=Depends(get_db)):
    return page(session.scalars(select(Well).where(Well.access_scope.in_(service.visible(user)))
        .order_by(Well.id).offset(offset).limit(limit+1)).all(),limit,offset)

@router.get('/wells/{well_id}',response_model=WellOut)
def get_well(well_id:str,user=Depends(access),session:Session=Depends(get_db)):
    return service.well(session,well_id,user)

@router.get('/wells/{well_id}/nearby',response_model=Page[MatchOut])
def nearby(well_id:str,radius_km:float=Query(10,gt=0,le=100),limit:int=Query(50,ge=1,le=100),
           offset:int=Query(0,ge=0,le=10000),user=Depends(access),session:Session=Depends(get_db)):
    active=service.well(session,well_id,user)
    ranked=service.offsets(session,active,user,radius_km)
    return page(ranked[offset:offset+limit+1],limit,offset)

@router.get('/wells/{well_id}/formations',response_model=Page[FormationOut])
def formations(well_id:str,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),
               user=Depends(access),session:Session=Depends(get_db)):
    service.well(session,well_id,user)
    rows=session.scalars(select(FormationInterval).where(FormationInterval.well_id==well_id)
        .order_by(FormationInterval.top_md,FormationInterval.id).offset(offset).limit(limit+1)).all()
    return page(rows,limit,offset)

@router.get('/reports/{report_id}/source')
def report_source(report_id:str,user=Depends(access),session:Session=Depends(get_db)):
    from app.core.config import settings
    from app.services.extraction import source_sha256
    report=session.get(DrillingReport,report_id)
    if report is None: raise HTTPException(404,'Report unavailable')
    service.well(session,report.well_id,user)
    if len(report.file_hash)!=64 or any(c not in '0123456789abcdef' for c in report.file_hash):
        raise HTTPException(409,'Source integrity mismatch')
    path=settings.data_root/'nwis'/'reports'/(report.file_hash+'.pdf')
    if not path.is_file(): raise HTTPException(404,'Source unavailable; seed or ingest the report')
    source=path.read_bytes()
    if source_sha256(source)!=report.file_hash: raise HTTPException(409,'Source integrity mismatch')
    return Response(source,media_type='application/pdf',headers={'Content-Disposition':'inline; filename="report.pdf"',
        'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})

@router.get('/events',response_model=Page[EventOut])
def events(well_id:str|None=None,formation:str|None=Query(None,max_length=100),type:Hazard|None=None,
    depth_min:float|None=Query(None,ge=-15000,le=15000),depth_max:float|None=Query(None,ge=-15000,le=15000),
    depth_basis:Literal['md','tvd','tvdss']='md',limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),
    user=Depends(access),session:Session=Depends(get_db)):
    q=service.event_query(user,well_id,formation,type,depth_min,depth_max,depth_basis)
    return page(session.scalars(q.offset(offset).limit(limit+1)).all(),limit,offset)

@router.get('/wells/{well_id}/correlation',response_model=CorrelationOut)
def correlation(well_id:str,radius_km:float=Query(10,gt=0,le=100),lookahead_m:int=Query(100,ge=50,le=150,multiple_of=50),user=Depends(access),session:Session=Depends(get_db)):
    active=service.well(session,well_id,user); matches=service.offsets(session,active,user,radius_km,lookahead_m)[:10]
    ids=[m.offset_well_id for m in matches]
    formations=session.scalars(select(FormationInterval).where(FormationInterval.well_id.in_([well_id,*ids]))
        .order_by(FormationInterval.well_id,FormationInterval.top_md,FormationInterval.id).limit(201)).all()
    if len(formations)>200: raise HTTPException(422,'Correlation exceeds 200 formation intervals')
    ev=session.scalars(service.event_query(user).where(DrillingEvent.well_id.in_([well_id,*ids])).limit(501)).all()
    if len(ev)>500: raise HTTPException(422,'Correlation exceeds 500 events; reduce radius')
    return CorrelationOut(well_id=well_id,as_of=active.as_of or service.now(),dataset_origin=active.dataset_origin,
        formations=[FormationOut.model_validate(f) for f in formations if f.well_id==well_id],
        offset_formations=[FormationOut.model_validate(f) for f in formations if f.well_id!=well_id],
        events=[EventOut.model_validate(e) for e in ev],offsets=matches,
        **service.correlation_context(session,active,matches,formations,ev,lookahead_m))

@router.get('/wells/{well_id}/risk',response_model=RiskOut)
def risk(well_id:str,lookahead_m:int=Query(100,ge=50,le=150,multiple_of=50),radius_km:float=Query(10,gt=0,le=100),
         user=Depends(access),session:Session=Depends(get_db)):
    return service.risk(session,service.well(session,well_id,user),user,lookahead_m,radius_km)[0]

@router.post('/wells/{well_id}/assess',response_model=AssessmentOut)
def assess(well_id:str,lookahead_m:int=Query(100,ge=50,le=150,multiple_of=50),radius_km:float=Query(10,gt=0,le=100),
           user=Depends(access),session:Session=Depends(get_db)):
    active=service.well(session,well_id,user)
    session.execute(select(Well).where(Well.id==well_id).with_for_update()).scalar_one()
    result,matches=service.risk(session,active,user,lookahead_m,radius_km)
    advisories=service.persist_assessment(session,active,result,matches,user); session.commit()
    return AssessmentOut(risk=result,advisories=[AdvisoryOut.model_validate(a) for a in advisories])

@router.get('/wells/{well_id}/telemetry',response_model=TelemetryPage)
def telemetry(well_id:str,channels:str|None=Query(None,max_length=300),start:datetime|None=Query(None,alias='from'),
    end:datetime|None=Query(None,alias='to'),limit:int=Query(500,ge=1,le=1000),offset:int=Query(0,ge=0,le=10000),
    user=Depends(access),session:Session=Depends(get_db)):
    selected=list(dict.fromkeys(c.strip() for c in channels.split(','))) if channels is not None else None
    if selected and (len(selected)>20 or any(not c or len(c)>50 for c in selected)): raise HTTPException(422,'Select 1 to 20 nonempty channel names of at most 50 characters')
    active=service.well(session,well_id,user)
    end=service.utc(end or active.as_of or service.now())
    start=service.utc(start or end-timedelta(hours=1))
    rows=service.telemetry(session,active,selected,start,end,limit+1,offset)
    return page(rows,limit,offset) | dict(as_of=end,dataset_origin=active.dataset_origin,
        source_mode='replay' if active.dataset_origin=='synthetic_demo' else 'historical',
        window_start=start,window_end=end,freshness_reference=end,
        channels=service.telemetry_channel_states(session,active,selected,start,end))

class ReplayIn(Schema):
    as_of: datetime

@router.post('/wells/{well_id}/replay',response_model=WellOut)
def replay(well_id:str,body:ReplayIn,user=Depends(reviewer),session:Session=Depends(get_db)):
    from app.services.nwis_telemetry import LocalReplay
    active=service.well(session,well_id,user)
    session.execute(select(Well).where(Well.id==well_id).with_for_update()).scalar_one()
    try: LocalReplay(session).seek(active,body.as_of,user)
    except ValueError as e: raise HTTPException(422,str(e)) from e
    session.commit(); return active

@router.post('/query',response_model=QueryOut)
def query(body:QueryIn,user=Depends(access),session:Session=Depends(get_db)):
    from app.agents.nwis import run
    try: return run(session,body,user)
    except HTTPException: raise
    except ValueError as e: raise HTTPException(422,'Query evidence or filters are invalid; inspect source data') from e
    except Exception as e: raise HTTPException(503,'NWIS retrieval unavailable; retry this request ID after checking local dependencies') from e

@router.get('/assessments/{ident}',response_model=AssessmentDetail)
def assessment_detail(ident:str,user=Depends(access),session:Session=Depends(get_db)):
    assessment=session.get(RiskAssessment,ident)
    if assessment is None: raise HTTPException(404,'Assessment unavailable')
    service.well(session,assessment.well_id,user)
    links=session.scalars(select(RiskEvidence).where(RiskEvidence.assessment_id==ident)
        .order_by(RiskEvidence.drilling_event_id)).all()
    evidence=[]
    for link in links:
        event=session.get(DrillingEvent,link.drilling_event_id)
        service.well(session,event.well_id,user)
        report=session.get(DrillingReport,event.source_report_id)
        service.well(session,report.well_id,user)
        evidence.append(dict(event=event,event_at_assessment=assessment.snapshot.get('event_snapshots',{}).get(event.id),
            evidence_chunk_id=link.evidence_chunk_id,contribution=link.contribution,reason=link.reason,
            source_sha256=report.file_hash,source_sha256_at_assessment=assessment.snapshot.get('source_hashes',{}).get(event.id),
            source_url=f'/api/reports/{report.id}/source#page={event.source_page}'))
    return dict(assessment_id=ident,well_id=assessment.well_id,as_of=assessment.as_of,current_md_m=assessment.current_md,
        formation=assessment.formation,lookahead_m=assessment.lookahead_m,model_version=assessment.model_version,
        dataset_origin=assessment.dataset_origin,hazard={k:assessment.snapshot[k] for k in HazardOut.model_fields},evidence=evidence)

@router.get('/advisories',response_model=Page[AdvisoryOut])
def advisories(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),
               user=Depends(access),session:Session=Depends(get_db)):
    rows=session.scalars(select(DrillingAdvisory).join(RiskAssessment).join(Well)
        .where(Well.access_scope.in_(service.visible(user))).order_by(DrillingAdvisory.created_at.desc(),DrillingAdvisory.id)
        .offset(offset).limit(limit+1)).all()
    return page(rows,limit,offset)

@router.post('/advisories/{ident}/review',response_model=AdvisoryOut)
def review(ident:str,body:ReviewIn,user=Depends(reviewer),session:Session=Depends(get_db)):
    row=session.scalar(select(DrillingAdvisory).where(DrillingAdvisory.id==ident).with_for_update())
    if row is None: raise HTTPException(404,'Advisory unavailable')
    assessment=session.get(RiskAssessment,row.assessment_id); service.well(session,assessment.well_id,user)
    if row.status!='pending_review': raise HTTPException(409,'Advisory already reviewed')
    row.status=body.status; row.feedback=body.reason; row.reviewer=user.id; row.reviewed_at=service.now()
    service.audit(session,'advisory_review',user,advisory_id=row.id,assessment_id=row.assessment_id,status=body.status,reason=body.reason,
                  evidence_ids=assessment.snapshot['evidence_ids'])
    session.commit(); return row

@router.get('/audit',response_model=Page[AuditEventResponse])
def audit(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),
          user=Depends(reviewer),session:Session=Depends(get_db)):
    q=select(AuditEvent).where(AuditEvent.payload['product'].as_string()=='SIH26121')
    if user.role!='admin': q=q.where(AuditEvent.actor_id==user.id)
    rows=session.scalars(q
        .order_by(AuditEvent.sequence_number.desc()).offset(offset).limit(limit+1)).all()
    return page([AuditEventResponse.model_validate(e) for e in rows],limit,offset)

class ValidationIn(Schema):
    status: Literal['validated','rejected']
    reason: str = Field(min_length=5,max_length=1000)

@router.post('/events/{ident}/validate',response_model=EventOut)
def validate_event(ident:str,body:ValidationIn,user=Depends(reviewer),session:Session=Depends(get_db)):
    e=session.scalar(select(DrillingEvent).where(DrillingEvent.id==ident).with_for_update())
    if e is None: raise HTTPException(404,'Event unavailable')
    service.well(session,e.well_id,user)
    if body.status=='validated' and (e.start_depth_md is None or e.confidence<.5):
        raise HTTPException(409,'Uncertain numbers require corrected source ingestion before validation')
    e.verification_state=body.status
    service.audit(session,'drilling_lesson_validation',user,event_id=e.id,status=body.status,reason=body.reason,
                  source_report_id=e.source_report_id,source_page=e.source_page,source_hash=service.digest(e.raw_phrase))
    session.commit(); return e

@router.post('/ingest/report',response_model=IngestOut)
async def ingest(request:Request,well_id:str,type:Literal['WCR','DDR','incident','program'],
                 dataset_origin:str=Query(min_length=1,max_length=100),
                 user=Depends(admin),session:Session=Depends(get_db)):
    active=service.well(session,well_id,user)
    if request.headers.get('content-type','').split(';')[0]!='application/pdf': raise HTTPException(415,'application/pdf required')
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>20*1024*1024: raise HTTPException(413,'Report exceeds 20 MiB')
    try:
        result=nwis_knowledge.ingest_pdf(session,active,bytes(data),type,user,dataset_origin=dataset_origin); session.commit()
        return result
    except ValueError as e: raise HTTPException(422,'PDF extraction failed validation') from e
