"""Small append-only audit helper for administrator operations."""

import json
import uuid
from typing import Any

from sqlalchemy import text


def write_operation_audit(
    session: Any, actor_user_id: uuid.UUID, category: str, action: str,
    target_type: str, target_id: uuid.UUID | None = None, target_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.execute(text("""
        INSERT INTO operation_audit_logs(
          id, actor_user_id, category, action, target_type, target_id, target_name, details_json
        ) VALUES (:id, :actor, :category, :action, :target_type, :target_id, :target_name, CAST(:details AS jsonb))
    """), {"id": uuid.uuid4(), "actor": actor_user_id, "category": category,
           "action": action, "target_type": target_type, "target_id": target_id,
           "target_name": target_name, "details": json.dumps(details or {}, ensure_ascii=False)})
