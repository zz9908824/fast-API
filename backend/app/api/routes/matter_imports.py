"""Administrator-only text-to-draft matter imports backed by local Ollama."""

import hashlib
import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import text

from app.api.deps import CurrentUser, SessionDep
from app.api.routes.precheck import envelope, one, require_administrator
from app.core.config import settings
from app.schemas.matter_import import MatterImportCandidate, MatterImportStart
from app.services.matter_import import (
    MatterImportModelError,
    extract_candidate,
    extract_cloud_candidate_from_files,
)

router = APIRouter(tags=["事项智能导入"])
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_FILE_SIZE = 30 * 1024 * 1024
MAX_MODEL_TEXT_CHARS = 120_000


def job_for_admin(session: SessionDep, job_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
    job = one(session, "SELECT * FROM matter_import_jobs WHERE id = :id AND initiated_by = :user_id", {"id": job_id, "user_id": user_id})
    if not job:
        raise HTTPException(status_code=404, detail="导入任务不存在或无权访问")
    return job


def mark_job_failed(session: SessionDep, job_id: uuid.UUID, message: str) -> None:
    session.execute(text("""UPDATE matter_import_jobs SET status = 'failed', error_message = :error,
      finished_at = now() WHERE id = :id"""), {"id": job_id, "error": message[:4000]})
    session.commit()


def save_candidate(session: SessionDep, job_id: uuid.UUID, source_text: str, model_provider: str) -> dict[str, Any]:
    try:
        candidate = extract_candidate(source_text, model_provider)
    except MatterImportModelError as error:
        mark_job_failed(session, job_id, str(error))
        raise HTTPException(status_code=503, detail=str(error)) from error
    candidate_json = candidate.model_dump(mode="json")
    session.execute(text("""UPDATE matter_import_jobs SET status = 'ready', input_text = :input_text,
      input_sha256 = :input_sha256, candidate_json = CAST(:candidate AS jsonb), finished_at = now() WHERE id = :id"""), {
        "id": job_id, "input_text": source_text, "input_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "candidate": json.dumps(candidate_json, ensure_ascii=False),
    })
    session.commit()
    return candidate_json


def save_cloud_file_candidate(
    session: SessionDep,
    job_id: uuid.UUID,
    source_text: str,
    cloud_files: list[dict[str, str]],
) -> dict[str, Any]:
    """Persist a candidate extracted from the original PDF/image attachments."""
    try:
        candidate = extract_cloud_candidate_from_files(cloud_files, source_text)
    except MatterImportModelError as error:
        mark_job_failed(session, job_id, str(error))
        raise HTTPException(status_code=503, detail=str(error)) from error
    candidate_json = candidate.model_dump(mode="json")
    session.execute(text("""UPDATE matter_import_jobs SET status = 'ready', input_text = :input_text,
      input_sha256 = :input_sha256, candidate_json = CAST(:candidate AS jsonb), finished_at = now() WHERE id = :id"""), {
        "id": job_id, "input_text": source_text, "input_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "candidate": json.dumps(candidate_json, ensure_ascii=False),
    })
    session.commit()
    return candidate_json


@router.post("/admin/matter-imports", status_code=status.HTTP_201_CREATED)
def start_matter_import(payload: MatterImportStart, session: SessionDep, current_user: CurrentUser) -> dict:
    """Persist input and candidate result. The model never writes business tables directly."""
    require_administrator(current_user)
    job_id = uuid.uuid4()
    source_text = payload.pasted_text.strip()
    session.execute(text("""
        INSERT INTO matter_import_jobs(
          id, initiated_by, status, region_code, region_name, source_url, source_kind,
          model_provider, source_title_override, import_note, input_text, input_sha256
        ) VALUES (
          :id, :user_id, 'running', :region_code, :region_name, :source_url, :source_kind,
          :model_provider, :title_override, :import_note, :input_text, :input_sha256
        )
    """), {
        "id": job_id, "user_id": current_user.id, "region_code": payload.region_code.strip(),
        "region_name": payload.region_name.strip(), "source_url": str(payload.source_url),
        "source_kind": payload.source_kind, "title_override": payload.source_title_override.strip() if payload.source_title_override else None,
        "model_provider": payload.model_provider,
        "import_note": payload.import_note.strip() if payload.import_note else None,
        "input_text": source_text, "input_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
    })
    session.commit()
    candidate_json = save_candidate(session, job_id, source_text, payload.model_provider)
    return envelope({"id": job_id, "status": "ready", "candidate": candidate_json})


@router.post("/admin/matter-imports/upload", status_code=status.HTTP_201_CREATED)
async def start_file_matter_import(
    session: SessionDep,
    current_user: CurrentUser,
    region_code: str = Form(...),
    region_name: str = Form(...),
    source_url: str = Form(...),
    source_kind: str = Form("guide"),
    model_provider: str = Form("local"),
    pasted_text: str = Form(""),
    source_title_override: str = Form(""),
    import_note: str = Form(""),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """Store documents, extract page-aware text in OCR worker, then call Ollama."""
    require_administrator(current_user)
    if not files and len(pasted_text.strip()) < 20:
        raise HTTPException(status_code=422, detail="请上传至少一个文件，或粘贴不少于 20 个字符的资料正文")
    try:
        payload = MatterImportStart(
            region_code=region_code, region_name=region_name, source_url=source_url, source_kind=source_kind,
            pasted_text=pasted_text or " " * 20, source_title_override=source_title_override or None,
            import_note=import_note or None, model_provider=model_provider,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    for upload in files:
        if Path(upload.filename or "").suffix.lower() not in ALLOWED_SUFFIXES:
            raise HTTPException(status_code=415, detail="仅支持 PDF、DOCX、TXT、JPG、PNG、WEBP 文件")
    job_id = uuid.uuid4()
    session.execute(text("""
        INSERT INTO matter_import_jobs(id, initiated_by, status, region_code, region_name, source_url, source_kind,
          model_provider, source_title_override, import_note, input_text, input_sha256)
        VALUES (:id, :user_id, 'running', :region_code, :region_name, :source_url, :source_kind,
          :model_provider, :title_override, :import_note, '', :input_sha256)
    """), {"id": job_id, "user_id": current_user.id, "region_code": payload.region_code.strip(),
              "region_name": payload.region_name.strip(), "source_url": str(payload.source_url), "source_kind": payload.source_kind,
              "model_provider": payload.model_provider,
              "title_override": payload.source_title_override, "import_note": payload.import_note,
              "input_sha256": hashlib.sha256(b"").hexdigest()})
    storage_root = Path(settings.IMPORT_STORAGE_PATH).resolve()
    job_root = (storage_root / str(job_id)).resolve()
    if storage_root not in job_root.parents:
        raise HTTPException(status_code=500, detail="导入文件存储路径配置无效")
    job_root.mkdir(parents=True, exist_ok=True)
    total_size = 0
    imported_files: list[dict[str, Any]] = []
    try:
        for upload in files:
            file_id = uuid.uuid4()
            suffix = Path(upload.filename or "").suffix.lower()
            storage_key = f"{job_id}/{file_id}{suffix}"
            target = (storage_root / storage_key).resolve()
            digest = hashlib.sha256()
            size = 0
            with target.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    total_size += len(chunk)
                    if size > MAX_FILE_SIZE or total_size > MAX_TOTAL_FILE_SIZE:
                        raise HTTPException(status_code=413, detail="单文件最大 10MB，所有文件合计最大 30MB")
                    digest.update(chunk)
                    output.write(chunk)
            if suffix == ".pdf":
                with target.open("rb") as uploaded_pdf:
                    pdf_header = uploaded_pdf.read(5)
                if not pdf_header.startswith(b"%PDF-"):
                    raise HTTPException(status_code=415, detail=f"{upload.filename} 不是有效的 PDF 文件")
            session.execute(text("""
              INSERT INTO matter_import_files(id, job_id, original_filename, mime_type, byte_size, file_sha256, storage_key)
              VALUES (:id, :job_id, :filename, :mime_type, :byte_size, :sha256, :storage_key)
            """), {"id": file_id, "job_id": job_id, "filename": Path(upload.filename or "upload").name,
                  "mime_type": upload.content_type or "application/octet-stream", "byte_size": size,
                  "sha256": digest.hexdigest(), "storage_key": storage_key})
            imported_files.append({
                "id": file_id, "storage_key": storage_key,
                "mime_type": upload.content_type or "application/octet-stream",
                "filename": Path(upload.filename or "upload").name, "suffix": suffix,
                "path": str(target),
            })
        session.commit()
        blocks: list[dict[str, Any]] = []
        # Cloud Qwen reads PDF/image binaries itself.  DOCX/TXT are the only
        # formats that still need their text extracted locally before sending.
        files_for_ocr = imported_files if payload.model_provider == "local" else [
            item for item in imported_files if item["suffix"] in {".docx", ".txt"}
        ]
        with httpx.Client(timeout=settings.OCR_TIMEOUT_SECONDS) as client:
            for item in files_for_ocr:
                response = client.post(f"{settings.OCR_SERVICE_URL.rstrip('/')}/extract", json={"storage_key": item["storage_key"], "mime_type": item["mime_type"]})
                response.raise_for_status()
                extracted = response.json().get("blocks", [])
                for block in extracted:
                    if not isinstance(block.get("text"), str):
                        continue
                    blocks.append({**block, "file_id": item["id"]})
                    session.execute(text("""
                      INSERT INTO matter_import_document_blocks(id, file_id, block_id, page_number, text_content, bbox_json, ocr_confidence, extraction_method)
                      VALUES (:id, :file_id, :block_id, :page_number, :text_content, CAST(:bbox AS jsonb), :confidence, :method)
                    """), {"id": uuid.uuid4(), "file_id": item["id"], "block_id": str(block.get("block_id", "block"))[:120],
                              "page_number": block.get("page_number"), "text_content": block["text"],
                              "bbox": json.dumps(block.get("bbox")), "confidence": block.get("confidence"), "method": block.get("method", "unknown")})
                page_numbers = [block.get("page_number") for block in extracted if isinstance(block.get("page_number"), int)]
                session.execute(text("""UPDATE matter_import_files
                  SET parse_status = 'succeeded', page_count = :page_count WHERE id = :id"""),
                                {"id": item["id"], "page_count": max(page_numbers) if page_numbers else None})
        if payload.model_provider == "cloud":
            for item in imported_files:
                if item["suffix"] in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
                    session.execute(text("""UPDATE matter_import_files
                      SET parse_status = 'succeeded' WHERE id = :id"""), {"id": item["id"]})
        session.commit()
    except HTTPException as error:
        session.rollback()
        mark_job_failed(session, job_id, str(error.detail))
        raise
    except httpx.HTTPError as error:
        session.rollback()
        mark_job_failed(session, job_id, f"OCR 服务不可用：{error}")
        raise HTTPException(status_code=503, detail="OCR 服务暂不可用，请确认 ocr-worker 已启动") from error
    except Exception as error:
        session.rollback()
        mark_job_failed(session, job_id, f"文件解析失败：{error}")
        raise HTTPException(status_code=422, detail="文件解析失败，请检查文件是否损坏或受保护") from error
    direct_cloud_file_names = [item["filename"] for item in imported_files if item["suffix"] in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}]
    source_parts = [
        pasted_text.strip(),
        *[f"[云端直接读取的附件] {name}" for name in direct_cloud_file_names],
        *[f"[文件 {block['file_id']} / 页 {block.get('page_number') or '无页码'}] {block['text']}" for block in blocks],
    ]
    source_text = "\n\n".join(part for part in source_parts if part).strip()
    if len(source_text) < 20 and not direct_cloud_file_names:
        mark_job_failed(session, job_id, "未能从上传资料中识别到可用文字")
        raise HTTPException(status_code=422, detail="未能从上传资料中识别到可用文字")
    if len(source_text) > MAX_MODEL_TEXT_CHARS:
        mark_job_failed(session, job_id, "提取文字超过模型单次处理上限")
        raise HTTPException(status_code=422, detail="提取文字过多，请拆分文件后再导入（单次最多 12 万字符）")
    if payload.model_provider == "cloud":
        cloud_files = [
            {"path": item["path"], "mime_type": item["mime_type"], "filename": item["filename"]}
            for item in imported_files if item["suffix"] in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
        ]
        candidate_json = save_cloud_file_candidate(session, job_id, source_text, cloud_files)
    else:
        candidate_json = save_candidate(session, job_id, source_text, payload.model_provider)
    return envelope({"id": job_id, "status": "ready", "candidate": candidate_json,
                     "file_count": len(imported_files), "block_count": len(blocks)})


@router.get("/admin/matter-imports/{job_id}")
def get_matter_import(job_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    require_administrator(current_user)
    job = job_for_admin(session, job_id, current_user.id)
    return envelope({
        "id": job["id"], "status": job["status"], "candidate": job["candidate_json"],
        "model_provider": job["model_provider"],
        "error_message": job["error_message"], "matter_version_id": job["matter_version_id"],
        "created_at": job["created_at"], "finished_at": job["finished_at"],
    })


def active_material_type_id(session: SessionDep, candidate_name: str | None) -> uuid.UUID:
    material_type = None
    if candidate_name:
        material_type = one(session, "SELECT id FROM material_types WHERE is_active = true AND name = :name", {"name": candidate_name.strip()})
    material_type = material_type or one(session, "SELECT id FROM material_types WHERE is_active = true ORDER BY name LIMIT 1")
    if not material_type:
        raise HTTPException(status_code=409, detail="尚未配置可用的材料类别，无法生成事项草稿")
    return material_type["id"]


@router.post("/admin/matter-imports/{job_id}/apply", status_code=status.HTTP_201_CREATED)
def apply_matter_import(job_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> dict:
    """Create one isolated draft from a reviewed candidate; publishing remains manual."""
    require_administrator(current_user)
    job = job_for_admin(session, job_id, current_user.id)
    if job["status"] == "applied":
        return envelope({"job_id": job_id, "matter_version_id": job["matter_version_id"], "status": "draft"})
    if job["status"] != "ready" or not job["candidate_json"]:
        raise HTTPException(status_code=409, detail="导入任务尚未生成可用候选结果")
    candidate = MatterImportCandidate.model_validate(job["candidate_json"])
    if not candidate.matter.name or not candidate.matter.name.strip():
        raise HTTPException(status_code=422, detail="候选结果缺少事项名称，不能生成草稿")
    if not candidate.location.name or not candidate.location.name.strip():
        raise HTTPException(status_code=422, detail="候选结果缺少办理地点名称，请补充资料后重新提取")

    source_id, location_id, matter_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    skipped_materials: list[str] = []
    try:
        published_date = None
        if candidate.source.published_date:
            try:
                published_date = date.fromisoformat(candidate.source.published_date)
            except ValueError:
                pass
        source_title = job["source_title_override"] or candidate.source.title or candidate.matter.name
        session.execute(text("""
            INSERT INTO policy_sources(id, title, source_kind, url, publisher, published_date, content_text, content_sha256)
            VALUES (:id, :title, :source_kind, :url, :publisher, :published_date, :content_text, :content_sha256)
        """), {"id": source_id, "title": source_title[:300], "source_kind": job["source_kind"], "url": job["source_url"],
              "publisher": candidate.source.publisher, "published_date": published_date, "content_text": job["input_text"], "content_sha256": job["input_sha256"]})
        session.execute(text("""
            INSERT INTO service_locations(id, name, region_code, address, phone, opening_hours, official_entry_url, source_id)
            VALUES (:id, :name, :region_code, :address, :phone, :opening_hours, :entry_url, :source_id)
        """), {"id": location_id, "name": candidate.location.name.strip(), "region_code": job["region_code"],
              "address": candidate.location.address, "phone": candidate.location.phone,
              "opening_hours": candidate.location.opening_hours, "entry_url": candidate.location.official_entry_url, "source_id": source_id})
        matter_code = f"import_{matter_id.hex}"
        session.execute(text("""
            INSERT INTO service_matters(id, code, official_code, name, region_code, region_name, description)
            VALUES (:id, :code, :official_code, :name, :region_code, :region_name, :description)
        """), {"id": matter_id, "code": matter_code, "official_code": candidate.matter.official_code,
              "name": candidate.matter.name.strip(), "region_code": job["region_code"], "region_name": job["region_name"],
              "description": candidate.matter.description})
        uncertainties = [item.message for item in candidate.uncertainties]
        metadata = {
            "acceptance_condition_raw": candidate.scope.acceptance_condition_raw or "",
            "channels": candidate.scope.channels,
            "uncertainties": uncertainties,
            "government_details_verification_status": "pending",
            "import_job_id": str(job_id), "import_note": job["import_note"],
        }
        session.execute(text("""
            INSERT INTO matter_versions(
              id, matter_id, version_no, status, service_location_id, created_by, metadata_json,
              government_profile_json, processing_steps_json, legal_bases_json, field_evidence_json
            ) VALUES (
              :id, :matter_id, 1, 'draft', :location_id, :created_by, CAST(:metadata AS jsonb),
              CAST(:government_profile AS jsonb), CAST(:processing_steps AS jsonb),
              CAST(:legal_bases AS jsonb), CAST(:field_evidence AS jsonb)
            )
        """), {"id": version_id, "matter_id": matter_id, "location_id": location_id, "created_by": current_user.id,
              "metadata": json.dumps(metadata, ensure_ascii=False),
              "government_profile": json.dumps(candidate.government_profile, ensure_ascii=False),
              "processing_steps": json.dumps([item.model_dump(mode="json") for item in candidate.processing_steps], ensure_ascii=False),
              "legal_bases": json.dumps(candidate.legal_bases, ensure_ascii=False),
              "field_evidence": json.dumps([item.model_dump(mode="json") for item in candidate.field_evidence], ensure_ascii=False)})
        for order, material in enumerate(candidate.materials, start=1):
            if not material.name or material.requirement_level is None or material.submission_mode is None:
                skipped_materials.append(material.name or material.local_key)
                continue
            requirement_id = uuid.uuid4()
            session.execute(text("""
                INSERT INTO material_requirements(
                  id, matter_version_id, material_type_id, requirement_code, name, requirement_level,
                  provider_role, submission_mode, original_required, copy_count, min_pages, format_requirements, sort_order
                ) VALUES (
                  :id, :version_id, :type_id, :code, :name, :level,
                  :provider_role, :submission_mode, :original_required, :copy_count, :min_pages, :format_requirements, :sort_order
                )
            """), {"id": requirement_id, "version_id": version_id,
                  "type_id": active_material_type_id(session, material.type_name_candidate),
                  "code": f"import_{requirement_id.hex[:16]}", "name": material.name.strip(),
                  "level": material.requirement_level, "provider_role": material.provider_role,
                  "submission_mode": material.submission_mode, "original_required": material.original_required,
                  "copy_count": material.copy_count, "min_pages": material.min_pages,
                  "format_requirements": material.format_requirements, "sort_order": order})
            for method_order, method in enumerate(material.acquisition_methods, start=1):
                if not method.title or method.method_type is None:
                    continue
                method_id = uuid.uuid4()
                session.execute(text("""
                    INSERT INTO material_acquisition_methods(
                      id, requirement_id, method_code, method_type, title, steps, entry_url, sort_order
                    ) VALUES (:id, :requirement_id, :code, :method_type, :title, :steps, :entry_url, :sort_order)
                """), {"id": method_id, "requirement_id": requirement_id, "code": f"import_{method_id.hex[:16]}",
                      "method_type": method.method_type, "title": method.title.strip(), "steps": method.steps,
                      "entry_url": method.entry_url, "sort_order": method_order})
        if skipped_materials:
            metadata["uncertainties"].append(f"以下材料的必要性或提交方式不明确，未自动导入：{'、'.join(skipped_materials)}")
            session.execute(text("UPDATE matter_versions SET metadata_json = CAST(:metadata AS jsonb) WHERE id = :id"),
                            {"id": version_id, "metadata": json.dumps(metadata, ensure_ascii=False)})
        session.execute(text("""UPDATE matter_import_jobs SET status = 'applied', matter_version_id = :version_id,
          applied_at = now() WHERE id = :job_id"""), {"job_id": job_id, "version_id": version_id})
        # A model conclusion is only a candidate. Store it in the versioned
        # delegation configuration as pending so an administrator must verify
        # it before the draft can be published.
        # Every imported draft gets one pending policy, even if the source is
        # silent. That makes “not extracted” visible to the reviewer instead
        # of silently treating it as “delegation is not allowed”.
        if candidate.delegation is not None:
            delegation_policy_id = uuid.uuid4()
            session.execute(text("""INSERT INTO matter_delegation_policies(
              id, matter_version_id, delegation_allowed, applicant_must_attend,
              relationship_required, allowed_relationships, condition_expr,
              questionnaire_required, verification_status, source_id)
              VALUES (:id, :version_id, :allowed, false, false, '[]'::jsonb,
                '{\"op\":\"always\"}'::jsonb, :questionnaire_required, 'pending', :source_id)"""),
              {"id": delegation_policy_id, "version_id": version_id,
               "allowed": bool(candidate.delegation.delegation_allowed),
               "questionnaire_required": bool(candidate.delegation.delegation_allowed),
               "source_id": source_id})
            for order, material in enumerate(candidate.delegation.materials, start=1):
                if not material.name or material.requirement_level is None or material.submission_mode is None:
                    continue
                session.execute(text("""INSERT INTO matter_delegation_material_requirements(
                  id, delegation_policy_id, material_code, name, requirement_level,
                  submission_mode, applicability_expr, sort_order, verification_status)
                  VALUES (:id, :policy_id, :code, :name, :level, :mode,
                    '{\"op\":\"always\"}'::jsonb, :sort_order, 'pending')"""),
                  {"id": uuid.uuid4(), "policy_id": delegation_policy_id,
                   "code": f"import_delegation_{order}_{uuid.uuid4().hex[:8]}",
                   "name": material.name.strip(), "level": material.requirement_level,
                   "mode": material.submission_mode, "sort_order": order})
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception as error:
        session.rollback()
        raise HTTPException(status_code=500, detail="生成事项草稿失败，未写入不完整数据") from error
    return envelope({"job_id": job_id, "matter_id": matter_id, "matter_version_id": version_id, "status": "draft"})
