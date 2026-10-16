"""P0 resident-facing API for the government-material precheck domain.

The database uses immutable matter versions.  This module deliberately queries
those tables directly instead of duplicating them into the template's generic
``Item`` model.
"""

import hashlib
import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
import httpx
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from sqlalchemy import text

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.schemas.precheck import (
    ApplicationCreate,
    ApplicationDisplayNameUpdate,
    CaseReviewComplete,
    DelegationPolicyUpdate,
    ExtraMaterialPreparationUpdate,
    MaterialReviewStart,
    QuestionnaireSubmit,
    MatterDisable,
    GovernmentDetailsConfirm,
    GovernmentDetailsUpdate,
    MatterNameUpdate,
    MatterVersionDraftCopy,
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
from app.services.operation_audit import write_operation_audit
from app.services.material_review import review_cloud_material_files, review_materials
from app.services.matter_import import MatterImportModelError

router = APIRouter(tags=["政务材料预审"])

APPLICATION_UPLOAD_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".docx", ".txt"}
MAX_APPLICATION_FILE_SIZE = 10 * 1024 * 1024
MAX_APPLICATION_TOTAL_UPLOAD_SIZE = 30 * 1024 * 1024


def envelope(data: Any) -> dict[str, Any]:
    return {"data": data}


def rows(session: SessionDep, statement: str, params: dict | None = None) -> list[dict]:
    return [dict(row) for row in session.execute(text(statement), params or {}).mappings()]


def one(session: SessionDep, statement: str, params: dict | None = None) -> dict | None:
    result = rows(session, statement, params)
    return result[0] if result else None


def checklist_for_review(session: SessionDep, app: dict) -> list[dict]:
    """Return all resident checklist items with their active uploaded files."""
    return rows(session, """
      SELECT 'requirement' AS item_kind, mr.id AS material_id, mr.name, pi.declaration,
        COALESCE(jsonb_agg(jsonb_build_object('file_id', dvf.id, 'document_version_id', dv.id,
          'storage_key', dvf.storage_key, 'filename', dvf.original_filename, 'mime_type', dvf.mime_type)
          ORDER BY dvf.file_order) FILTER (WHERE dvf.id IS NOT NULL), '[]'::jsonb) AS files
      FROM material_requirements mr
      LEFT JOIN application_preparation_items pi ON pi.application_id = :app_id AND pi.requirement_id = mr.id AND pi.participant_id IS NULL
      LEFT JOIN application_documents ad ON ad.application_id = :app_id AND ad.requirement_id = mr.id
      LEFT JOIN document_versions dv ON dv.document_id = ad.id AND dv.status = 'active'
      LEFT JOIN document_version_files dvf ON dvf.document_version_id = dv.id AND dvf.availability = 'available'
      WHERE mr.matter_version_id = :version_id GROUP BY mr.id, mr.name, pi.declaration
      UNION ALL
      SELECT 'extra' AS item_kind, aem.id AS material_id, aem.name, aem.declaration,
        COALESCE(jsonb_agg(jsonb_build_object('file_id', dvf.id, 'document_version_id', dv.id,
          'storage_key', dvf.storage_key, 'filename', dvf.original_filename, 'mime_type', dvf.mime_type)
          ORDER BY dvf.file_order) FILTER (WHERE dvf.id IS NOT NULL), '[]'::jsonb) AS files
      FROM application_extra_materials aem
      LEFT JOIN application_documents ad ON ad.application_id = :app_id AND ad.document_code = 'extra-' || aem.id::text
      LEFT JOIN document_versions dv ON dv.document_id = ad.id AND dv.status = 'active'
      LEFT JOIN document_version_files dvf ON dvf.document_version_id = dv.id AND dvf.availability = 'available'
      WHERE aem.application_id = :app_id AND aem.material_code <> 'agent_identity_card'
      GROUP BY aem.id, aem.name, aem.declaration
    """, {"app_id": app["id"], "version_id": app["matter_version_id"]})


def package_snapshot(session: SessionDep, app: dict) -> tuple[dict, list[str]]:
    """Freeze only active originals after every checklist item has passed."""
    items = checklist_for_review(session, app)
    decisions = latest_staff_material_decisions(session, app["id"])
    blocked: list[str] = []
    material_rows: list[dict] = []
    for item in items:
        latest_model = one(session, """SELECT model_result_json FROM check_runs
          WHERE application_id = :app_id AND config_snapshot->>'purpose' = 'single_material'
            AND config_snapshot->>'material_id' = :material_id
          ORDER BY run_no DESC LIMIT 1""", {"app_id": app["id"], "material_id": str(item["material_id"])})
        human_pass = decisions.get(item["name"], {}).get("decision") == "pass"
        model_pass = ((latest_model or {}).get("model_result_json") or {}).get("decision") == "pass"
        if not item["files"] or not (human_pass or model_pass):
            blocked.append(item["name"])
        material_rows.append({"name": item["name"], "item_kind": item["item_kind"],
                              "passed_by": "human" if human_pass else "model" if model_pass else None,
                              "files": item["files"]})
    info = one(session, """SELECT a.application_no, a.content_revision, sm.name AS matter_name,
      sm.region_name, mv.version_no, sl.name AS location_name, sl.address, sl.phone, sl.opening_hours,
      COALESCE(sl.official_entry_url, ps.url) AS guide_url
      FROM applications a JOIN matter_versions mv ON mv.id = a.matter_version_id
      JOIN service_matters sm ON sm.id = mv.matter_id
      LEFT JOIN service_locations sl ON sl.id = mv.service_location_id
      LEFT JOIN policy_sources ps ON ps.id = sl.source_id WHERE a.id = :id""", {"id": app["id"]})
    participants = rows(session, """SELECT role_code, display_name FROM application_participants
      WHERE application_id = :id ORDER BY participant_code""", {"id": app["id"]})
    return {"application": info, "participants": participants, "materials": material_rows,
            "generated_at": datetime.now(UTC).isoformat()}, blocked


def package_pdf(snapshot: dict, package_id: uuid.UUID) -> bytes:
    stream = io.BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    doc = canvas.Canvas(stream, pagesize=A4)
    doc.setFont("STSong-Light", 14)
    doc.drawString(48, 800, "办前准备单（材料预审辅助）")
    doc.setFont("STSong-Light", 9)
    y = 775
    app = snapshot["application"]
    lines = [f"准备包编号：{package_id}", f"准备记录：{app['application_no']}",
             f"事项：{app['matter_name']}  地区：{app.get('region_name') or '—'}",
             f"办理地点：{app.get('location_name') or '—'}  {app.get('address') or ''}",
             f"电话：{app.get('phone') or '—'}  时间：{app.get('opening_hours') or '—'}",
             "使用说明：本单仅用于办前准备；正式受理、材料要求和办理结论以线下受理部门核验为准。",
             "携带材料清单："]
    lines += [f"- {item['name']}：已通过{'人工复核' if item['passed_by'] == 'human' else '模型检查'}，含 {len(item['files'])} 个当前文件" for item in snapshot["materials"]]
    for line in lines:
        if y < 50:
            doc.showPage(); doc.setFont("STSong-Light", 9); y = 800
        doc.drawString(48, y, line[:80]); y -= 18
    doc.save()
    return stream.getvalue()


def owned_application(session: SessionDep, app_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    app = one(
        session,
        "SELECT * FROM applications WHERE id = :id AND owner_user_id = :owner",
        {"id": app_id, "owner": user_id},
    )
    if not app:
        raise HTTPException(status_code=404, detail="办件不存在或您无权访问")
    return app


def require_open_preparation(app: dict) -> None:
    if app["status"] in {"closed", "cancelled"}:
        raise HTTPException(status_code=409, detail="该材料准备记录已结束，不能再修改")


def require_revision(app: dict, expected_revision: int) -> None:
    if app["content_revision"] != expected_revision:
        raise HTTPException(status_code=409, detail="办件内容已被更新，请刷新后重试")


def require_administrator(current_user: CurrentUser) -> None:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="仅管理员可以审核和发布事项")


def latest_staff_material_decisions(session: SessionDep, app_id: uuid.UUID) -> dict[str, dict]:
    """Return the latest staff decision recorded for every material of an application."""
    decisions = rows(session, """SELECT DISTINCT ON (entry->>'material_name')
      entry->>'material_name' AS material_name, entry->>'decision' AS decision,
      COALESCE(entry->>'note', '') AS note, rr.created_at
      FROM review_records rr
      JOIN review_tasks rt ON rt.id = rr.task_id
      CROSS JOIN LATERAL jsonb_array_elements(COALESCE(rr.details->'item_decisions', '[]'::jsonb)) AS entry
      WHERE rt.application_id = :app_id AND rt.status = 'completed'
      ORDER BY entry->>'material_name', rr.created_at DESC""", {"app_id": app_id})
    return {item["material_name"]: item for item in decisions}


@router.get("/admin/matter-versions/drafts")
def list_draft_matter_versions(
    session: SessionDep, current_user: CurrentUser,
    q: str = Query(default="", max_length=100),
) -> dict:
    """Return the complete review context for administrator-held draft versions."""
    require_administrator(current_user)
    versions = rows(session, """
        SELECT mv.id AS version_id, mv.version_no, mv.status, mv.config_revision,
          mv.change_summary, mv.metadata_json, mv.government_profile_json, mv.processing_steps_json,
          mv.legal_bases_json, mv.field_evidence_json, mv.created_at, mv.updated_at,
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
          ,(SELECT jsonb_build_object(
              'id', mdp.id,
              'delegation_allowed', mdp.delegation_allowed,
              'applicant_must_attend', mdp.applicant_must_attend,
              'relationship_required', mdp.relationship_required,
              'allowed_relationships', mdp.allowed_relationships,
              'condition_expr', mdp.condition_expr,
              'questionnaire_required', mdp.questionnaire_required,
              'verification_status', mdp.verification_status,
              'source_id', mdp.source_id,
              'materials', COALESCE((
                SELECT jsonb_agg(jsonb_build_object(
                  'id', mdmr.id, 'material_code', mdmr.material_code,
                  'name', mdmr.name, 'requirement_level', mdmr.requirement_level,
                  'submission_mode', mdmr.submission_mode,
                  'applicability_expr', mdmr.applicability_expr,
                  'sort_order', mdmr.sort_order,
                  'verification_status', mdmr.verification_status
                ) ORDER BY mdmr.sort_order, mdmr.material_code)
                FROM matter_delegation_material_requirements mdmr
                WHERE mdmr.delegation_policy_id = mdp.id
              ), '[]'::jsonb)
            ) FROM matter_delegation_policies mdp
            WHERE mdp.matter_version_id = mv.id) AS delegation_policy
        FROM matter_versions mv
        JOIN service_matters sm ON sm.id = mv.matter_id
        LEFT JOIN service_locations sl ON sl.id = mv.service_location_id
        LEFT JOIN policy_sources ps ON ps.id = sl.source_id
        WHERE mv.status = 'draft'
          AND (:pattern = '%%' OR sm.name ILIKE :pattern OR sm.code ILIKE :pattern
            OR COALESCE(sm.official_code, '') ILIKE :pattern OR sm.region_name ILIKE :pattern
            OR COALESCE(sl.name, '') ILIKE :pattern OR COALESCE(sl.address, '') ILIKE :pattern
            OR COALESCE(sm.description, '') ILIKE :pattern)
        ORDER BY mv.created_at ASC, sm.name
    """, {"pattern": f"%{q.strip()}%"})
    return envelope({"items": versions, "count": len(versions), "keyword": q.strip()})


@router.get("/admin/matter-versions/finished")
def list_finished_matter_versions(
    session: SessionDep, current_user: CurrentUser,
    q: str = Query(default="", max_length=100),
) -> dict:
    """List administrator-visible matter versions that have completed review."""
    require_administrator(current_user)
    versions = rows(session, """
        SELECT mv.id AS version_id, mv.version_no, mv.status, mv.published_at,
          mv.source_checked_at, mv.config_revision,
          sm.id AS matter_id, sm.code, sm.official_code, sm.name, sm.is_active,
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
          AND (:pattern = '%%' OR sm.name ILIKE :pattern OR sm.code ILIKE :pattern
            OR COALESCE(sm.official_code, '') ILIKE :pattern OR sm.region_name ILIKE :pattern
            OR COALESCE(sl.name, '') ILIKE :pattern OR COALESCE(sl.address, '') ILIKE :pattern
            OR COALESCE(sm.description, '') ILIKE :pattern)
        ORDER BY mv.published_at DESC NULLS LAST, sm.name
    """, {"pattern": f"%{q.strip()}%"})
    return envelope({"items": versions, "count": len(versions), "keyword": q.strip()})


@router.post("/admin/matter-versions/{version_id}/create-draft", status_code=status.HTTP_201_CREATED)
def create_draft_from_finished_version(
    version_id: uuid.UUID, payload: MatterVersionDraftCopy,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Copy a finished configuration into an isolated next draft version.

    Historical applications continue to reference the finished version.  Sources,
    locations, materials, acquisition methods and rules are duplicated so editing
    this draft cannot mutate the published configuration.
    """
    require_administrator(current_user)
    source = one(session, "SELECT * FROM matter_versions WHERE id = :id FOR UPDATE", {"id": version_id})
    if not source:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if source["status"] != "finished":
        raise HTTPException(status_code=409, detail="仅已发布 finished 版本可以创建新草稿")
    if source["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重新创建草稿")

    source_id_map: dict[uuid.UUID, uuid.UUID] = {}
    location_id_map: dict[uuid.UUID, uuid.UUID] = {}

    def clone_source(old_id: uuid.UUID | None) -> uuid.UUID | None:
        if old_id is None:
            return None
        if old_id in source_id_map:
            return source_id_map[old_id]
        old = one(session, "SELECT * FROM policy_sources WHERE id = :id", {"id": old_id})
        if not old:
            return None
        new_id = uuid.uuid4()
        session.execute(text("""
            INSERT INTO policy_sources(
              id, title, source_kind, url, publisher, published_date, retrieved_at,
              content_text, content_sha256, verification_status, verified_by, verified_at
            ) VALUES (
              :id, :title, :source_kind, :url, :publisher, :published_date, :retrieved_at,
              :content_text, :content_sha256, 'pending', NULL, NULL
            )
        """), {"id": new_id, "title": old["title"], "source_kind": old["source_kind"],
               "url": old["url"], "publisher": old["publisher"], "published_date": old["published_date"],
               "retrieved_at": old["retrieved_at"], "content_text": old["content_text"],
               "content_sha256": old["content_sha256"]})
        source_id_map[old_id] = new_id
        return new_id

    def clone_location(old_id: uuid.UUID | None) -> uuid.UUID | None:
        if old_id is None:
            return None
        if old_id in location_id_map:
            return location_id_map[old_id]
        old = one(session, "SELECT * FROM service_locations WHERE id = :id", {"id": old_id})
        if not old:
            return None
        new_id = uuid.uuid4()
        session.execute(text("""
            INSERT INTO service_locations(
              id, name, region_code, address, phone, opening_hours, official_entry_url,
              source_id, verification_status, checked_at
            ) VALUES (
              :id, :name, :region_code, :address, :phone, :opening_hours, :official_entry_url,
              :source_id, 'pending', NULL
            )
        """), {"id": new_id, "name": old["name"], "region_code": old["region_code"],
               "address": old["address"], "phone": old["phone"], "opening_hours": old["opening_hours"],
               "official_entry_url": old["official_entry_url"], "source_id": clone_source(old["source_id"])})
        location_id_map[old_id] = new_id
        return new_id

    try:
        new_version_id = uuid.uuid4()
        next_version_no = session.execute(text("""
            SELECT COALESCE(MAX(version_no), 0) + 1 FROM matter_versions WHERE matter_id = :matter_id
        """), {"matter_id": source["matter_id"]}).scalar_one()
        metadata = dict(source["metadata_json"] or {})
        metadata.pop("review_confirmations", None)
        metadata.pop("review_notes", None)
        metadata["derived_from_version_id"] = str(version_id)
        metadata["draft_copy_reason"] = "基于已发布版本创建新的待复核草稿"
        if any((source["government_profile_json"], source["processing_steps_json"], source["legal_bases_json"], source["field_evidence_json"])):
            metadata["government_details_verification_status"] = "pending"
        new_location_id = clone_location(source["service_location_id"])
        session.execute(text("""
            INSERT INTO matter_versions(
              id, matter_id, version_no, status, valid_from, valid_to, change_summary,
              service_location_id, created_by, metadata_json, government_profile_json,
              processing_steps_json, legal_bases_json, field_evidence_json, config_revision
            ) VALUES (
              :id, :matter_id, :version_no, 'draft', NULL, NULL, :summary,
              :location_id, :created_by, CAST(:metadata AS jsonb), CAST(:government_profile AS jsonb),
              CAST(:processing_steps AS jsonb), CAST(:legal_bases AS jsonb), CAST(:field_evidence AS jsonb), 1
            )
        """), {"id": new_version_id, "matter_id": source["matter_id"], "version_no": next_version_no,
               "summary": f"基于已发布第 {source['version_no']} 版创建草稿，待重新核验。",
               "location_id": new_location_id, "created_by": current_user.id,
               "metadata": json.dumps(metadata, ensure_ascii=False),
               "government_profile": json.dumps(source["government_profile_json"] or {}, ensure_ascii=False),
               "processing_steps": json.dumps(source["processing_steps_json"] or [], ensure_ascii=False),
               "legal_bases": json.dumps(source["legal_bases_json"] or [], ensure_ascii=False),
               "field_evidence": json.dumps(source["field_evidence_json"] or [], ensure_ascii=False)})

        requirement_id_map: dict[uuid.UUID, uuid.UUID] = {}
        requirements = rows(session, "SELECT * FROM material_requirements WHERE matter_version_id = :version_id", {"version_id": version_id})
        for requirement in requirements:
            new_requirement_id = uuid.uuid4()
            session.execute(text("""
                INSERT INTO material_requirements(
                  id, matter_version_id, material_type_id, requirement_code, name,
                  applicability_expr, requirement_level, provider_role, submission_mode,
                  original_required, copy_count, min_pages, format_requirements,
                  template_source_id, field_schema, sort_order, verification_status,
                  verified_by, verified_at, alternative_group_code
                ) VALUES (
                  :id, :version_id, :material_type_id, :requirement_code, :name,
                  CAST(:applicability_expr AS jsonb), :requirement_level, :provider_role, :submission_mode,
                  :original_required, :copy_count, :min_pages, :format_requirements,
                  :template_source_id, CAST(:field_schema AS jsonb), :sort_order, 'pending',
                  NULL, NULL, :alternative_group_code
                )
            """), {"id": new_requirement_id, "version_id": new_version_id,
                   "material_type_id": requirement["material_type_id"], "requirement_code": requirement["requirement_code"],
                   "name": requirement["name"], "applicability_expr": json.dumps(requirement["applicability_expr"]),
                   "requirement_level": requirement["requirement_level"], "provider_role": requirement["provider_role"],
                   "submission_mode": requirement["submission_mode"], "original_required": requirement["original_required"],
                   "copy_count": requirement["copy_count"], "min_pages": requirement["min_pages"],
                   "format_requirements": requirement["format_requirements"],
                   "template_source_id": clone_source(requirement["template_source_id"]),
                   "field_schema": json.dumps(requirement["field_schema"]), "sort_order": requirement["sort_order"],
                   "alternative_group_code": requirement.get("alternative_group_code")})
            requirement_id_map[requirement["id"]] = new_requirement_id

        methods = rows(session, """
            SELECT mam.* FROM material_acquisition_methods mam
            JOIN material_requirements mr ON mr.id = mam.requirement_id
            WHERE mr.matter_version_id = :version_id
        """, {"version_id": version_id})
        for method in methods:
            session.execute(text("""
                INSERT INTO material_acquisition_methods(
                  id, requirement_id, method_code, method_type, title, steps, entry_url,
                  location_id, source_id, applicability_expr, verification_status, sort_order
                ) VALUES (
                  :id, :requirement_id, :method_code, :method_type, :title, :steps, :entry_url,
                  :location_id, :source_id, CAST(:applicability_expr AS jsonb), 'pending', :sort_order
                )
            """), {"id": uuid.uuid4(), "requirement_id": requirement_id_map[method["requirement_id"]],
                   "method_code": method["method_code"], "method_type": method["method_type"],
                   "title": method["title"], "steps": method["steps"], "entry_url": method["entry_url"],
                   "location_id": clone_location(method["location_id"]), "source_id": clone_source(method["source_id"]),
                   "applicability_expr": json.dumps(method["applicability_expr"]), "sort_order": method["sort_order"]})

        rules = rows(session, "SELECT * FROM verification_rules WHERE matter_version_id = :version_id", {"version_id": version_id})
        for rule in rules:
            session.execute(text("""
                INSERT INTO verification_rules(
                  id, matter_version_id, rule_code, name, rule_type, applicability_expr,
                  input_spec, operator_code, parameters, on_missing, severity,
                  message_template, remedy_template, primary_source_id, source_excerpt, sort_order
                ) VALUES (
                  :id, :version_id, :rule_code, :name, :rule_type, CAST(:applicability_expr AS jsonb),
                  CAST(:input_spec AS jsonb), :operator_code, CAST(:parameters AS jsonb), :on_missing, :severity,
                  :message_template, :remedy_template, :primary_source_id, :source_excerpt, :sort_order
                )
            """), {"id": uuid.uuid4(), "version_id": new_version_id, "rule_code": rule["rule_code"],
                   "name": rule["name"], "rule_type": rule["rule_type"],
                   "applicability_expr": json.dumps(rule["applicability_expr"]), "input_spec": json.dumps(rule["input_spec"]),
                   "operator_code": rule["operator_code"], "parameters": json.dumps(rule["parameters"]),
                   "on_missing": rule["on_missing"], "severity": rule["severity"],
                   "message_template": rule["message_template"], "remedy_template": rule["remedy_template"],
                   "primary_source_id": clone_source(rule["primary_source_id"]), "source_excerpt": rule["source_excerpt"],
                   "sort_order": rule["sort_order"]})
        # Delegation is versioned too: copy the structure, but require a new
        # administrator verification before the draft can affect residents.
        delegation = one(session, "SELECT * FROM matter_delegation_policies WHERE matter_version_id = :id", {"id": version_id})
        if delegation:
            new_policy_id = uuid.uuid4()
            session.execute(text("""INSERT INTO matter_delegation_policies(
              id, matter_version_id, delegation_allowed, applicant_must_attend, relationship_required,
              allowed_relationships, condition_expr, questionnaire_required, source_id, verification_status)
              VALUES (:id, :version_id, :allowed, :must_attend, :relationship_required,
              CAST(:relationships AS jsonb), CAST(:condition AS jsonb), :questionnaire_required, :source_id, 'pending')"""),
              {"id": new_policy_id, "version_id": new_version_id, "allowed": delegation["delegation_allowed"],
               "must_attend": delegation["applicant_must_attend"], "relationship_required": delegation["relationship_required"],
               "relationships": json.dumps(delegation["allowed_relationships"]), "condition": json.dumps(delegation["condition_expr"]),
               "questionnaire_required": delegation["questionnaire_required"], "source_id": clone_source(delegation["source_id"])})
            for material in rows(session, "SELECT * FROM matter_delegation_material_requirements WHERE delegation_policy_id = :id", {"id": delegation["id"]}):
                session.execute(text("""INSERT INTO matter_delegation_material_requirements(
                  id, delegation_policy_id, material_code, name, requirement_level, submission_mode,
                  applicability_expr, sort_order, verification_status)
                  VALUES (:id, :policy_id, :code, :name, :level, :mode, CAST(:expr AS jsonb), :order, 'pending')"""),
                  {"id": uuid.uuid4(), "policy_id": new_policy_id, "code": material["material_code"],
                   "name": material["name"], "level": material["requirement_level"], "mode": material["submission_mode"],
                   "expr": json.dumps(material["applicability_expr"]), "order": material["sort_order"]})
        session.commit()
    except Exception:
        session.rollback()
        raise
    return envelope({"version_id": new_version_id, "matter_id": source["matter_id"], "version_no": next_version_no, "status": "draft"})


@router.patch("/admin/matter-versions/{version_id}/government-details")
def update_government_details(
    version_id: uuid.UUID, payload: GovernmentDetailsUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Edit imported official details and reset their verification status."""
    require_administrator(current_user)
    version = one(session, "SELECT metadata_json, config_revision, status FROM matter_versions WHERE id = :id", {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["status"] != "draft":
        raise HTTPException(status_code=409, detail="仅 draft 待审核事项可以编辑政务基础信息")
    metadata = dict(version["metadata_json"] or {})
    metadata["government_details_verification_status"] = "pending"
    updated = one(session, """
        UPDATE matter_versions SET government_profile_json = CAST(:profile AS jsonb),
          processing_steps_json = CAST(:steps AS jsonb), legal_bases_json = CAST(:bases AS jsonb),
          field_evidence_json = CAST(:evidence AS jsonb), metadata_json = CAST(:metadata AS jsonb),
          config_revision = config_revision + 1, updated_at = now()
        WHERE id = :id AND config_revision = :revision
        RETURNING config_revision
    """, {"id": version_id, "revision": payload.expected_config_revision,
           "profile": json.dumps(payload.government_profile, ensure_ascii=False),
           "steps": json.dumps(payload.processing_steps, ensure_ascii=False),
           "bases": json.dumps([item.strip() for item in payload.legal_bases if item.strip()], ensure_ascii=False),
           "evidence": json.dumps(payload.field_evidence, ensure_ascii=False),
           "metadata": json.dumps(metadata, ensure_ascii=False)})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    write_operation_audit(session, current_user.id, "matter_review", "编辑政务基础信息", "matter_version", version_id)
    session.commit()
    return envelope({"config_revision": updated["config_revision"], "verification_status": "pending"})


@router.post("/admin/matter-versions/{version_id}/government-details/confirm")
def confirm_government_details(
    version_id: uuid.UUID, payload: GovernmentDetailsConfirm,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Record an administrator's verification of imported government details."""
    require_administrator(current_user)
    version = one(session, "SELECT metadata_json, config_revision, status FROM matter_versions WHERE id = :id", {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["status"] != "draft":
        raise HTTPException(status_code=409, detail="仅 draft 待审核事项可以确认")
    metadata = dict(version["metadata_json"] or {})
    metadata["government_details_verification_status"] = "verified"
    metadata["government_details_verified_by"] = str(current_user.id)
    metadata["government_details_verified_at"] = datetime.now(UTC).isoformat()
    updated = one(session, """
        UPDATE matter_versions SET metadata_json = CAST(:metadata AS jsonb),
          config_revision = config_revision + 1, updated_at = now()
        WHERE id = :id AND config_revision = :revision
        RETURNING config_revision
    """, {"id": version_id, "revision": payload.expected_config_revision,
           "metadata": json.dumps(metadata, ensure_ascii=False)})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    write_operation_audit(session, current_user.id, "matter_review", "确认政务基础信息", "matter_version", version_id)
    session.commit()
    return envelope({"config_revision": updated["config_revision"], "verification_status": "verified"})


@router.patch("/admin/matter-versions/{version_id}/matter-name")
def update_draft_matter_name(
    version_id: uuid.UUID, payload: MatterNameUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Rename one draft while preserving a previously released version."""
    require_administrator(current_user)
    version = one(session, """
        SELECT mv.id, mv.matter_id, mv.config_revision, mv.status, sm.code, sm.official_code,
          sm.region_code, sm.region_name, sm.description
        FROM matter_versions mv JOIN service_matters sm ON sm.id = mv.matter_id
        WHERE mv.id = :id FOR UPDATE
    """, {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["status"] != "draft":
        raise HTTPException(status_code=409, detail="仅 draft 待审核事项可以修改名称")
    if version["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")

    base_name = payload.name.strip()
    # Public matter names are normalized as “region + matter”, so identical
    # service names from different districts remain distinguishable.
    name = base_name if base_name.startswith(version["region_name"]) else f"{version['region_name']}{base_name}"
    released_exists = one(session, """
        SELECT 1 FROM matter_versions WHERE matter_id = :matter_id
          AND id <> :version_id AND status IN ('finished', 'published') LIMIT 1
    """, {"matter_id": version["matter_id"], "version_id": version_id})
    matter_id = version["matter_id"]
    if released_exists:
        # service_matters.name is shared by all versions. Fork it so a draft
        # rename can never silently rename a public, historical version.
        matter_id = uuid.uuid4()
        session.execute(text("""
            INSERT INTO service_matters(id, code, official_code, name, region_code, region_name, description)
            VALUES (:id, :code, :official_code, :name, :region_code, :region_name, :description)
        """), {"id": matter_id, "code": f"{version['code']}-draft-{version_id.hex[:8]}",
               "official_code": version["official_code"], "name": name,
               "region_code": version["region_code"], "region_name": version["region_name"],
               "description": version["description"]})
        session.execute(text("""UPDATE matter_versions SET matter_id = :matter_id,
          config_revision = config_revision + 1, updated_at = now() WHERE id = :id"""),
                        {"matter_id": matter_id, "id": version_id})
    else:
        session.execute(text("""UPDATE service_matters SET name = :name, updated_at = now()
          WHERE id = :matter_id"""), {"name": name, "matter_id": matter_id})
        session.execute(text("""UPDATE matter_versions SET config_revision = config_revision + 1,
          updated_at = now() WHERE id = :id"""), {"id": version_id})
    write_operation_audit(session, current_user.id, "matter_review", "修改事项名称", "matter_version", version_id, name)
    session.commit()
    return envelope({"version_id": version_id, "matter_id": matter_id, "name": name})


@router.delete("/admin/matter-versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft_matter_version(
    version_id: uuid.UUID, session: SessionDep, current_user: CurrentUser,
) -> None:
    """Delete an unused draft and its configuration; never delete case history."""
    require_administrator(current_user)
    version = one(session, "SELECT id, matter_id, status FROM matter_versions WHERE id = :id FOR UPDATE", {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["status"] != "draft":
        raise HTTPException(status_code=409, detail="仅 draft 待审核事项可以删除；已发布事项请在事项配置中禁用")
    usage = one(session, """
        SELECT EXISTS(SELECT 1 FROM applications WHERE matter_version_id = :id)
          OR EXISTS(SELECT 1 FROM application_documents WHERE matter_version_id = :id)
          OR EXISTS(SELECT 1 FROM check_runs WHERE matter_version_id = :id)
          OR EXISTS(SELECT 1 FROM check_results WHERE matter_version_id = :id)
          OR EXISTS(SELECT 1 FROM application_preparation_items WHERE matter_version_id = :id) AS in_use
    """, {"id": version_id})
    if usage and usage["in_use"]:
        raise HTTPException(status_code=409, detail="该事项已有办件或检查记录，不能删除；如需停止使用，请在事项配置中禁用")
    session.execute(text("""DELETE FROM material_acquisition_methods WHERE requirement_id IN
      (SELECT id FROM material_requirements WHERE matter_version_id = :id)"""), {"id": version_id})
    session.execute(text("DELETE FROM verification_rules WHERE matter_version_id = :id"), {"id": version_id})
    session.execute(text("DELETE FROM material_requirements WHERE matter_version_id = :id"), {"id": version_id})
    # Keep the audit record of an import, but detach its no-longer-existing draft.
    session.execute(text("UPDATE matter_import_jobs SET matter_version_id = NULL WHERE matter_version_id = :id"), {"id": version_id})
    session.execute(text("DELETE FROM matter_versions WHERE id = :id"), {"id": version_id})
    remaining = one(session, "SELECT 1 FROM matter_versions WHERE matter_id = :matter_id LIMIT 1", {"matter_id": version["matter_id"]})
    if not remaining:
        session.execute(text("DELETE FROM service_matters WHERE id = :id"), {"id": version["matter_id"]})
    write_operation_audit(session, current_user.id, "matter_review", "删除待审核事项", "matter_version", version_id)
    session.commit()


@router.patch("/admin/matter-versions/{version_id}/disable")
def disable_matter(
    version_id: uuid.UUID, payload: MatterDisable,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Disable a matter globally without deleting versions or historical cases."""
    require_administrator(current_user)
    version = one(session, "SELECT matter_id, config_revision FROM matter_versions WHERE id = :id", {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    session.execute(text("UPDATE service_matters SET is_active = false, updated_at = now() WHERE id = :id"), {"id": version["matter_id"]})
    write_operation_audit(session, current_user.id, "matter_review", "禁用事项", "service_matter", version["matter_id"])
    session.commit()
    return envelope({"matter_id": version["matter_id"], "is_active": False})


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
          ) AS acquisition_verified,
          CASE WHEN mv.government_profile_json <> '{}'::jsonb
                 OR mv.processing_steps_json <> '[]'::jsonb
                 OR mv.legal_bases_json <> '[]'::jsonb
                 OR mv.field_evidence_json <> '[]'::jsonb
            THEN COALESCE(mv.metadata_json ->> 'government_details_verification_status', 'pending') = 'verified'
            ELSE true END AS government_details_verified,
          EXISTS(SELECT 1 FROM matter_delegation_policies mdp
            WHERE mdp.matter_version_id = mv.id AND mdp.verification_status = 'verified'
          ) AS delegation_policy_verified
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
    if not verification["government_details_verified"]:
        unfinished.append("政务基础信息、办理流程与提取证据")
    if not verification["delegation_policy_verified"]:
        unfinished.append("事项代办规则")
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
    write_operation_audit(
        session, current_user.id, "matter_review", "确认核对并发布事项",
        "matter_version", version_id,
    )
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
    write_operation_audit(
        session, current_user.id, "matter_review", f"编辑{section}复核备注",
        "matter_version", version_id,
    )
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
    section_names = {
        "status": "事项状态与适用范围", "source": "官方网页与来源",
        "location": "办理地点与联系电话", "materials": "材料要求",
        "acquisition": "材料获取方式与线上渠道",
    }
    write_operation_audit(
        session, current_user.id, "matter_review", f"确认{section_names[section]}",
        "matter_version", version_id,
    )
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


@router.get("/admin/matter-versions/{version_id}/delegation-policy")
def get_delegation_policy(version_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    require_administrator(current_user)
    policy = one(session, """SELECT id, delegation_allowed, applicant_must_attend,
      relationship_required, allowed_relationships, condition_expr, questionnaire_required,
      verification_status, source_id, verified_at FROM matter_delegation_policies
      WHERE matter_version_id = :version_id""", {"version_id": version_id})
    if not policy:
        return envelope(None)
    policy["materials"] = rows(session, """SELECT id, material_code, name, requirement_level,
      submission_mode, applicability_expr, sort_order, verification_status
      FROM matter_delegation_material_requirements WHERE delegation_policy_id = :id ORDER BY sort_order, material_code""", {"id": policy["id"]})
    return envelope(policy)


@router.put("/admin/matter-versions/{version_id}/delegation-policy")
def update_delegation_policy(
    version_id: uuid.UUID, payload: DelegationPolicyUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Save a draft version's delegation policy and its conditional materials."""
    require_administrator(current_user)
    version = one(session, "SELECT config_revision, status FROM matter_versions WHERE id = :id", {"id": version_id})
    if not version:
        raise HTTPException(status_code=404, detail="事项版本不存在")
    if version["status"] != "draft" or version["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项状态或配置已更新，请刷新后重试")
    if payload.source_id and not one(session, "SELECT id FROM policy_sources WHERE id = :id", {"id": payload.source_id}):
        raise HTTPException(status_code=404, detail="代办规则的信息来源不存在")
    policy = one(session, "SELECT id FROM matter_delegation_policies WHERE matter_version_id = :id", {"id": version_id})
    policy_id = policy["id"] if policy else uuid.uuid4()
    values = {"id": policy_id, "version_id": version_id, "allowed": payload.delegation_allowed,
              "must_attend": payload.applicant_must_attend, "relationship_required": payload.relationship_required,
              "relationships": json.dumps([item.strip() for item in payload.allowed_relationships if item.strip()], ensure_ascii=False),
              "condition": json.dumps(payload.condition_expr, ensure_ascii=False),
              "questionnaire_required": payload.questionnaire_required, "source_id": payload.source_id}
    session.execute(text("""INSERT INTO matter_delegation_policies(
      id, matter_version_id, delegation_allowed, applicant_must_attend, relationship_required,
      allowed_relationships, condition_expr, questionnaire_required, source_id, verification_status)
      VALUES (:id, :version_id, :allowed, :must_attend, :relationship_required,
      CAST(:relationships AS jsonb), CAST(:condition AS jsonb), :questionnaire_required, :source_id, 'pending')
      ON CONFLICT (matter_version_id) DO UPDATE SET delegation_allowed = EXCLUDED.delegation_allowed,
      applicant_must_attend = EXCLUDED.applicant_must_attend, relationship_required = EXCLUDED.relationship_required,
      allowed_relationships = EXCLUDED.allowed_relationships, condition_expr = EXCLUDED.condition_expr,
      questionnaire_required = EXCLUDED.questionnaire_required, source_id = EXCLUDED.source_id,
      verification_status = 'pending', verified_by = NULL, verified_at = NULL, updated_at = now()"""), values)
    session.execute(text("DELETE FROM matter_delegation_material_requirements WHERE delegation_policy_id = :id"), {"id": policy_id})
    for order, material in enumerate(payload.materials):
        session.execute(text("""INSERT INTO matter_delegation_material_requirements(
          id, delegation_policy_id, material_code, name, requirement_level, submission_mode,
          applicability_expr, sort_order, verification_status)
          VALUES (:id, :policy_id, :code, :name, :level, :mode, CAST(:expr AS jsonb), :order, 'pending')"""),
          {"id": uuid.uuid4(), "policy_id": policy_id, "code": material.material_code.strip(),
           "name": material.name.strip(), "level": material.requirement_level, "mode": material.submission_mode,
           "expr": json.dumps(material.applicability_expr, ensure_ascii=False), "order": order})
    updated = one(session, """UPDATE matter_versions SET config_revision = config_revision + 1, updated_at = now()
      WHERE id = :id AND config_revision = :revision RETURNING config_revision""", {"id": version_id, "revision": payload.expected_config_revision})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    write_operation_audit(session, current_user.id, "matter_review", "编辑事项代办规则", "matter_version", version_id)
    session.commit()
    return envelope({"id": policy_id, "config_revision": updated["config_revision"], "verification_status": "pending"})


@router.post("/admin/matter-versions/{version_id}/delegation-policy/confirm")
def confirm_delegation_policy(
    version_id: uuid.UUID, payload: MatterVersionPublish,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    require_administrator(current_user)
    version = one(session, "SELECT config_revision, status FROM matter_versions WHERE id = :id", {"id": version_id})
    if not version or version["status"] != "draft" or version["config_revision"] != payload.expected_config_revision:
        raise HTTPException(status_code=409, detail="事项状态或配置已更新，请刷新后重试")
    policy = one(session, """UPDATE matter_delegation_policies SET verification_status = 'verified',
      verified_by = :user_id, verified_at = now(), updated_at = now() WHERE matter_version_id = :id
      RETURNING id""", {"id": version_id, "user_id": current_user.id})
    if not policy:
        raise HTTPException(status_code=404, detail="尚未配置事项代办规则")
    session.execute(text("""UPDATE matter_delegation_material_requirements SET verification_status = 'verified'
      WHERE delegation_policy_id = :id"""), {"id": policy["id"]})
    updated = one(session, """UPDATE matter_versions SET config_revision = config_revision + 1, updated_at = now()
      WHERE id = :id AND config_revision = :revision RETURNING config_revision""", {"id": version_id, "revision": payload.expected_config_revision})
    if not updated:
        raise HTTPException(status_code=409, detail="事项配置已更新，请刷新后重试")
    write_operation_audit(session, current_user.id, "matter_review", "确认事项代办规则", "matter_version", version_id)
    session.commit()
    return envelope({"config_revision": updated["config_revision"], "verification_status": "verified"})


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


@router.get("/operation-records")
def list_current_user_operation_records(session: SessionDep, current_user: CurrentUser) -> dict:
    """Return only the authenticated user's cases and administrator operations."""
    application_records = rows(session, """
        SELECT a.id, a.application_no, a.status, a.created_at, a.updated_at,
          COALESCE(a.display_name, sm.name) AS matter_name, sm.region_name
        FROM applications a
        JOIN matter_versions mv ON mv.id = a.matter_version_id
        JOIN service_matters sm ON sm.id = mv.matter_id
        WHERE a.owner_user_id = :user_id ORDER BY a.updated_at DESC
    """, {"user_id": current_user.id})
    result: dict[str, Any] = {"role": "administrator" if current_user.is_superuser else "user", "application_records": application_records}
    if current_user.is_superuser:
        result["case_review_records"] = rows(session, """
            SELECT rr.id, rr.outcome AS action, rr.comment, rr.created_at, rt.status AS task_status,
              a.application_no, sm.name AS matter_name
            FROM review_records rr JOIN review_tasks rt ON rt.id = rr.task_id
            JOIN applications a ON a.id = rt.application_id
            JOIN matter_versions mv ON mv.id = a.matter_version_id
            JOIN service_matters sm ON sm.id = mv.matter_id
            WHERE rr.actor_user_id = :user_id ORDER BY rr.created_at DESC
        """, {"user_id": current_user.id})
        audits = rows(session, """
            SELECT id, category, action, target_type, target_name, details_json, created_at
            FROM operation_audit_logs WHERE actor_user_id = :user_id ORDER BY created_at DESC
        """, {"user_id": current_user.id})
        result["matter_review_records"] = [row for row in audits if row["category"] == "matter_review"]
        result["user_management_records"] = [row for row in audits if row["category"] == "user_management"]
    return envelope(result)


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
        SELECT mv.id FROM matter_versions mv JOIN service_matters sm ON sm.id = mv.matter_id
        WHERE mv.id = :version_id AND mv.matter_id = :matter_id
          AND mv.status IN ('finished', 'published') AND sm.is_active = true
    """, {"version_id": payload.matter_version_id, "matter_id": payload.matter_id})
    if not version:
        raise HTTPException(status_code=409, detail="事项版本不存在、未发布或不能新建办件")
    existing = rows(session, """
        SELECT a.id, a.application_no, a.status, a.updated_at
        FROM applications a
        JOIN matter_versions existing_mv ON existing_mv.id = a.matter_version_id
        WHERE a.owner_user_id = :owner AND existing_mv.matter_id = :matter_id
          AND a.status NOT IN ('closed', 'cancelled')
        ORDER BY a.updated_at DESC
    """, {"owner": current_user.id, "matter_id": payload.matter_id})
    if existing and not payload.create_new:
        raise HTTPException(
            status_code=409,
            detail="该事项已有未结束的材料准备记录，请继续准备，或确认后新建一份。",
        )
    app_id = uuid.uuid4()
    application_no = f"PRE-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    result = {"id": app_id, "application_no": application_no, "matter_version_id": payload.matter_version_id,
              "status": "draft", "questionnaire_status": "draft", "content_revision": 1,
              "record_type": "material_preparation"}
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


@router.get("/applications/open")
def list_open_applications_for_matter(
    matter_id: uuid.UUID, session: SessionDep, current_user: CurrentUser,
) -> dict:
    """List only this user's unfinished material-preparation records for one matter."""
    data = rows(session, """
        SELECT a.id, a.application_no, a.status, a.questionnaire_status, a.is_delegated,
          a.content_revision, a.created_at, a.updated_at,
          COALESCE(a.display_name, sm.name) AS matter_name, sm.region_name
        FROM applications a
        JOIN matter_versions mv ON mv.id = a.matter_version_id
        JOIN service_matters sm ON sm.id = mv.matter_id
        WHERE a.owner_user_id = :owner AND mv.matter_id = :matter_id
          AND a.status NOT IN ('closed', 'cancelled')
        ORDER BY a.updated_at DESC
    """, {"owner": current_user.id, "matter_id": matter_id})
    return envelope({"items": data, "count": len(data)})


@router.get("/applications")
def list_applications(session: SessionDep, current_user: CurrentUser) -> dict:
    data = rows(session, """
        SELECT a.id, a.application_no, a.status, a.questionnaire_status, a.is_delegated, a.content_revision,
               a.created_at, a.updated_at, COALESCE(a.display_name, sm.name) AS matter_name, sm.region_name, mv.version_no,
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


@router.patch("/applications/{app_id}/display-name")
def update_application_display_name(
    app_id: uuid.UUID, payload: ApplicationDisplayNameUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    app = owned_application(session, app_id, current_user.id)
    require_open_preparation(app)
    require_revision(app, payload.expected_revision)
    updated = one(session, """UPDATE applications SET display_name = :display_name,
      status = 'preparing', content_revision = content_revision + 1, updated_at = now()
      WHERE id = :id RETURNING display_name, content_revision""",
      {"id": app_id, "display_name": payload.display_name.strip()})
    write_operation_audit(session, current_user.id, "application", "修改办件事项名称", "application", app_id)
    session.commit()
    return envelope(updated)


@router.get("/applications/{app_id}")
def get_application(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    detail = one(session, """
        SELECT COALESCE(a.display_name, sm.name) AS matter_name, sm.region_name, mv.version_no, mv.valid_from, mv.valid_to
        FROM applications a JOIN matter_versions mv ON mv.id = a.matter_version_id
        JOIN service_matters sm ON sm.id = mv.matter_id WHERE a.id = :id
    """, {"id": app_id})
    return envelope({**app, "matter": detail})


@router.get("/applications/{app_id}/questionnaire")
def get_questionnaire(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    location = one(session, "SELECT service_location_id FROM matter_versions WHERE id = :id", {"id": app["matter_version_id"]})
    policy = one(session, """SELECT delegation_allowed, applicant_must_attend, relationship_required,
      allowed_relationships, questionnaire_required, verification_status
      FROM matter_delegation_policies WHERE matter_version_id = :id""", {"id": app["matter_version_id"]})
    policy_data = policy or {"delegation_allowed": False, "applicant_must_attend": False,
                             "relationship_required": False, "allowed_relationships": [],
                             "questionnaire_required": False, "verification_status": "unavailable"}
    policy_data["is_verified"] = policy_data["verification_status"] == "verified"
    show_submission_plan = bool(location and location["service_location_id"])
    return envelope({"questions": [], "answers": app["scenario_answers"],
                     "visible_codes": [], "unknown_codes": [],
                     "delegation_policy": policy_data,
                     "show_submission_plan": show_submission_plan,
                     "questionnaire_status": app["questionnaire_status"],
                     "content_revision": app["content_revision"]})


@router.put("/applications/{app_id}/scenario")
def save_scenario(app_id: uuid.UUID, payload: ScenarioUpdate, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    require_open_preparation(app)
    require_revision(app, payload.expected_revision)
    next_revision = app["content_revision"] + 1
    # Editing an already packaged record makes its immutable package stale.
    next_status = "preparing" if payload.mode == "submit" or app["status"] == "prepared" else app["status"]
    session.execute(text("""
        UPDATE applications SET scenario_answers = CAST(:answers AS jsonb),
          questionnaire_status = :questionnaire_status, status = :status,
          content_revision = :revision, updated_at = now() WHERE id = :id
    """), {"answers": json.dumps(payload.answers), "questionnaire_status": "submitted" if payload.mode == "submit" else "draft",
           "status": next_status, "revision": next_revision, "id": app_id})
    session.commit()
    return envelope({"answers": payload.answers, "questionnaire_status": "submitted" if payload.mode == "submit" else "draft",
                     "content_revision": next_revision})


@router.put("/applications/{app_id}/questionnaire")
def submit_questionnaire(
    app_id: uuid.UUID, payload: QuestionnaireSubmit,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    """Save the resident's minimal questionnaire and distinct applicant/agent records together."""
    app = owned_application(session, app_id, current_user.id)
    require_open_preparation(app)
    require_revision(app, payload.expected_revision)
    policy = one(session, """SELECT id, delegation_allowed, applicant_must_attend, relationship_required,
      allowed_relationships, verification_status FROM matter_delegation_policies
      WHERE matter_version_id = :id""", {"id": app["matter_version_id"]})
    delegation_allowed = bool(policy and policy["delegation_allowed"] and policy["verification_status"] == "verified")
    if payload.submission_plan == "agent":
        if not payload.agent_name or not payload.agent_name.strip():
            raise HTTPException(status_code=422, detail="请填写代办人姓名")
        allowed_relationships = policy["allowed_relationships"] if policy else []
        if delegation_allowed and policy["relationship_required"]:
            if not payload.agent_relationship or payload.agent_relationship not in allowed_relationships:
                raise HTTPException(status_code=422, detail="请选择该事项规则允许的代办关系")

    def upsert_person(role: str, name: str, identity_payload: dict[str, Any]) -> None:
        existing = one(session, "SELECT id FROM application_participants WHERE application_id = :app_id AND role_code = :role", {"app_id": app_id, "role": role})
        if existing:
            session.execute(text("""UPDATE application_participants SET display_name = :name,
              identity_payload = CAST(:identity AS jsonb), updated_at = now() WHERE id = :id"""),
              {"id": existing["id"], "name": name, "identity": json.dumps(identity_payload, ensure_ascii=False)})
            return
        count = one(session, "SELECT count(*) AS count FROM application_participants WHERE application_id = :id", {"id": app_id})["count"]
        session.execute(text("""INSERT INTO application_participants(
              id, application_id, participant_code, role_code, display_name, identity_payload)
            VALUES (:id, :app_id, :code, :role, :name, CAST(:identity AS jsonb))"""),
            {"id": uuid.uuid4(), "app_id": app_id, "code": f"P{count + 1:03d}", "role": role,
             "name": name, "identity": json.dumps(identity_payload, ensure_ascii=False)})

    upsert_person("applicant", payload.applicant_name.strip(), {"prepared_for": payload.prepared_for})
    if payload.submission_plan == "agent":
        upsert_person("agent", payload.agent_name.strip(), {"delegation_intent": "agent", "relationship": payload.agent_relationship})
    else:
        linked_documents = one(session, """SELECT 1 FROM application_documents ad
          JOIN application_participants ap ON ap.id = ad.participant_id
          WHERE ap.application_id = :app_id AND ap.role_code = 'agent' LIMIT 1""", {"app_id": app_id})
        if linked_documents:
            raise HTTPException(status_code=409, detail="代办人已关联上传材料，不能直接移除；请先调整相关材料")
        session.execute(text("DELETE FROM application_participants WHERE application_id = :app_id AND role_code = 'agent'"), {"app_id": app_id})
    answers = dict(app["scenario_answers"] or {})
    delegation_status = (
        "delegated" if payload.submission_plan == "agent" and delegation_allowed
        else "pending_confirmation" if payload.submission_plan == "agent"
        else "not_delegated" if payload.submission_plan == "applicant"
        else "unknown"
    )
    answers.update({"prepared_for": payload.prepared_for, "submission_plan": payload.submission_plan,
                    "agent_relationship": payload.agent_relationship if payload.submission_plan == "agent" else None,
                    "delegation_status": delegation_status,
                    "applicant_must_attend": bool(policy and policy["applicant_must_attend"])})
    next_revision = app["content_revision"] + 1
    is_delegated = delegation_status == "delegated"
    if is_delegated:
        materials = rows(session, """SELECT material_code, name, requirement_level
          FROM matter_delegation_material_requirements WHERE delegation_policy_id = :id
          AND verification_status = 'verified' AND COALESCE(applicability_expr ->> 'op', 'always') = 'always'
          ORDER BY sort_order""", {"id": policy["id"]})
        for material in materials:
            session.execute(text("""INSERT INTO application_extra_materials(
              id, application_id, material_code, name, requirement_level, declaration)
              VALUES (:id, :app_id, :code, :name, :level, 'unknown')
              ON CONFLICT (application_id, material_code) DO NOTHING"""),
              {"id": uuid.uuid4(), "app_id": app_id, "code": f"delegation-{material['material_code']}",
               "name": material["name"], "level": material["requirement_level"]})
    else:
        session.execute(text("""DELETE FROM application_extra_materials
          WHERE application_id = :app_id AND material_code LIKE 'delegation-%'"""), {"app_id": app_id})
    session.execute(text("""UPDATE applications SET scenario_answers = CAST(:answers AS jsonb),
      questionnaire_status = 'submitted', status = 'preparing', content_revision = :revision,
      is_delegated = :is_delegated, updated_at = now() WHERE id = :id"""),
      {"answers": json.dumps(answers, ensure_ascii=False), "revision": next_revision,
       "is_delegated": is_delegated, "id": app_id})
    session.commit()
    return envelope({"answers": answers, "questionnaire_status": "submitted",
                     "is_delegated": is_delegated, "delegation_status": delegation_status,
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
    require_open_preparation(app)
    require_revision(app, payload.expected_revision)
    count = one(session, "SELECT count(*) AS count FROM application_participants WHERE application_id = :id", {"id": app_id})["count"]
    participant = {"id": uuid.uuid4(), "participant_code": f"P{count + 1:03d}", "role_code": payload.role_code,
                   "display_name": payload.display_name}
    session.execute(text("""
        INSERT INTO application_participants(id, application_id, participant_code, role_code, display_name, identity_payload)
        VALUES (:id, :app_id, :code, :role, :name, CAST(:identity AS jsonb))
    """), {"id": participant["id"], "app_id": app_id, "code": participant["participant_code"], "role": payload.role_code,
           "name": payload.display_name, "identity": json.dumps(payload.identity_payload)})
    session.execute(text("UPDATE applications SET status = 'preparing', content_revision = content_revision + 1, updated_at = now() WHERE id = :id"), {"id": app_id})
    session.commit()
    return envelope({"participant": participant, "content_revision": app["content_revision"] + 1})


@router.post("/applications/{app_id}/cancel")
def cancel_application(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    """Cancel a preparation record without deleting its audit/check history."""
    app = owned_application(session, app_id, current_user.id)
    if app["status"] in {"closed", "cancelled"}:
        raise HTTPException(status_code=409, detail="该材料准备记录已经结束，不能重复取消")
    session.execute(text("""UPDATE applications SET status = 'cancelled', closed_at = now(),
      content_revision = content_revision + 1, updated_at = now() WHERE id = :id"""), {"id": app_id})
    # Preserve the task and model/audit history, but make it explicit to staff
    # that the resident stopped this preparation record.
    session.execute(text("""UPDATE review_tasks SET status = 'cancelled',
      request_note = CONCAT(COALESCE(request_note || E'\n', ''), '用户已取消办件'), updated_at = now()
      WHERE application_id = :id AND status IN ('pending', 'in_progress')"""), {"id": app_id})
    session.commit()
    return envelope({"id": app_id, "status": "cancelled"})


@router.get("/applications/{app_id}/checklist")
def get_checklist(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    items = rows(session, """
        SELECT 'requirement' AS item_kind, mr.id AS requirement_id, mr.requirement_code, mr.name, mr.requirement_level,
          mr.submission_mode, mr.provider_role, mr.alternative_group_code, mr.sort_order,
          pi.declaration AS preparation_declaration,
          COALESCE((SELECT count(*) FROM document_version_files dvf
            JOIN document_versions dv ON dv.id = dvf.document_version_id AND dv.status = 'active'
            JOIN application_documents ad ON ad.id = dv.document_id
            WHERE ad.application_id = :app_id AND ad.requirement_id = mr.id), 0) AS uploaded_file_count
        FROM material_requirements mr
        LEFT JOIN application_preparation_items pi ON pi.requirement_id = mr.id
          AND pi.application_id = :app_id AND pi.participant_id IS NULL
        WHERE mr.matter_version_id = :version_id
        UNION ALL
        SELECT 'extra' AS item_kind, aem.id AS requirement_id, aem.material_code AS requirement_code,
          aem.name, aem.requirement_level, 'on_site' AS submission_mode, NULL AS provider_role,
          NULL AS alternative_group_code, 100000 AS sort_order, aem.declaration AS preparation_declaration,
          COALESCE((SELECT count(*) FROM document_version_files dvf
            JOIN document_versions dv ON dv.id = dvf.document_version_id AND dv.status = 'active'
            JOIN application_documents ad ON ad.id = dv.document_id
            WHERE ad.application_id = :app_id AND ad.document_code = 'extra-' || aem.id::text), 0) AS uploaded_file_count
        FROM application_extra_materials aem WHERE aem.application_id = :app_id
          AND aem.material_code <> 'agent_identity_card'
        ORDER BY sort_order, requirement_code
    """, {"app_id": app_id, "version_id": app["matter_version_id"]})
    staff_decisions = latest_staff_material_decisions(session, app_id)
    for item in items:
        if item["item_kind"] == "requirement":
            item["files"] = rows(session, """SELECT dvf.id, dvf.original_filename, dvf.mime_type,
              dvf.byte_size
              FROM application_documents ad
              JOIN document_versions dv ON dv.document_id = ad.id AND dv.status = 'active'
              JOIN document_version_files dvf ON dvf.document_version_id = dv.id
                AND dvf.availability = 'available'
              WHERE ad.application_id = :app_id AND ad.requirement_id = :material_id
              ORDER BY dvf.file_order""", {"app_id": app_id, "material_id": item["requirement_id"]})
        else:
            item["files"] = rows(session, """SELECT dvf.id, dvf.original_filename, dvf.mime_type,
              dvf.byte_size
              FROM application_documents ad
              JOIN document_versions dv ON dv.document_id = ad.id AND dv.status = 'active'
              JOIN document_version_files dvf ON dvf.document_version_id = dv.id
                AND dvf.availability = 'available'
              WHERE ad.application_id = :app_id AND ad.document_code = :document_code
              ORDER BY dvf.file_order""", {"app_id": app_id,
                                               "document_code": f"extra-{item['requirement_id']}"})
        latest_item_review = one(session, """SELECT model_result_json
          FROM check_runs
          WHERE application_id = :app_id
            AND config_snapshot->>'purpose' = 'single_material'
            AND config_snapshot->>'material_id' = :material_id
          ORDER BY run_no DESC LIMIT 1""", {"app_id": app_id, "material_id": str(item["requirement_id"])})
        item["review_result"] = latest_item_review["model_result_json"] if latest_item_review else None
        decision = staff_decisions.get(item["name"])
        item["review_decision"] = decision["decision"] if decision else None
        item["review_note"] = decision["note"] if decision else None
        item["reupload_file_saved"] = False
        if decision and decision["decision"] == "reupload":
            if item["item_kind"] == "requirement":
                newer_file = one(session, """SELECT EXISTS(SELECT 1 FROM application_documents ad
                  JOIN document_versions dv ON dv.document_id = ad.id AND dv.status = 'active'
                  WHERE ad.application_id = :app_id AND ad.requirement_id = :material_id
                    AND dv.created_at > :reviewed_at) AS exists""",
                  {"app_id": app_id, "material_id": item["requirement_id"], "reviewed_at": decision["created_at"]})
            else:
                newer_file = one(session, """SELECT EXISTS(SELECT 1 FROM application_documents ad
                  JOIN document_versions dv ON dv.document_id = ad.id AND dv.status = 'active'
                  WHERE ad.application_id = :app_id AND ad.document_code = :document_code
                    AND dv.created_at > :reviewed_at) AS exists""",
                  {"app_id": app_id, "document_code": f"extra-{item['requirement_id']}", "reviewed_at": decision["created_at"]})
            item["reupload_file_saved"] = bool(newer_file["exists"])
            # A replacement can finish the model check without requiring the
            # resident to send the whole checklist through the model again.
            # It is deliberately not treated as a staff pass: only a human
            # pass locks a material from later replacement.
            model_passed = one(session, """SELECT EXISTS(
              SELECT 1 FROM check_runs
              WHERE application_id = :app_id AND status = 'succeeded'
                AND model_result_json->>'decision' = 'pass'
                AND config_snapshot->>'purpose' = 'single_material'
                AND config_snapshot->>'material_id' = :material_id
                AND finished_at > :reviewed_at
            ) AS exists""", {"app_id": app_id, "material_id": str(item["requirement_id"]),
                              "reviewed_at": decision["created_at"]})
            if model_passed["exists"]:
                item["review_decision"] = "model_pass"
    return envelope({"items": items, "alternative_groups": [], "unknown_conditions": [],
                     "content_revision": app["content_revision"]})


@router.post("/applications/{app_id}/materials/{material_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_application_material(
    app_id: uuid.UUID,
    material_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    item_kind: str = Form(...),
    expected_revision: int = Form(...),
    files: list[UploadFile] = File(...),
) -> dict:
    """Store files for exactly one checklist item, ready for a later OCR/check run."""
    app = owned_application(session, app_id, current_user.id)
    require_open_preparation(app)
    require_revision(app, expected_revision)
    if item_kind not in {"requirement", "extra"}:
        raise HTTPException(status_code=422, detail="材料类型无效")
    if not files:
        raise HTTPException(status_code=422, detail="请至少选择一个文件")

    requirement_id: uuid.UUID | None = None
    if item_kind == "requirement":
        material = one(session, """SELECT mr.id, mr.material_type_id, mr.name
          FROM material_requirements mr WHERE mr.id = :id AND mr.matter_version_id = :version_id""",
          {"id": material_id, "version_id": app["matter_version_id"]})
        if not material:
            raise HTTPException(status_code=404, detail="材料清单项不存在或不属于当前办件")
        requirement_id, material_type_id = material["id"], material["material_type_id"]
        document_code = f"requirement-{material_id}"
    else:
        material = one(session, """SELECT id, name FROM application_extra_materials
          WHERE id = :id AND application_id = :app_id""", {"id": material_id, "app_id": app_id})
        if not material:
            raise HTTPException(status_code=404, detail="办件专属材料不存在")
        fallback_type = one(session, "SELECT id FROM material_types WHERE is_active = true ORDER BY created_at LIMIT 1")
        if not fallback_type:
            raise HTTPException(status_code=409, detail="系统未配置可用材料类型，暂不能上传")
        material_type_id = fallback_type["id"]
        document_code = f"extra-{material_id}"

    staff_decision = latest_staff_material_decisions(session, app_id).get(material["name"])
    if staff_decision and staff_decision["decision"] == "pass":
        raise HTTPException(status_code=409, detail="该材料已通过复核，不能重新上传或替换文件")

    storage_root = Path(settings.APPLICATION_DOCUMENT_STORAGE_PATH).resolve()
    version_id = uuid.uuid4()
    target_root = (storage_root / str(app_id) / str(version_id)).resolve()
    if storage_root not in target_root.parents:
        raise HTTPException(status_code=500, detail="办件文件存储路径配置无效")
    target_root.mkdir(parents=True, exist_ok=True)

    saved_files: list[dict[str, Any]] = []
    total_size = 0
    try:
        for order, upload in enumerate(files, start=1):
            original_filename = Path(upload.filename or "upload").name
            suffix = Path(original_filename).suffix.lower()
            if suffix not in APPLICATION_UPLOAD_SUFFIXES:
                raise HTTPException(status_code=415, detail="仅支持 PDF、DOCX、TXT、JPG、PNG、WEBP 文件")
            file_id = uuid.uuid4()
            target = (target_root / f"{file_id}{suffix}").resolve()
            if target_root not in target.parents:
                raise HTTPException(status_code=500, detail="上传文件路径无效")
            digest, size = hashlib.sha256(), 0
            with target.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    total_size += len(chunk)
                    if size > MAX_APPLICATION_FILE_SIZE or total_size > MAX_APPLICATION_TOTAL_UPLOAD_SIZE:
                        raise HTTPException(status_code=413, detail="单个文件最大 10MB，单次上传总大小最大 30MB")
                    digest.update(chunk)
                    output.write(chunk)
            saved_files.append({"id": file_id, "order": order, "filename": original_filename,
                                "mime_type": upload.content_type or "application/octet-stream",
                                "size": size, "sha256": digest.hexdigest(),
                                "storage_key": str(target.relative_to(storage_root)).replace("\\", "/")})

        document = one(session, """SELECT id FROM application_documents
          WHERE application_id = :app_id AND document_code = :document_code""",
          {"app_id": app_id, "document_code": document_code})
        document_id = document["id"] if document else uuid.uuid4()
        if not document:
            session.execute(text("""INSERT INTO application_documents(
              id, application_id, matter_version_id, material_type_id, requirement_id, document_code)
              VALUES (:id, :app_id, :version_id, :material_type_id, :requirement_id, :document_code)"""),
              {"id": document_id, "app_id": app_id, "version_id": app["matter_version_id"],
               "material_type_id": material_type_id, "requirement_id": requirement_id, "document_code": document_code})
        previous = one(session, """SELECT COALESCE(MAX(version_no), 0) AS version_no
          FROM document_versions WHERE document_id = :document_id""", {"document_id": document_id})
        session.execute(text("""UPDATE document_versions SET status = 'superseded'
          WHERE document_id = :document_id AND status = 'active'"""), {"document_id": document_id})
        session.execute(text("""INSERT INTO document_versions(
          id, document_id, application_id, version_no, uploaded_by, status, data_origin)
          VALUES (:id, :document_id, :app_id, :version_no, :user_id, 'active', 'authorized_real')"""),
          {"id": version_id, "document_id": document_id, "app_id": app_id,
           "version_no": previous["version_no"] + 1, "user_id": current_user.id})
        for item in saved_files:
            session.execute(text("""INSERT INTO document_version_files(
              id, document_version_id, application_id, file_order, storage_backend, storage_key,
              original_filename, mime_type, byte_size, file_sha256)
              VALUES (:id, :version_id, :app_id, :order, 'local', :storage_key,
                :filename, :mime_type, :size, :sha256)"""),
              {"id": item["id"], "version_id": version_id, "app_id": app_id, "order": item["order"],
               "storage_key": item["storage_key"], "filename": item["filename"],
               "mime_type": item["mime_type"], "size": item["size"], "sha256": item["sha256"]})
        # Uploading a usable file is the resident's declaration that this
        # individual material has been prepared.  It removes the redundant
        # separate "mark prepared" action while keeping the state in the DB.
        if item_kind == "requirement":
            session.execute(text("""
              INSERT INTO application_preparation_items(
                id, application_id, matter_version_id, requirement_id, participant_id, declaration, declared_by)
              VALUES (:id, :app_id, :version_id, :requirement_id, NULL, 'ready', :user_id)
              ON CONFLICT (application_id, requirement_id) WHERE participant_id IS NULL
              DO UPDATE SET declaration = 'ready', declared_by = EXCLUDED.declared_by, updated_at = now()
            """), {"id": uuid.uuid4(), "app_id": app_id, "version_id": app["matter_version_id"],
                   "requirement_id": material_id, "user_id": current_user.id})
        else:
            session.execute(text("""UPDATE application_extra_materials
              SET declaration = 'ready', updated_at = now()
              WHERE id = :id AND application_id = :app_id"""), {"id": material_id, "app_id": app_id})
        session.execute(text("""UPDATE applications SET status = 'preparing',
          content_revision = content_revision + 1, updated_at = now() WHERE id = :id"""), {"id": app_id})
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception as error:
        session.rollback()
        raise HTTPException(status_code=500, detail="保存上传材料失败") from error
    return envelope({"document_id": document_id, "document_version_id": version_id,
                     "file_count": len(saved_files), "content_revision": app["content_revision"] + 1})


@router.get("/applications/{app_id}/documents/{file_id}")
def download_application_document(app_id: uuid.UUID, file_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> FileResponse:
    """Owner-only download endpoint; the browser never receives storage paths."""
    owned_application(session, app_id, current_user.id)
    file = one(session, """SELECT original_filename, mime_type, storage_key
      FROM document_version_files WHERE id = :id AND application_id = :app_id AND availability = 'available'""",
      {"id": file_id, "app_id": app_id})
    if not file:
        raise HTTPException(status_code=404, detail="上传文件不存在")
    root = Path(settings.APPLICATION_DOCUMENT_STORAGE_PATH).resolve()
    target = (root / file["storage_key"]).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="上传文件已不可用")
    return FileResponse(target, media_type=file["mime_type"], filename=file["original_filename"])


def owned_package(session: SessionDep, package_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    package = one(session, """SELECT pp.*, a.content_revision AS current_revision
      FROM preparation_packages pp JOIN applications a ON a.id = pp.application_id
      WHERE pp.id = :id AND a.owner_user_id = :user_id""", {"id": package_id, "user_id": user_id})
    if not package:
        raise HTTPException(status_code=404, detail="准备包不存在或无权访问")
    package["is_current"] = package["content_revision"] == package["current_revision"]
    return package


@router.post("/applications/{app_id}/preparation-packages", status_code=status.HTTP_201_CREATED)
def create_preparation_package(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    snapshot, blocked = package_snapshot(session, app)
    if blocked:
        raise HTTPException(status_code=409, detail=f"尚不能生成办理准备包；以下材料未完成核查：{'、'.join(blocked)}")
    next_no = int(one(session, "SELECT COALESCE(MAX(package_no), 0) AS no FROM preparation_packages WHERE application_id = :id", {"id": app_id})["no"]) + 1
    package_id = uuid.uuid4()
    session.execute(text("""INSERT INTO preparation_packages(
      id, application_id, matter_version_id, content_revision, package_no, snapshot_json, created_by)
      VALUES (:id, :app_id, :version_id, :revision, :package_no, CAST(:snapshot AS jsonb), :user_id)"""),
      {"id": package_id, "app_id": app_id, "version_id": app["matter_version_id"],
       "revision": app["content_revision"], "package_no": next_no,
       "snapshot": json.dumps(snapshot, ensure_ascii=False), "user_id": current_user.id})
    # A package is an immutable snapshot.  Its successful creation marks this
    # preparation record ready for the subsequent offline counter handling.
    session.execute(text("UPDATE applications SET status = 'prepared', updated_at = now() WHERE id = :id"),
                    {"id": app_id})
    write_operation_audit(session, current_user.id, "application", "生成办理准备包", "preparation_package", package_id)
    session.commit()
    return envelope({"id": package_id, "package_no": next_no, "is_current": True, "application_status": "prepared",
                     "result_url": f"{settings.FRONTEND_HOST.rstrip('/')}/applications/{app_id}#preparation-package"})


@router.get("/applications/{app_id}/preparation-packages/latest")
def get_latest_preparation_package(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    owned_application(session, app_id, current_user.id)
    package = one(session, """SELECT id, package_no, content_revision, created_at
      FROM preparation_packages WHERE application_id = :app_id ORDER BY package_no DESC LIMIT 1""", {"app_id": app_id})
    if package:
        current = one(session, "SELECT content_revision FROM applications WHERE id = :id", {"id": app_id})
        package["is_current"] = package["content_revision"] == current["content_revision"]
    return envelope(package)


@router.get("/preparation-packages/{package_id}/pdf")
def download_preparation_package_pdf(package_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> Response:
    package = owned_package(session, package_id, current_user.id)
    content = package_pdf(package["snapshot_json"], package_id)
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=preparation-sheet.pdf"})


@router.get("/preparation-packages/{package_id}/zip")
def download_preparation_package_zip(package_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> Response:
    package = owned_package(session, package_id, current_user.id)
    stream = io.BytesIO()
    root = Path(settings.APPLICATION_DOCUMENT_STORAGE_PATH).resolve()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("办前准备单.pdf", package_pdf(package["snapshot_json"], package_id))
        for index, material in enumerate(package["snapshot_json"]["materials"], start=1):
            for file in material["files"]:
                path = (root / file["storage_key"]).resolve()
                if root in path.parents and path.is_file():
                    archive.write(path, f"材料/{index:02d}_{material['name']}_{file['filename']}")
    return Response(stream.getvalue(), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=preparation-package.zip"})


@router.get("/preparation-packages/{package_id}/qr")
def preparation_package_qr(package_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> Response:
    package = owned_package(session, package_id, current_user.id)
    url = f"{settings.FRONTEND_HOST.rstrip('/')}/applications/{package['application_id']}#preparation-package"
    image = qrcode.make(url)
    stream = io.BytesIO(); image.save(stream, format="PNG")
    return Response(stream.getvalue(), media_type="image/png")


@router.get("/applications/{app_id}/material-review")
def get_latest_material_review(app_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    """Return the newest saved model-assisted review for the record owner."""
    owned_application(session, app_id, current_user.id)
    review = one(session, """SELECT id, run_no, status, material_summary, model_info,
      model_result_json, error_code, started_at, finished_at, created_at
      FROM check_runs WHERE application_id = :app_id ORDER BY run_no DESC LIMIT 1""", {"app_id": app_id})
    if review:
        review["staff_review"] = one(session, """SELECT rr.outcome, rr.comment, rr.details, rr.created_at
          FROM review_records rr JOIN review_tasks rt ON rt.id = rr.task_id
          WHERE rt.application_id = :app_id AND rt.check_run_id = :run_id AND rt.status = 'completed'
          ORDER BY rr.created_at DESC LIMIT 1""", {"app_id": app_id, "run_id": review["id"]})
    return envelope(review)


@router.get("/staff/review-tasks")
def list_case_review_tasks(session: SessionDep, current_user: CurrentUser) -> dict:
    """Show unclaimed tasks and tasks claimed by this administrator."""
    require_administrator(current_user)
    tasks = rows(session, """SELECT rt.id, rt.status, rt.priority, rt.request_note, rt.created_at, rt.claimed_at,
      rt.application_id, a.application_no, sm.name AS matter_name, cr.model_result_json,
      (a.status = 'cancelled') AS user_cancelled,
      CASE WHEN rt.assigned_to = :user_id THEN true ELSE false END AS claimed_by_me
      FROM review_tasks rt JOIN applications a ON a.id = rt.application_id
      JOIN matter_versions mv ON mv.id = a.matter_version_id JOIN service_matters sm ON sm.id = mv.matter_id
      LEFT JOIN check_runs cr ON cr.id = rt.check_run_id
      WHERE rt.status = 'pending' OR (rt.status = 'in_progress' AND rt.assigned_to = :user_id)
        OR (rt.status = 'cancelled' AND a.status = 'cancelled')
      ORDER BY rt.priority DESC, rt.created_at ASC""", {"user_id": current_user.id})
    return envelope({"items": tasks, "count": len(tasks)})


@router.post("/staff/review-tasks/{task_id}/claim")
def claim_case_review_task(task_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    """Atomically claim one pending case-review task for the current administrator."""
    require_administrator(current_user)
    claimed = one(session, """UPDATE review_tasks SET status = 'in_progress', assigned_to = :user_id,
      claimed_at = now(), updated_at = now() WHERE id = :task_id AND status = 'pending'
      RETURNING id, status, application_id, claimed_at""", {"task_id": task_id, "user_id": current_user.id})
    if not claimed:
        raise HTTPException(status_code=409, detail="该复核任务已被其他工作人员领取或不再可领取，请刷新队列")
    write_operation_audit(session, current_user.id, "case_review", "领取办件复核任务", "review_task", task_id)
    session.commit()
    return envelope(claimed)


@router.post("/staff/review-tasks/{task_id}/mark-user-cancelled")
def mark_case_review_application_cancelled(task_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    """Administrator correction: mark the linked resident record as user-cancelled."""
    require_administrator(current_user)
    task = one(session, """SELECT rt.application_id, a.status AS application_status
      FROM review_tasks rt JOIN applications a ON a.id = rt.application_id
      WHERE rt.id = :task_id FOR UPDATE""", {"task_id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")
    session.execute(text("""UPDATE applications SET status = 'cancelled', closed_at = COALESCE(closed_at, now()),
      content_revision = content_revision + 1, updated_at = now() WHERE id = :id"""), {"id": task["application_id"]})
    updated = session.execute(text("""UPDATE review_tasks SET status = 'cancelled',
      request_note = CONCAT(COALESCE(request_note || E'\n', ''), '用户已取消办件（管理员更正）'), updated_at = now()
      WHERE application_id = :id AND status IN ('pending', 'in_progress')"""), {"id": task["application_id"]})
    write_operation_audit(session, current_user.id, "case_review", "标记办件为用户已取消", "application", task["application_id"])
    session.commit()
    return envelope({"application_id": task["application_id"], "status": "cancelled", "cancelled_task_count": updated.rowcount})


@router.delete("/staff/review-tasks/{task_id}")
def delete_cancelled_case_review_task(task_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    """Remove an unprocessed queue entry after its resident cancelled the record."""
    require_administrator(current_user)
    task = one(session, """SELECT rt.id FROM review_tasks rt JOIN applications a ON a.id = rt.application_id
      WHERE rt.id = :task_id AND rt.status = 'cancelled' AND a.status = 'cancelled'
      AND NOT EXISTS (SELECT 1 FROM review_records rr WHERE rr.task_id = rt.id)""", {"task_id": task_id})
    if not task:
        raise HTTPException(status_code=409, detail="仅能删除用户已取消且尚未提交复核记录的任务")
    session.execute(text("DELETE FROM review_tasks WHERE id = :id"), {"id": task_id})
    write_operation_audit(session, current_user.id, "case_review", "删除已取消办件复核任务", "review_task", task_id)
    session.commit()
    return envelope({"id": task_id, "deleted": True})


@router.get("/staff/review-tasks/{task_id}")
def get_case_review_task(task_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    """Return the evidence and model conclusion for one task claimed by this worker."""
    require_administrator(current_user)
    task = one(session, """SELECT rt.id, rt.status, rt.request_note, rt.created_at, rt.claimed_at,
      rt.assigned_to AS reviewer_user_id,
      a.id AS application_id, a.application_no, a.status AS application_status, sm.name AS matter_name,
      cr.id AS check_run_id, cr.model_info, cr.model_result_json, cr.material_summary
      FROM review_tasks rt JOIN applications a ON a.id = rt.application_id
      JOIN matter_versions mv ON mv.id = a.matter_version_id JOIN service_matters sm ON sm.id = mv.matter_id
      LEFT JOIN check_runs cr ON cr.id = rt.check_run_id
      WHERE rt.id = :task_id AND (rt.status = 'cancelled' OR (rt.assigned_to = :user_id AND rt.status IN ('in_progress', 'completed')))""",
      {"task_id": task_id, "user_id": current_user.id})
    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在，或请先领取该任务")
    task["documents"] = rows(session, """SELECT dvf.id, dvf.original_filename, dvf.mime_type, dvf.byte_size,
      ad.document_code, COALESCE(mr.name, aem.name, '办件材料') AS material_name
      FROM check_run_documents crd JOIN document_versions dv ON dv.id = crd.document_version_id
      JOIN application_documents ad ON ad.id = dv.document_id
      JOIN document_version_files dvf ON dvf.document_version_id = dv.id
      LEFT JOIN material_requirements mr ON mr.id = ad.requirement_id
      LEFT JOIN application_extra_materials aem ON ad.document_code = 'extra-' || aem.id::text
      WHERE crd.check_run_id = :run_id AND dvf.availability = 'available'
      ORDER BY material_name, dvf.file_order""", {"run_id": task["check_run_id"]}) if task["check_run_id"] else []
    return envelope(task)


@router.get("/staff/review-tasks/{task_id}/documents/{file_id}")
def download_case_review_document(
    task_id: uuid.UUID, file_id: uuid.UUID, session: SessionDep, current_user: CurrentUser,
) -> FileResponse:
    """Allow only the administrator who claimed the task to open its uploaded evidence."""
    require_administrator(current_user)
    file = one(session, """SELECT dvf.original_filename, dvf.mime_type, dvf.storage_key
      FROM review_tasks rt
      JOIN check_run_documents crd ON crd.check_run_id = rt.check_run_id
      JOIN document_versions dv ON dv.id = crd.document_version_id
      JOIN document_version_files dvf ON dvf.document_version_id = dv.id
      WHERE rt.id = :task_id AND rt.assigned_to = :user_id
        AND rt.status IN ('in_progress', 'completed')
        AND dvf.id = :file_id AND dvf.availability = 'available'""",
      {"task_id": task_id, "file_id": file_id, "user_id": current_user.id})
    if not file:
        raise HTTPException(status_code=404, detail="上传文件不存在，或您尚未领取该复核任务")
    root = Path(settings.APPLICATION_DOCUMENT_STORAGE_PATH).resolve()
    target = (root / file["storage_key"]).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="上传文件已不可用")
    return FileResponse(target, media_type=file["mime_type"], filename=file["original_filename"])


@router.post("/staff/review-tasks/{task_id}/complete")
def complete_case_review_task(task_id: uuid.UUID, payload: CaseReviewComplete, session: SessionDep, current_user: CurrentUser) -> dict:
    """Save per-item administrator decisions and finish the claimed task."""
    require_administrator(current_user)
    task = one(session, """SELECT rt.id, rt.application_id, rt.check_run_id, a.status AS application_status
      FROM review_tasks rt JOIN applications a ON a.id = rt.application_id
      WHERE rt.id = :task_id AND rt.status = 'in_progress' AND rt.assigned_to = :user_id FOR UPDATE""",
      {"task_id": task_id, "user_id": current_user.id})
    if not task:
        raise HTTPException(status_code=409, detail="任务不存在、已取消、已完成或未由您领取")
    model_result = one(session, "SELECT model_result_json FROM check_runs WHERE id = :id", {"id": task["check_run_id"]})
    model_items = ((model_result or {}).get("model_result_json") or {}).get("items", [])
    flagged_names = {str(item.get("material_name", "")).strip() for item in model_items
                     if item.get("result") != "pass" and str(item.get("material_name", "")).strip()}
    decisions = [item.model_dump() for item in payload.item_decisions]
    decision_names = {item["material_name"].strip() for item in decisions}
    if flagged_names and decision_names != flagged_names:
        raise HTTPException(status_code=422, detail="请对模型标记的每一项待复核材料作出处理决定")
    reupload_items = [item for item in decisions if item["decision"] == "reupload"]
    if any(not item["note"].strip() for item in reupload_items):
        raise HTTPException(status_code=422, detail="选择“要求重传”时必须填写给用户的备注")
    outcome = "supplement_required" if reupload_items else "confirmed"
    # A review task now belongs to one material.  Passing this task must not
    # incorrectly label the whole application as prepared while other
    # checklist items are still being collected or reviewed.
    # Passing a review only completes material checking.  The resident creates
    # the immutable preparation package explicitly; only then is it "prepared".
    next_status = "needs_action" if reupload_items else "preparing"
    record_no = int(one(session, "SELECT COALESCE(MAX(record_no), 0) AS no FROM review_records WHERE task_id = :id", {"id": task_id})["no"]) + 1
    session.execute(text("""INSERT INTO review_records(id, task_id, record_no, actor_user_id, outcome, comment, details)
      VALUES (:id, :task_id, :record_no, :user_id, :outcome, :comment, CAST(:details AS jsonb))"""),
      {"id": uuid.uuid4(), "task_id": task_id, "record_no": record_no, "user_id": current_user.id,
       "outcome": outcome, "comment": payload.comment.strip(),
       "details": json.dumps({"source": "staff_case_review", "item_decisions": decisions}, ensure_ascii=False)})
    session.execute(text("""UPDATE review_tasks SET status = 'completed', completed_at = now(), updated_at = now()
      WHERE id = :id"""), {"id": task_id})
    session.execute(text("UPDATE applications SET status = :status, updated_at = now() WHERE id = :id"),
      {"status": next_status, "id": task["application_id"]})
    write_operation_audit(session, current_user.id, "case_review", "提交办件复核结果", "review_task", task_id)
    session.commit()
    return envelope({"id": task_id, "status": "completed", "application_status": next_status,
                     "outcome": outcome, "item_decisions": decisions})


@router.post("/applications/{app_id}/material-review")
def start_material_review(app_id: uuid.UUID, payload: MaterialReviewStart, session: SessionDep, current_user: CurrentUser) -> dict:
    """Run a preparation-only model check and route uncertainty to human review.

    Local uses OCR text then Ollama; cloud submits PDF/image bytes directly.
    """
    app = owned_application(session, app_id, current_user.id)
    require_open_preparation(app)
    require_revision(app, payload.expected_revision)
    checklist = checklist_for_review(session, app)
    if payload.material_id:
        checklist = [item for item in checklist if str(item["material_id"]) == str(payload.material_id)
                     and (payload.item_kind is None or item["item_kind"] == payload.item_kind)]
        if not checklist:
            raise HTTPException(status_code=404, detail="要审核的材料不属于当前办件")
        decision = latest_staff_material_decisions(session, app_id).get(checklist[0]["name"])
        if decision and decision["decision"] == "pass":
            raise HTTPException(status_code=409, detail="该材料已通过人工复核，无需再次模型审核")
        if decision and decision["decision"] == "reupload":
            if checklist[0]["item_kind"] == "requirement":
                newer_file = one(session, """SELECT EXISTS(SELECT 1 FROM application_documents ad
                  JOIN document_versions dv ON dv.document_id = ad.id AND dv.status = 'active'
                  WHERE ad.application_id = :app_id AND ad.requirement_id = :material_id
                    AND dv.created_at > :reviewed_at) AS exists""",
                  {"app_id": app_id, "material_id": payload.material_id, "reviewed_at": decision["created_at"]})
            else:
                newer_file = one(session, """SELECT EXISTS(SELECT 1 FROM application_documents ad
                  JOIN document_versions dv ON dv.document_id = ad.id AND dv.status = 'active'
                  WHERE ad.application_id = :app_id AND ad.document_code = :document_code
                    AND dv.created_at > :reviewed_at) AS exists""",
                  {"app_id": app_id, "document_code": f"extra-{payload.material_id}", "reviewed_at": decision["created_at"]})
            if not newer_file["exists"]:
                raise HTTPException(status_code=409, detail="该材料待重传，请先上传新的文件再进行模型检查")
    incomplete = [item["name"] for item in checklist if item["declaration"] != "ready" or not item["files"]]
    if not checklist:
        raise HTTPException(status_code=409, detail="当前事项尚未配置材料清单，不能开始材料审核")
    if incomplete:
        raise HTTPException(status_code=409, detail=f"请先标记并上传全部材料：{'、'.join(incomplete)}")

    run_id = uuid.uuid4()
    last_run = one(session, "SELECT COALESCE(MAX(run_no), 0) AS run_no FROM check_runs WHERE application_id = :id", {"id": app_id})
    run_no = int(last_run["run_no"]) + 1
    model_name = settings.OLLAMA_MODEL if payload.provider == "local" else settings.DASHSCOPE_MODEL
    session.execute(text("""INSERT INTO check_runs(
      id, application_id, matter_version_id, run_no, input_revision, idempotency_key, status,
      scenario_snapshot, config_snapshot, input_preparation_snapshot, engine_version, model_info, initiated_by, started_at)
      VALUES (:id, :app_id, :version_id, :run_no, :revision, :key, 'running',
        CAST(:scenario AS jsonb), CAST(:config AS jsonb), CAST(:items AS jsonb),
        'material-review-v1', CAST(:model AS jsonb), :user_id, now())"""), {
      "id": run_id, "app_id": app_id, "version_id": app["matter_version_id"], "run_no": run_no,
      "revision": app["content_revision"], "key": f"material-review-{uuid.uuid4().hex}",
      "scenario": json.dumps(app["scenario_answers"] or {}, ensure_ascii=False),
      "config": json.dumps({"provider": payload.provider, "purpose": "single_material" if payload.material_id else "preparation_only",
                              "material_id": str(payload.material_id) if payload.material_id else None}, ensure_ascii=False),
      "items": json.dumps([{"name": item["name"], "declaration": item["declaration"], "file_count": len(item["files"])} for item in checklist], ensure_ascii=False),
      "model": json.dumps({"provider": payload.provider, "model": model_name}, ensure_ascii=False), "user_id": current_user.id,
    })
    version_ids = {file["document_version_id"] for item in checklist for file in item["files"]}
    for version_id in version_ids:
        session.execute(text("""INSERT INTO check_run_documents(check_run_id, application_id, document_version_id)
          VALUES (:run_id, :app_id, :version_id)"""), {"run_id": run_id, "app_id": app_id, "version_id": version_id})
    session.commit()

    run_status, material_summary, next_status, error_code = "succeeded", "no_issue", "preparing" if payload.material_id else "prepared", None
    if payload.provider == "cloud":
        try:
            cloud_files: list[dict[str, Any]] = []
            storage_root = Path(settings.APPLICATION_DOCUMENT_STORAGE_PATH).resolve()
            for item in checklist:
                file_items: list[dict[str, str]] = []
                for file in item["files"]:
                    path = (storage_root / file["storage_key"]).resolve()
                    if storage_root not in path.parents or not path.is_file():
                        raise MatterImportModelError(f"上传文件不可用：{file['filename']}")
                    file_items.append({"path": str(path), "filename": file["filename"], "mime_type": file["mime_type"]})
                cloud_files.append({"material_name": item["name"], "files": file_items})
            checked, raw_content = review_cloud_material_files(cloud_files)
            result_data = {**checked.model_dump(), "raw_model_content": raw_content}
            if checked.decision == "manual_review":
                material_summary, next_status = "issues_found", "review_pending"
        except Exception as error:
            result_data = {"decision": "manual_review", "manual_review_required": True,
              "summary": "模型检查暂不可用，已转入人工复核。", "items": [
                {"material_name": item["name"], "result": "uncertain", "reason": str(error), "suggested_action": "稍后重试或申请人工复核"}
                for item in checklist], "raw_model_content": None}
            run_status, material_summary, next_status, error_code = "failed", "undetermined", "review_pending", "review_model_failed"
    else:
        evidence: list[dict[str, Any]] = []
        technical_errors: list[dict[str, str]] = []
        for item in checklist:
            file_evidence: list[dict[str, Any]] = []
            for file in item["files"]:
                try:
                    response = httpx.post(f"{settings.OCR_SERVICE_URL.rstrip('/')}/extract", json={
                        "storage_key": file["storage_key"], "mime_type": file["mime_type"], "storage_area": "applications",
                    }, timeout=settings.OCR_TIMEOUT_SECONDS)
                    response.raise_for_status()
                    blocks = response.json().get("blocks", [])
                    text_value = "\n".join(str(block.get("text", "")).strip() for block in blocks if block.get("text"))
                    if not text_value:
                        raise ValueError("未识别到可用文字")
                    file_evidence.append({"filename": file["filename"], "text": text_value[:30000]})
                except Exception as error:
                    technical_errors.append({"material_name": item["name"], "reason": f"{file['filename']}：{error}"})
            evidence.append({"material_name": item["name"], "files": file_evidence})
        if technical_errors:
            result_data = {"decision": "manual_review", "manual_review_required": True,
              "summary": "部分上传材料无法识别，已进入人工复核。", "items": [
                {"material_name": error["material_name"], "result": "uncertain", "reason": error["reason"], "suggested_action": "请重新上传清晰文件或申请人工复核"}
                for error in technical_errors], "raw_model_content": None}
            run_status, material_summary, next_status, error_code = "failed", "undetermined", "review_pending", "ocr_extract_failed"
        else:
            try:
                checked, raw_content = review_materials(evidence, "local")
                result_data = {**checked.model_dump(), "raw_model_content": raw_content}
                if checked.decision == "manual_review":
                    material_summary, next_status = "issues_found", "review_pending"
            except Exception as error:
                result_data = {"decision": "manual_review", "manual_review_required": True,
                  "summary": "模型检查暂不可用，已转入人工复核。", "items": [
                    {"material_name": item["name"], "result": "uncertain", "reason": str(error), "suggested_action": "稍后重试或申请人工复核"}
                    for item in checklist], "raw_model_content": None}
                run_status, material_summary, next_status, error_code = "failed", "undetermined", "review_pending", "review_model_failed"

    session.execute(text("""UPDATE check_runs SET status = :status, material_summary = :summary,
      eligibility_summary = 'not_evaluated', model_result_json = CAST(:result AS jsonb),
      error_code = :error_code, finished_at = now() WHERE id = :id"""), {
      "status": run_status, "summary": material_summary, "result": json.dumps(result_data, ensure_ascii=False),
      "error_code": error_code, "id": run_id,
    })
    session.execute(text("UPDATE applications SET status = :status, updated_at = now() WHERE id = :id"), {"status": next_status, "id": app_id})
    if next_status == "review_pending":
        session.execute(text("""INSERT INTO review_tasks(id, application_id, check_run_id, scope, status, requested_by, request_note)
          VALUES (:id, :app_id, :run_id, 'application', 'pending', :user_id, '模型材料检查存在待确认项')"""),
          {"id": uuid.uuid4(), "app_id": app_id, "run_id": run_id, "user_id": current_user.id})
    write_operation_audit(session, current_user.id, "application", "材料模型审核", "check_run", run_id)
    session.commit()
    return envelope({"id": run_id, "status": run_status, "provider": payload.provider,
                     "decision": result_data["decision"], "application_status": next_status, "result": result_data})


@router.put("/applications/{app_id}/preparation-items")
def update_preparation_item(app_id: uuid.UUID, payload: PreparationItemUpdate, session: SessionDep, current_user: CurrentUser) -> dict:
    app = owned_application(session, app_id, current_user.id)
    require_open_preparation(app)
    require_revision(app, payload.expected_revision)
    requirement = one(session, """
        SELECT name, submission_mode FROM material_requirements WHERE id = :requirement_id
          AND matter_version_id = :version_id
    """, {"requirement_id": payload.requirement_id, "version_id": app["matter_version_id"]})
    if not requirement:
        raise HTTPException(status_code=404, detail="该材料要求不属于当前办件版本")
    staff_decision = latest_staff_material_decisions(session, app_id).get(requirement["name"])
    if staff_decision and staff_decision["decision"] == "pass" and payload.declaration != "ready":
        raise HTTPException(status_code=409, detail="该材料已通过复核，不能取消“已准备”状态")
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
    session.execute(text("UPDATE applications SET status = 'preparing', content_revision = content_revision + 1, updated_at = now() WHERE id = :id"), {"id": app_id})
    session.commit()
    return envelope({"requirement_id": payload.requirement_id, "participant_id": payload.participant_id,
                     "declaration": payload.declaration, "content_revision": app["content_revision"] + 1})


@router.put("/applications/{app_id}/extra-materials/{material_id}")
def update_extra_material_preparation(
    app_id: uuid.UUID, material_id: uuid.UUID, payload: ExtraMaterialPreparationUpdate,
    session: SessionDep, current_user: CurrentUser,
) -> dict:
    app = owned_application(session, app_id, current_user.id)
    require_open_preparation(app)
    require_revision(app, payload.expected_revision)
    material = one(session, "SELECT id, name FROM application_extra_materials WHERE id = :id AND application_id = :app_id",
                   {"id": material_id, "app_id": app_id})
    if not material:
        raise HTTPException(status_code=404, detail="办件专属材料不存在")
    staff_decision = latest_staff_material_decisions(session, app_id).get(material["name"])
    if staff_decision and staff_decision["decision"] == "pass" and payload.declaration != "ready":
        raise HTTPException(status_code=409, detail="该材料已通过复核，不能取消“已准备”状态")
    updated = one(session, """UPDATE application_extra_materials SET declaration = :declaration,
      updated_at = now() WHERE id = :id AND application_id = :app_id RETURNING id""",
      {"id": material_id, "app_id": app_id, "declaration": payload.declaration})
    session.execute(text("UPDATE applications SET status = 'preparing', content_revision = content_revision + 1, updated_at = now() WHERE id = :id"), {"id": app_id})
    session.commit()
    return envelope({"id": material_id, "declaration": payload.declaration,
                     "content_revision": app["content_revision"] + 1})
