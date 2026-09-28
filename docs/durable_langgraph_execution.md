# Durable LangGraph execution (A2)

## Entry point and scope

`POST /executions` accepts the existing `QueryRequest`. Supply a UUID `request_id`
before sending the request so recovery remains possible if the connection closes
before the response. The response contains execution status and, when available,
the governed draft/informational response. Repeating creation with the same owner
and identical request returns stored progress; conflicting content returns 409.

`GET /executions/{id}` reports status, current node, failure classification,
checkpoint version, node attempts/timestamps, model, execution path, resume/retry
counts, and reasons. `POST /executions/{id}/resume` performs authorized recovery.
There is no client-supplied graph state, model override, or approval flag.

This entry point compiles the existing `app.agents.graph.build_graph`, with its
existing router, specialists, validators, tools, and governance service. It adds
governance and approval terminal nodes. It does not introduce another scheduler.
Legacy `/query` and direct `run_graph` calls retain their synchronous single-shot
contract; clients requiring restart recovery must use `/executions`. No frontend
or benchmark caller was changed. Exact verified-knowledge/cache responses are
outside this graph-execution API; their existing endpoints remain available.

## Storage and identity

PostgreSQL remains authoritative. Migration `0015_durable_execution` adds:

* `durable_executions`: owner, operational request, pinned graph revision/model/path,
  status and recovery counters.
* `graph_checkpoints`: LangGraph channel values/versions, parent links and metadata.
* `graph_writes`: task pending writes, including durable interrupt records.
* `execution_operations`: completed node/tool results, attempts and timestamps.

The execution ID, LangGraph thread ID and originating run ID reuse the request UUID.
The existing governance action revision ID remains separate and authoritative.
`revision=1` is the executable graph contract version, not an approval revision.

The SQLAlchemy `BaseCheckpointSaver` implementation supports synchronous put,
pending writes, get and history listing. Graph invocation uses `durability="sync"`.
Each saver transaction commits independently of the HTTP request transaction.
A PostgreSQL session advisory lock excludes concurrent workers for one execution
and is released when its connection/process dies. No timeout lease lets a slow
but live worker run concurrently with recovery.

## Resume semantics and idempotency

Recovery loads the last committed checkpoint and invokes LangGraph with `None`
(or a resume command at an interrupt). Completed channels/tasks are preserved.
An additional operation receipt closes the gap between node return and graph
checkpoint commit: if the node result committed first, its wrapper returns that
result without invoking the node again. The current graph is acyclic; receipts
are keyed by node name within one execution/revision.

Tool receipts use execution, node, call position, tool name and canonical validated
arguments. A completed tool call is returned from storage even if its surrounding
model node must restart. Current registered graph tools are read-only, including
B2's deterministic `analyze_sensor_maintenance`; a test fails if a registered tool
is missing from the durable read-only allowlist. An interrupted read may retry. Unregistered/write-capable tools are rejected by the
durable boundary until they implement a reviewed transactional/idempotent adapter.
An uncertain side effect is never treated as permission to repeat it.

Governance writes, trace, audit events and the governance-node receipt commit in
one transaction using the existing service's `commit=False` option. A crash before
commit rolls them all back; a crash after commit replays the receipt. Approval
decisions retain their existing unique constraints, actor checks and audit
transaction. No new document writes, notifications or webhook senders were added;
the existing webhook receipt mechanism remains unchanged.

After a hard process exit, a status read can acquire the abandoned execution lock
and mark RUNNING work INTERRUPTED. Authorized recovery also handles abandoned
RUNNING work without requiring a status read first. Recovery is explicit, not an
unattended startup worker. It never steals a live execution lock.

## Human approval

Governance freezes the existing authoritative proposal/evidence revision before
the approval node calls LangGraph `interrupt`. The checkpoint survives browser
close, application restart and indefinite waiting. Reviewers use the existing
approval API; an owner/admin subsequently calls the resume API.

The approval node ignores the resume value and reloads the governance ledger.
PENDING_REVIEW remains paused; APPROVED completes the advisory graph; rejection,
revocation and expiry terminate it as REJECTED. No model can approve or self-resume
this gate. Completion is not release or equipment execution. Existing release
endpoints still perform exact-revision, evidence-integrity, expiry/revocation and
locking checks. Status responses reload approval state rather than trusting an
old checkpoint. A later revocation remains visible in the response even if graph
computation is already complete.

## Retry and model policy

* RETRYABLE_INFRASTRUCTURE: local model timeout/unavailability, connection timeout,
  interrupted safe computation, or database operational failure.
* NON_RETRYABLE_VALIDATION: schema/value/structured-output failures.
* WAITING_FOR_HUMAN: durable approval pause.
* FAIL_CLOSED: unknown failure, unsafe/ambiguous operation, governance denial.
* COMPLETED: replay persisted results, never automatically rerun.

Retries are explicit authorized resume requests, not an answer-quality loop.
Existing bounded gateway/validator repair rules are unchanged; A2 adds no safety
validator retry. A model runtime error with ambiguous cause fails closed rather
than assuming it is transient. An interruption before a model response is
persisted can repeat generation; any completed tool receipts remain intact.

The existing deterministic strategy and A1 model policy select the durable graph
path. These graphs require evidence and therefore pin the primary `qwen3.5:9b`.
`qwen3.5:4b` remains available only to existing bounded low-risk helpers outside
this evidence graph. Recovery never reselects a weaker path/model after failure.
Changed graph revision or primary-model configuration blocks recovery until an
operator explicitly migrates the workflow. No hosted dependency was added.

## RBAC and operational privacy

Authentication uses existing server-issued sessions. Services reload user roles
from the database, ignoring mutated caller objects. Requesters/reviewers can read
and resume their own executions; admins can recover another user's execution.
Being a reviewer alone does not grant access to another user's recovery state.
Approval review permissions remain governed by the existing approval service.
Preflight runs both at creation and recovery.

Recovery stores only operational request/state/results. Its closed JSON codec
supports primitive state, evidence references and LangGraph interrupt records;
it performs no pickle decoding or arbitrary class loading. It excludes model
message histories, prompts, raw rejected output, reasoning fields (including
router reasoning), common secret fields and exception messages. Errors persist
only a class/reason code. The operator's query and evidence needed for recovery
may themselves contain sensitive plant information: protect these tables with
the same database controls and backups as governance data. This is not a general
free-text secret detector.

## Failure modes and limitations

* Database unavailability can prevent recording the latest failure status. Recovery
  uses the last committed checkpoint/receipt once PostgreSQL returns.
* A process may remain alive but hung. Recovery returns conflict while it owns the
  lock; operators must stop it before recovering. Per-invocation model deadlines
  remain active, while approval waits have no application-process dependency.
* There is no claim of exactly-once external effects across arbitrary remote
  systems. Write-capable adapters need downstream idempotency or an atomic outbox
  before admission. Document ingestion/webhook workflows are not graph nodes here.
* Receipt keys assume this graph's acyclic node topology. Future loops/subgraphs
  need stable task/iteration identities and a new graph revision before adoption.
* SQLite supports deterministic tests only; its process-local lock is not a
  production concurrency mechanism. PostgreSQL is the supported deployment store.
* Checkpoints have no automatic retention deletion. Back up before downgrading;
  downgrade removes the four recovery tables and all recovery history, while
  existing governance/audit tables remain intact.

## Validation

`tests/test_durable_execution.py` tests checkpoint creation, restart and hard
process exit, cached completion and pending-write crash gaps, tool replay,
approval/rejection, unauthorized HTTP/service access, transient versus validation
failure, model pinning, atomic audit/receipt rollback, reasoning exclusion, and
evidence serialization. With `WORKBENCH_TEST_POSTGRES=1`, the same recovery tests
run against an isolated PostgreSQL schema, plus advisory-lock exclusion and
Alembic upgrade/check/downgrade/upgrade/check. Local model calls are stubbed.

Use the shared workbench Python executable from this worktree's `backend` directory
with `MODEL_NAME=qwen3.5:9b`. Confirm `app.__path__` points to this worktree before
running targeted tests or the full backend suite. No BLIND benchmark is involved.
