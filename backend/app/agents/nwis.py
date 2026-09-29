"""Four NWIS tool agents, with the existing SQL checkpoint and execution lock."""
from typing import TypedDict
from fastapi import HTTPException
from langgraph.graph import StateGraph, START, END
from app.agents.checkpoint import SQLCheckpointSaver, config_for
from app.db.models.durable_execution import DurableExecution
from app.schemas.nwis import QueryOut, EventOut
from app.services import nwis, nwis_knowledge
from app.services.durable_execution import execution_lock, RecoveryConflict

class State(TypedDict, total=False):
    offsets: list[dict]
    evidence: list[dict]
    warnings: list[str]
    risk: dict
    answer: str

def graph(session,request,user):
    active=nwis.well(session,request.well_id,user)
    def OffsetWellAgent(state):
        return {'offsets':[m.model_dump(mode='json') for m in nwis.offsets(session,active,user,request.radius_km,request.lookahead_m)]}
    def WellKnowledgeAgent(state):
        from app.schemas.nwis import MatchOut
        rows,warnings=nwis_knowledge.evidence_search(session,request,user,[MatchOut(**m) for m in state['offsets']])
        return {'evidence':[EventOut.model_validate(e).model_dump(mode='json') for e in rows], 'warnings':warnings}
    def DrillingRiskAgent(state):
        result,_=nwis.risk(session,active,user,request.lookahead_m,request.radius_km)
        return {'risk':result.model_dump(mode='json')}
    def AdvisoryAgent(state):
        evidence=state['evidence']
        if not evidence: return {'answer':'Insufficient cited evidence to answer this drilling question.'}
        # Source text is returned as evidence, never executed or converted into operating instructions.
        refs='; '.join(f"{e['id']} ({e['well_id']}, {e['source_report_id']}, page {e['source_page']})" for e in evidence)
        return {'answer':f'Historical evidence for engineering review: {refs}. '
            'Compare the cited observations, historical mitigations and outcomes with current well conditions. '
            'The risk estimates are uncalibrated prototype advisories. Engineering review is required.'}
    builder=StateGraph(State)
    for node in (OffsetWellAgent,WellKnowledgeAgent,DrillingRiskAgent,AdvisoryAgent): builder.add_node(node.__name__,node)
    for a,b in zip((START,'OffsetWellAgent','WellKnowledgeAgent','DrillingRiskAgent','AdvisoryAgent'),
                   ('OffsetWellAgent','WellKnowledgeAgent','DrillingRiskAgent','AdvisoryAgent',END)): builder.add_edge(a,b)
    return builder.compile(checkpointer=SQLCheckpointSaver(session.get_bind()))

def run(session,request,user):
    active=nwis.well(session,request.well_id,user)
    if nwis_knowledge.INJECTION.search(request.query):
        return QueryOut(execution_id=request.request_id,status='refused',answer='This request is outside evidence-only drilling support.',
            evidence=[],offsets=[],risk=None,warnings=[],model_route='deterministic-evidence-template',as_of=nwis.now(),dataset_origin=active.dataset_origin)
    try:
        with execution_lock(session.get_bind(),request.request_id):
            row=session.get(DurableExecution,request.request_id)
            payload=request.model_dump(mode='json')
            if row and (row.user_id!=user.id or row.request!=payload or row.execution_path!='NWIS'):
                raise HTTPException(409,'Request identity is unavailable or has different inputs')
            if row is None:
                row=DurableExecution(id=request.request_id,user_id=user.id,request=payload,status='RUNNING',
                    selected_model='deterministic-evidence-template',execution_path='NWIS',updated_at=nwis.now())
                session.add(row)
            row.status='RUNNING'; session.commit()
            flow=graph(session,request,user); config=config_for(request.request_id)
            prior=flow.get_state(config)
            try:
                result=flow.invoke(None if prior.values else {},config,durability='sync')
                # Reauthorize all cached evidence on replay; checkpoints never confer access.
                from app.db.models.nwis import DrillingEvent
                for e in result['evidence']:
                    nwis.well(session,e['well_id'],user)
                    current=session.get(DrillingEvent,e['id'])
                    if current is None or EventOut.model_validate(current).model_dump(mode='json')!=e:
                        raise HTTPException(409,'Source evidence changed; submit a new request ID')
                for m in result['offsets']: nwis.well(session,m['offset_well_id'],user)
                row=session.get(DurableExecution,request.request_id)
                row.status='COMPLETED'; row.updated_at=nwis.now()
                nwis.audit(session,'knowledge_query',user,execution_id=str(request.request_id),evidence_ids=[e['id'] for e in result['evidence']])
                session.commit()
            except Exception:
                session.rollback(); row=session.get(DurableExecution,request.request_id)
                row.status='FAILED'; row.updated_at=nwis.now(); session.commit()
                raise
            return QueryOut(execution_id=request.request_id,status='completed',answer=result['answer'],evidence=result['evidence'],
                offsets=result['offsets'],risk=result['risk'],warnings=result['warnings'],model_route='deterministic-evidence-template',
                as_of=result['risk']['as_of'],dataset_origin=active.dataset_origin)
    except RecoveryConflict as error:
        raise HTTPException(409,'Execution already running') from error
