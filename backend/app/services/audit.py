"""Phase 5C tamper-evident audit chain: deterministic hashing, append-only
persistence with PostgreSQL row-locked sequencing, and independent
verification.

This module is the ONLY writer of app.db.models.AuditEvent rows. It grants no
governance authority and performs no authorization check itself -- Phase
5A/5B's own services (app.services.governance, app.services.approval) remain
authoritative for that; this module only records that something happened.

Verification is deterministic backend code, never an LLM (docs/phase5c.md,
"Verification service").
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import AuditChainHead, AuditCheckpoint, AuditEvent
from app.services.canonicalization import canonical_hash, canonical_json

SCHEMA_VERSION = "phase5c-audit-v1"
# The single authoritative chain for this deployment's security/governance
# events. Not user-configurable -- a fixed identity, the same way
# app.services.governance.POLICY_VERSION is fixed, so every event's binding
# is unambiguous. A future phase could add more chains; nothing here forecloses
# that, but nothing invents it either.
CHAIN_ID = "workbench-governance-v1"


class AuditChainError(RuntimeError):
    """Mandatory audit persistence failed (DB failure, chain-head conflict,
    duplicate sequence, hash calculation failure, transaction rollback, ...).
    The caller must fail closed: never treat a governance/approval state
    change as complete if the audit event describing it could not be
    recorded (docs/phase5c.md, "Atomic governance/audit behavior")."""


def _genesis_previous_hash(chain_id: str) -> str:
    """The one documented, deterministic genesis representation
    (docs/phase5c.md, "Genesis design"): event #1's previous_hash always
    equals this value. Reproducible offline by anyone re-verifying the chain,
    without needing a database row to exist."""
    return canonical_hash({
        "schema_version": SCHEMA_VERSION, "genesis_marker": "PHASE5C_AUDIT_CHAIN_GENESIS",
        "chain_id": chain_id,
    })


def _json_safe(payload: dict) -> dict:
    """Normalize arbitrary payload values (UUID, datetime, ...) to the same
    plain JSON-native form a JSONB round trip through PostgreSQL always
    returns, so canonical_payload_hash is stable across insert and later
    verification reads. allow_nan=False rejects NaN/infinity up front."""
    return json.loads(json.dumps(payload, default=str, allow_nan=False))


def _envelope(*, schema_version, chain_id, sequence_number, event_id, occurred_at, actor_id, actor_kind,
             event_type, request_id, action_revision_id, decision_id, canonical_payload_hash, previous_hash) -> dict:
    """The exact, documented, versioned set of fields event_hash binds. Order
    here is irrelevant to the hash (canonical_json sorts keys); it matters
    only for readability."""
    return {
        "schema_version": schema_version, "chain_id": chain_id, "sequence_number": sequence_number,
        "event_id": event_id, "occurred_at": occurred_at, "actor_id": actor_id, "actor_kind": actor_kind,
        "event_type": event_type, "request_id": request_id, "action_revision_id": action_revision_id,
        "decision_id": decision_id, "canonical_payload_hash": canonical_payload_hash, "previous_hash": previous_hash,
    }


def _insert_once(session, model, values):
    dialect = session.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise ValueError("Unsupported audit database")
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    session.execute(insert(model).values(**values).on_conflict_do_nothing())


def append_event(session, *, event_type: str, actor_id: UUID | None, actor_kind: str, payload: dict,
                 request_id: UUID | None = None, action_revision_id: UUID | None = None,
                 decision_id: UUID | None = None, chain_id: str = CHAIN_ID) -> AuditEvent:
    """Append one authoritative event to `chain_id`, within the CALLER's own
    transaction -- this function never commits. For a MANDATORY audit event
    (one that describes an authoritative governance/approval state change),
    the caller must append it in the SAME transaction as that state change
    and let this function's exceptions propagate so both roll back together
    (docs/phase5c.md, "Atomic governance/audit behavior"): a state change must
    never appear to have succeeded while going unaudited.

    Concurrency: locks (SELECT ... FOR UPDATE) the chain's single head row
    for the duration of this call, serializing all concurrent appenders to
    THE SAME chain. A hash chain is inherently sequential -- this lock is
    correct, not merely an optimization (docs/phase5c.md, "Append/locking
    design").
    """
    try:
        _insert_once(session, AuditChainHead, {
            "chain_id": chain_id, "next_sequence_number": 1, "head_hash": _genesis_previous_hash(chain_id),
        })
        head = session.execute(
            select(AuditChainHead).where(AuditChainHead.chain_id == chain_id).with_for_update()
        ).scalar_one()

        sequence_number = head.next_sequence_number
        previous_hash = head.head_hash
        event_id = uuid4()
        occurred_at = datetime.now(timezone.utc)
        safe_payload = _json_safe(payload)
        canonical_payload_hash = canonical_hash(safe_payload)

        envelope = _envelope(
            schema_version=SCHEMA_VERSION, chain_id=chain_id, sequence_number=sequence_number,
            event_id=event_id, occurred_at=occurred_at, actor_id=actor_id, actor_kind=actor_kind,
            event_type=event_type, request_id=request_id, action_revision_id=action_revision_id,
            decision_id=decision_id, canonical_payload_hash=canonical_payload_hash, previous_hash=previous_hash,
        )
        canonical_event_json = canonical_json(envelope)
        event_hash = hashlib.sha256(canonical_event_json.encode("utf-8")).hexdigest()

        record = AuditEvent(
            id=event_id, schema_version=SCHEMA_VERSION, chain_id=chain_id, sequence_number=sequence_number,
            occurred_at=occurred_at, actor_id=actor_id, actor_kind=actor_kind, event_type=event_type,
            request_id=request_id, action_revision_id=action_revision_id, decision_id=decision_id,
            payload=safe_payload, canonical_payload_hash=canonical_payload_hash, previous_hash=previous_hash,
            canonical_event_json=canonical_event_json, event_hash=event_hash,
        )
        session.add(record)
        head.next_sequence_number = sequence_number + 1
        head.head_hash = event_hash
        session.flush()
        return record
    except Exception as error:
        raise AuditChainError(f"Mandatory audit append failed: {error}") from error


def create_checkpoint(session, *, chain_id: str = CHAIN_ID) -> AuditCheckpoint | None:
    """A minimal, future-compatible local checkpoint (docs/phase5c.md, "Chain
    checkpoint / anchor hook"): records the chain's current head at call
    time. No external/off-host anchoring is implemented here. Returns None if
    the chain has no events yet (nothing to checkpoint)."""
    head = session.execute(select(AuditChainHead).where(AuditChainHead.chain_id == chain_id)).scalar_one_or_none()
    if head is None or head.next_sequence_number <= 1:
        return None
    checkpoint = AuditCheckpoint(chain_id=chain_id, sequence_number=head.next_sequence_number - 1,
                                 head_hash=head.head_hash)
    session.add(checkpoint)
    session.flush()
    return checkpoint


def verify_chain(session, *, chain_id: str = CHAIN_ID) -> dict:
    """Deterministic backend verification -- NEVER an LLM. Walks every event
    for `chain_id` in sequence order, independently recomputing every hash
    from each row's own stored fields, and reports the FIRST point of
    inconsistency (docs/phase5c.md, "Verification service", for the full
    contract and error_type vocabulary: sequence_gap, sequence_out_of_order,
    duplicate_sequence_number, wrong_chain_id, previous_hash_mismatch,
    payload_hash_mismatch, event_hash_mismatch)."""
    events = session.execute(
        select(AuditEvent).where(AuditEvent.chain_id == chain_id).order_by(AuditEvent.sequence_number)
    ).scalars().all()

    result = {
        "valid": True, "chain_id": chain_id, "events_checked": 0,
        "first_sequence": events[0].sequence_number if events else None,
        "last_sequence": None, "head_hash": _genesis_previous_hash(chain_id),
        "first_error_sequence": None, "error_type": None,
    }
    expected_previous = _genesis_previous_hash(chain_id)
    expected_sequence = 1
    seen_sequences = set()

    def _fail(sequence_number, error_type):
        result["valid"] = False
        result["first_error_sequence"] = sequence_number
        result["error_type"] = error_type

    for record in events:
        seq = record.sequence_number
        result["events_checked"] += 1

        if seq in seen_sequences:
            _fail(seq, "duplicate_sequence_number")
            break
        seen_sequences.add(seq)

        if seq != expected_sequence:
            _fail(seq, "sequence_gap" if seq > expected_sequence else "sequence_out_of_order")
            break

        if record.chain_id != chain_id:
            _fail(seq, "wrong_chain_id")
            break

        if record.previous_hash != expected_previous:
            _fail(seq, "previous_hash_mismatch")
            break

        recomputed_payload_hash = canonical_hash(record.payload)
        if recomputed_payload_hash != record.canonical_payload_hash:
            _fail(seq, "payload_hash_mismatch")
            break

        occurred_at = record.occurred_at
        if occurred_at.tzinfo is None:
            # SQLite (test fixtures only) returns naive datetimes even for
            # DateTime(timezone=True); PostgreSQL never does. Treat a naive
            # value as already UTC, matching app.services.governance's
            # identical documented SQLite workaround.
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)

        envelope = _envelope(
            schema_version=record.schema_version, chain_id=record.chain_id, sequence_number=record.sequence_number,
            event_id=record.id, occurred_at=occurred_at, actor_id=record.actor_id, actor_kind=record.actor_kind,
            event_type=record.event_type, request_id=record.request_id, action_revision_id=record.action_revision_id,
            decision_id=record.decision_id, canonical_payload_hash=record.canonical_payload_hash,
            previous_hash=record.previous_hash,
        )
        recomputed_text = canonical_json(envelope)
        recomputed_hash = hashlib.sha256(recomputed_text.encode("utf-8")).hexdigest()
        if recomputed_text != record.canonical_event_json or recomputed_hash != record.event_hash:
            embedded_chain_id = None
            try:
                embedded_chain_id = json.loads(record.canonical_event_json).get("payload", {}).get("chain_id")
            except (ValueError, AttributeError, TypeError):
                pass
            error_type = ("wrong_chain_id" if embedded_chain_id is not None and embedded_chain_id != record.chain_id
                         else "event_hash_mismatch")
            _fail(seq, error_type)
            break

        expected_previous = record.event_hash
        expected_sequence = seq + 1
        result["last_sequence"] = seq
        result["head_hash"] = record.event_hash

    return result
