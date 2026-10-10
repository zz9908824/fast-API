"""P0 resident-facing API for the government-material precheck domain.

The database uses immutable matter versions.  This module deliberately queries
those tables directly instead of duplicating them into the template's generic
``Item`` model.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy import text

from app.api.deps import CurrentUser, SessionDep
from app.schemas.precheck import (
    ApplicationCreate,
    ParticipantCreate,
    PreparationItemUpdate,
    ScenarioUpdate,
)

router = APIRouter(tags=["政务材料预审"])


def envelope(data: Any) -> dict[str, Any]:
    return {"data": data}


def rows(session: SessionDep, statement: str, params: dict | None = None) -> list[dict]:
    return [dict(row) for row in session.execute(text(statement), params or {}).mappings()]


def one(session: SessionDep, statement: str, params: dict | None = None) -> dict | None:
    result = rows(session, statement, params)
    return result[0] if result else None


def owned_application(session: SessionDep, app_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    app = one(
        session,
        "SELECT * FROM applications WHERE id = :id AND owner_user_id = :owner",
        {"id": app_id, "owner": user_id},
    )
    if not app:
        raise HTTPException(status_code=404, detail="办件不存在或您无权访问")
    return app


def require_revision(app: dict, expected_revision: int) -> None:
    if app["content_revision"] != expected_revision:
        raise HTTPException(status_code=409, detail="办件内容已被更新，请刷新后重试")


@router.get("/matters")
def list_matters(
    session: SessionDep,
    q: str | None = Query(default=None, max_length=100),
    region_code: str | None = Query(default=None, max_length=32),
) -> dict:
    """Return publicly available, published matters without exposing draft config."""
    clauses = ["sm.is_active = true"]
    params: dict[str, Any] = {}
    if q:
        clauses.append("(sm.name ILIKE :q OR sm.code ILIKE :q)")
        params["q"] = f"%{q}%"
    if region_code:
        clauses.append("sm.region_code = :region_code")
        params["region_code"] = region_code
    return envelope(rows(session, f"""
        SELECT sm.id, sm.code, sm.official_code, sm.name, sm.region_code, sm.region_name,
               sm.description, mv.id AS published_version_id, mv.version_no, mv.valid_from, mv.valid_to
        FROM service_matters sm
        JOIN LATERAL (
          SELECT id, version_no, valid_from, valid_to FROM matter_versions
          WHERE matter_id = sm.id AND status = 'published'
          ORDER BY version_no DESC LIMIT 1
        ) mv ON true
        WHERE {' AND '.join(clauses)}
        ORDER BY sm.region_name, sm.name
    """, params))


@router.get("/matters/{matter_id}")
def get_matter(matter_id: uuid.UUID, session: SessionDep) -> dict:
    matter = one(session, """
        SELECT sm.id, sm.code, sm.official_code, sm.name, sm.region_code, sm.region_name,
               sm.description, mv.id AS version_id, mv.version_no, mv.valid_from, mv.valid_to,
               sl.name AS location_name, sl.address, sl.phone, sl.opening_hours, sl.official_entry_url
        FROM service_matters sm JOIN matter_versions mv ON mv.matter_id = sm.id
        LEFT JOIN service_locations sl ON sl.id = mv.service_location_id
        WHERE sm.id = :id AND sm.is_active = true AND mv.status = 'published'
        ORDER BY mv.version_no DESC LIMIT 1
    """, {"id": matter_id})
    if not matter:
        raise HTTPException(status_code=404, detail="未找到已发布事项")
    requirements = rows(session, """
        SELECT mr.id, mr.requirement_code, mr.name, mr.requirement_level, mr.provider_role,
               mr.submission_mode, mr.original_required, mr.copy_count, mr.min_pages,
               mr.format_requirements, mr.alternative_group_code, mr.sort_order,
               mt.code AS material_type_code, mt.name AS material_type_name
        FROM material_requirements mr JOIN material_types mt ON mt.id = mr.material_type_id
        WHERE mr.matter_version_id = :version_id ORDER BY mr.sort_order, mr.requirement_code
    """, {"version_id": matter["version_id"]})
    return envelope({**matter, "requirements": requirements})


@router.get("/matter-versions/{version_id}/requirements/{requirement_id}/acquisition-methods")
def list_acquisition_methods(
    version_id: uuid.UUID, requirement_id: uuid.UUID, session: SessionDep
) -> dict:
    """Publicly expose only verified guidance belonging to a published version."""
    version = one(session, """
        SELECT mv.id FROM matter_versions mv JOIN service_matters sm ON sm.id = mv.matter_id
        WHERE mv.id = :version_id AND mv.status = 'published' AND sm.is_active = true
    """, {"version_id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="未找到已发布事项版本")
    methods = rows(session, """
        SELECT mam.id, mam.method_code, mam.method_type, mam.title, mam.steps, mam.entry_url,
          mam.verification_status, sl.name AS location_name, sl.address, sl.phone,
          ps.id AS source_id, ps.title AS source_title, ps.url AS source_url
        FROM material_acquisition_methods mam
        JOIN material_requirements mr ON mr.id = mam.requirement_id
        LEFT JOIN service_locations sl ON sl.id = mam.location_id
        LEFT JOIN policy_sources ps ON ps.id = mam.source_id
        WHERE mam.requirement_id = :requirement_id AND mr.matter_version_id = :version_id
          AND mam.verification_status = 'verified'
        ORDER BY mam.sort_order, mam.method_code
    """, {"requirement_id": requirement_id, "version_id": version_id})
    return envelope(methods)


@router.get("/policy-sources/{source_id}")
def get_policy_source(source_id: uuid.UUID, session: SessionDep) -> dict:
    source = one(session, """
        SELECT id, title, source_kind, url, publisher, published_date, retrieved_at,
          verification_status, verified_at
        FROM policy_sources WHERE id = :id AND verification_status = 'verified'
    """, {"id": source_id})
    if not source:
        raise HTTPException(status_code=404, detail="未找到已核验的公开来源")
    return envelope(source)


@router.post("/applications", status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    session: SessionDep,
    current_user: CurrentUser,
    idempotency_key: str = Header(..., alias="Idempotency-Key", max_length=255),
) -> dict:
    request_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    operation = "POST:/applications"
    saved = one(session, """
        SELECT request_hash, response_json FROM api_idempotency_records
        WHERE user_id = :user_id AND operation = :operation AND idempotency_key = :key
    """, {"user_id": current_user.id, "operation": operation, "key": idempotency_key})
    if saved:
        if saved["request_hash"] != request_hash:
            raise HTTPException(status_code=409, detail="该幂等键已用于不同请求")
        return envelope(saved["response_json"])
    version = one(session, """
        SELECT id FROM matter_versions WHERE id = :version_id AND matter_id = :matter_id
          AND status = 'published'
    """, {"version_id": payload.matter_version_id, "matter_id": payload.matter_id})
    if not version:
        raise HTTPException(status_code=409, detail="事项版本不存在、未发布或不能新建办件")
    app_id = uuid.uuid4()
    application_no = f"PRE-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    result = {"id": app_id, "application_no": application_no, "matter_version_id": payload.matter_version_id,
              "status": "draft", "content_revision": 1, "data_origin": "synthetic"}
    session.execute(text("""
        INSERT INTO applications(id, application_no, owner_user_id, matter_version_id)
        VALUES (:id, :no, :owner, :version_id)
    """), {"id": app_id, "no": application_no, "owner": current_user.id, "version_id": payload.matter_version_id})
    session.execute(text("""
        INSERT INTO api_idempotency_records(id, user_id, operation, idempotency_key, request_hash,
          resource_id, response_status, response_json, expires_at)
        VALUES (:id, :user_id, :operation, :key, :hash, :resource_id, 201,
          CAST(:response AS jsonb), :expires_at)
    """), {"id": uuid.uuid4(), "user_id": current_user.id, "operation": operation, "key": idempotency_key,
           "hash": request_hash, "resource_id": app_id, "response": json.dumps(result, default=str),
           "expires_at": datetime.now(UTC) + timedelta(hours=24)})
    session.commit()
    return envelope(result)


@router.get("/applications")
def list_applications(session: SessionDep, current_user: CurrentUser) -> dict:
    data = rows(session, """
        SELECT a.id, a.application_no, a.status, a.questionnaire_status, a.content_revision,
               a.created_at, a.updated_at, sm.name AS matter_name, sm.region_name, mv.version_no,
               latest.status AS latest_check_status, latest.material_summary
        FROM applications a JOIN matter_versions mv ON mv.id = a.matter_version_id
        JOIN service_matters sm ON sm.id = mv.matter_id
        LEFT JOIN LATERAL (
          SELECT status, material_summary FROM check_runs WHERE application_id = a.id
          ORDER BY run_no DESC LIMIT 1
        ) latest ON true
        WHERE a.owner_user_id = :owner ORDER BY a.created_at DESC
    """, {"owner": current_user.id})
    return envelope({"items": data, "count": len(data)})


@router.get("/applications/{app_id}")
def get_application(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    detail = one(session, """
        SELECT sm.name AS matter_name, sm.region_name, mv.version_no, mv.valid_from, mv.valid_to
        FROM matter_versions mv JOIN service_matters sm ON sm.id = mv.matter_id WHERE mv.id = :id
    """, {"id": app["matter_version_id"]})
    return envelope({**app, "matter": detail})


@router.get("/applications/{app_id}/questionnaire")
def get_questionnaire(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    return envelope({"questions": [], "answers": app["scenario_answers"],
                     "visible_codes": [], "unknown_codes": [],
                     "questionnaire_status": app["questionnaire_status"],
                     "content_revision": app["content_revision"]})


@router.put("/applications/{app_id}/scenario")
def save_scenario(app_id: uuid.UUID, payload: ScenarioUpdate, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    require_revision(app, payload.expected_revision)
    next_revision = app["content_revision"] + 1
    next_status = "preparing" if payload.mode == "submit" else app["status"]
    session.execute(text("""
        UPDATE applications SET scenario_answers = CAST(:answers AS jsonb),
          questionnaire_status = :questionnaire_status, status = :status,
          content_revision = :revision, updated_at = now() WHERE id = :id
    """), {"answers": json.dumps(payload.answers), "questionnaire_status": "submitted" if payload.mode == "submit" else "draft",
           "status": next_status, "revision": next_revision, "id": app_id})
    session.commit()
    return envelope({"answers": payload.answers, "questionnaire_status": "submitted" if payload.mode == "submit" else "draft",
                     "content_revision": next_revision})


@router.get("/applications/{app_id}/participants")
def list_participants(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    owned_application(session, app_id, current_user.id)
    return envelope(rows(session, """
        SELECT id, participant_code, role_code, display_name, created_at, updated_at
        FROM application_participants WHERE application_id = :id ORDER BY created_at
    """, {"id": app_id}))


@router.post("/applications/{app_id}/participants", status_code=status.HTTP_201_CREATED)
def add_participant(app_id: uuid.UUID, payload: ParticipantCreate, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    require_revision(app, payload.expected_revision)
    count = one(session, "SELECT count(*) AS count FROM application_participants WHERE application_id = :id", {"id": app_id})["count"]
    participant = {"id": uuid.uuid4(), "participant_code": f"P{count + 1:03d}", "role_code": payload.role_code,
                   "display_name": payload.display_name}
    session.execute(text("""
        INSERT INTO application_participants(id, application_id, participant_code, role_code, display_name, identity_payload)
        VALUES (:id, :app_id, :code, :role, :name, CAST(:identity AS jsonb))
    """), {"id": participant["id"], "app_id": app_id, "code": participant["participant_code"], "role": payload.role_code,
           "name": payload.display_name, "identity": json.dumps(payload.identity_payload)})
    session.execute(text("UPDATE applications SET content_revision = content_revision + 1, updated_at = now() WHERE id = :id"), {"id": app_id})
    session.commit()
    return envelope({"participant": participant, "content_revision": app["content_revision"] + 1})


@router.get("/applications/{app_id}/checklist")
def get_checklist(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    items = rows(session, """
        SELECT mr.id AS requirement_id, mr.requirement_code, mr.name, mr.requirement_level,
          mr.submission_mode, mr.provider_role, mr.alternative_group_code, mr.sort_order,
          pi.declaration AS preparation_declaration
        FROM material_requirements mr
        LEFT JOIN application_preparation_items pi ON pi.requirement_id = mr.id
          AND pi.application_id = :app_id AND pi.participant_id IS NULL
        WHERE mr.matter_version_id = :version_id ORDER BY mr.sort_order, mr.requirement_code
    """, {"app_id": app_id, "version_id": app["matter_version_id"]})
    return envelope({"items": items, "alternative_groups": [], "unknown_conditions": [],
                     "content_revision": app["content_revision"]})


@router.put("/applications/{app_id}/preparation-items")
def update_preparation_item(app_id: uuid.UUID, payload: PreparationItemUpdate, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    require_revision(app, payload.expected_revision)
    requirement = one(session, """
        SELECT submission_mode FROM material_requirements WHERE id = :requirement_id
          AND matter_version_id = :version_id
    """, {"requirement_id": payload.requirement_id, "version_id": app["matter_version_id"]})
    if not requirement:
        raise HTTPException(status_code=404, detail="该材料要求不属于当前办件版本")
    if requirement["submission_mode"] == "user_upload" and payload.declaration == "ready":
        raise HTTPException(status_code=409, detail="需上传的材料不能仅以“已准备”声明替代")
    if payload.participant_id:
        participant = one(session, "SELECT id FROM application_participants WHERE id = :id AND application_id = :app_id", {"id": payload.participant_id, "app_id": app_id})
        if not participant:
            raise HTTPException(status_code=404, detail="参与人不属于当前办件")
    # Two partial unique indexes make the NULL and non-NULL cases unambiguous.
    if payload.participant_id:
        session.execute(text("""
          INSERT INTO application_preparation_items(id, application_id, matter_version_id, requirement_id, participant_id, declaration, declared_by)
          VALUES (:id, :app, :version, :requirement, :participant, :declaration, :user)
          ON CONFLICT (application_id, requirement_id, participant_id) WHERE participant_id IS NOT NULL
          DO UPDATE SET declaration = EXCLUDED.declaration, declared_by = EXCLUDED.declared_by, updated_at = now()
        """), {"id": uuid.uuid4(), "app": app_id, "version": app["matter_version_id"], "requirement": payload.requirement_id,
               "participant": payload.participant_id, "declaration": payload.declaration, "user": current_user.id})
    else:
        session.execute(text("""
          INSERT INTO application_preparation_items(id, application_id, matter_version_id, requirement_id, declaration, declared_by)
          VALUES (:id, :app, :version, :requirement, :declaration, :user)
          ON CONFLICT (application_id, requirement_id) WHERE participant_id IS NULL
          DO UPDATE SET declaration = EXCLUDED.declaration, declared_by = EXCLUDED.declared_by, updated_at = now()
        """), {"id": uuid.uuid4(), "app": app_id, "version": app["matter_version_id"], "requirement": payload.requirement_id,
               "declaration": payload.declaration, "user": current_user.id})
    session.execute(text("UPDATE applications SET content_revision = content_revision + 1, updated_at = now() WHERE id = :id"), {"id": app_id})
    session.commit()
    return envelope({"requirement_id": payload.requirement_id, "participant_id": payload.participant_id,
                     "declaration": payload.declaration, "content_revision": app["content_revision"] + 1})
