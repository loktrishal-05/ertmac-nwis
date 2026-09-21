"""Phase 5D cryptographic evidence integrity: an immutable manifest binding a
governed ActionRevision to the EXACT evidence snapshot used to produce it.

Evidence INTEGRITY is not evidence CORRECTNESS, OCR confidence, authorization,
or plant-state truth (see docs/phase5d.md). A manifest only proves "this is
the exact evidence content that was present when the revision was created,
and it still matches its authoritative source where re-verification is
possible" -- never that the evidence is factually right, that OCR text was
read correctly, that anyone was authorized to act on it, or that a valve/
process is actually in the state a document describes.

Immutable after insert: a PostgreSQL trigger rejects UPDATE/DELETE, the same
established pattern as action_revision.py/approval_decision.py/audit_event.py.
"""
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, CreatedAtMixin, IdentityMixin

JSONVariant = JSON().with_variant(JSONB(), "postgresql")

MANIFEST_VERSION = "phase5d-evidence-v1"
# One-to-one with app.agents.evidence.EvidenceRef's `kind` discriminator --
# reused, not reinvented (docs/phase5d.md, "Reuse, not duplication").
EVIDENCE_TYPES = ("document_chunk", "pid_region", "csv_row", "sensor_window")


class EvidenceManifest(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence_manifests"

    # One governed revision binds to exactly one frozen manifest version.
    action_revision_id: Mapped[UUID] = mapped_column(ForeignKey("action_revisions.id"), unique=True, index=True)
    manifest_version: Mapped[str] = mapped_column(String(40))
    canonical_manifest: Mapped[str] = mapped_column(Text)
    canonical_manifest_hash: Mapped[str] = mapped_column(String(64))
    item_count: Mapped[int] = mapped_column(Integer)
    # Frozen baseline constant -- mirrors ActionRevision.evidence_binding_status
    # and ActionRevision.governance_status: the LIVE status is always computed
    # on demand by app.services.evidence_integrity.get_evidence_integrity_status,
    # never cached here. This column existing and staying constant is itself
    # the guardrail against "mark legacy evidence VERIFIED merely because it
    # exists" (docs/phase5d.md, "Integrity status") -- nothing can ever set it
    # to VERIFIED without a real, live recomputation happening elsewhere.
    integrity_status: Mapped[str] = mapped_column(String(30))

    __table_args__ = (
        CheckConstraint("manifest_version = 'phase5d-evidence-v1'", name="manifest_version"),
        CheckConstraint("integrity_status = 'PENDING_INTEGRITY'", name="frozen_pending_integrity"),
        CheckConstraint("item_count >= 0", name="item_count_non_negative"),
        CheckConstraint("length(canonical_manifest_hash) = 64", name="manifest_hash_length"),
        CheckConstraint("canonical_manifest_hash = encode(sha256(convert_to(canonical_manifest, 'UTF8')), 'hex')",
                        name="manifest_hash_binding").ddl_if(dialect="postgresql"),
    )


class EvidenceManifestItem(IdentityMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence_manifest_items"

    manifest_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_manifests.id"), index=True)
    # Stable position within the manifest -- item ORDER is itself part of what
    # gets hashed at the manifest level (docs/phase5d.md, "Canonical hashing").
    item_index: Mapped[int] = mapped_column(Integer)
    evidence_type: Mapped[str] = mapped_column(String(30))
    # The existing app.agents.evidence.make_evidence_id value -- reused
    # verbatim, never a new identity scheme.
    evidence_id: Mapped[str] = mapped_column(String(80))
    # e.g. "document:<id>:chunk:<id>", "maintenance_record:<id>",
    # "sensor_window:<citation_label>" -- human-diagnosable, not itself security.
    source_identifier: Mapped[str] = mapped_column(Text)
    # The ORIGINAL source's sha256 (document/CSV file) -- reused from the
    # existing DocumentVersion/MaintenanceRecord/SensorReading source_sha256
    # columns and app.agents.evidence.EvidenceRef.source_sha256; never invented.
    source_hash: Mapped[str] = mapped_column(String(64))
    # A freshly-computed hash of the actual evidence CONTENT used (chunk quote,
    # OCR text, normalized record fields, ordered sensor-reading values) -- no
    # such hash existed anywhere before Phase 5D; computed once here.
    content_hash: Mapped[str] = mapped_column(String(64))
    # Structured locator metadata for investigation (page/section/bbox/window
    # bounds/record ids) -- never large raw blobs or secrets.
    provenance: Mapped[dict] = mapped_column(JSONVariant)
    canonical_item_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("manifest_id", "item_index", name="uq_evidence_item_manifest_index"),
        CheckConstraint(
            "evidence_type IN (" + ", ".join(f"'{value}'" for value in EVIDENCE_TYPES) + ")",
            name="evidence_type",
        ),
        CheckConstraint(
            "length(source_hash) = 64 AND length(content_hash) = 64 AND length(canonical_item_hash) = 64",
            name="hash_lengths",
        ),
    )


def _immutable(mapper, connection, target):
    raise ValueError("Evidence manifests are immutable once frozen; create a new governed revision")


for _model in (EvidenceManifest, EvidenceManifestItem):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
