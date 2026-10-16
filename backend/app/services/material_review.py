"""AI-assisted review of materials uploaded to one preparation record.

The result is deliberately an aid for preparation only.  It never represents
an administrative acceptance decision and uncertain evidence is routed to a
human reviewer instead of being treated as a pass.
"""

import base64
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.matter_import import MatterImportModelError, call_model, parse_model_json


class MaterialReviewItem(BaseModel):
    material_name: str
    result: Literal["pass", "issue", "uncertain"]
    reason: str = Field(min_length=1, max_length=1000)
    suggested_action: str | None = Field(default=None, max_length=1000)


class MaterialReviewResult(BaseModel):
    decision: Literal["pass", "manual_review"]
    summary: str = Field(min_length=1, max_length=2000)
    manual_review_required: bool
    items: list[MaterialReviewItem] = Field(default_factory=list)


SYSTEM_PROMPT = """You are an assistant helping residents prepare government-service materials.
You are not an administrative authority and must not make a formal acceptance decision.
Review only the supplied OCR/text evidence against the supplied material list.  Do not invent facts.
Use decision=pass only when every listed material has readable, non-conflicting evidence and no item is uncertain.
If a file is unreadable, missing information, appears inconsistent, or evidence is insufficient, use decision=manual_review and explain why.
Write summary, every reason, and every suggested_action in Simplified Chinese. Keep material_name in the same language as the supplied checklist.
Return exactly one JSON object matching the schema. Do not return Markdown, explanations, or reasoning outside JSON."""


def review_materials(materials: list[dict[str, Any]], provider: str) -> tuple[MaterialReviewResult, str]:
    """Call the selected model once with all extracted material evidence.

    The raw model content is returned separately so it can be retained for an
    audit trail alongside the validated structured result.
    """
    evidence = json.dumps(materials, ensure_ascii=False)
    raw = call_model([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Material requirements and extracted evidence:\n{evidence}"},
    ], MaterialReviewResult, provider)
    try:
        result = MaterialReviewResult.model_validate(parse_model_json(raw))
    except (json.JSONDecodeError, ValueError) as error:
        raise MatterImportModelError("模型返回的材料检查结果不是有效 JSON") from error
    # Never allow a contradictory or incomplete structured response to become a pass.
    # A pass must explicitly cover every checklist material, not merely omit it.
    expected_names = {str(item.get("material_name", "")).strip() for item in materials}
    returned_names = {item.material_name.strip() for item in result.items}
    missing_names = sorted(name for name in expected_names if name and name not in returned_names)
    if missing_names:
        result.items.extend(MaterialReviewItem(
            material_name=name, result="uncertain",
            reason="模型未对该材料返回可核验的检查结论。",
            suggested_action="请人工复核或重新检查。",
        ) for name in missing_names)
    if result.manual_review_required or any(item.result != "pass" for item in result.items):
        result.decision = "manual_review"
        result.manual_review_required = True
    return result, raw


def review_cloud_material_files(materials: list[dict[str, Any]]) -> tuple[MaterialReviewResult, str]:
    """Send uploaded PDF/image bytes directly to the configured cloud model.

    This path intentionally does not call OCR.  The compatible DashScope API
    accepts PDF and image attachments; unsupported file types are described as
    unavailable rather than being silently OCR-processed.
    """
    attachment_content: list[dict[str, Any]] = []
    mapping: list[str] = []
    unsupported: list[str] = []
    for material in materials:
        material_name = str(material["material_name"])
        for file in material["files"]:
            path = Path(file["path"])
            suffix = path.suffix.lower()
            mapping.append(f"- {material_name}: {file['filename']}")
            if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
                unsupported.append(f"{material_name}（{file['filename']}）")
                continue
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            data_url = f"data:{file['mime_type']};base64,{encoded}"
            if suffix == ".pdf":
                attachment_content.append({"type": "file", "file": {
                    "file_data": data_url, "filename": file["filename"], "file_format": "pdf",
                }})
            else:
                attachment_content.append({"type": "image_url", "image_url": {"url": data_url}})
    if unsupported:
        raise MatterImportModelError("云端直接审核暂支持 PDF 和图片；以下文件请转换后重新上传：" + "、".join(unsupported))
    if not attachment_content:
        raise MatterImportModelError("没有可直接提交给云端模型的 PDF 或图片")
    attachment_content.append({"type": "text", "text": """Review the uploaded resident materials directly.
You are an assistant for preparation only, not an administrative authority. Do not make a formal acceptance decision.
Return exactly one JSON object matching the schema. A pass requires every listed material to be readable and consistent; otherwise use manual_review.
Write summary, every reason, and every suggested_action in Simplified Chinese.
Material-to-file mapping:\n""" + "\n".join(mapping)})
    raw = call_model([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": attachment_content},
    ], MaterialReviewResult, "cloud")
    try:
        result = MaterialReviewResult.model_validate(parse_model_json(raw))
    except (json.JSONDecodeError, ValueError) as error:
        raise MatterImportModelError("云端模型返回的材料检查结果不是有效 JSON") from error
    expected_names = {str(item.get("material_name", "")).strip() for item in materials}
    returned_names = {item.material_name.strip() for item in result.items}
    for name in sorted(name for name in expected_names if name and name not in returned_names):
        result.items.append(MaterialReviewItem(material_name=name, result="uncertain",
            reason="模型未对该材料返回可核验的检查结论。", suggested_action="请人工复核或重新检查。"))
    if result.manual_review_required or any(item.result != "pass" for item in result.items):
        result.decision = "manual_review"
        result.manual_review_required = True
    return result, raw
