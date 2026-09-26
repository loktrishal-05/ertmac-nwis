"""Import the existing fictional P-204 scenario through ordinary ingestion.

Source facts: the synthetic corpus inventory (model-evaluation-spec section 2)
and Phase 3C smoke CSVs, NOT evaluation cases, expected answers or model output.
P-204 family records are explicitly instantiated as P-204A for this demo.
Fixed historical timestamps are never shifted to pretend they are live telemetry.
Run only against the local demonstration database. No direct evidence-table writes.
"""
import json
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.core.security import hash_password, verify_password
from app.db.models import User
from app.db.session import SessionLocal
from sqlalchemy import select

DEMO_USERS = [('phase9_requester', 'phase9-requester-local-only', 'requester'),
              ('phase9_reviewer', 'phase9-reviewer-local-only', 'reviewer')]

QUERY = ('Pump P-204A vibration is elevated. Review the available sensor data, '
         'maintenance history, SOP and P&ID evidence and advise what should be done.')

SOP = (
    'SYNTHETIC DEMONSTRATION ONLY - NOT A REAL PLANT OPERATING PROCEDURE.\n'
    'SOP-P204-001 section 4.2. Fictional pump P-204A vibration alert threshold 7.1 mm/s RMS. '
    'The high-high vibration threshold is 11.0 mm/s RMS. Notify the console and verify the sensor. '
    'Any controlled shutdown proposal requires supervisor approval.\n'
    'Section 5.1: isolation requires stop authorization, electrical isolation, suction/discharge '
    'isolation, drain/depressurize, LOTO and gas testing under the approved site procedure. '
    'Drawing labels cannot establish field isolation, valve state, permit status or readiness.\n'
    'Section 6.3: restart requires cause resolved, guards installed, lubrication confirmed, '
    'valves lined up, permits closed and supervisor authorization. '
    'This fictional source grants no authorization and the software cannot operate equipment.'
)
HISTORY = (
    'equipment_tag,work_order_id,maintenance_type,failure_mode,maintenance_date,description,downtime_hours,parts_replaced,technician_notes,status\n'
    'P-204A,WO-7712,corrective,bearing wear,2026-04-12,Drive-end bearing temperature investigated; lubrication corrected,4.5,drive-end bearing,No impeller damage confirmed; synthetic MH-P204 family fixture mapped to P-204A,closed\n'
    'P-204A,WO-7713,preventive,,2026-05-03,Coupling alignment check,1.0,,Synthetic MH-P204 routine inspection,closed\n'
    'P-204A,WO-7714,inspection,,2026-06-01,Suction strainer fouling noted,0.5,strainer,Synthetic MH-P204 recurring issue flagged for follow-up,open\n'
)
SENSORS = 'timestamp,equipment_tag,sensor_tag,measurement,value,unit,quality\n' + ''.join(
    f'2026-09-16T10:{minute:02}:00Z,P-204A,VIB-P204A-01,vibration,{value},mm/s,good\n'
    for minute, value in [(0, 3.1), (5, 3.3), (10, 3.4), (15, 3.5), (20, 8.2)]
)


def write_once(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = content.encode('utf-8')
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f'Immutable demo source differs: {path.name}; use a new revision, never overwrite it.')
    else:
        with path.open('xb') as stream:
            stream.write(raw)


def prepare_sources():
    raw = settings.data_root / 'raw'
    sop = raw / 'sops/source/SOP-P204-001-demo-v1.pdf'
    sop.parent.mkdir(parents=True, exist_ok=True)
    if not sop.exists():
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((40, 45), 'SOP-P204-001 - Synthetic P-204A reference', fontsize=16)
            if page.insert_textbox(pymupdf.Rect(40, 80, 550, 790), SOP, fontsize=12) < 0:
                raise ValueError('Synthetic SOP text does not fit')
            pdf.save(sop)
    write_once(raw / 'maintenance/work_orders/MH-P204-demo-v1.csv', HISTORY)
    write_once(raw / 'sensors/faults/SENSOR-P204-A-demo-v1.csv', SENSORS)
    drawing = raw / 'pids/source/PID-U2-017-R3-demo-v1.png'
    drawing.parent.mkdir(parents=True, exist_ok=True)
    if not drawing.exists():
        canvas = np.full((900, 1600, 3), 255, dtype=np.uint8)
        for index, label in enumerate(['PID-U2-017 R3 - SYNTHETIC LABEL EXCERPT', 'P-204A     P-204B',
                                       'XV-204S     XV-204D     NRV-204',
                                       'AS DRAWN LABELS ONLY - NO FIELD STATE',
                                       'NOT A CONNECTIVITY OR ISOLATION PLAN']):
            cv2.putText(canvas, label, (50, 100 + index * 160), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
        ok, encoded = cv2.imencode('.png', canvas)
        if not ok:
            raise ValueError('Could not render synthetic label excerpt')
        with drawing.open('xb') as stream:
            stream.write(encoded.tobytes())


def main():
    prepare_sources()
    results = {}
    with TestClient(app) as client:
        requests = [
            ('sop', '/documents/ingest', {'source_path': 'sops/source/SOP-P204-001-demo-v1.pdf',
             'title': 'SOP-P204-001 synthetic P-204A vibration', 'revision': 'DEMO-1', 'document_type': 'sop', 'synthetic': True}),
            ('maintenance', '/data/maintenance/ingest', {'source_path': 'work_orders/MH-P204-demo-v1.csv', 'synthetic': True}),
            ('sensors', '/data/sensors/ingest', {'source_path': 'faults/SENSOR-P204-A-demo-v1.csv', 'synthetic': True}),
            ('pid', '/documents/pid/process', {'source_path': 'PID-U2-017-R3-demo-v1.png',
             'title': 'PID-U2-017 R3 synthetic P-204A label excerpt', 'revision': 'R3', 'synthetic': True}),
        ]
        for name, endpoint, body in requests:
            response = client.post(endpoint, json=body)
            response.raise_for_status()
            results[name] = response.json()
            print(name, json.dumps(results[name]), flush=True)
        version = results['pid']['document_version_id']
        response = client.post(f'/documents/pid/{version}/index')
        response.raise_for_status()
        results['pid_index'] = response.json()
    output = settings.data_root / 'processed/phase9-seed.json'
    output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    with SessionLocal() as session:
        for username, password, role in DEMO_USERS:
            user = session.scalar(select(User).where(User.username == username))
            if user is None:
                session.add(User(username=username, password_hash=hash_password(password), role=role))
            elif user.role != role or not verify_password(password, user.password_hash):
                raise ValueError(f'Existing account {username} differs; will not overwrite it.')
        session.commit()
    print('Seed report:', output, flush=True)


if __name__ == '__main__':
    main()
