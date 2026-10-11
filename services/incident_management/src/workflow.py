from enum import Enum

class IncidentStatus(str, Enum):
    OPEN = "open"
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

VALID_TRANSITIONS: dict[str, set[str]] = {
    "open": {"acknowledged", "investigating"},
    "active": {"acknowledged", "investigating", "in_progress"},
    "acknowledged": {"investigating", "in_progress", "resolved"},
    "investigating": {"resolved"},
    "in_progress": {"resolved"},
    "resolved": {"closed", "investigating", "in_progress"},
    "closed": set(),
}

def is_valid_transition(current: str, target: str) -> bool:
    curr_key = (current or "").lower()
    targ_key = (target or "").lower()
    return targ_key in VALID_TRANSITIONS.get(curr_key, set())

def all_valid_next_states(current: str) -> list[str]:
    curr_key = (current or "").lower()
    return sorted(list(VALID_TRANSITIONS.get(curr_key, set())))