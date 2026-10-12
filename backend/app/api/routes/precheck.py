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
    MatterVersionPublish,
    MatterStatusConfigUpdate,
    MaterialAcquisitionMethodCreate,
    MaterialAcquisitionMethodUpdate,
    MaterialRequirementCreate,
    MaterialRequirementUpdate,
    PolicySourceConfigUpdate,
    ParticipantCreate,
    PreparationItemUpdate,
    ReviewSectionUpdate,
    ServiceLocationConfigUpdate,
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


def require_administrator(current_user: CurrentUser) -> None:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="仅管理员可以审核和发布事项")


@router.get("/admin/matter-versions/drafts")
def list_draft_matter_versions(
    session: SessionDep, current_user: CurrentUser
) -> dict:
    """Return the complete review context for administrator-held draft versions."""
    require_administrator(current_user)
    versions = rows(session, """
        SELECT mv.id AS version_id, mv.version_no, mv.status, mv.config_revision,
          mv.change_summary, mv.metadata_json, mv.created_at, mv.updated_at,
          sm.id AS matter_id, sm.code AS matter_code, sm.official_code,
          sm.name AS matter_name, sm.region_code, sm.region_name, sm.description,
          sl.id AS location_id, sl.name AS location_name, sl.address, sl.source_id,
          sl.phone, sl.opening_hours, sl.official_entry_url,
          sl.verification_status AS location_verification_status, sl.checked_at AS location_checked_at,
          ps.id AS source_id, ps.title AS source_title, ps.url AS source_url,
          ps.publisher AS source_publisher,
          ps.verification_status AS source_verification_status,
          COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
              'id', mr.id, 'name', mr.name, 'requirement_code', mr.requirement_code,
              'level', mr.requirement_level, 'submission_mode', mr.submission_mode,
              'format_requirements', mr.format_requirements,
              'verification_status', mr.verification_status,
              'material_type_id', mt.id,
              'material_type', mt.name
            ) ORDER BY mr.sort_order, mr.requirement_code)
            FROM material_requirements mr
            JOIN material_types mt ON mt.id = mr.material_type_id
            WHERE mr.matter_version_id = mv.id
          ), '[]'::jsonb) AS materials,
          COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
              'id', mam.id, 'requirement_id', mr.id, 'material_name', mr.name,
              'title', mam.title, 'method_type', mam.method_type,
              'steps', mam.steps, 'entry_url', mam.entry_url,
              'verification_status', mam.verification_status
            ) ORDER BY mam.sort_order, mam.method_code)
            FROM material_acquisition_methods mam
            JOIN material_requirements mr ON mr.id = mam.requirement_id
            WHERE mr.matter_version_id = mv.id
          ), '[]'::jsonb) AS acquisition_methods
        FROM matter_versions mv
        JOIN service_matters sm ON sm.id = mv.matter_id
        LEFT JOIN service_locations sl ON sl.id = mv.service_location_id
        LEFT JOIN policy_sources ps ON ps.id = sl.source_id
        WHERE mv.status = 'draft'
        ORDER BY mv.created_at ASC, sm.name
    """)
    return envelope({"items": versions, "count": len(versions)})


@router.get("/admin/matter-versions/finished")
def list_finished_matter_versions(
    session: SessionDep, current_user: CurrentUser
) -> dict:
    """List administrator-visible matter versions that have completed review."""
    require_administrator(current_user)
    versions = rows(session, """
        SELECT mv.id AS version_id, mv.version_no, mv.status, mv.published_at,
          mv.source_checked_at, mv.config_revision,
          sm.id AS matter_id, sm.code, sm.official_code, sm.name,
          sm.region_code, sm.region_name, sm.description,
          sl.name AS location_name, sl.address, sl.phone,
          (SELECT count(*) FROM material_requirements mr
            WHERE mr.matter_version_id = mv.id) AS material_count,
          (SELECT count(*) FROM material_acquisition_methods mam
            JOIN material_requirements mr ON mr.id = mam.requirement_id
            WHERE mr.matter_version_id = mv.id) AS acquisition_method_count
        FROM matter_versions mv
        JOIN service_matters sm ON sm.id = mv.matter_id
        LEFT JOIN service_locations sl ON sl.id = mv.service_location_id
        WHERE mv.status = 'finished'
        ORDER BY mv.published_at DESC NULLS LAST, sm.name
    """)
    return envelope({"items": versions, "count": len(versions)})


@router.post("/admin/matter-versions/{version_id}/publish")
def publish_matter_version(
    version_id: uuid.UUID,
    payload: MatterVersionPublish,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict:
    """Release a fully verified draft with optimistic locking on configuration revision."""
    require_administrator(current_user)
    verification = one(session, """
        SELECT
          EXISTS(
            SELECT 1 FROM service_locations sl
            JOIN policy_sources ps ON ps.id = sl.source_id
            WHERE sl.id = mv.service_location_id AND ps.verification_status = 'verified'
          ) AS source_verified,
          EXISTS(
            SELECT 1 FROM service_locations sl
            WHERE sl.id = mv.service_location_id AND sl.verification_status = 'verified'
          ) AS location_verified,
          EXISTS(SELECT 1 FROM material_requirements mr WHERE mr.matter_version_id = mv.id)
            AND NOT EXISTS(
              SELECT 1 FROM material_requirements mr
              WHERE mr.matter_version_id = mv.id AND mr.verification_status <> 'verified'
            ) AS materials_verified,
          EXISTS(
            SELECT 1 FROM material_acquisition_methods mam
            JOIN material_requirements mr ON mr.id = mam.requirement_id
            WHERE mr.matter_version_id = mv.id
          ) AND NOT EXISTS(
            SELECT 1 FROM material_acquisition_methods mam
            JOIN material_requirements mr ON mr.id = mam.requirement_id
            WHERE mr.matter_version_id = mv.id AND mam.verification_status <> 'verified'
          ) AS acquisition_verified
        FROM matter_versions mv WHERE mv.id = :version_id
    """, {"version_id": version_id})
    if not verification:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    unfinished = []
    if not verification["source_verified"]:
        unfinished.append("官方网页与来源")
    if not verification["location_verified"]:
        unfinished.append("办理地点与联系电话")
    if not verification["materials_verified"]:
        unfinished.append("材料要求")
    if not verification["acquisition_verified"]:
        unfinished.append("材料获取方式与线上渠道")
    if unfinished:
        raise HTTPException(status_code=409, detail=f"无法发布，以下内容尚未核验为 verified：{'、'.join(unfinished)}")
    published = one(session, """
        UPDATE matter_versions
        SET status = 'finished', approved_by = :administrator_id, published_at = now(),
          source_checked_at = now(), config_revision = config_revision + 1,
          updated_at = now()
        WHERE id = :version_id AND status = 'draft'
          AND config_revision = :expected_config_revision
        RETURNING id, matter_id, version_no, status, config_revision, published_at
    """, {
        "version_id": version_id,
        "administrator_id": current_user.id,
        "expected_config_revision": payload.expected_config_revision,
    })
    if not published:
        version = one(session, "SELECT status, config_revision FROM matter_versions WHERE id = :id", {"id": version_id})
        if not version:
            raise HTTPException(status_code=404, detail="事项版本不存在")
        if version["status"] != "draft":
            raise HTTPException(status_code=409, detail="该事项版本不是待审核草稿，不能再次发布")
        raise HTTPException(status_code=409, detail="事项配置已被其他管理员修改，请刷新后重新核对")
    session.commit()
    return envelope(published)


@router.patch("/admin/matter-versions/{version_id}/review-sections/{section}")
def update_review_section_note(
    version_id: uuid.UUID, section: str, payload: ReviewSectionUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Save a concise administrator review note for one configured section."""
    require_administrator(current_user)
    allowed_sections = {"status", "source", "location", "materials", "acquisition"}
    if section not in allowed_sections:
        raise HTTPException(status_code=404, detail="不存在的审核区块")
    version = one(session, "SELECT metadata_json, config_revision, status FROM matter_versions WHERE id = :id", {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["status"] != "draft":
        raise HTTPException(status_code=409, detail="仅草稿事项可以编辑审核备注")
    if version["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    metadata = dict(version["metadata_json"] or {})
    notes = dict(metadata.get("review_notes") or {})
    notes[section] = payload.note.strip()
    metadata["review_notes"] = notes
    updated = one(session, """
        UPDATE matter_versions SET metadata_json = CAST(:metadata AS jsonb),
          config_revision = config_revision + 1, updated_at = now()
        WHERE id = :id AND config_revision = :revision
        RETURNING config_revision
    """, {"id": version_id, "revision": payload.expected_config_revision,
           "metadata": json.dumps(metadata, ensure_ascii=False)})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    session.commit()
    return envelope({"section": section, "note": notes[section], "config_revision": updated["config_revision"]})


@router.patch("/admin/matter-versions/{version_id}/status-config")
def update_matter_status_config(
    version_id: uuid.UUID, payload: MatterStatusConfigUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Edit the public-facing acceptance scope of a draft matter version."""
    require_administrator(current_user)
    version = one(session, "SELECT metadata_json, config_revision, status FROM matter_versions WHERE id = :id", {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["status"] != "draft" or version["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项状态或配置已更新，请刷新后重试")
    metadata = dict(version["metadata_json"] or {})
    metadata["acceptance_condition_raw"] = payload.acceptance_condition_raw.strip()
    metadata["channels"] = [value.strip() for value in payload.channels if value.strip()]
    metadata["uncertainties"] = [value.strip() for value in payload.uncertainties if value.strip()]
    updated = one(session, """
        UPDATE matter_versions SET metadata_json = CAST(:metadata AS jsonb),
          config_revision = config_revision + 1, updated_at = now()
        WHERE id = :id AND config_revision = :revision
        RETURNING config_revision, metadata_json
    """, {"id": version_id, "revision": payload.expected_config_revision,
           "metadata": json.dumps(metadata, ensure_ascii=False)})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    session.commit()
    return envelope(updated)


@router.patch("/admin/matter-versions/{version_id}/source-config")
def update_policy_source_config(
    version_id: uuid.UUID, payload: PolicySourceConfigUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Edit the publisher and portal URL associated with a draft matter version."""
    require_administrator(current_user)
    version = one(session, """
        SELECT mv.config_revision, mv.status, sl.source_id
        FROM matter_versions mv LEFT JOIN service_locations sl ON sl.id = mv.service_location_id
        WHERE mv.id = :id
    """, {"id": version_id})
    if not version or not version["source_id"]:
        raise HTTPException(status_code=404, detail="事项版本未关联可编辑的官方来源")
    if version["status"] != "draft" or version["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项状态或配置已更新，请刷新后重试")
    session.execute(text("""
        UPDATE policy_sources SET publisher = :publisher, url = :url
        WHERE id = :source_id
    """), {"publisher": payload.publisher.strip() or None, "url": payload.url.strip(), "source_id": version["source_id"]})
    updated = one(session, """
        UPDATE matter_versions SET config_revision = config_revision + 1, updated_at = now()
        WHERE id = :id AND config_revision = :revision
        RETURNING config_revision
    """, {"id": version_id, "revision": payload.expected_config_revision})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    session.commit()
    return envelope({"publisher": payload.publisher.strip(), "url": payload.url.strip(), "config_revision": updated["config_revision"]})


@router.patch("/admin/matter-versions/{version_id}/location-config")
def update_service_location_config(
    version_id: uuid.UUID, payload: ServiceLocationConfigUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Edit the service-location fields linked to one draft matter version."""
    require_administrator(current_user)
    version = one(session, "SELECT config_revision, status, service_location_id FROM matter_versions WHERE id = :id", {"id": version_id})
    if not version or not version["service_location_id"]:
        raise HTTPException(status_code=404, detail="事项版本未关联可编辑的办理地点")
    if version["status"] != "draft" or version["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项状态或配置已更新，请刷新后重试")
    if payload.source_id and not one(session, "SELECT id FROM policy_sources WHERE id = :id", {"id": payload.source_id}):
        raise HTTPException(status_code=404, detail="指定的信息来源不存在")
    session.execute(text("""
        UPDATE service_locations SET name = :name, address = :address, phone = :phone,
          opening_hours = :opening_hours, official_entry_url = :official_entry_url,
          verification_status = :verification_status, checked_at = :checked_at,
          source_id = :source_id
        WHERE id = :location_id
    """), {
        "location_id": version["service_location_id"], "name": payload.name.strip(),
        "address": payload.address.strip() if payload.address else None,
        "phone": payload.phone.strip() if payload.phone else None,
        "opening_hours": payload.opening_hours.strip() if payload.opening_hours else None,
        "official_entry_url": payload.official_entry_url.strip() if payload.official_entry_url else None,
        "verification_status": payload.verification_status, "checked_at": payload.checked_at,
        "source_id": payload.source_id,
    })
    updated = one(session, """
        UPDATE matter_versions SET config_revision = config_revision + 1, updated_at = now()
        WHERE id = :id AND config_revision = :revision RETURNING config_revision
    """, {"id": version_id, "revision": payload.expected_config_revision})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    session.commit()
    return envelope({"config_revision": updated["config_revision"]})


def draft_version_for_material_change(session: SessionDep, version_id: uuid.UUID, revision: int) -> dict:
    version = one(session, "SELECT id, config_revision, status FROM matter_versions WHERE id = :id", {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["status"] != "draft" or version["config_revision"] != revision:
        raise HTTPException(status_code=409, detail="事项状态或配置已更新，请刷新后重试")
    return version


def advance_material_config_revision(session: SessionDep, version_id: uuid.UUID, revision: int) -> None:
    updated = one(session, """
        UPDATE matter_versions SET config_revision = config_revision + 1, updated_at = now()
        WHERE id = :id AND config_revision = :revision RETURNING config_revision
    """, {"id": version_id, "revision": revision})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")


@router.post("/admin/matter-versions/{version_id}/material-requirements", status_code=status.HTTP_201_CREATED)
def create_material_requirement(
    version_id: uuid.UUID, payload: MaterialRequirementCreate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    require_administrator(current_user)
    draft_version_for_material_change(session, version_id, payload.expected_config_revision)
    if not one(session, "SELECT id FROM material_types WHERE id = :id", {"id": payload.material_type_id}):
        raise HTTPException(status_code=404, detail="材料类型不存在")
    requirement_id = uuid.uuid4()
    code = f"custom_{requirement_id.hex[:16]}"
    session.execute(text("""
        INSERT INTO material_requirements(
          id, matter_version_id, material_type_id, requirement_code, name,
          requirement_level, provider_role, submission_mode, format_requirements
        ) VALUES (:id, :version_id, :type_id, :code, :name, :level, 'applicant', 'user_upload', :format)
    """), {"id": requirement_id, "version_id": version_id, "type_id": payload.material_type_id,
           "code": code, "name": payload.name.strip(), "level": payload.requirement_level,
           "format": payload.format_requirements.strip() if payload.format_requirements else None})
    advance_material_config_revision(session, version_id, payload.expected_config_revision)
    session.commit()
    return envelope({"id": requirement_id, "name": payload.name.strip(), "verification_status": "pending"})


@router.patch("/admin/matter-versions/{version_id}/material-requirements/{requirement_id}")
def update_material_requirement(
    version_id: uuid.UUID, requirement_id: uuid.UUID, payload: MaterialRequirementUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    require_administrator(current_user)
    draft_version_for_material_change(session, version_id, payload.expected_config_revision)
    changed = one(session, """
        UPDATE material_requirements SET name = :name, requirement_level = :level,
          format_requirements = :format, verification_status = 'pending',
          verified_by = NULL, verified_at = NULL
        WHERE id = :id AND matter_version_id = :version_id
        RETURNING id
    """, {"id": requirement_id, "version_id": version_id, "name": payload.name.strip(),
           "level": payload.requirement_level,
           "format": payload.format_requirements.strip() if payload.format_requirements else None})
    if not changed:
        raise HTTPException(status_code=404, detail="材料要求不属于当前事项版本")
    advance_material_config_revision(session, version_id, payload.expected_config_revision)
    session.commit()
    return envelope({"id": requirement_id, "verification_status": "pending"})


@router.delete("/admin/matter-versions/{version_id}/material-requirements/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material_requirement(
    version_id: uuid.UUID, requirement_id: uuid.UUID, *,
    expected_config_revision: int = Query(gt=0), session: SessionDep, current_user: CurrentUser,
) -> None:
    require_administrator(current_user)
    draft_version_for_material_change(session, version_id, expected_config_revision)
    linked = one(session, """
        SELECT EXISTS(SELECT 1 FROM application_documents WHERE requirement_id = :id)
          OR EXISTS(SELECT 1 FROM issue_evidence WHERE requirement_id = :id) AS exists
    """, {"id": requirement_id})
    if linked and linked["exists"]:
        raise HTTPException(status_code=409, detail="该材料要求已有办件材料或历史证据，不能删除")
    session.execute(text("DELETE FROM material_acquisition_methods WHERE requirement_id = :id"), {"id": requirement_id})
    deleted = session.execute(text("DELETE FROM material_requirements WHERE id = :id AND matter_version_id = :version_id"), {"id": requirement_id, "version_id": version_id})
    if deleted.rowcount != 1:
        raise HTTPException(status_code=404, detail="材料要求不属于当前事项版本")
    advance_material_config_revision(session, version_id, expected_config_revision)
    session.commit()


def requirement_belongs_to_version(session: SessionDep, requirement_id: uuid.UUID, version_id: uuid.UUID) -> None:
    if not one(session, "SELECT id FROM material_requirements WHERE id = :id AND matter_version_id = :version_id", {"id": requirement_id, "version_id": version_id}):
        raise HTTPException(status_code=404, detail="关联材料不属于当前事项版本")


@router.post("/admin/matter-versions/{version_id}/acquisition-methods", status_code=status.HTTP_201_CREATED)
def create_material_acquisition_method(
    version_id: uuid.UUID, payload: MaterialAcquisitionMethodCreate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Create one material acquisition method for a draft matter version."""
    require_administrator(current_user)
    draft_version_for_material_change(session, version_id, payload.expected_config_revision)
    requirement_belongs_to_version(session, payload.requirement_id, version_id)
    method_id = uuid.uuid4()
    session.execute(text("""
        INSERT INTO material_acquisition_methods(
          id, requirement_id, method_code, method_type, title, steps, entry_url
        ) VALUES (:id, :requirement_id, :code, :method_type, :title, :steps, :entry_url)
    """), {"id": method_id, "requirement_id": payload.requirement_id,
           "code": f"custom_{method_id.hex[:16]}", "method_type": payload.method_type,
           "title": payload.title.strip(), "steps": payload.steps.strip() if payload.steps else None,
           "entry_url": payload.entry_url.strip() if payload.entry_url else None})
    advance_material_config_revision(session, version_id, payload.expected_config_revision)
    session.commit()
    return envelope({"id": method_id, "verification_status": "pending"})


@router.patch("/admin/matter-versions/{version_id}/acquisition-methods/{method_id}")
def update_material_acquisition_method(
    version_id: uuid.UUID, method_id: uuid.UUID, payload: MaterialAcquisitionMethodUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Update one acquisition method and require it to be verified again."""
    require_administrator(current_user)
    draft_version_for_material_change(session, version_id, payload.expected_config_revision)
    requirement_belongs_to_version(session, payload.requirement_id, version_id)
    changed = one(session, """
        UPDATE material_acquisition_methods SET requirement_id = :requirement_id,
          method_type = :method_type, title = :title, steps = :steps, entry_url = :entry_url,
          verification_status = 'pending'
        WHERE id = :id AND requirement_id IN (
          SELECT id FROM material_requirements WHERE matter_version_id = :version_id
        ) RETURNING id
    """, {"id": method_id, "version_id": version_id, "requirement_id": payload.requirement_id,
           "method_type": payload.method_type, "title": payload.title.strip(),
           "steps": payload.steps.strip() if payload.steps else None,
           "entry_url": payload.entry_url.strip() if payload.entry_url else None})
    if not changed:
        raise HTTPException(status_code=404, detail="材料获取方式不属于当前事项版本")
    advance_material_config_revision(session, version_id, payload.expected_config_revision)
    session.commit()
    return envelope({"id": method_id, "verification_status": "pending"})


@router.delete("/admin/matter-versions/{version_id}/acquisition-methods/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material_acquisition_method(
    version_id: uuid.UUID, method_id: uuid.UUID, *, expected_config_revision: int = Query(gt=0),
    session: SessionDep, current_user: CurrentUser,
) -> None:
    require_administrator(current_user)
    draft_version_for_material_change(session, version_id, expected_config_revision)
    deleted = session.execute(text("""
        DELETE FROM material_acquisition_methods WHERE id = :id AND requirement_id IN (
          SELECT id FROM material_requirements WHERE matter_version_id = :version_id
        )
    """), {"id": method_id, "version_id": version_id})
    if deleted.rowcount != 1:
        raise HTTPException(status_code=404, detail="材料获取方式不属于当前事项版本")
    advance_material_config_revision(session, version_id, expected_config_revision)
    session.commit()


@router.post("/admin/matter-versions/{version_id}/review-sections/{section}/confirm")
def confirm_review_section(
    version_id: uuid.UUID, section: str, payload: MatterVersionPublish,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Record an administrator confirmation and update the related verification flag."""
    require_administrator(current_user)
    allowed_sections = {"status", "source", "location", "materials", "acquisition"}
    if section not in allowed_sections:
        raise HTTPException(status_code=404, detail="不存在的审核区块")
    version = one(session, """
        SELECT mv.metadata_json, mv.config_revision, mv.status, mv.service_location_id
        FROM matter_versions mv WHERE mv.id = :id
    """, {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["status"] != "draft" or version["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项状态或配置已更新，请刷新后重试")
    if section == "source":
        session.execute(text("""
            UPDATE policy_sources SET verification_status = 'verified', verified_by = :user_id, verified_at = now()
            WHERE id = (SELECT source_id FROM service_locations WHERE id = :location_id)
        """), {"user_id": current_user.id, "location_id": version["service_location_id"]})
    elif section == "location":
        session.execute(text("""
            UPDATE service_locations SET verification_status = 'verified', checked_at = now()
            WHERE id = :location_id
        """), {"location_id": version["service_location_id"]})
    elif section == "acquisition":
        session.execute(text("""
            UPDATE material_acquisition_methods SET verification_status = 'verified'
            WHERE requirement_id IN (SELECT id FROM material_requirements WHERE matter_version_id = :version_id)
        """), {"version_id": version_id})
    elif section == "materials":
        session.execute(text("""
            UPDATE material_requirements
            SET verification_status = 'verified', verified_by = :user_id, verified_at = now()
            WHERE matter_version_id = :version_id
        """), {"version_id": version_id, "user_id": current_user.id})
    metadata = dict(version["metadata_json"] or {})
    confirmations = dict(metadata.get("review_confirmations") or {})
    confirmations[section] = {"confirmed_by": str(current_user.id), "confirmed_at": datetime.now(UTC).isoformat()}
    metadata["review_confirmations"] = confirmations
    updated = one(session, """
        UPDATE matter_versions SET metadata_json = CAST(:metadata AS jsonb),
          config_revision = config_revision + 1, updated_at = now()
        WHERE id = :id AND config_revision = :revision
        RETURNING config_revision
    """, {"id": version_id, "revision": payload.expected_config_revision,
           "metadata": json.dumps(metadata, ensure_ascii=False)})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    session.commit()
    return envelope({"section": section, "config_revision": updated["config_revision"]})


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
          WHERE matter_id = sm.id AND status IN ('finished', 'published')
          ORDER BY version_no DESC LIMIT 1
        ) mv ON true
        WHERE {' AND '.join(clauses)}
        ORDER BY sm.region_name, sm.name
    """, params))


@router.get("/matters/search")
def search_matters(
    session: SessionDep,
    q: str = Query(default="", max_length=100),
) -> dict:
    """Search published matters and their public material-guide configuration.

    A keyword may match the matter itself, its region, a material requirement,
    an acquisition guide, a published location, or a verified source. Draft
    versions are intentionally excluded from this public endpoint.
    """
    keyword = q.strip()
    params = {"pattern": f"%{keyword}%"}
    cards = rows(session, """
        SELECT sm.id, sm.code, sm.name, sm.region_code, sm.region_name AS region,
          sm.description, mv.id AS version_id, mv.version_no,
          COALESCE(sl.name, '办理地点待确认') AS location,
          COALESCE(mv.source_checked_at, mv.updated_at)::date AS checked_at,
          CASE
            WHEN mv.metadata_json ->> 'online_precheck_available' = 'true' THEN true
            WHEN mv.metadata_json ->> 'configuration_kind' = 'synthetic_pilot' THEN true
            ELSE false
          END AS supported,
          (SELECT count(*) FROM material_requirements mr
            WHERE mr.matter_version_id = mv.id) AS material_count
        FROM service_matters sm
        JOIN LATERAL (
          SELECT * FROM matter_versions
          WHERE matter_id = sm.id AND status IN ('finished', 'published')
          ORDER BY version_no DESC LIMIT 1
        ) mv ON true
        LEFT JOIN service_locations sl ON sl.id = mv.service_location_id
        WHERE sm.is_active = true
          AND (
            :pattern = '%%'
            OR sm.name ILIKE :pattern
            OR sm.code ILIKE :pattern
            OR sm.region_name ILIKE :pattern
            OR sm.region_code ILIKE :pattern
            OR COALESCE(sl.name, '') ILIKE :pattern
            OR COALESCE(sl.address, '') ILIKE :pattern
            OR EXISTS (
              SELECT 1 FROM material_requirements mr
              JOIN material_types mt ON mt.id = mr.material_type_id
              LEFT JOIN policy_sources ps ON ps.id = mr.template_source_id
                AND ps.verification_status = 'verified'
              WHERE mr.matter_version_id = mv.id AND (
                mr.name ILIKE :pattern OR mr.requirement_code ILIKE :pattern
                OR mt.name ILIKE :pattern OR COALESCE(ps.title, '') ILIKE :pattern
                OR COALESCE(ps.content_text, '') ILIKE :pattern
              )
            )
            OR EXISTS (
              SELECT 1 FROM material_acquisition_methods mam
              LEFT JOIN policy_sources ps ON ps.id = mam.source_id
                AND ps.verification_status = 'verified'
              WHERE mam.requirement_id IN (
                SELECT id FROM material_requirements WHERE matter_version_id = mv.id
              ) AND (
                mam.title ILIKE :pattern OR COALESCE(mam.steps, '') ILIKE :pattern
                OR COALESCE(ps.title, '') ILIKE :pattern
              )
            )
          )
        ORDER BY sm.region_name, sm.name
    """, params)
    return envelope({"items": cards, "count": len(cards), "keyword": keyword})


@router.get("/matters/{matter_id}")
def get_matter(matter_id: uuid.UUID, session: SessionDep) -> dict:
    matter = one(session, """
        SELECT sm.id, sm.code, sm.official_code, sm.name, sm.region_code, sm.region_name,
               sm.description, mv.id AS version_id, mv.version_no, mv.valid_from, mv.valid_to,
               mv.metadata_json,
               sl.name AS location_name, sl.address, sl.phone, sl.opening_hours, sl.official_entry_url
        FROM service_matters sm JOIN matter_versions mv ON mv.matter_id = sm.id
        LEFT JOIN service_locations sl ON sl.id = mv.service_location_id
        WHERE sm.id = :id AND sm.is_active = true AND mv.status IN ('finished', 'published')
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
        WHERE mv.id = :version_id AND mv.status IN ('finished', 'published') AND sm.is_active = true
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
          AND status IN ('finished', 'published')
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
