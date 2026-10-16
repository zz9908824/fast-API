"""Map a government-portal JSON result into the project's import candidate.

The mapper accepts the Chinese-key JSON commonly returned by government-document
prompts.  It keeps every unmapped official field in ``government_profile`` so a
correct model answer is never silently discarded merely because the application
does not yet have a dedicated relational column for it.
"""

from typing import Any


PROFILE_KEYS = (
    "实施主体", "实施主体性质", "服务对象", "事项类型", "公共服务分类", "事项分类",
    "行使层级", "办件类型", "办理形式", "是否支持预约", "是否收费", "监督投诉方式",
    "是否网办", "自然人主题分类", "法人主题分类", "通办范围", "权力来源", "联办机构",
    "法定办结时限", "法定办结时限说明", "承诺办结时限", "承诺办结时限说明",
    "到现场次数", "是否支持网上支付", "是否可移动端办理", "网上办理深度", "禁止性受理条件",
    "数量限制", "实施主体编码", "实施编码", "业务办理项编码", "基本编码",
)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _channels(value: Any, online: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, str):
        for item in value.replace("，", "、").replace("/", "、").split("、"):
            if item.strip() and item.strip() not in result:
                result.append(item.strip())
    if _text(online) == "是" and not any("网上" in item or "在线" in item for item in result):
        result.append("网上办理")
    return result


def _yes_no(value: Any) -> bool | None:
    text = _text(value)
    if text in {"是", "允许", "可以", "可", "支持"}:
        return True
    if text in {"否", "不允许", "不可", "不支持"}:
        return False
    return None


def normalize_government_portal_payload(value: object) -> object:
    """Return internal candidate JSON, or leave an already-internal payload alone."""
    if not isinstance(value, dict) or "事项名称" not in value:
        return value

    profile = {key: text for key in PROFILE_KEYS if (text := _text(value.get(key))) is not None}
    materials: list[dict[str, Any]] = []
    for index, raw in enumerate(value.get("申请材料") or [], start=1):
        if not isinstance(raw, dict):
            continue
        name = _text(raw.get("材料名称"))
        if not name:
            continue
        source = _text(raw.get("来源渠道")) or ""
        form = _text(raw.get("材料形式")) or ""
        count = _text(raw.get("纸质材料份数")) or ""
        level = "required" if _text(raw.get("材料必要性")) in {"必要", "必需", "是"} else "optional"
        mode = "department_fetch" if "共享" in source or "免提交" in (_text(raw.get("材料类型")) or "") else "user_upload"
        materials.append({
            "local_key": f"material_{index}", "name": name, "type_name_candidate": None,
            "requirement_level": level, "provider_role": "applicant", "submission_mode": mode,
            "original_required": "原件" in form, "copy_count": None, "min_pages": None,
            "format_requirements": "；".join(part for part in (source, form, count) if part) or None,
            "acquisition_methods": [],
        })

    steps: list[dict[str, Any]] = []
    uncertainties: list[dict[str, Any]] = []
    delegation_materials: list[dict[str, Any]] = []
    raw_delegation_materials = value.get("代办需要准备的材料") or []
    if isinstance(raw_delegation_materials, str):
        raw_delegation_materials = [raw_delegation_materials]
    for index, raw in enumerate(raw_delegation_materials, start=1):
        if isinstance(raw, dict):
            delegation_name = _text(raw.get("材料名称")) or _text(raw.get("名称"))
            level = "optional" if _text(raw.get("材料必要性")) in {"可选", "非必要"} else "required"
        else:
            delegation_name, level = _text(raw), "required"
        if delegation_name:
            delegation_materials.append({
                "local_key": f"delegation_material_{index}", "name": delegation_name,
                "requirement_level": level, "submission_mode": "on_site",
            })
    matter_name = _text(value.get("事项名称"))
    for index, raw in enumerate(value.get("办理流程") or [], start=1):
        if not isinstance(raw, dict):
            continue
        step = {
            "step": _text(raw.get("步骤")), "time_limit": _text(raw.get("办理时限")),
            "result": _text(raw.get("办理结果")), "review_standard": _text(raw.get("审查标准")),
        }
        steps.append(step)
        # A common portal scrape issue: password-reset content is mixed into a
        # card-application page. Preserve it, but force an administrator check.
        if matter_name and "申领" in matter_name and "密码" in (step["result"] or ""):
            uncertainties.append({"field_path": f"processing_steps[{index - 1}]", "kind": "conflict",
                                  "message": "办理流程包含密码修改/重置内容，可能与当前申领事项混入，需人工核验。",
                                  "blocking": True})

    return {
        "matter": {"name": matter_name, "official_code": _text(value.get("基本编码")) or _text(value.get("实施编码")), "description": None},
        "scope": {"acceptance_condition_raw": _text(value.get("受理条件")), "channels": _channels(value.get("办理形式"), value.get("是否网办"))},
        "source": {"title": None, "publisher": _text(value.get("实施主体")), "published_date": None},
        "location": {"name": _text(value.get("办理地点")), "address": None, "phone": _text(value.get("咨询方式")), "opening_hours": _text(value.get("办理时间")), "official_entry_url": None},
        "materials": materials, "uncertainties": uncertainties, "government_profile": profile,
        "delegation": {
            "delegation_allowed": _yes_no(value.get("是否允许代办")),
            "materials": delegation_materials,
        },
        "processing_steps": steps,
        "legal_bases": [item.strip() for item in value.get("设定依据") or [] if isinstance(item, str) and item.strip()],
        "field_evidence": [],
    }
