"""Read the existing Phase 3B1 artifacts; never run OCR or infer connectivity."""
import hashlib
import json

from app.core.config import settings
from app.db.models import DocumentVersion
from app.schemas.pid import OCRRegion, PIDManifest
from app.agents.evidence import pid_region_evidence
from app.services.canonicalization import canonical_hash


def load_pid_evidence(session, version_id):
    version = session.get(DocumentVersion, version_id)
    if version is None or version.ingestion_metadata.get('kind') != 'pid':
        raise ValueError('No processed P&ID found for this document_version_id.')
    root = settings.data_root.resolve()
    def read(uri, directory):
        path = (root / uri).resolve()
        if not path.is_relative_to(root / directory) or not path.is_file():
            raise ValueError('P&ID manifest artifact is missing.' if '/manifests/' in uri
                             else 'P&ID artifact is missing or outside its source directory.')
        return path.read_bytes()
    manifest = PIDManifest.model_validate_json(read(f'processed/pids/manifests/{version.id}.json', 'processed/pids'))
    if (manifest.document_version_id != version.id or manifest.document_id != version.document_id
            or manifest.source_sha256 != version.source_sha256):
        raise ValueError('P&ID source/version binding mismatch.')
    if hashlib.sha256(read(manifest.source_uri, 'raw/pids/source')).hexdigest() != version.source_sha256:
        raise ValueError('P&ID source content changed.')
    artifact = json.loads(read(manifest.region_json_uri, 'processed/pids'))
    if (not isinstance(artifact, dict) or artifact.get('document_id') != str(version.document_id)
            or artifact.get('document_version_id') != str(version.id)
            or artifact.get('source_sha256') != version.source_sha256):
        raise ValueError('P&ID region artifact source/version binding mismatch.')
    regions = [OCRRegion.model_validate(item) for item in artifact['regions']]
    if len(regions) != manifest.regions or len({r.region_id for r in regions}) != len(regions):
        raise ValueError('P&ID region set is inconsistent.')
    refs = []
    for region in regions:
        if not region.text_items or not region.combined_text.strip():
            continue
        if region.page > manifest.page_count or region.combined_text != '\n'.join(i.text for i in region.text_items):
            raise ValueError('P&ID raw OCR/page binding mismatch.')
        confidence = min(item.confidence for item in region.text_items)
        refs.append(pid_region_evidence(
            region_id=region.region_id, document_id=version.document_id, document_version_id=version.id,
            source_filename=manifest.source_filename, source_sha256=version.source_sha256,
            page=region.page, bbox=region.bbox, confidence=confidence,
            ocr_status='ambiguous' if confidence < .6 else 'unverified', combined_text=region.combined_text,
            source_uri=manifest.source_uri, source_image_uri=region.source_image_uri,
            revision=version.ingestion_metadata.get('request', {}).get('revision'),
            text_items=region.text_items, ocr_region_hash=canonical_hash(region.model_dump(mode='json')),
        ))
    return refs
