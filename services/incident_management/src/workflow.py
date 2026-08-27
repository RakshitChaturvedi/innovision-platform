from enum import Enum

class IncidentStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

VALID_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.ACTIVE:       {IncidentStatus.ACKNOWLEDGED},
    IncidentStatus.ACKNOWLEDGED: {IncidentStatus.IN_PROGRESS},
    IncidentStatus.IN_PROGRESS:  {IncidentStatus.RESOLVED},
    IncidentStatus.RESOLVED:     {IncidentStatus.CLOSED, IncidentStatus.IN_PROGRESS},
    IncidentStatus.CLOSED:       set(),
}

def is_valid_transition(current: str, target: str) -> bool:
    try:
        return IncidentStatus(target) in VALID_TRANSITIONS[IncidentStatus(current)]
    except (KeyError, ValueError):
        return False

def all_valid_next_states(current: str) -> list[str]:
    try:
        return [s.value for s in VALID_TRANSITIONS[IncidentStatus(current)]]
    except (KeyError, ValueError):
        return []