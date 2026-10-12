"""Idempotent development seed for the Nangang social-security-card snapshot.

The values come from the user-provided, pending-verification source checklist.
They intentionally create a *draft* official snapshot; this code never
publishes it and never claims a data-sharing integration is connected.
"""

import json
import uuid

from sqlalchemy import text
from sqlmodel import Session


SOURCE_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb801")
LOCATION_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb802")
MATTER_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb803")
VERSION_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb804")
REQUIREMENT_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb805")

MINOR_SOURCE_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb807")
MINOR_LOCATION_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb808")
MINOR_MATTER_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb809")
MINOR_VERSION_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb80a")
MINOR_IDENTITY_REQUIREMENT_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb80b")
MINOR_GUARDIAN_REQUIREMENT_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb80c")
MINOR_RELATIONSHIP_REQUIREMENT_ID = uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb80d")

DETAIL_URL = (
    "https://www.zwfw.hlj.gov.cn/zhcx/bszn?syncItemId=848ba5e1-7f70-4e90-"
    "a35e-f1b4c21b8a3f&areaCode=230103000000"
)


def seed_social_card_snapshot(session: Session, administrator_id: uuid.UUID) -> None:
    """Create only missing configuration records; preserve user-maintained data."""
    session.execute(text("""
        INSERT INTO policy_sources(
          id, title, source_kind, url, publisher, content_text, verification_status
        ) VALUES (
          :id, :title, 'guide', :url, '黑龙江政务服务网', :content, 'pending'
        ) ON CONFLICT (id) DO NOTHING
    """), {
        "id": SOURCE_ID,
        "title": "南岗区社会保障卡申领办事指南（2026-10-12采集快照）",
        "url": DETAIL_URL,
        "content": """来源门户：https://www.zwfw.hlj.gov.cn
用户确认采集日期：2026-10-12；具体时刻未知。
材料：身份证；来源渠道：政府部门核发；材料类型：原件。
材料形式：数据共享（系统自动获取，如数据不全则需申请者提交）。
电子证照：已关联电子证照，可免提交。纸质材料：无需纸质材料。必要性：必要。
受理条件：本人持身份证到现场办理。
疑点：同时标注网上办理；办理流程受理结果出现密码修改与重置咨询。
本记录来自用户提供截图，尚未完成在线核验。""",
    })
    session.execute(text("""
        INSERT INTO service_locations(
          id, name, region_code, address, phone, opening_hours, official_entry_url,
          source_id, verification_status
        ) VALUES (
          :id, :name, '230103000000', :address, :phone, :hours, :url, :source_id, 'pending'
        ) ON CONFLICT (id) DO NOTHING
    """), {
        "id": LOCATION_ID,
        "name": "南岗区政务服务中心综合业务办理窗口",
        "address": "黑龙江省哈尔滨市南岗区中山路181号市民大厦1楼A区综合窗口",
        "phone": "0451-86224288",
        "hours": "周一至周五8:00—11:30、13:30—17:00，法定节假日除外",
        "url": DETAIL_URL,
        "source_id": SOURCE_ID,
    })
    session.execute(text("""
        INSERT INTO service_matters(
          id, code, official_code, name, region_code, region_name, description
        ) VALUES (
          :id, :code, :official_code, :name, '230103000000', '哈尔滨市南岗区', :description
        ) ON CONFLICT (code) DO NOTHING
    """), {
        "id": MATTER_ID,
        "code": "nangang_social_security_card_application",
        "official_code": "12230103MB1J64708Q4002014010001A0",
        "name": "社会保障卡申领",
        "description": "南岗区社会保障卡申领；依据2026-10-12采集截图；支持材料准备说明，线上渠道及子情形待核实。",
    })
    matter_id = session.execute(text("SELECT id FROM service_matters WHERE code = :code"), {
        "code": "nangang_social_security_card_application"
    }).scalar_one()

    session.execute(text("""
        INSERT INTO material_types(id, code, name, description)
        VALUES (:id, 'resident_identity_card', '身份证', :description)
        ON CONFLICT (code) DO NOTHING
    """), {
        "id": uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb806"),
        "description": "本事项必要身份核验材料；身份证信息可通过共享取得。",
    })
    material_type_id = session.execute(
        text("SELECT id FROM material_types WHERE code = 'resident_identity_card'")
    ).scalar_one()

    metadata = {
        "authority_name": "哈尔滨市南岗区社会保险经办服务中心",
        "authority_code": "12230103MB1J64708Q",
        "basic_code": "002014010001",
        "implementation_code": "12230103MB1J64708Q4002014010001",
        "administrative_level": "县级",
        "service_scope": "全市",
        "applicant_type": "自然人",
        "item_type": "公共服务",
        "processing_type": "即办件",
        "channels": ["窗口办理", "网上办理"],
        "online_depth": "在线核验（III级）",
        "mobile_supported": True,
        "self_service_terminal_supported": False,
        "appointment_supported": False,
        "fee_required": False,
        "promised_workdays": 1,
        "statutory_workdays": 15,
        "onsite_visits_displayed": 1,
        "complaint_phone": "0451-82637137",
        "acceptance_condition_raw": "本人持身份证到现场办理",
        "onsite_reminder": "指南受理条件要求本人持身份证到现场；无需纸质材料不等于无需携带证件",
        "source_portal_url": "https://www.zwfw.hlj.gov.cn",
        "source_collected_date": "2026-10-12",
        "source_capture_time_known": False,
        "configuration_kind": "official_snapshot",
        "source_status": "snapshot_pending",
        "sharing_integration": "not_connected",
        "review_scope": "材料准备与辅助核对",
        "uncertainties": [
            "网上办理与本人到场要求的关系",
            "流程中混入密码修改重置咨询",
            "首次申领及不同申请情形要求",
        ],
    }
    version = session.execute(text("""
        SELECT id FROM matter_versions WHERE matter_id = :matter_id AND version_no = 1
    """), {"matter_id": matter_id}).scalar_one_or_none()
    if version is None:
        session.execute(text("""
            INSERT INTO matter_versions(
              id, matter_id, version_no, status, change_summary, service_location_id,
              created_by, metadata_json
            ) VALUES (
              :id, :matter_id, 1, 'draft', :summary, :location_id, :created_by,
              CAST(:metadata AS jsonb)
            )
        """), {
            "id": VERSION_ID,
            "matter_id": matter_id,
            "summary": "根据2026-10-12用户提供截图及链接整理官方材料要求；冲突与缺项待核实。",
            "location_id": LOCATION_ID,
            "created_by": administrator_id,
            "metadata": json.dumps(metadata, ensure_ascii=False),
        })
        version = VERSION_ID

    requirement = session.execute(text("""
        SELECT id FROM material_requirements
        WHERE matter_version_id = :version_id AND requirement_code = 'identity_document'
    """), {"version_id": version}).scalar_one_or_none()
    if requirement is None:
        field_schema = {
            "schema_version": "1",
            "fields": [
                {"key": "name", "label": "姓名", "type": "string", "required_status": "project_extraction_target"},
                {"key": "id_number", "label": "公民身份号码", "type": "string", "required_status": "project_extraction_target"},
                {"key": "valid_from", "label": "有效期起始", "type": "date", "required_status": "project_extraction_target"},
                {"key": "valid_until", "label": "有效期截止", "type": "date", "required_status": "project_extraction_target"},
                {"key": "validity_long_term", "label": "长期有效", "type": "boolean", "required_status": "project_extraction_target"},
            ],
            "official_submission": {
                "primary": "department_fetch",
                "fallback": "applicant_submit_if_data_incomplete",
                "electronic_license_exemptible": True,
                "paper_required": False,
            },
            "project_upload_contract": {
                "official_photo_requirement_verified": False,
                "allow_both_sides_in_one_image": True,
            },
        }
        session.execute(text("""
            INSERT INTO material_requirements(
              id, matter_version_id, material_type_id, requirement_code, name,
              requirement_level, provider_role, submission_mode, original_required,
              copy_count, format_requirements, field_schema, sort_order
            ) VALUES (
              :id, :version_id, :material_type_id, 'identity_document', '身份证',
              'required', 'applicant', 'department_fetch', true, 0, :format_requirements,
              CAST(:field_schema AS jsonb), 10
            )
        """), {
            "id": REQUIREMENT_ID,
            "version_id": version,
            "material_type_id": material_type_id,
            "format_requirements": "官方：共享获取，数据不全补交，可免提交，无需纸质材料；项目共享尚未接通。",
            "field_schema": json.dumps(field_schema, ensure_ascii=False),
        })
        requirement = REQUIREMENT_ID

    methods = [
        ("bring_existing_identity_card", "self_prepare", "本人携带已有身份证", "根据受理条件，本人持身份证到场；证件换领等另查对应事项。"),
        ("official_data_sharing", "department_fetch", "官方电子证照共享获取说明", "指南支持共享，数据不全补交；本项目未接入。"),
    ]
    for code, method_type, title, steps in methods:
        session.execute(text("""
            INSERT INTO material_acquisition_methods(
              id, requirement_id, method_code, method_type, title, steps, source_id,
              verification_status
            ) VALUES (
              :id, :requirement_id, :code, :method_type, :title, :steps, :source_id, 'pending'
            ) ON CONFLICT (requirement_id, method_code) DO NOTHING
        """), {
            "id": uuid.uuid4(), "requirement_id": requirement, "code": code,
            "method_type": method_type, "title": title, "steps": steps, "source_id": SOURCE_ID,
        })

    session.commit()


def seed_minor_social_card_snapshot(session: Session, administrator_id: uuid.UUID) -> None:
    """Create an isolated, pending-verification draft for minor card applications.

    It reuses the supplied Nangang service-location details only as a data-entry
    starting point.  The child/guardian rules are deliberately marked pending and
    must not be published before an administrator verifies the official guide.
    """
    session.execute(text("""
        INSERT INTO policy_sources(
          id, title, source_kind, url, publisher, content_text, verification_status
        ) VALUES (
          :id, :title, 'guide', :url, '黑龙江政务服务网', :content, 'pending'
        ) ON CONFLICT (id) DO NOTHING
    """), {
        "id": MINOR_SOURCE_ID,
        "title": "南岗区未成年社会保障卡申领办事指南（待核验草稿）",
        "url": DETAIL_URL,
        "content": """本记录以“南岗区社会保障卡申领”采集快照为录入结构参考。
未成年人申领是否适用该官方链接、监护人到场要求、身份证明与监护关系证明的具体要求，均未完成官方核验。
仅用于系统演示和管理员录入、复核流程，不能作为政务办理依据。""",
    })
    session.execute(text("""
        INSERT INTO service_locations(
          id, name, region_code, address, phone, opening_hours, official_entry_url,
          source_id, verification_status
        ) VALUES (
          :id, :name, '230103000000', :address, :phone, :hours, :url, :source_id, 'pending'
        ) ON CONFLICT (id) DO NOTHING
    """), {
        "id": MINOR_LOCATION_ID,
        "name": "南岗区政务服务中心综合业务办理窗口（未成年人事项待核验）",
        "address": "黑龙江省哈尔滨市南岗区中山路181号市民大厦1楼A区综合窗口",
        "phone": "0451-86224288",
        "hours": "周一至周五8:00—11:30、13:30—17:00，法定节假日除外",
        "url": DETAIL_URL,
        "source_id": MINOR_SOURCE_ID,
    })
    session.execute(text("""
        INSERT INTO service_matters(
          id, code, official_code, name, region_code, region_name, description
        ) VALUES (
          :id, :code, NULL, :name, '230103000000', '哈尔滨市南岗区', :description
        ) ON CONFLICT (code) DO NOTHING
    """), {
        "id": MINOR_MATTER_ID,
        "code": "nangang_minor_social_security_card_application",
        "name": "未成年社会保障卡申领",
        "description": "南岗区未成年社会保障卡申领录入草稿；办理条件、监护关系材料和线上渠道均待官方核验。",
    })
    matter_id = session.execute(text("SELECT id FROM service_matters WHERE code = :code"), {
        "code": "nangang_minor_social_security_card_application"
    }).scalar_one()

    for type_id, code, name, description in [
        (uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb80e"), "guardian_identity_card", "监护人身份证", "未成年事项的监护人身份证明；具体要求待官方核验。"),
        (uuid.UUID("81734622-6a7e-4d12-8e81-8ec23fedb80f"), "guardian_relationship_proof", "监护关系证明", "可用于证明监护关系的材料类别；具体证件范围待官方核验。"),
    ]:
        session.execute(text("""
            INSERT INTO material_types(id, code, name, description)
            VALUES (:id, :code, :name, :description) ON CONFLICT (code) DO NOTHING
        """), {"id": type_id, "code": code, "name": name, "description": description})
    material_types = {
        row["code"]: row["id"] for row in session.execute(text("""
            SELECT code, id FROM material_types
            WHERE code IN ('resident_identity_card', 'guardian_identity_card', 'guardian_relationship_proof')
        """)).mappings()
    }

    metadata = {
        "authority_name": "哈尔滨市南岗区社会保险经办服务中心（待核验）",
        "administrative_level": "县级",
        "service_scope": "南岗区",
        "applicant_type": "未成年人及其监护人",
        "item_type": "公共服务",
        "channels": ["窗口办理（待核验）", "网上办理（待核验）"],
        "acceptance_condition_raw": "未成年人社会保障卡申领的申请人、监护人到场及证件要求待官方核验。",
        "source_portal_url": DETAIL_URL,
        "source_collected_date": "2026-10-12",
        "configuration_kind": "pending_demo_snapshot",
        "source_status": "snapshot_pending",
        "review_scope": "未成年人社保卡申领材料与渠道的录入、复核",
        "uncertainties": [
            "官方指南是否单列未成年人申领事项",
            "申请人本人和监护人是否均需到场",
            "监护关系证明的有效证件范围",
            "是否支持线上申办或电子证照共享",
        ],
    }
    version = session.execute(text("""
        SELECT id FROM matter_versions WHERE matter_id = :matter_id AND version_no = 1
    """), {"matter_id": matter_id}).scalar_one_or_none()
    if version is None:
        session.execute(text("""
            INSERT INTO matter_versions(
              id, matter_id, version_no, status, change_summary, service_location_id,
              created_by, metadata_json
            ) VALUES (
              :id, :matter_id, 1, 'draft', :summary, :location_id, :created_by,
              CAST(:metadata AS jsonb)
            )
        """), {
            "id": MINOR_VERSION_ID, "matter_id": matter_id,
            "summary": "参照南岗区社会保障卡申领快照录入未成年人事项草稿；全部关键信息待官方核验。",
            "location_id": MINOR_LOCATION_ID, "created_by": administrator_id,
            "metadata": json.dumps(metadata, ensure_ascii=False),
        })
        version = MINOR_VERSION_ID

    requirements = [
        (MINOR_IDENTITY_REQUIREMENT_ID, "minor_identity_document", "resident_identity_card", "未成年人身份证明", "申请人身份信息或相关身份证明；具体可接受证件待官方核验。", 10),
        (MINOR_GUARDIAN_REQUIREMENT_ID, "guardian_identity_document", "guardian_identity_card", "监护人身份证", "监护人身份证明；是否必须提供原件及复印件待官方核验。", 20),
        (MINOR_RELATIONSHIP_REQUIREMENT_ID, "guardian_relationship", "guardian_relationship_proof", "监护关系证明", "出生医学证明、户口簿或其他证明的适用范围待官方核验。", 30),
    ]
    for requirement_id, code, type_code, name, format_requirements, sort_order in requirements:
        session.execute(text("""
            INSERT INTO material_requirements(
              id, matter_version_id, material_type_id, requirement_code, name,
              requirement_level, provider_role, submission_mode, format_requirements, sort_order
            ) VALUES (
              :id, :version_id, :material_type_id, :code, :name,
              'required', 'applicant', 'user_upload', :format_requirements, :sort_order
            ) ON CONFLICT (matter_version_id, requirement_code) DO NOTHING
        """), {
            "id": requirement_id, "version_id": version, "material_type_id": material_types[type_code],
            "code": code, "name": name, "format_requirements": format_requirements, "sort_order": sort_order,
        })

    requirement_ids = {
        row["requirement_code"]: row["id"] for row in session.execute(text("""
            SELECT id, requirement_code FROM material_requirements WHERE matter_version_id = :version_id
        """), {"version_id": version}).mappings()
    }
    methods = [
        ("minor_identity_prepare", "minor_identity_document", "self_prepare", "准备未成年人身份证明", "根据官方要求准备申请人身份证明；可接受证件范围待核验。"),
        ("guardian_identity_prepare", "guardian_identity_document", "self_prepare", "准备监护人身份证", "根据官方要求准备监护人身份证明；原件、复印件要求待核验。"),
        ("relationship_proof_prepare", "guardian_relationship", "self_prepare", "准备监护关系证明", "准备可证明监护关系的材料；具体材料类型待官方核验。"),
        ("minor_window_service", "minor_identity_document", "in_person", "前往南岗区政务服务中心窗口咨询办理", "当前仅作为线下咨询与办理地点录入，是否需要预约或本人到场待核验。"),
    ]
    for code, requirement_code, method_type, title, steps in methods:
        session.execute(text("""
            INSERT INTO material_acquisition_methods(
              id, requirement_id, method_code, method_type, title, steps, source_id,
              verification_status
            ) VALUES (
              :id, :requirement_id, :code, :method_type, :title, :steps, :source_id, 'pending'
            ) ON CONFLICT (requirement_id, method_code) DO NOTHING
        """), {
            "id": uuid.uuid4(), "requirement_id": requirement_ids[requirement_code], "code": code,
            "method_type": method_type, "title": title, "steps": steps, "source_id": MINOR_SOURCE_ID,
        })
    session.commit()
