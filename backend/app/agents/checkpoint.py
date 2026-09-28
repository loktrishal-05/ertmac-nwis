"""Synchronous SQLAlchemy LangGraph saver with a closed, JSON-only codec.

No pickle, message histories, gateway responses, or arbitrary class loading.
Each checkpoint and pending write commits before returning to LangGraph.
"""
from datetime import datetime
from uuid import UUID
from typing import get_args

from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple, WRITES_IDX_MAP
from langgraph.types import Interrupt
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.evidence import EvidenceRef
from app.db.models.durable_execution import DurableExecution, GraphCheckpoint, GraphWrite

_PRIVATE = {"route_reasoning", "reasoning", "reasoning_content", "chain_of_thought", "hidden_reasoning",
            "raw_text", "messages", "prompt", "password", "password_hash", "api_key", "authorization", "secret"}


def encode(value):
    if isinstance(value, get_args(EvidenceRef)):
        return {"__type": "evidence", "value": encode(value.model_dump(mode="json"))}
    if isinstance(value, Interrupt):
        return {"__type": "interrupt", "value": encode(value.value), "id": value.id}
    if isinstance(value, tuple):
        return {"__type": "tuple", "value": [encode(v) for v in value]}
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items() if str(k).lower() not in _PRIVATE}
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, (UUID, datetime)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("Unsupported recovery state type")


def decode(value):
    if isinstance(value, list):
        return [decode(v) for v in value]
    if isinstance(value, dict):
        kind = value.get("__type")
        if kind == "evidence":
            return TypeAdapter(EvidenceRef).validate_python(decode(value["value"]))
        if kind == "interrupt":
            return Interrupt(value=decode(value["value"]), id=value["id"])
        if kind == "tuple":
            return tuple(decode(v) for v in value["value"])
        return {k: decode(v) for k, v in value.items()}
    return value


def config_for(execution_id, namespace="", checkpoint_id=None):
    config = {"thread_id": str(execution_id), "checkpoint_ns": namespace}
    if checkpoint_id:
        config["checkpoint_id"] = checkpoint_id
    return {"configurable": config}


class SQLCheckpointSaver(BaseCheckpointSaver):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def get_tuple(self, config):
        values = config["configurable"]
        ident, ns = UUID(values["thread_id"]), values.get("checkpoint_ns", "")
        with Session(self.engine) as session:
            query = select(GraphCheckpoint).where(GraphCheckpoint.execution_id == ident, GraphCheckpoint.namespace == ns)
            if values.get("checkpoint_id"):
                query = query.where(GraphCheckpoint.checkpoint_id == values["checkpoint_id"])
            row = session.scalars(query.order_by(GraphCheckpoint.checkpoint_id.desc()).limit(1)).first()
            if row is None:
                return None
            writes = session.scalars(select(GraphWrite).where(GraphWrite.execution_id == ident,
                GraphWrite.namespace == ns, GraphWrite.checkpoint_id == row.checkpoint_id)
                .order_by(GraphWrite.task_id, GraphWrite.idx)).all()
            return CheckpointTuple(config=config_for(ident, ns, row.checkpoint_id),
                checkpoint=decode(row.checkpoint), metadata=decode(row.meta),
                parent_config=config_for(ident, ns, row.parent_id) if row.parent_id else None,
                pending_writes=[(w.task_id, w.channel, decode(w.value)["value"]) for w in writes])

    def put(self, config, checkpoint, metadata, new_versions):
        values = config["configurable"]
        ident, ns = UUID(values["thread_id"]), values.get("checkpoint_ns", "")
        with Session(self.engine) as session, session.begin():
            key = (ident, ns, checkpoint["id"])
            if session.get(GraphCheckpoint, key) is None:
                session.add(GraphCheckpoint(execution_id=ident, namespace=ns, checkpoint_id=checkpoint["id"],
                    parent_id=values.get("checkpoint_id"), checkpoint=encode(checkpoint), meta=encode(metadata)))
                row = session.get(DurableExecution, ident)
                row.checkpoint_version += 1
        return config_for(ident, ns, checkpoint["id"])

    def put_writes(self, config, writes, task_id, task_path=""):
        values = config["configurable"]
        ident, ns = UUID(values["thread_id"]), values.get("checkpoint_ns", "")
        with Session(self.engine) as session, session.begin():
            for index, (channel, value) in enumerate(writes):
                index = WRITES_IDX_MAP.get(channel, index)
                key = (ident, ns, values["checkpoint_id"], task_id, index)
                row = session.get(GraphWrite, key)
                if row is not None and index >= 0:
                    continue
                # Exception text can contain rejected output or transport credentials.
                if channel == "__error__":
                    value = "node_failed"
                if row is None:
                    row = GraphWrite(execution_id=ident, namespace=ns, checkpoint_id=values["checkpoint_id"],
                        task_id=task_id, idx=index)
                    session.add(row)
                row.channel, row.value = channel, encode({"value": value})

    def list(self, config, *, filter=None, before=None, limit=None):
        with Session(self.engine) as session:
            query = select(GraphCheckpoint)
            if config:
                query = query.where(GraphCheckpoint.execution_id == UUID(config["configurable"]["thread_id"]),
                    GraphCheckpoint.namespace == config["configurable"].get("checkpoint_ns", ""))
            if before:
                query = query.where(GraphCheckpoint.checkpoint_id < before["configurable"]["checkpoint_id"])
            rows = session.scalars(query.order_by(GraphCheckpoint.checkpoint_id.desc())).all()
            count = 0
            for row in rows:
                if filter and any(row.meta.get(k) != v for k, v in filter.items()):
                    continue
                if limit is not None and count >= limit:
                    break
                yield self.get_tuple(config_for(row.execution_id, row.namespace, row.checkpoint_id))
                count += 1
