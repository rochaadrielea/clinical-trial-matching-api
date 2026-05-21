"""audit.py — Append-only audit event log."""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from models import AuditEvent, AuditEventType


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event_type: AuditEventType, entity_type: str,
               entity_id: Optional[str] = None, payload: Optional[dict[str, Any]] = None) -> AuditEvent:
        event = AuditEvent(event_type=event_type, entity_type=entity_type,
                           entity_id=entity_id, payload=payload or {})
        self._events.append(event)
        return event

    def query(self, *, entity_type: Optional[str] = None, entity_id: Optional[str] = None,
              event_type: Optional[AuditEventType] = None,
              after: Optional[datetime] = None, before: Optional[datetime] = None) -> list[AuditEvent]:
        results = self._events
        if entity_type is not None:
            results = [e for e in results if e.entity_type == entity_type]
        if entity_id is not None:
            results = [e for e in results if e.entity_id == entity_id]
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        if after is not None:
            results = [e for e in results if e.timestamp >= after]
        if before is not None:
            results = [e for e in results if e.timestamp <= before]
        return results

    def entity_history(self, entity_id: str) -> list[AuditEvent]:
        return [e for e in self._events if e.entity_id == entity_id]

    def list_all(self) -> list[AuditEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()
