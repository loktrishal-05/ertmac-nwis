"""Constrained report extraction and evidence retrieval using existing local services."""
import re
from datetime import date
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import select
from qdrant_client import models
from app.db.models.nwis import DrillingEvent, DrillingReport
from app.schemas.nwis import EventOut
from app.services import nwis
from app.services.extraction import extract_pdf, source_sha256
from app.services.qdrant_service import QdrantService
from app.services.embeddings import get_embeddings
from app.services.reranking import get_reranker
from app.services.ranking import fuse
from app.services.sparse import encode
from app.core.config import settings

PARSER='nwis-rules-v1'
COLLECTION='nwis_evidence_v1'
SYNONYMS={
    'mud_loss':r'\b(mud.loss|lost circulation|losses)\b',
    'stuck_pipe':r'\b(stuck.pipe|pack.off)\b',
    'kick_or_overpressure':r'\b(kick|influx|overpressure)\b',
    'torque_drag':r'\b(torque.drag|torque spike|overpull)\b',
    'cementing_issue':r'\b(cementing.issue|poor cement returns)\b',
    'fishing':r'\bfishing\b', 'npt':r'\b(npt|non.productive)\b'}
INJECTION=re.compile(r'ignore.{0,50}(instructions|rules)|system\s*prompt|chain.of.thought|\b(actuator|BOP command|rig control)\b|\b(?:increase|decrease|set|change|adjust|activate|operate|close|open)\b.{0,40}\b(?:WOB|RPM|BOP|mud weight|mud program|rig equipment)\b',re.I|re.S)

def field(text,name):
    match=re.search(r'(?:^|[;\n])\s*'+re.escape(name)+r'\s*:\s*([^;\n]+)',text,re.I)
    return match.group(1).strip() if match else None

def extract_event(text, *, well_id, report_id, page, origin, span=None):
    explicit=field(text,'Event')
    labels=[explicit] if explicit in SYNONYMS else [k for k,p in SYNONYMS.items() if re.search(p, explicit or text,re.I)]
    labels=list(dict.fromkeys(labels))
    if len(labels)!=1: return None
    depth={}
    uncertain=bool(INJECTION.search(text))
    for basis in ('MD','TVD','TVDSS'):
        raw=field(text,basis)
        match=re.fullmatch(r'(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?\s*(m|ft)',raw or '',re.I)
        if raw and not match: uncertain=True
        if match:
            factor=.3048 if match[3].lower()=='ft' else 1
            a,b=float(match[1])*factor,float(match[2] or match[1])*factor
            if a>b or b>15000: uncertain=True
            else: depth[basis]=(a,b)
    if 'MD' not in depth: uncertain=True
    if field(text,'Well') not in (None,well_id): uncertain=True
    npt=field(text,'NPT')
    npt_match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*h',npt or '')
    if npt and not npt_match: uncertain=True
    md=depth.get('MD',(None,None))
    return DrillingEvent(id='EVT-'+nwis.digest([report_id,page,text])[:32],well_id=well_id,event_type=labels[0],
        start_depth_md=md[0],end_depth_md=md[1],tvd=depth.get('TVD',(None,None))[0],tvdss=depth.get('TVDSS',(None,None))[0],
        formation=field(text,'Formation'),severity=field(text,'Severity') or 'unavailable',observation=field(text,'Observation') or text,
        cause=field(text,'Cause'),mitigation=field(text,'Mitigation'),outcome=field(text,'Outcome'),
        npt_hours=float(npt_match[1]) if npt_match else None,confidence=.35 if uncertain else .9,
        source_report_id=report_id,source_page=page,source_span=span,raw_phrase=text,
        verification_state='review_needed' if uncertain else 'unverified',dataset_origin=origin)

def ingest_pdf(session, active, source, report_type, actor, *, dataset_origin):
    if dataset_origin!=active.dataset_origin:
        raise ValueError('Source origin must match the registered well dataset; never infer provenance from file contents')
    if not source.startswith(b'%PDF-') or not 0<len(source)<=20*1024*1024:
        raise ValueError('A PDF of at most 20 MiB is required')
    checksum=source_sha256(source)
    ident='REPORT-'+nwis.digest([active.id,checksum])[:32]
    existing=session.get(DrillingReport,ident)
    if existing and existing.extraction_status!='ocr_required':
        return dict(report_id=ident,status=existing.extraction_status,events=session.scalars(select(DrillingEvent)
            .where(DrillingEvent.source_report_id==ident).order_by(DrillingEvent.id)).all(),warnings=[],dataset_origin=active.dataset_origin)
    extraction=extract_pdf(source)
    folder=settings.data_root/'nwis'/'reports'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(checksum+'.pdf')
    if path.exists():
        if source_sha256(path.read_bytes())!=checksum: raise ValueError('Stored source hash mismatch')
    else:
        with path.open('xb') as stream: stream.write(source)
    report=existing or DrillingReport(id=ident,well_id=active.id,type=report_type,file_hash=checksum,
        extraction_status=extraction.status,parser_version=PARSER,dataset_origin=active.dataset_origin)
    if not existing: session.add(report)
    session.flush()
    ocr=False
    if extraction.status=='ocr_required':
        try:
            from app.services.pid_images import render_pages
            from app.services.paddle_ocr import get_paddle_ocr
            from app.schemas.pid import PreprocessOptions
            from app.services.extraction import Block
            pages=render_pages(source,'.pdf',uuid5(NAMESPACE_URL,ident),300,PreprocessOptions())
            blocks=[]
            for detections in get_paddle_ocr().recognize_pages(pages):
                if detections:
                    blocks.append(Block(' '.join(d.text for d in detections),[],detections[0].page,detections[0].page,
                        [{'page':d.page,'coordinates':list(d.bbox),'origin':'TOPLEFT','ocr_confidence':d.confidence} for d in detections]))
            extraction.blocks=blocks; extraction.status='extracted'; ocr=True
            extraction.report['warnings'].append('OCR numeric fields require human source verification.')
        except (RuntimeError,ValueError,ImportError,OSError):
            extraction.report['warnings'].append('Local OCR unavailable or report exceeds bounded OCR limits; report awaits review.')
    events=[]
    for block in extraction.blocks:
        e=extract_event(block.text,well_id=active.id,report_id=ident,page=block.page_start,origin=active.dataset_origin,
            span={'bounding_boxes':block.bounding_boxes})
        if e:
            if ocr: e.verification_state='review_needed'; e.confidence=min(e.confidence,.49)
            session.add(e); events.append(e)
    dates=set(re.findall(r'(?:Date|Report date):\s*(\d{4}-\d{2}-\d{2})','\n'.join(b.text for b in extraction.blocks),re.I))
    if len(dates)==1:
        try: report.report_date=date.fromisoformat(next(iter(dates)))
        except ValueError: extraction.report['warnings'].append('Invalid report date requires review.')
    if extraction.status=='extracted':
        report.extraction_status='review_needed' if not events or any(e.verification_state=='review_needed' for e in events) else 'extracted'
    nwis.audit(session,'report_ingested',actor,report_id=ident,file_hash=checksum,status=report.extraction_status)
    session.flush()
    return dict(report_id=ident,status=report.extraction_status,events=events,
        warnings=extraction.report.get('warnings',[]),dataset_origin=active.dataset_origin)

def query_filters(request):
    """Only explicit supported depth/formation phrases constrain retrieval."""
    kind=request.type
    if kind is None:
        labels=[k for k,p in SYNONYMS.items() if re.search(p,request.query,re.I)]
        if len(labels)==1: kind=labels[0]
    form=request.formation
    m=re.search(r'\b(TIPAM_A|TIPAM_B|BARAIL_SYN|DHEKIA_SYN)\b',request.query,re.I)
    if form is None and m: form=m[1].upper()
    if form is None and re.search(r'\bTipam\b',request.query,re.I): form='TIPAM_A'
    lo,hi,basis=request.depth_min,request.depth_max,request.depth_basis
    m=re.search(r'\b(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*m\s*(TVDSS|TVD|MD)\b',request.query,re.I)
    if m and lo is None and hi is None: lo,hi,basis=float(m[1]),float(m[2]),m[3].lower()
    return form,kind,lo,hi,basis

def evidence_search(session, request, user, ranked):
    form,kind,lo,hi,basis=query_filters(request)
    ids=[m.offset_well_id for m in ranked]
    if not ids: return [],[]
    q=nwis.event_query(user,formation=form,kind=kind,depth_min=lo,depth_max=hi,basis=basis)
    rows=session.scalars(q.where(DrillingEvent.well_id.in_(ids),DrillingEvent.verification_state!='rejected').limit(501)).all()
    if len(rows)>500: raise ValueError('Evidence set exceeds 500 events; narrow filters')
    warnings=[]
    if any(e.verification_state=='review_needed' for e in rows): warnings.append('Uncertain extraction requires review; it cannot support risk.')
    if request.retrieval=='hybrid':
        # IDs are selected from authorized relational facts before dense/sparse ranking.
        rows=hybrid(rows,request.query,request.top_k)
    else:
        terms=set(re.findall(r'\w+',request.query.lower()))-{'show','what','the','in','and','m','near','this','well'}
        rows=sorted(rows,key=lambda e:(-len(terms & set(re.findall(r'\w+',e.raw_phrase.lower()))),e.id))
        rows=[e for e in rows if kind or form or terms & set(re.findall(r'\w+',e.raw_phrase.lower()))]
    groups={}
    for e in rows:
        key=(e.well_id,e.event_type,e.start_depth_md)
        groups.setdefault(key,set()).add((e.outcome,e.mitigation))
    if any(len(g)>1 for g in groups.values()): warnings.append('Conflicting historical accounts retained; engineering review required.')
    return rows[:request.top_k],warnings

def vector_store(client=None):
    service=QdrantService(client)
    service.collection=COLLECTION
    return service

def index_events(session, client=None, embeddings=None):
    service=vector_store(client)
    service.initialize(require_sparse=True)
    for name in ('well_id','report_id','event_id','event_type','formation','dataset_origin','verification_state'):
        service.client.create_payload_index(COLLECTION,name,models.PayloadSchemaType.KEYWORD,wait=True)
    count=0; last=''
    while True:
        batch=session.scalars(select(DrillingEvent).where(DrillingEvent.id>last).order_by(DrillingEvent.id).limit(16)).all()
        if not batch: break
        previous={str(p.id):p for p in service.client.retrieve(COLLECTION,
            ids=[str(uuid5(NAMESPACE_URL,e.id)) for e in batch],with_payload=True,with_vectors=True)}
        vectors=[]; missing=[]
        for i,e in enumerate(batch):
            old=previous.get(str(uuid5(NAMESPACE_URL,e.id)))
            cached=old.vector.get('dense') if old and isinstance(old.vector,dict) and old.payload.get('content_sha256')==nwis.digest(e.raw_phrase) else None
            vectors.append(cached)
            if cached is None: missing.append(i)
        fresh=(embeddings or get_embeddings()).embed([batch[i].raw_phrase for i in missing]) if missing else []
        if len(fresh)!=len(missing): raise ValueError('Embedding count mismatch')
        for i,vector in zip(missing,fresh): vectors[i]=vector
        points=[]
        for e,vector in zip(batch,vectors):
            report=session.get(DrillingReport,e.source_report_id)
            payload=dict(event_id=e.id,well_id=e.well_id,report_id=e.source_report_id,page=e.source_page,
                event_type=e.event_type,formation=e.formation,depth_min=e.start_depth_md,depth_max=e.end_depth_md,
                tvd=e.tvd,tvdss=e.tvdss,date=str(report.report_date) if report.report_date else None,
                verification_state=e.verification_state,dataset_origin=e.dataset_origin,content=e.raw_phrase,
                source_sha256=report.file_hash,content_sha256=nwis.digest(e.raw_phrase),
                event_snapshot_sha256=nwis.digest(EventOut.model_validate(e).model_dump(mode='json')))
            points.append(models.PointStruct(id=str(uuid5(NAMESPACE_URL,e.id)),vector={'dense':vector,'sparse':encode(e.raw_phrase)},payload=payload))
        service.client.upsert(COLLECTION,points=points,wait=True); count+=len(points)
        last=batch[-1].id
    return count

def hybrid(events,query,limit,client=None,embeddings=None,reranker=None):
    if not events: return []
    service=vector_store(client)
    service.initialize(require_sparse=True,read_only=True)
    filt={'event_id':[e.id for e in events]}
    dense=service.search((embeddings or get_embeddings()).embed([query],query=True)[0],30,filt)
    sparse=service.search(encode(query,query=True),30,filt,using='sparse')
    candidates=fuse(dense,sparse)[:20]
    by_id={e.id:e for e in events}
    valid=[]
    for c in candidates:
        p=c['point']; e=by_id.get(p.payload.get('event_id'))
        if e is None or str(p.id)!=str(uuid5(NAMESPACE_URL,e.id)) or p.payload.get('event_snapshot_sha256')!=nwis.digest(EventOut.model_validate(e).model_dump(mode='json')):
            raise ValueError('Evidence index is stale or inconsistent; reindex before retrieval')
        valid.append(e)
    scores=(reranker or get_reranker()).score(query,[e.raw_phrase for e in valid])
    if len(scores)!=len(valid): raise ValueError('Reranker count mismatch')
    return [e for e,s in sorted(zip(valid,scores),key=lambda x:(-x[1],x[0].id))][:limit]
