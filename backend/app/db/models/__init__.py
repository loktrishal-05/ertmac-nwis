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

__all__ = ["User","Agent","AgentAction","Document","Equipment","SensorReading","IncidentReport","Approval","AuditLog"]

