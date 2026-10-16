import base64
import json
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.schemas.matter_import import (
    ImportChannelsCandidate,
    ImportCoreCandidate,
    ImportDelegationCandidate,
    ImportLocation,
    ImportLocationCandidate,
    ImportMaterialsCandidate,
    ImportPhoneCandidate,
    MatterImportCandidate,
)
from app.services.matter_import_examples import few_shot_messages
from app.services.matter_import_mapping import normalize_government_portal_payload


class MatterImportModelError(Exception):
    pass


def parse_model_json(content: str) -> object:
    """Accept JSON wrapped in a Markdown code fence or explanatory text."""
    value = content.strip()
    if value.startswith("```"):
        first_newline = value.find("\n")
        if first_newline != -1:
            value = value[first_newline + 1 :]
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    try:
        return json.loads(value.strip())
    except json.JSONDecodeError as first_error:
        start, end = value.find("{"), value.rfind("}")
        if start == -1 or end <= start:
            raise first_error
        return json.loads(value[start : end + 1])


SYSTEM_PROMPT = """Extract facts only from the supplied government-service document.
Return exactly one JSON object that conforms to the supplied JSON Schema. Do not return Markdown, explanations, or reasoning.
Unknown scalar values must be null and unknown lists must be []. Never invent a phone number, address, material, date, URL, or official code.
Do not output UUIDs, database IDs, or system statuses. Put ambiguous or conditional requirements in uncertainties instead of marking them universally required."""

T = TypeVar("T", bound=BaseModel)

TASK_INSTRUCTIONS = {
    "core": "Extract only the matter name/code/description, source metadata, acceptance condition, and uncertainties. Leave scope.channels as [].",
    "materials": "Extract only the material list and each material's requirement, submission mode, and acquisition methods. Do not extract location, phone, or channels.",
    "location": "Extract only the service-location name, full address, opening hours, and official entry URL. Do not extract the phone number.",
    "phone": "Extract only the public consultation or service phone number. Return null when no phone number is explicitly stated.",
    "channels": "Extract only confirmed handling channels. Do not include a channel described as pending, uncertain, consultation-only, password reset, or unrelated.",
    "delegation": "Extract only whether the matter explicitly permits an agent to handle it, and materials required only for that agent. Return delegation_allowed as null when the source does not explicitly say. Do not treat help preparing materials as permission to act as an agent.",
}


def call_model(messages: list[dict[str, Any]], result_model: type[T], model_provider: str) -> str:
    """Call either the private Ollama endpoint or DashScope's OpenAI-compatible API."""
    schema = result_model.model_json_schema()
    try:
        if model_provider == "local":
            response = httpx.post(
                f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "stream": False,
                    "think": False,
                    "format": schema,
                    "messages": messages,
                    "options": {"temperature": 0},
                },
                timeout=settings.OLLAMA_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            content = response.json().get("message", {}).get("content")
        elif model_provider == "cloud":
            if not settings.DASHSCOPE_API_KEY:
                raise MatterImportModelError("云端模型未配置：请先在 .env 设置 DASHSCOPE_API_KEY")
            response = httpx.post(
                f"{settings.DASHSCOPE_BASE_URL.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}"},
                json={
                    "model": settings.DASHSCOPE_MODEL,
                    "messages": messages,
                    # JSON Schema is more reliable for importing records than
                    # streaming a reasoning trace into the application.
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": result_model.__name__, "strict": True, "schema": schema},
                    },
                    "enable_thinking": False,
                    "temperature": 0,
                },
                timeout=settings.DASHSCOPE_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            choices = response.json().get("choices", [])
            content = choices[0].get("message", {}).get("content") if choices else None
        else:
            raise MatterImportModelError("不支持的模型来源")
    except httpx.HTTPError as error:
        name = "云端大模型" if model_provider == "cloud" else "本地 Ollama"
        raise MatterImportModelError(f"无法连接{name}：{error}") from error
    if not isinstance(content, str) or not content.strip():
        raise MatterImportModelError("模型未返回结构化内容")
    return content


def extract_task(document_text: str, task: str, result_model: type[T], model_provider: str) -> T:
    """Run a small, field-specific extraction task with a curated few-shot pair."""
    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nTask: {TASK_INSTRUCTIONS[task]}"},
        *few_shot_messages(task),
        {"role": "user", "content": f"Document to extract:\n{document_text}"},
    ]
    content = call_model(messages, result_model, model_provider)
    try:
        return result_model.model_validate(parse_model_json(content))
    except json.JSONDecodeError as error:
        raise MatterImportModelError("模型返回内容不是有效的 JSON") from error
    except ValidationError as error:
        first_issue = error.errors()[0]
        field_path = ".".join(str(part) for part in first_issue.get("loc", ()))
        message = first_issue.get("msg", "字段格式不符合要求")
        raise MatterImportModelError(f"模型返回的 JSON 不符合字段模板：{field_path}：{message}") from error


def extract_candidate(document_text: str, model_provider: str = "local") -> MatterImportCandidate:
    """Extract independently, then merge deterministic field-specific results.

    The browser makes one import request only.  These model calls happen on the
    backend so no document text or Ollama endpoint is exposed to the frontend.
    """
    # Cloud imports use the complete template once, including government profile,
    # procedure, legal bases, and evidence. Local Ollama retains the smaller
    # field-specific calls that are more reliable on limited hardware.
    if model_provider == "cloud":
        return extract_cloud_candidate_from_files([], document_text)

    core = extract_task(document_text, "core", ImportCoreCandidate, model_provider)
    materials = extract_task(document_text, "materials", ImportMaterialsCandidate, model_provider)
    location = extract_task(document_text, "location", ImportLocationCandidate, model_provider)
    phone = extract_task(document_text, "phone", ImportPhoneCandidate, model_provider)
    channels = extract_task(document_text, "channels", ImportChannelsCandidate, model_provider)
    delegation = extract_task(document_text, "delegation", ImportDelegationCandidate, model_provider)
    return MatterImportCandidate(
        matter=core.matter,
        scope=core.scope.model_copy(update={"channels": channels.channels}),
        source=core.source,
        location=ImportLocation(
            name=location.name,
            address=location.address,
            phone=phone.phone,
            opening_hours=location.opening_hours,
            official_entry_url=location.official_entry_url,
        ),
        materials=materials.materials,
        delegation=delegation,
        uncertainties=core.uncertainties,
    )


def extract_cloud_candidate_from_files(
    files: list[dict[str, str]], supplemental_text: str = "",
) -> MatterImportCandidate:
    """Have Qwen read uploaded PDFs/images directly in one structured request.

    `qwen3.8-max` accepts PDFs as ``type=file`` and images as ``type=image_url``
    using Base64 data URLs.  DOCX/TXT are not native attachment types for this
    endpoint; their decoded text is supplied in ``supplemental_text`` instead.
    One request avoids uploading the same binary document once per extraction
    subtask, which would multiply both latency and cloud-document charges.
    """
    if not settings.DASHSCOPE_API_KEY:
        raise MatterImportModelError("云端模型未配置：请先在 .env 设置 DASHSCOPE_API_KEY")

    content: list[dict[str, Any]] = []
    for item in files:
        path = Path(item["path"])
        suffix = path.suffix.lower()
        mime_type = item["mime_type"]
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"
        if suffix == ".pdf":
            content.append({
                "type": "file",
                "file": {"file_data": data_url, "filename": item["filename"], "file_format": "pdf"},
            })
        elif suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            content.append({"type": "image_url", "image_url": {"url": data_url}})

    instruction = """Read the attached official government-service documents and images directly.
Extract one complete matter-import candidate. Return facts only; do not invent any address, phone, material, URL, code, or condition.
Unknown scalar values must be null and unknown lists must be []. Put ambiguity, conflicts, and conditional requirements in uncertainties.
Preserve official portal fields that have no dedicated project field in government_profile, using their original Chinese labels.
Extract whether the matter permits an agent and materials required only for that agent into delegation. Use null when the document is silent; do not infer permission.
Extract the full 办理流程 into processing_steps and 设定依据 into legal_bases. For each fact whose page can be identified, add field_path, page_number, and a short original quote to field_evidence.
Return exactly one JSON object matching the supplied JSON Schema, with no Markdown or reasoning."""
    if supplemental_text.strip():
        instruction += f"\n\nSupplemental text from TXT/DOCX or administrator:\n{supplemental_text}"
    content.append({"type": "text", "text": instruction})
    raw = call_model(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        MatterImportCandidate,
        "cloud",
    )
    try:
        return MatterImportCandidate.model_validate(normalize_government_portal_payload(parse_model_json(raw)))
    except json.JSONDecodeError as error:
        raise MatterImportModelError("云端模型返回内容不是有效的 JSON") from error
    except ValidationError as error:
        first_issue = error.errors()[0]
        field_path = ".".join(str(part) for part in first_issue.get("loc", ()))
        raise MatterImportModelError(f"云端模型返回的 JSON 不符合字段模板：{field_path}：{first_issue.get('msg')}") from error
