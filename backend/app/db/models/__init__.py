"""Register every database model in shared metadata."""

from app.db.models.user import User
from app.db.models.agent import Agent
from app.db.models.agent_action import AgentAction
from app.db.models.document import Document
from app.db.models.equipment import Equipment
from app.db.models.sensor_reading import SensorReading
from app.db.models.incident_report import IncidentReport
from app.db.models.approval import Approval
from app.db.models.audit_log import AuditLog

from app.db.models.document_version import DocumentVersion
from app.db.models.structured_data_source import StructuredDataSource
from app.db.models.maintenance_record import MaintenanceRecord
from app.db.models.agent_run import AgentRun
from app.db.models.agent_run_step import AgentRunStep
from app.db.models.action_revision import GovernanceRequest, ActionRevision

__all__ = ["User","Agent","AgentAction","Document","Equipment","SensorReading","IncidentReport","Approval","AuditLog","DocumentVersion","StructuredDataSource","MaintenanceRecord","AgentRun","AgentRunStep","GovernanceRequest","ActionRevision"]
