"""Deterministic isolated NWIS seed: python -m scripts.seed_nwis [--generate] [--index]."""
import argparse
import json
import math
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from sqlalchemy import select, text
from app.db.models.nwis import Well, WellTrajectoryPoint, FormationInterval, DrillingReport, DrillingEvent, TelemetrySample, HAZARDS
from app.services.nwis import audit, digest
from app.services.nwis_knowledge import extract_event, PARSER

ROOT=Path(__file__).resolve().parents[2]/'data'/'nwis_demo'
ORIGIN='synthetic_demo'
AT=datetime(2026,9,29,16,tzinfo=timezone.utc)

def generate():
    data=dict(dataset_origin=ORIGIN,version='nwis-demo-v1',wells=[],trajectories=[],formations=[],reports=[],telemetry=[])
    for i in range(12):
        ident='ACTIVE-01' if i==0 else f'OFF-{i:02}'
        shift=0 if i in (0,4,9) else (i-5)*15
        ratio=1 if i in (0,1,4,9) else .92
        data['wells'].append(dict(id=ident,name=ident,field='SYNTHETIC-ASSAM-DEMO',latitude=27.4+(0.001 if i==1 else i*.003),
            longitude=95.3+(0.001 if i==1 else i*.002),operator='Synthetic demo operator',status='ACTIVE' if i==0 else 'historical',
            total_depth_md=3200,current_md=2450 if i==0 else None,as_of=AT.isoformat(),spud_date='2025-01-01',
            program=dict(mud_system='synthetic_water_based',hole_size_in=8.5,casing_size_in=7),access_scope='public',dataset_origin=ORIGIN))
        for md in range(0,3300,100):
            data['trajectories'].append(dict(well_id=ident,md=md,tvd=md*ratio,tvdss=None,inclination=0 if ratio==1 else 23,
                azimuth=0 if ratio==1 else 45,northing=None,easting=None,source='synthetic survey',quality=.95,dataset_origin=ORIGIN))
        for j,(formation,top,bottom) in enumerate([('DHEKIA_SYN',0,1500),('BARAIL_SYN',1500,2300),('TIPAM_A',2300,2800),('TIPAM_B',2800,3200)]):
            # Close OFF-01 has no TIPAM_A at the active interval.
            name='TIPAM_B' if i==1 and formation=='TIPAM_A' else formation
            data['formations'].append(dict(id=f'{ident}-F{j}',well_id=ident,formation=name,top_md=max(0,top+shift)/ratio,
                bottom_md=(bottom+shift)/ratio,top_tvd=max(0,top+shift),bottom_tvd=bottom+shift,top_tvdss=None,bottom_tvdss=None,
                confidence=.95,source='synthetic formation table',dataset_origin=ORIGIN))
        if i:
            passages=[]
            for j in range(6):
                hazard=HAZARDS[(i+j)%len(HAZARDS)]
                tvd=2410+j*24
                if i in (4,9) and j in (1,2): hazard='stuck_pipe'; tvd=2470+(j-1)*40
                md=tvd/ratio
                form='TIPAM_B' if i==1 else 'TIPAM_A'
                phrase=(f'Well: {ident}; Event: {hazard}; Formation: {form}; MD: {md:.2f}-{md+5:.2f} m; TVD: {tvd:.2f} m; '
                    f'Severity: warning; Observation: Historical synthetic {hazard} reported; '
                    'Mitigation: Engineering review and documented site procedure used; Outcome: Synthetic incident resolved; NPT: 2 h')
                passages.append(dict(page=j+1,text=phrase,dataset_origin=ORIGIN))
            data['reports'].append(dict(id=f'{ident}-DDR',well_id=ident,type='DDR' if i%2 else 'WCR',report_date='2025-02-01',
                passages=passages,dataset_origin=ORIGIN))
    units=dict(MD='m',bit_depth='m',ROP='m/h',WOB='kN',RPM='rpm',torque='kN.m',hookload='kN',standpipe_pressure='kPa',flow='L/min',mud_weight='g/cm3')
    for t in range(61):
        md=2444+t*.1
        values=dict(MD=md,bit_depth=md,ROP=6+math.sin(t),WOB=90+math.sin(t),RPM=110+math.cos(t),
            torque=12+math.sin(t)*.4+max(0,t-50)*.7,hookload=900+math.sin(t)*3,
            standpipe_pressure=18000+math.sin(t)*100,flow=1200+math.cos(t)*10,mud_weight=1.2)
        for channel,value in values.items():
            data['telemetry'].append(dict(well_id='ACTIVE-01',timestamp=(AT-timedelta(minutes=60-t)).isoformat(),
                md=md,tvd=md,channel=channel,value=round(value,4),unit=units[channel],quality='good',dataset_origin=ORIGIN))
    return data

def report_pdf(report):
    """Same ground truth and page numbers as events; fixed PDF metadata and IDs."""
    import pymupdf
    with pymupdf.open() as doc:
        for passage in report['passages']:
            page=doc.new_page()
            page.insert_text((40,40), f"SYNTHETIC DEMO - {report['type']} - {report['well_id']}", fontsize=14)
            page.insert_text((40,65), f"Date: {report['report_date']}; dataset_origin: synthetic_demo", fontsize=10)
            remaining=page.insert_textbox((40,100,550,720),passage['text'],fontsize=11)
            if remaining<0: raise ValueError('Synthetic report text exceeds page')
        doc.set_metadata({'title':report['id'],'author':'NWIS synthetic generator','creationDate':'D:20260929160000Z'})
        return doc.tobytes(no_new_id=True,deflate=True)


def seed(session,data=None):
    data=data or generate()
    if data['dataset_origin']!=ORIGIN: raise ValueError('Only synthetic demo seed is supported')
    if session.bind.dialect.name=='postgresql': session.execute(text('SELECT pg_advisory_xact_lock(2612101)'))
    for model,key,pk in ((Well,'wells',lambda r:r['id']),(WellTrajectoryPoint,'trajectories',lambda r:(r['well_id'],r['md'])),
                         (FormationInterval,'formations',lambda r:r['id'])):
        for raw in data[key]:
            row=dict(raw)
            if row.get('as_of'): row['as_of']=datetime.fromisoformat(row['as_of'])
            if row.get('spud_date'): row['spud_date']=date.fromisoformat(row['spud_date'])
            existing=session.get(model,pk(row))
            if existing and existing.dataset_origin!=ORIGIN: raise ValueError('Seed identity collides with non-demo data')
            if existing is None: session.add(model(**row))
        session.flush()
    for raw in data['reports']:
        report=session.get(DrillingReport,raw['id'])
        from app.services.extraction import source_sha256
        from app.core.config import settings
        source=report_pdf(raw)
        checksum=source_sha256(source)
        if report and (report.dataset_origin!=ORIGIN or report.file_hash not in (checksum,digest(raw['passages']))):
            raise ValueError('Seed report collision')
        if report: report.file_hash=checksum
        folder=settings.data_root/'nwis'/'reports'
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/(checksum+'.pdf')
        if not path.exists(): path.write_bytes(source)
        elif source_sha256(path.read_bytes())!=checksum: raise ValueError('Stored synthetic report hash mismatch')
        if report is None:
            report=DrillingReport(id=raw['id'],well_id=raw['well_id'],type=raw['type'],report_date=date.fromisoformat(raw['report_date']),
                file_hash=checksum,extraction_status='extracted',parser_version=PARSER,dataset_origin=ORIGIN)
            session.add(report); session.flush()
        for passage in raw['passages']:
            event=extract_event(passage['text'],well_id=raw['well_id'],report_id=raw['id'],page=passage['page'],origin=ORIGIN)
            if event is None: raise ValueError('Synthetic source did not extract')
            if session.get(DrillingEvent,event.id) is None: session.add(event)
    session.flush()
    for raw in data['telemetry']:
        row=dict(raw); row['timestamp']=datetime.fromisoformat(row['timestamp'])
        if session.get(TelemetrySample,(row['well_id'],row['timestamp'],row['channel'])) is None: session.add(TelemetrySample(**row))
    session.flush()
    audit(session,'synthetic_seed',dataset_origin=ORIGIN,version=data['version'])

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--generate',action='store_true'); parser.add_argument('--index',action='store_true')
    args=parser.parse_args()
    if args.generate:
        ROOT.mkdir(parents=True,exist_ok=True)
        data=generate()
        (ROOT/'dataset.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
        (ROOT/'reports').mkdir(exist_ok=True)
        for report in data['reports']:
            (ROOT/'reports'/(report['id']+'.pdf')).write_bytes(report_pdf(report))
        return
    from app.db.session import SessionLocal
    with SessionLocal() as session:
        seed(session); session.commit()
        if args.index:
            from app.services.nwis_knowledge import index_events
            print('Indexed',index_events(session),'NWIS source events')
    print('Seeded synthetic NWIS demo')

if __name__=='__main__': main()
