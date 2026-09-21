from pydantic import BaseModel
from typing import List, Optional
import uuid
import datetime

class Incident(BaseModel):
    id: str
    timestamp: str
    affected_service: str
    severity: str
    failure_type: str
    status: str
    trace_ids: List[str] = []
    hypothesis: Optional[str] = None
    proposed_action: Optional[str] = None

class IncidentManager:
    def __init__(self):
        # In-memory store for now. Will be moved to pgvector in Phase 3.
        self.active_incidents = {}

    def create_incident(self, affected_service: str, failure_type: str, severity: str = "HIGH", trace_ids: List[str] = None):
        incident_id = f"INC-{str(uuid.uuid4())[:8]}"
        new_incident = Incident(
            id=incident_id,
            timestamp=datetime.datetime.utcnow().isoformat() + "Z",
            affected_service=affected_service,
            severity=severity,
            failure_type=failure_type,
            status="DETECTED",
            trace_ids=trace_ids or []
        )
        self.active_incidents[incident_id] = new_incident
        return new_incident

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return self.active_incidents.get(incident_id)

    def list_incidents(self) -> List[Incident]:
        return list(self.active_incidents.values())

    def update_incident_status(self, incident_id: str, new_status: str, hypothesis: str = None, action: str = None):
        if incident_id in self.active_incidents:
            self.active_incidents[incident_id].status = new_status
            if hypothesis:
                self.active_incidents[incident_id].hypothesis = hypothesis
            if action:
                self.active_incidents[incident_id].proposed_action = action
            return self.active_incidents[incident_id]
        return None

incident_manager = IncidentManager()
