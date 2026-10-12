# 南岗区社会保障卡申领：数据库入库数据与缺项检查

## 1. 结论与依据

现有资料足够建立事项查询、身份证材料说明和有限范围的模拟预审配置，可开始开发；不足以自动判断全部正式申领资格或证件真实性。

- 来源网站：黑龙江政务服务网。
- 来源门户：https://www.zwfw.hlj.gov.cn
- 采集日期：2026-10-12，由用户确认；准确采集时刻未知。
- 事项资料：用户提供的三张南岗区“社会保障卡申领”页面截图。
- 用户此前提供的事项详情链接：https://www.zwfw.hlj.gov.cn/zhcx/bszn?syncItemId=848ba5e1-7f70-4e90-a35e-f1b4c21b8a3f&areaCode=230103000000
- 上述详情链接单独保留为追溯地址，不用首页替代；本次网页工具无法读取其内容，不能声称已重新在线核验。
- 截图文件：image(20261012-021124).png、image(20261012-021131).png、image(20261012-021151).png。
- 不把2026-10-12当作政策生效日或官方更新日期。

数据库依据仓库 https://github.com/zz9908824/fast-API ，核查提交 `19215fa7397574cd1ca6b4277d03f254930d36c8`（2026-10-12 fetch后默认分支仍为此提交）。本文只整理待入库数据，未修改仓库、未写入用户数据库。

## 2. 官方事实与项目设计必须分开

| 类型 | 内容 |
|---|---|
| 截图事实 | 正式名称社会保障卡申领，地区南岗区，身份证必要、原件、政府部门核发 |
| 截图事实 | 数据共享自动获取；数据不全时申请者提交；关联电子证照，可免提交；无需纸质材料 |
| 截图事实 | 受理条件“本人持身份证到现场办理”，同时显示窗口和网上办理 |
| 项目设计 | 限定成年人本人申领作为开发情形、模拟照片上传、图片格式和大小限制、OCR字段一致性提示 |
| 尚未证实 | 首次申领子项全部条件、未成年人及代办要求、线上是否全程完成、照片正反面规范、正式制卡和领取时限 |

正式名称不能擅自改成“成年人首次申领”；可以在项目界面附加“试点范围：成年人本人办理，模拟预审”。

## 3. 已有表的写入计划

| 实际表名 | 建议操作 | 初始数据量 |
|---|---|---:|
| `policy_sources` | 新增指南来源，保存详情URL和截图摘录 | 1 |
| `service_locations` | 新增或复用南岗区窗口 | 1 |
| `service_matters` | 按内部code创建或复用事项 | 1 |
| `matter_versions` | 建立官方快照draft版本 | 1 |
| `material_types` | 按code复用身份证种类 | 1 |
| `material_requirements` | 本版本身份证要求 | 1 |
| `material_acquisition_methods` | 已有证件自备／共享取得说明 | 可选1–2，pending |
| `verification_rules` | 官方配置先不放无依据的自动规则；模拟版单独配置检查 | 官方0，模拟若干 |

需要完整闭环演示时，另建明确标注的模拟版本；不要把official版本的共享要求改成无条件user_upload。当前API缺少演示标记过滤，公开发布模拟版本之前应增加前端标识／环境限制。

## 4. policy_sources：来源记录

| 属性 | 建议值 | 状态 |
|---|---|---|
| `id` | 新UUID | 由导入程序生成 |
| `title` | 南岗区社会保障卡申领办事指南（2026-10-12采集快照） | 可入库 |
| `source_kind` | `guide` | 现有枚举 |
| `url` | 前述事项详情链接 | 用户提供，在线读取未成功 |
| `publisher` | 黑龙江政务服务网 | 来源网站，不冒充实施主体 |
| `published_date` | null | 官方发布日期未知 |
| `retrieved_at` | 实际导入时刻，或采用日期代理时刻并标注 | 准确采集时刻未知，不捏造真实时刻 |
| `content_text` | 来源门户、采集日期、材料原文、受理条件原文及以下冲突说明 | 可入库 |
| `content_sha256` | 实际归档来源文件的SHA256 | 由程序计算，文件未归档则null |
| `verification_status` | `pending` | 已读截图，不等于已在线核验 |
| `verified_by` / `verified_at` | null | 后续真实管理员核验后填写 |

建议content_text包含：

```text
来源门户：https://www.zwfw.hlj.gov.cn
用户确认采集日期：2026-10-12；具体时刻未知。
材料：身份证；来源渠道：政府部门核发；材料类型：原件。
材料形式：数据共享（系统自动获取，如数据不全则需申请者提交）。
电子证照：已关联电子证照，可免提交。纸质材料：无需纸质材料。必要性：必要。
受理条件：本人持身份证到现场办理。
疑点：同时标注网上办理；办理流程受理结果出现密码修改与重置咨询。
```

如用户最终只希望把首页作为来源URL，可以 `url=https://www.zwfw.hlj.gov.cn`，但content_text必须保留事项详情链接和“url为门户地址”说明。推荐用详情链接作为url、门户作为附加信息，以提高追溯准确性。

当前来源表无 `portal_url`、`collected_date`及附件数组字段；第一版可写content_text。后续新增source_metadata JSONB更利于结构化保存，但不是入库前置条件。

## 5. service_matters：事项身份

| 属性 | 建议值 |
|---|---|
| `id` | 新UUID，已存在则复用 |
| `code` | `nangang_social_security_card_application`（内部键） |
| `official_code` | `12230103MB1J64708Q4002014010001A0`（截图业务办理项编码） |
| `name` | 社会保障卡申领 |
| `region_code` | `230103000000`，采用本次详情链接areaCode；同库地区码需统一 |
| `region_name` | 哈尔滨市南岗区 |
| `description` | 南岗区社会保障卡申领；依据2026-10-12采集截图；支持材料准备说明，线上渠道及子情形待核实 |
| `is_active` | true；是否公开可查由版本status决定 |

其他编码不塞进official_code，以版本元信息保存：

| 编码 | 截图值 |
|---|---|
| 实施主体编码 | `12230103MB1J64708Q` |
| 基本编码 | `002014010001` |
| 实施编码 | `12230103MB1J64708Q4002014010001` |
| 业务办理项编码 | `12230103MB1J64708Q4002014010001A0` |

编码统一保存字符串，不转换数字。区划归属南岗区与通办范围“全市”分别存，不把事项地区改成全市。

## 6. service_locations：办理地点与联系方式

| 属性 | 建议值 |
|---|---|
| `id` | 新UUID或复用准确匹配的记录 |
| `name` | 南岗区政务服务中心综合业务办理窗口 |
| `region_code` | `230103000000` |
| `address` | 黑龙江省哈尔滨市南岗区中山路181号市民大厦1楼A区综合窗口 |
| `phone` | `0451-86224288` |
| `opening_hours` | 周一至周五8:00—11:30、13:30—17:00，法定节假日除外 |
| `official_entry_url` | 事项详情链接，标注为指南而非实际提交入口 |
| `source_id` | 前述来源UUID |
| `verification_status` | `pending` |
| `checked_at` | null，尚未在线确认办公信息 |

投诉电话 `0451-82637137`保存到版本元信息；不能覆盖业务咨询phone。

## 7. matter_versions：官方快照版本

| 属性 | 建议值 |
|---|---|
| `matter_id` | 事项UUID |
| `version_no` | 第一版为1；存在历史时取下一版本，不覆盖已发布版本 |
| `status` | `draft` |
| `config_revision` | 1 |
| `valid_from` / `valid_to` | null，未确认有效期 |
| `service_location_id` | 地点UUID |
| `created_by` | 实际管理用户UUID，不能虚构 |
| `approved_by` / `published_at` | 初始null |
| `source_checked_at` | 初始null；仅记录实际完成核查的时间 |
| `change_summary` | 根据2026-10-12用户提供截图及链接整理官方材料要求；冲突与缺项待核实 |

现有表缺少部门、时限、共享策略、试点标记等字段。推荐新增 `metadata_json`；若前次文档的扩展已落地则直接复用，未落地不要对不存在的列INSERT。

新增Alembic迁移，down_revision接真实当前head；仓库核查head为 `20261010_precheck_api`：

```sql
ALTER TABLE matter_versions ADD COLUMN metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
  CHECK (jsonb_typeof(metadata_json) = 'object');
```

建议版本元信息：

```json
{
  "authority_name":"哈尔滨市南岗区社会保险经办服务中心",
  "authority_code":"12230103MB1J64708Q",
  "basic_code":"002014010001",
  "implementation_code":"12230103MB1J64708Q4002014010001",
  "administrative_level":"县级",
  "service_scope":"全市",
  "applicant_type":"自然人",
  "item_type":"公共服务",
  "processing_type":"即办件",
  "channels":["窗口办理","网上办理"],
  "online_depth":"在线核验（III级）",
  "mobile_supported":true,
  "self_service_terminal_supported":false,
  "appointment_supported":false,
  "fee_required":false,
  "promised_workdays":1,
  "statutory_workdays":15,
  "onsite_visits_displayed":1,
  "complaint_phone":"0451-82637137",
  "acceptance_condition_raw":"本人持身份证到现场办理",
  "onsite_reminder":"指南受理条件要求本人持身份证到现场；无需纸质材料不等于无需携带证件",
  "source_portal_url":"https://www.zwfw.hlj.gov.cn",
  "source_collected_date":"2026-10-12",
  "source_capture_time_known":false,
  "configuration_kind":"official_snapshot",
  "source_status":"snapshot_pending",
  "sharing_integration":"not_connected",
  "review_scope":"材料准备与辅助核对",
  "uncertainties":["网上办理与本人到场要求的关系","流程中混入密码修改重置咨询","首次申领及不同申请情形要求"]
}
```

指南时限说明又写“即时办结”，与表格1/15工作日同时保留并标需要核实。不把上述时限解释成所有渠道的制卡、邮寄、领取或金融激活时限。

事项GET接口显式增加metadata_json；前端显示来源状态。不要只加数据库列而不修改API返回与页面。

## 8. material_types：身份证种类

| 属性 | 值 |
|---|---|
| `code` | `resident_identity_card`，如果已有identity_card等同义code应复用已有种类 |
| `name` | 身份证 |
| `description` | 本事项必要身份核验材料；身份证信息可通过共享取得 |
| `is_active` | true |

材料种类只有1项，不按“正面”“反面”新增两个官方材料种类。照片正反面是项目材料内容／文件结构。

## 9. material_requirements：官方要求与提取schema

| 属性 | 官方快照建议值 | 说明 |
|---|---|---|
| `matter_version_id` / `material_type_id` | 实际UUID | 关联准确 |
| `requirement_code` | `identity_document` | 同一事项版本唯一 |
| `name` | 身份证 | 官方清单仅此1项 |
| `applicability_expr` | `{"op":"always"}` | 无已核实材料分支 |
| `requirement_level` | `required` | 必要核验材料，不等于必须上传 |
| `provider_role` | `applicant` | 本人办理试点；不由此推断代办规则 |
| `submission_mode` | `department_fetch` | 代表指南首选共享方式，不意味着项目已接通 |
| `original_required` | true | 截图材料类型原件；不强制上传“原件PDF” |
| `copy_count` | 0 | 无需纸质材料；不代表不需本人携带身份证 |
| `min_pages` | null | 没有官方最低页数要求 |
| `format_requirements` | 官方：共享获取，数据不全补交，可免提交，无需纸质材料；项目共享尚未接通 | 原文与项目状态分别标明 |
| `template_source_id` | null | 无官方表格下载，不缺空白表 |
| `alternative_group_code` | null | 不把共享与补交配置成两个必须的材料 |
| `sort_order` | 10 | 界面顺序 |

field_schema是项目提取设计，不是官方必填列表：

```json
{
  "schema_version":"1",
  "fields":[
    {"key":"name","label":"姓名","type":"string","required_status":"project_extraction_target"},
    {"key":"id_number","label":"公民身份号码","type":"string","required_status":"project_extraction_target"},
    {"key":"valid_from","label":"有效期起始","type":"date","required_status":"project_extraction_target"},
    {"key":"valid_until","label":"有效期截止","type":"date","required_status":"project_extraction_target"},
    {"key":"validity_long_term","label":"长期有效","type":"boolean","required_status":"project_extraction_target"}
  ],
  "official_submission":{
    "primary":"department_fetch",
    "fallback":"applicant_submit_if_data_incomplete",
    "electronic_license_exemptible":true,
    "paper_required":false
  },
  "project_upload_contract":{
    "official_photo_requirement_verified":false,
    "allow_both_sides_in_one_image":true
  }
}
```

field_schema只被当前数据库保存，现有代码还没有官方fallback解释器；必须实现解析逻辑，不能认为写了JSON就能自动按条件切换渠道。

### 如何处理共享和模拟照片上传

现有submission_mode只能取一个枚举值，applicability_expr也没有现成共享状态引擎。第一阶段推荐：

1. official版本保持department_fetch和原文要求，展示未接通状态。
2. 开发测试单独建version_no=2，metadata_json.configuration_kind=synthetic_pilot，change_summary明确“模拟照片上传，不改变官方免提交要求”。
3. 模拟版本的同一材料要求设置user_upload；其min_pages仍null，不把2张照片冒充官方页数要求。公开显示必须有模拟标识。
4. 官方snapshot来源记录复用，模拟上传检查在parameters注明project_check；事项版本不能标成新的官方政策版本。
5. 真实业务支持fallback时，新增服务端维护的材料获取状态，如not_connected/pending/complete/incomplete/failed；complete必须有实际来源与核验记录，不能由用户在问卷里自报为“共享通过”。

如不愿建立两个版本，可先只建一个draft模拟配置，但必须明确configuration_kind=synthetic_pilot并保留official_submission原文；不能无标识发布。两种方案只选一种，不重复建立办件材料。

## 10. material_acquisition_methods：材料准备说明

可记录两项pending方法，不捏造下载模板：

| 字段 | 自备证件提醒 | 共享说明 |
|---|---|---|
| `method_code` | `bring_existing_identity_card` | `official_data_sharing` |
| `method_type` | `self_prepare` | `department_fetch` |
| `title` | 本人携带已有身份证 | 官方电子证照共享获取说明 |
| `steps` | 根据受理条件，本人持身份证到场；证件换领等另查对应事项 | 指南支持共享，数据不全补交；本项目未接入 |
| `entry_url` | null | null；指南链接放source，不充当核验接口 |
| `source_id` | 指南UUID | 指南UUID |
| `verification_status` | pending | pending |
| `applicability_expr` | always | always |

现有获取方式API只返回verified数据。待核查完成后填写来源verified_by/verified_at，方法改verified；不要为页面显示绕过核验状态。

## 11. verification_rules：第一版配置清单

官方版本未接共享时，不能设“无上传文件→缺身份证”的blocking规则。以下规则属于模拟版本或明确标注的项目技术检查；operator_code需要实现对应Python函数，当前仓库无执行引擎。

| rule_code | rule_type | operator_code | on_missing | 建议结果 |
|---|---|---|---|---|
| `ID-MATERIAL-001` | completeness | `material_present` | missing_material | 仅模拟user_upload版：无文件fail；已上传但无法确认类型unknown |
| `ID-QUALITY-001` | format | `image_readable` | unknown | 文件损坏error/重传；模糊unknown/重拍；阈值为项目参数 |
| `ID-SIDES-001` | completeness | `identity_sides_present` | unknown | 项目内容核对，按两面信息而非文件数量；不确认时unknown |
| `ID-NAME-001` | consistency | `field_equals` | unknown | OCR姓名与申请姓名比对；可靠不一致fail |
| `ID-NUMBER-001` | consistency | `field_equals` | unknown | 号码与申请信息比对；报告默认脱敏 |
| `ID-VALIDITY-001` | format | `date_interval_hint` | unknown | 有效期提示，支持长期；不是自动拒绝正式申领 |

文件类型、大小限制优先在上传接口校验并给出错误提示，不强行把所有技术异常变成官方材料不合格。第一版无身份证号码国家格式依据核查时不增加“格式正确=证件真实”的结论。

每条规则填写id、matter_version_id、name、applicability_expr、input_spec、parameters、severity、message_template、remedy_template、sort_order。现有表没有source_kind或enabled，第一版通过parameters.basis_kind=project_check区分；待核实规则不插入可执行集合。

示例：

```json
{
  "rule_code":"ID-NAME-001",
  "name":"申请信息与身份证姓名一致性提示",
  "rule_type":"consistency",
  "operator_code":"field_equals",
  "applicability_expr":{"op":"always"},
  "input_spec":{
    "left":{"source":"application_form","field":"name"},
    "right":{"source":"material","requirement_code":"identity_document","field":"name"}
  },
  "parameters":{"basis_kind":"project_check","normalize":["trim"],"scope":"synthetic_pilot"},
  "on_missing":"unknown",
  "severity":"warning",
  "message_template":"申请姓名与材料识别姓名不一致，请核对原图。",
  "remedy_template":"识别错误可申请人工核对；材料错误应补传新版本。",
  "primary_source_id":null,
  "source_excerpt":"项目设计的一致性提示，不是官方受理资格裁决"
}
```

当前规则结果枚举pass/fail/unknown/not_applicable/error，不能直接写needs_correction；办件状态另映射到needs_action/review_pending/prepared。

## 12. 申请表与运行时数据

申请表第一版输入姓名、身份证号（仅在确有一致性测试需要时）、办理方式范围确认；数据为synthetic，不预填真实用户信息。

推荐使用applications.form_data；仓库当前没有此列。如未做过迁移：

```sql
ALTER TABLE applications ADD COLUMN form_data jsonb NOT NULL DEFAULT '{}'::jsonb
  CHECK (jsonb_typeof(form_data) = 'object');
```

字段更新同步API schema和路由，校验expected_revision并使用行锁或条件UPDATE增加content_revision。不要把表单写进只有问卷意义的scenario_answers而不约定格式。

身份证上传后由现有application_documents、document_versions、document_version_files保存；OCR由extraction_runs、extracted_fields保存；字段校正写field_corrections；预审写check_runs/results/issues/evidence；复核写review_tasks/records/messages。不提前填造运行结果。

报告及交接清单默认隐藏完整号码，不在日志、公共事项页面或通知内容中显示；工作人员权限和文件读取仍按办件授权校验。

## 13. 缺项检查：哪些影响开发、哪些影响真实使用

| 数据／能力 | 当前状态 | 是否阻止第一版开发 | 补齐方法 |
|---|---|---|---|
| 来源网站、采集日期 | 已有 | 否 | 本次可入库 |
| 事项详情链接 | 用户已提供，读取失败 | 否 | 人工打开确认对应标题、区县和材料 |
| 官方更新时间／生效日期 | 未知 | 否 | 不猜测，设null |
| 实施主体、代码、地点、材料清单 | 截图已有 | 否 | 入库并保留快照核查状态 |
| 身份证展开详情 | 未提供 | 否，但限制官方规则 | 展开材料行查看提交说明及核验方式 |
| 本人到场与网上办理关系 | 冲突待核实 | 否，但不能宣传全程线上 | 官方咨询电话／完整渠道指南核实 |
| 密码重置咨询混入申领流程 | 待核实 | 否，不自动生成这段流程 | 核对原页面或联系部门 |
| 成年人首次申领专门条件 | 未完整明确 | 否，仅限模拟范围 | 核实具体服务子项，不自行新增官方条件 |
| 未成年人、代办、港澳台等要求 | 缺失 | 不影响限定本人试点 | 扩展前逐情形核实 |
| 照片正反面、尺寸／制卡照片规范 | 缺失 | 否，测试约定标项目要求 | 查实际线上申领入口指南；不能跨地区套用 |
| 官方共享接口与凭据 | 未接通 | 否，明确模拟 | 获授权后实现，不由OCR替代 |
| 政务受理、制卡、邮寄和领取阶段 | 未明确 | 否，不承诺正式办结 | 逐阶段核实 |
| 实际办理量 | 未核实 | 否 | 不在展示中写高频排名或虚构数量 |
| 测试图片及字段标准答案 | 尚需制作 | 是，影响OCR验证 | 准备清晰／缺面／冲突／模糊／长期有效／补传样本 |
| 实际管理员UUID | 文档未提供 | 是，影响插入版本 | 从本机user表选真实管理员 |
| 新增metadata_json/form_data是否已迁移 | 运行库未知 | 是，影响相关列写入 | alembic current并检查列 |
| 上传、OCR、预审、复核接口 | 核查仓库尚未实现 | 是，影响闭环运行 | 按阶段开发，不把表存在当成功能已实现 |

没有空白表和样例不是本事项的数据缺陷：身份证属于已有证件，不应虚构一个官方身份证填写模板。

## 14. 入库顺序与验收

1. 确認Alembic已到实际head，选择管理用户；核对地区码约定。
2. 按上述数据插入来源、地点、事项和draft版本，关联身份证种类与材料要求。
3. 如果需要metadata_json/form_data，先创建新迁移再写入。
4. 仅为开发演示建立显式模拟配置及对应规则，不能覆盖官方免提交配置。
5. seed脚本采用绑定SQL参数和单事务；按code查重复，已发布配置不覆盖；不存在的UUID不得填入外键。
6. 管理员核对后可在开发环境发布模拟版本，填写approved_by与published_at；公开查询只返回published，来源pending仍不可通过公开来源接口读取。
7. 前端替换precheck-demo.ts数据，读取GET /api/v1/matters和事项详情，并展示来源与模拟标记。
8. 上传／提取／预审测试后逐步启用人工复核和交接清单。

首次入库验收：1个事项、1个官方draft版本、1种身份证材料及1条要求；公开演示另有明确模拟标识；无伪造政策条件、无模拟“共享核验成功”。

数据库写入不等于闭环已完成。本文没有执行任何运行库INSERT、发布或迁移。
