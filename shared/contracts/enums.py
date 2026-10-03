"""
Canonical string enums used in events and across the Innovision platform.
Supports both UPPERCASE and lowercase attributes for 100% platform compatibility.
"""
from enum import Enum


class FrameProvider(str, Enum):
    MINIO = "minio"
    REDIS = "redis"
    minio = "minio"
    redis = "redis"


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AlertStatus(str, Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    pending = "pending"
    acknowledged = "acknowledged"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class IncidentStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    active = "active"
    acknowledged = "acknowledged"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class SourceUC(str, Enum):
    UC1 = "uc1"
    UC2 = "uc2"
    UC3 = "uc3"
    UC4 = "uc4"
    uc1 = "uc1"
    uc2 = "uc2"
    uc3 = "uc3"
    uc4 = "uc4"


class CameraStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    RECONNECTING = "reconnecting"
    DISABLED = "disabled"
    online = "online"
    offline = "offline"
    reconnecting = "reconnecting"
    disabled = "disabled"


class OperatorRole(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    superadmin = "superadmin"
    admin = "admin"
    operator = "operator"
    viewer = "viewer"
