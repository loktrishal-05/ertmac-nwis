"""Phase 5C tamper-evident audit chain: an append-only, hash-linked ledger of
security/governance events. Separate from the legacy Phase 2
app.db.models.audit_log.AuditLog placeholder, which is NEVER hash-chained and
holds no rows (see docs/phase5c.md, "Legacy audit data").

TAMPER-EVIDENT, not tamper-proof: modification, deletion, insertion,
reordering, or truncation of an authoritative row is DETECTABLE by
app.services.audit.verify_chain, never silently invisible. This chain is NOT
an authorization mechanism and grants no governance authority by itself --
Phase 5A/5B's own services (app.services.governance, app.services.approval)
remain authoritative for that.

Immutable after insert: a PostgreSQL trigger rejects UPDATE/DELETE, mirroring
action_revision.py/approval_decision.py's established pattern.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, CreatedAtMixin, IdentityMixin

JSONVariant = JSON().with_variant(JSONB(), "postgresql")

# The bounded, non-flooding vocabulary of authoritative security/governance
# events this chain records (docs/phase5c.md, "Security-event integration").
# Deliberately does NOT include low-value internal model/token events.
EVENT_TYPES = (
    "GOVERNED_REVISION_CREATED", "LOGIN_SUCCESS", "LOGIN_FAILURE",
    "APPROVAL_DECISION_APPROVE", "APPROVAL_DECISION_REJECT", "APPROVAL_DECISION_REVOKE",
    "APPROVAL_AUTHORIZATION_DENIED", "ADVISORY_RELEASE_SUCCESS", "ADVISORY_RELEASE_DENIED",
    # Phase 5D
    "EVIDENCE_MANIFEST_CREATED", "EVIDENCE_INTEGRITY_VERIFIED", "EVIDENCE_INTEGRITY_FAILED",
    # Phase 5E: deterministic pre-routing guardrail outcomes (docs/phase5e.md).
    # Best-effort events -- nothing state-changing happened, so a logging
    # failure must never turn a correct refusal/clarification response into a
    # 500 (same split as APPROVAL_AUTHORIZATION_DENIED/ADVISORY_RELEASE_DENIED).
    "PREFLIGHT_OUT_OF_SCOPE_REFUSED", "PREFLIGHT_INJECTION_REFUSED",
    "PREFLIGHT_UNSAFE_ACTION_REFUSED", "PREFLIGHT_SCOPE_DENIED", "PREFLIGHT_CLARIFICATION_REQUIRED",
)
ACTOR_KINDS = ("user", "system", "anonymous")


class AuditEvent(IdentityMixin, Base):
    __tablename__ = "audit_events"

    schema_version: Mapped[str] = mapped_column(String(40))
    chain_id: Mapped[str] = mapped_column(String(100), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    actor_kind: Mapped[str] = mapped_column(String(20))
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    request_id: Mapped[UUID | None] = mapped_column(ForeignKey("governance_requests.id"), default=None, index=True)
    action_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("action_revisions.id"), default=None, index=True)
    decision_id: Mapped[UUID | None] = mapped_column(ForeignKey("approval_decisions.id"), default=None, index=True)
    # Structured investigation metadata. Never passwords/tokens/session secrets
    # (app.services.audit.append_event callers are responsible for this; see
    # docs/phase5c.md, "Security-event integration").
    payload: Mapped[dict] = mapped_column(JSONVariant)
    canonical_payload_hash: Mapped[str] = mapped_column(String(64))
    previous_hash: Mapped[str] = mapped_column(String(64))
    # The exact deterministic JSON text that was hashed to produce event_hash
    # (app.services.canonicalization.canonical_json over the event envelope) --
    # stored verbatim so the PostgreSQL CHECK below, and any offline verifier,
    # can recompute/confirm event_hash without reimplementing canonicalization.
    canonical_event_json: Mapped[str] = mapped_column(Text)
    event_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("chain_id", "sequence_number", name="uq_audit_events_chain_sequence"),
        UniqueConstraint("event_hash", name="uq_audit_events_hash"),
        CheckConstraint("schema_version = 'phase5c-audit-v1'", name="schema_version"),
        CheckConstraint("actor_kind IN ('user', 'system', 'anonymous')", name="actor_kind"),
        CheckConstraint(
            "event_type IN (" + ", ".join(f"'{value}'" for value in EVENT_TYPES) + ")",
            name="event_type",
        ),
        CheckConstraint("sequence_number >= 1", name="sequence_positive"),
        CheckConstraint(
            "length(canonical_payload_hash) = 64 AND length(previous_hash) = 64 AND length(event_hash) = 64",
            name="hash_lengths",
        ),
        # Defense in depth against a raw-SQL forged row (bypassing
        # app.services.audit.append_event): the DB itself refuses to store an
        # event_hash that doesn't match the row's own canonical_event_json
        # text. Cross-row chain linkage (previous_hash) cannot be a CHECK
        # constraint (Postgres CHECK cannot reference other rows) -- that is
        # exactly what app.services.audit.verify_chain independently verifies.
        CheckConstraint("event_hash = encode(sha256(convert_to(canonical_event_json, 'UTF8')), 'hex')",
                        name="event_hash_binding").ddl_if(dialect="postgresql"),
    )


class AuditChainHead(IdentityMixin, Base):
    """Mutable append-cursor/lock row -- NOT part of the tamper-evident chain
    itself and carries no integrity guarantee on its own. Locked via
    SELECT ... FOR UPDATE to serialize concurrent appends to the same chain
    (see app.services.audit.append_event). The actual integrity guarantee
    comes only from walking the immutable audit_events rows
    (app.services.audit.verify_chain), never from trusting this pointer."""
    __tablename__ = "audit_chain_heads"

    chain_id: Mapped[str] = mapped_column(String(100), unique=True)
    next_sequence_number: Mapped[int] = mapped_column(Integer, default=1)
    head_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("next_sequence_number >= 1", name="next_sequence_positive"),
        CheckConstraint("length(head_hash) = 64", name="head_hash_length"),
    )


class AuditCheckpoint(IdentityMixin, CreatedAtMixin, Base):
    """A point-in-time snapshot of a chain's head (docs/phase5c.md, "Chain
    checkpoint / anchor hook"). Minimal and future-compatible: this phase
    persists checkpoints LOCALLY only -- no external/off-host anchoring is
    implemented or claimed here (see the docs for that as a documented future
    hardening option). Checkpoint rows are themselves append-only but are NOT
    part of the hash chain; a checkpoint is an independent reference an
    operator can later compare a `verify_chain` result against."""
    __tablename__ = "audit_checkpoints"

    chain_id: Mapped[str] = mapped_column(String(100), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    head_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("sequence_number >= 1", name="sequence_positive"),
        CheckConstraint("length(head_hash) = 64", name="head_hash_length"),
    )


def _immutable(mapper, connection, target):
    raise ValueError("Audit events are append-only and immutable; they can never be updated or deleted")


for _model in (AuditEvent, AuditCheckpoint):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
