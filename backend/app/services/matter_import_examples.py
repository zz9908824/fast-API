"""Curated few-shot examples for the matter-import extraction tasks.

These examples are deliberately short and hand-authored.  They are not model
responses and must be changed only after an administrator checks the source
text and desired JSON result.
"""

from __future__ import annotations

import json
from typing import Any


EXAMPLE_SOURCE = """事项名称：社会保障卡申领。
受理条件：本人持身份证到现场办理。
办理地点：哈尔滨市南岗区中山路181号市民大厦1楼A区综合窗口。
咨询电话：0451-12345。工作时间：工作日 8:30-16:30。
办理渠道：现场办理；网上办理入口待核实。
材料：居民身份证，必要，原件；电子证照可共享获取，数据不全时补交。"""


FEW_SHOT_OUTPUTS: dict[str, dict[str, Any]] = {
    "core": {
        "matter": {"name": "社会保障卡申领", "official_code": None, "description": None},
        "scope": {"acceptance_condition_raw": "本人持身份证到现场办理。", "channels": []},
        "source": {"title": None, "publisher": None, "published_date": None},
        "uncertainties": [
            {"field_path": "scope.channels", "kind": "manual_needed", "message": "网上办理入口待核实", "blocking": False}
        ],
    },
    "materials": {
        "materials": [
            {
                "local_key": "resident_identity_card",
                "name": "居民身份证",
                "type_name_candidate": None,
                "requirement_level": "required",
                "provider_role": "applicant",
                "submission_mode": "department_fetch",
                "original_required": True,
                "copy_count": None,
                "min_pages": None,
                "format_requirements": "原件；电子证照可共享获取，数据不全时补交。",
                "acquisition_methods": [
                    {
                        "local_key": "official_data_sharing",
                        "title": "电子证照共享获取",
                        "method_type": "department_fetch",
                        "steps": "系统共享获取；数据不全时补交。",
                        "entry_url": None,
                    }
                ],
            }
        ]
    },
    "location": {
        "name": "市民大厦1楼A区综合窗口",
        "address": "哈尔滨市南岗区中山路181号市民大厦1楼A区综合窗口",
        "opening_hours": "工作日 8:30-16:30",
        "official_entry_url": None,
    },
    "phone": {"phone": "0451-12345"},
    "channels": {"channels": ["现场办理"]},
    "delegation": {
        "delegation_allowed": None,
        "materials": [],
    },
}


def few_shot_messages(task: str) -> list[dict[str, str]]:
    """Return a source/result pair formatted as an Ollama chat example."""
    return [
        {"role": "user", "content": f"Example document:\n{EXAMPLE_SOURCE}"},
        {
            "role": "assistant",
            "content": json.dumps(FEW_SHOT_OUTPUTS[task], ensure_ascii=False),
        },
    ]
