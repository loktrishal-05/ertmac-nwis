"""Recovery around the existing graph, never an alternative scheduler."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID, uuid4

from langgraph.errors import GraphInterrupt
from langgraph.types import Command, interrupt
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.agents.checkpoint import SQLCheckpointSaver, config_for, encode, decode
from app.agents import context
from app.core.config import settings
from app.db.models import User
from app.db.models.durable_execution import DurableExecution, ExecutionOperation
from app.schemas.query import QueryRequest
from app.services.governance import GovernanceConflict, govern_response, get_governance_state, replay_request
from app.services.model_gateway import ModelTimeoutError, ModelUnavailableError, StructuredOutputError

_active = ContextVar("durable_execution", default=None)
_node = ContextVar("durable_node", default=None)
_sqlite_lock = RLock()
READ_ONLY_TOOLS = frozenset({"retrieve_documents", "get_pid_regions", "get_maintenance_history", "get_work_order",
                             "get_sensor_readings", "get_latest_reading", "compute_sensor_features"})


class RecoveryConflict(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc)


def retry_class(error):
    if isinstance(error, (ModelTimeoutError, ModelUnavailableError, ConnectionError, TimeoutError, OperationalError)):
        return "RETRYABLE_INFRASTRUCTURE"
    if isinstance(error, (ValueError, StructuredOutputError)):
        return "NON_RETRYABLE_VALIDATION"
    return "FAIL_CLOSED"


@contextmanager
def execution_lock(engine, ident):
    if engine.dialect.name == "sqlite":
        # SQLite is a deterministic test backend, not a multi-process deployment.
        with _sqlite_lock:
            yield
        return
    if engine.dialect.name != "postgresql":
        raise RecoveryConflict("Unsupported durable execution database")
    key = int.from_bytes(ident.bytes[:8], "big", signed=True)
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        connection.commit()
        if not acquired:
            raise RecoveryConflict("Execution is already running")
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            connection.commit()


def authorize(session, ident, actor):
    with session.no_autoflush:
        role = session.scalar(select(User.role).where(User.id == getattr(actor, "id", None)))
        row = session.get(DurableExecution, ident, populate_existing=True)
    if role not in ("requester", "reviewer", "admin") or row is None or (row.user_id != actor.id and role != "admin"):
        raise PermissionError("Execution access denied")
    return row


def status(session, ident, actor):
    row = authorize(session, ident, actor)
    if row.status == "RUNNING":
        try:
            with execution_lock(session.get_bind(), ident):
                session.refresh(row)
                if row.status == "RUNNING":
                    row.status, row.interruption_reason = "INTERRUPTED", "process_interrupted"
                    row.updated_at = now()
                    for op in session.scalars(select(ExecutionOperation).where(
                            ExecutionOperation.execution_id == ident, ExecutionOperation.status == "RUNNING")):
                        op.status = "INTERRUPTED"
                    session.commit()
        except RecoveryConflict:
            pass  # The live worker holds the lock; its RUNNING state is authoritative.
    result = {name: getattr(row, name) for name in (
        "status", "current_node", "retry_class", "resume_count", "retry_count", "checkpoint_version",
        "interruption_reason", "resume_reason", "selected_model", "execution_path", "created_at", "updated_at", "revision")}
    result.update(execution_id=row.id, thread_id=row.id, request_id=row.id, user_id=row.user_id)
    result["nodes"] = [{"node": op.key[5:], "status": op.status, "retry_class": op.retry_class,
        "attempts": op.attempts, "started_at": op.started_at, "finished_at": op.finished_at}
        for op in session.scalars(select(ExecutionOperation).where(ExecutionOperation.execution_id == ident,
            ExecutionOperation.key.like("node:%")).order_by(ExecutionOperation.started_at))]
    # Resolve draft status fresh: a cached checkpoint never grants approval authority.
    request = QueryRequest.model_validate(row.request)
    response = replay_request(session, request, requester_user_id=row.user_id)
    if response:
        result["response"] = response.model_dump(mode="json")
    else:
        op = session.get(ExecutionOperation, (ident, "node:governance"))
        if op and op.status == "COMPLETED":
            result["response"] = decode(op.result).get("response")
    return result


class Runtime:
    def __init__(self, engine, ident, session):
        self.engine, self.ident, self.session = engine, ident, session

    def operation(self, key, fn, *, safe_retry=False, transactional=False):
        with Session(self.engine) as journal:
            op = journal.get(ExecutionOperation, (self.ident, key))
            if op and op.status == "COMPLETED":
                return decode(op.result)
            if op and op.status not in ("WAITING_APPROVAL",):
                if not safe_retry or op.retry_class not in (None, "RETRYABLE_INFRASTRUCTURE"):
                    raise RecoveryConflict("Operation requires reconciliation: " + key)
            if op is None:
                op = ExecutionOperation(execution_id=self.ident, key=key, attempts=0)
                journal.add(op)
            op.attempts += 1
            op.status, op.started_at = "RUNNING", now()
            row = journal.get(DurableExecution, self.ident)
            row.current_node = key.split(":", 1)[1] if key.startswith("node:") else row.current_node
            row.updated_at = now()
            journal.commit()
        try:
            result = fn()
            # A governance response, its audit events, and this receipt share one commit.
            with Session(self.engine) if not transactional else _borrow(self.session) as journal:
                op = journal.get(ExecutionOperation, (self.ident, key))
                op.result, op.status, op.retry_class, op.finished_at = encode(result), "COMPLETED", "COMPLETED", now()
                journal.commit()
            return decode(encode(result))
        except GraphInterrupt:
            self.session.rollback()
            with Session(self.engine) as journal:
                op = journal.get(ExecutionOperation, (self.ident, key))
                op.status, op.retry_class = "WAITING_APPROVAL", "WAITING_FOR_HUMAN"
                journal.commit()
            raise
        except BaseException as error:
            self.session.rollback()
            classification = retry_class(error) if isinstance(error, Exception) else "RETRYABLE_INFRASTRUCTURE"
            if not safe_retry:
                classification = "FAIL_CLOSED"
            with Session(self.engine) as journal:
                op = journal.get(ExecutionOperation, (self.ident, key))
                op.status = "FAILED" if isinstance(error, Exception) else "INTERRUPTED"
                op.retry_class, op.finished_at = classification, now()
                journal.commit()
            raise

    def wrap(self, name, fn):
        def wrapped(state):
            token = _node.set({"name": name, "index": 0})
            try:
                return self.operation("node:" + name, lambda: fn(state), safe_retry=True,
                    transactional=name == "governance")
            finally:
                _node.reset(token)
        return wrapped

    def governance(self, state):
        row = self.session.get(DurableExecution, self.ident)
        request = QueryRequest.model_validate(row.request)
        state = dict(state, finished_at=now().isoformat())
        from app.services.execution_observability import attach
        attach(self.session, request, state, {"selected_path": row.execution_path})
        response = govern_response(self.session, request, state, requester_user_id=row.user_id, commit=False)
        return {"response": response.model_dump(mode="json"), "finished_at": state["finished_at"]}

    def approval(self, state):
        revision = state["response"].get("action_revision_id")
        if not revision:
            return {"approval_outcome": "INFORMATIONAL"}
        # Never accept a model or client resume value as approval evidence.
        outcome = get_governance_state(self.session, UUID(revision))
        self.session.rollback()
        if outcome == "PENDING_REVIEW":
            interrupt({"action_revision_id": revision, "status": "WAITING_APPROVAL"})
            outcome = get_governance_state(self.session, UUID(revision))
            self.session.rollback()
            if outcome == "PENDING_REVIEW":
                raise RecoveryConflict("Human decision still required")
        return {"approval_outcome": outcome}


@contextmanager
def _borrow(session):
    yield session


def durable_tool(name, arguments, fn):
    runtime, node = _active.get(), _node.get()
    if runtime is None or node is None:
        return fn()
    if name not in READ_ONLY_TOOLS:
        raise RecoveryConflict("Side-effect tool requires an explicit transactional/idempotent adapter")
    from app.services.canonicalization import canonical_hash
    index = node["index"]
    node["index"] += 1
    key = f"tool:{node['name']}:{index}:{name}:{canonical_hash(arguments)}"
    return runtime.operation(key, fn, safe_retry=name in READ_ONLY_TOOLS)


def start(session, request, actor):
    from app.services.preflight import run_preflight
    from app.services.adaptive_execution import strategy
    from app.services.model_routing import select_model, RiskSignals
    if run_preflight(request.query, request.access_scope).decision != "ALLOW":
        raise ValueError("Durable execution requires an allowed query")
    with session.no_autoflush:
        role = session.scalar(select(User.role).where(User.id == getattr(actor, "id", None)))
    if role not in ("requester", "reviewer", "admin"):
        raise PermissionError("Execution access denied")
    ident = request.request_id or uuid4()
    request = request.model_copy(update={"request_id": ident})
    engine = session.get_bind()
    session.rollback()
    with execution_lock(engine, ident):
        row = session.get(DurableExecution, ident)
        if row:
            authorize(session, ident, actor)
            if row.user_id != actor.id or row.request != request.model_dump(mode="json"):
                raise GovernanceConflict("request_id is already bound to another request")
            return status(session, ident, actor)
        if replay_request(session, request, requester_user_id=actor.id):
            raise GovernanceConflict("request_id already belongs to a non-durable governed request")
        path = strategy(request.query) or "EXISTING_AGENTIC_PATH"
        selection = select_model(request.query, requested_path=path,
            signals=RiskSignals(evidence_required=True, missing_verified_knowledge=True))
        session.add(DurableExecution(id=ident, user_id=actor.id, request=request.model_dump(mode="json"),
            selected_model=selection["model_selected"], execution_path=path, updated_at=now()))
        session.commit()
        _invoke(session, ident, resume=False)
    return status(session, ident, actor)


def resume(session, ident, actor):
    engine = session.get_bind()
    authorize(session, ident, actor)
    session.rollback()
    with execution_lock(engine, ident):
        row = authorize(session, ident, actor)
        if row.status in ("COMPLETED", "REJECTED"):
            return status(session, ident, actor)
        if row.retry_class in ("FAIL_CLOSED", "NON_RETRYABLE_VALIDATION"):
            raise RecoveryConflict("Execution is not automatically retryable")
        _invoke(session, ident, resume=True)
    return status(session, ident, actor)


def _invoke(session, ident, *, resume):
    from app.agents.graph import build_graph
    from app.services.preflight import run_preflight
    from app.services.execution_observability import record_routing
    row = session.get(DurableExecution, ident, populate_existing=True)
    request = QueryRequest.model_validate(row.request)
    if row.revision != 1 or row.selected_model != settings.primary_model:
        raise RecoveryConflict("Graph revision or pinned model changed; operator migration required")
    if run_preflight(request.query, request.access_scope).decision != "ALLOW":
        raise RecoveryConflict("Current preflight denies recovery")
    runtime = Runtime(session.get_bind(), ident, session)
    saver = SQLCheckpointSaver(session.get_bind())
    config = config_for(ident)
    config["recursion_limit"] = settings.agent_max_steps + 2
    checkpoint = saver.get_tuple(config)
    if resume:
        row.resume_count += 1
        row.resume_reason = "human_decision" if row.status == "WAITING_APPROVAL" else "authorized_recovery"
        if row.status not in ("WAITING_APPROVAL", "PENDING"):
            row.retry_count += 1
            row.interruption_reason = row.interruption_reason or "process_interrupted"
    row.status, row.updated_at = "RUNNING", now()
    path = row.execution_path
    actor_id = str(row.user_id)
    session.commit()
    tokens = [(_active, _active.set(runtime)), (context._access_scope, context.set_access_scope(request.access_scope)),
        (context._deadline, context.set_deadline(settings.agent_run_timeout_seconds)),
        (context._tool_records, context.set_tool_records([])), (context._gateway_repairs, context.set_gateway_repairs([0]))]
    try:
        record_routing({"model_selected": row.selected_model, "selected_model": row.selected_model,
                        "model_role": "primary", "requested_path": path})
        graph = build_graph(session=session, knowledge_only=path == "HYBRID_RAG_PATH", mgs=path == "MGS_PATH",
                            checkpointer=saver, durable=runtime)
        initial = {"run_id": str(ident), "query": request.query, "actor_id": actor_id,
            "access_scope": request.access_scope, "started_at": now().isoformat(), "evidence": [],
            "warnings": [], "errors": [], "step_records": [], "tool_invocations": [],
            "route": "knowledge" if path in ("HYBRID_RAG_PATH", "MGS_PATH") else None}
        snapshot = graph.get_state(config) if checkpoint else None
        waiting = snapshot and any(task.interrupts for task in snapshot.tasks)
        if waiting:
            response = snapshot.values.get("response") or {}
            revision = response.get("action_revision_id")
            if not revision or get_governance_state(session, UUID(revision)) == "PENDING_REVIEW":
                row.status, row.retry_class = "WAITING_APPROVAL", "WAITING_FOR_HUMAN"
                session.commit()
                return
        value = Command(resume=True) if waiting else (None if checkpoint else initial)
        result = graph.invoke(value, config=config, durability="sync")
        session.expire_all()
        row = session.get(DurableExecution, ident)
        if result.get("__interrupt__"):
            row.status, row.retry_class = "WAITING_APPROVAL", "WAITING_FOR_HUMAN"
        elif result.get("approval_outcome") in ("REJECTED", "REVOKED", "EXPIRED"):
            row.status, row.retry_class = "REJECTED", "FAIL_CLOSED"
        else:
            row.status, row.retry_class = "COMPLETED", "COMPLETED"
        row.updated_at = now()
        session.commit()
    except BaseException as error:
        session.rollback()
        row = session.get(DurableExecution, ident)
        row.status = "FAILED" if isinstance(error, Exception) else "INTERRUPTED"
        row.retry_class = retry_class(error) if isinstance(error, Exception) else "RETRYABLE_INFRASTRUCTURE"
        row.interruption_reason, row.updated_at = type(error).__name__, now()
        session.commit()
        if not isinstance(error, Exception):
            raise
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
