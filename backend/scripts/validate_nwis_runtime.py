"""Readiness, spatial, seed and provenance checks for the isolated NWIS runtime."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
from sqlalchemy import select, text, func
from qdrant_client import QdrantClient
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models.nwis import (Well, WellTrajectoryPoint, FormationInterval, DrillingReport,
                               DrillingEvent, TelemetrySample, NWIS_TABLES)
from app.services.audit import verify_chain
from app.services.readiness import runtime_readiness
from app.services.nwis import NEARBY_SQL
from scripts.seed_nwis import seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='data/nwis_c2_runtime.json')
    args = parser.parse_args()
    result = {'readiness': runtime_readiness()}
    assert result['readiness']['status'] == 'ready', result
    with SessionLocal() as session:
        assert session.bind.dialect.name == 'postgresql' and session.bind.url.database == 'nwis', 'Dedicated real PostGIS database required'
        result['migration'] = session.scalar(text('SELECT version_num FROM alembic_version'))
        assert result['migration'] == '0018_nwis'
        result['postgis'] = session.scalar(text('SELECT PostGIS_Full_Version()'))
        result['spatial_index'] = session.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_nwis_wells_location'"))
        assert 'USING gist' in result['spatial_index']
        params = dict(active='ACTIVE-01', radius=10000, limit=100, offset=0)
        nearby = [dict(row) for row in session.execute(text(NEARBY_SQL), params).mappings()]
        assert len(nearby) == 11 and nearby[0]['id'] == 'OFF-01'
        assert nearby == [dict(row) for row in session.execute(text(NEARBY_SQL), params).mappings()]
        result['spatial_sql'] = NEARBY_SQL
        result['spatial_parameters'] = params
        result['distance_order'] = nearby
        session.execute(text('SET LOCAL enable_seqscan=off'))
        result['spatial_plan'] = list(session.scalars(text('EXPLAIN '+NEARBY_SQL), params))
        assert any('ix_nwis_wells_location' in line for line in result['spatial_plan'])
        models = (Well, WellTrajectoryPoint, FormationInterval, DrillingReport, DrillingEvent, TelemetrySample)
        def counts():
            return {m.__tablename__: session.scalar(select(func.count()).select_from(m)) for m in models}
        before = counts()
        seed(session)
        session.commit()
        assert counts() == before
        seed(session)
        session.commit()
        assert counts() == before
        assert list(before.values()) == [12, 396, 48, 11, 66, 610]
        result['seed_counts_after_two_repeats'] = before
        for model in NWIS_TABLES:
            if hasattr(model, 'dataset_origin'):
                assert session.scalar(select(func.count()).select_from(model).where(model.dataset_origin != 'synthetic_demo')) == 0
        result['all_domain_origins_synthetic'] = True
        reports = session.scalars(select(DrillingReport).order_by(DrillingReport.id)).all()
        for report in reports:
            path = settings.data_root/'nwis'/'reports'/(report.file_hash+'.pdf')
            assert hashlib.sha256(path.read_bytes()).hexdigest() == report.file_hash
        result['source_files_verified'] = len(reports)
        result['audit_chain'] = verify_chain(session)
        assert result['audit_chain']['valid']
    with closing(QdrantClient(url=settings.qdrant_url)) as client:
        info = client.get_collection('nwis_evidence_v1')
        result['qdrant'] = dict(collection='nwis_evidence_v1', status=str(info.status),
                                points=client.count('nwis_evidence_v1', exact=True).count)
        assert result['qdrant']['points'] == 66
    result['model_artifacts'] = {}
    for folder in ('bge-base-en-v1.5', 'bge-reranker-base'):
        path = settings.model_root/folder
        assert (path/'config.json').is_file() and (path/'model.safetensors').is_file()
        result['model_artifacts'][folder] = 'local config and safetensors present; inference checked separately'
    Path(args.output).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
