from uuid import UUID
from shared.contracts.alert_event import AlertEvent, AlertEventValidator

def validate_alert(alert: AlertEvent, known_camera_ids: set[UUID]) -> list[str]:
    return AlertEventValidator.validate(alert, known_camera_ids)
