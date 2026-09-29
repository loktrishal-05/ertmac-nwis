"""Read-only acquisition boundary: local replay now, WITSML 2.1/ETP 1.2 later."""
from datetime import datetime
from typing import Protocol
from sqlalchemy import select
from app.db.models.nwis import TelemetrySample, Well
from app.services import nwis

class WITSMLAdapter(Protocol):
    def samples(self, well_id: str, start: datetime, end: datetime, limit: int) -> list[dict]: ...

class LocalReplay:
    def __init__(self, session): self.session=session
    def samples(self, well_id, start, end, limit=1000):
        from app.schemas.nwis import TelemetryOut
        well=self.session.get(Well,well_id)
        return [TelemetryOut.model_validate(s).model_dump(mode='json') for s in nwis.telemetry(self.session,well,start=start,end=end,limit=min(limit,1000))]
    def seek(self,well,at,actor):
        if well.dataset_origin!='synthetic_demo' or well.status!='ACTIVE':
            raise ValueError('Replay is only available for synthetic active wells')
        sample=self.session.scalar(select(TelemetrySample).where(TelemetrySample.well_id==well.id,
            TelemetrySample.channel=='MD',TelemetrySample.timestamp==at,TelemetrySample.quality=='good'))
        if sample is None or sample.value is None: raise ValueError('No valid replay MD sample exists at this timestamp')
        well.current_md=sample.md; well.as_of=sample.timestamp
        nwis.audit(self.session,'telemetry_replay_seek',actor,well_id=well.id,as_of=at,md=sample.md,dataset_origin=well.dataset_origin)
