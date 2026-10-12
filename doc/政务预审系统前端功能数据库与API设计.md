# 政务材料预审系统：前端功能、数据库与API接口设计

版本：v1.0；日期：2026-10-10。  
配套文档：《政务材料预审系统前端完整设计》《政务材料预审系统数据库详细设计》。  
本文逐项建立“前端功能 → 业务API → 数据表读写 → 校验与状态变化”的对应关系。它是待实现的接口契约，不代表现有FastAPI模板已经提供这些接口，也不是已经执行的数据库迁移。

## 1. 架构与范围

前端通过HTTP调用后端，后端执行业务校验并访问数据库；前端不能直接连接数据库。OCR与大模型由后端处理服务调用。文件字节存文件存储，数据库保存文件记录与受控存储键。

本文沿用已有34张逻辑表；新增部分集中在第4章说明，不能将新增字段误认为原数据库设计已经包含。角色、版本和任务状态沿用原设计。

**实施范围**：P0=一个事项完整闭环；P1=扩展交互与管理；P2=平台对接等后续能力。即使P1功能暂未实施，后端鉴权、输入快照、并发保护和基础审计仍属于P0。

**认证角色**：访客、resident居民、reviewer复核员、config_admin配置管理员。配置管理权限不自动获得居民材料权限。工作人员未领取任务前，队列仅提供有权限的任务摘要；原图与字段须在领取或获得明确授权后访问。

## 2. API通用契约

### 2.1 路径与数据约定

- 基础路径：`/api/v1`。后续接口表省略该前缀。
- 路径参数统一使用UUID字符串；示例中的`A1`、`V1`等是阅读占位符，开发时替换为合法UUID。
- JSON字段使用snake_case；日期`YYYY-MM-DD`，时间点ISO 8601 UTC，前端按中国时区显示。
- 常规请求使用`application/json`，上传文件使用`multipart/form-data`。
- 前端业务响应是DTO，可以包含关联展示值和计算字段，不等同于完整数据库行。
- 标记`?`的请求字段为可选。未列出的敏感或只读字段禁止批量写入。
- `owner_user_id`、`uploaded_by`、`initiated_by`、`actor_user_id`和操作时间由后端生成，不能信任前端指定。
- 前端不传或接收模型密钥、密码哈希、内部文件存储键、原始服务异常堆栈。

### 2.2 返回格式

资源创建返回201，异步任务受理返回202，正常读取与更新返回200。删除草稿等无响应体操作返回204；204不返回下面的包装体。

```json
{
  "data": {"id": "A1", "content_revision": 3},
  "request_id": "req-demo-01"
}
```

列表采用分页：`page>=1`、`page_size=20`，最大100；服务端固定排序并用ID作同时间的次级排序。

```json
{
  "data": {
    "items": [], "page": 1, "page_size": 20, "total": 0
  },
  "request_id": "req-demo-02"
}
```

错误结构统一；框架原有校验错误可经异常处理器映射到这一结构：

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "材料已更新，请刷新后继续。",
    "details": {"current_revision": 8},
    "field_errors": []
  },
  "request_id": "req-demo-03"
}
```

| HTTP状态 | 业务码示例 | 前端行为 |
| --- | --- | --- |
| 401 | AUTH_REQUIRED | 登录后返回原页面 |
| 403 | PERMISSION_DENIED | 显示无操作权限 |
| 404 | RESOURCE_NOT_FOUND | 显示不存在；他人私有资源可同样返回404避免泄露 |
| 409 | REVISION_CONFLICT、TASK_ALREADY_CLAIMED、DUPLICATE_ACTIVE_TASK | 刷新版本、任务或跳转已有任务 |
| 410 | FILE_PURGED | 提示原文件已按规则清理 |
| 413 | FILE_TOO_LARGE | 展示配置中的文件限制 |
| 415 | UNSUPPORTED_FILE_TYPE | 更换允许的格式 |
| 422 | INVALID_ANSWER、INVALID_SCOPE、INVALID_STATE | 定位表单项或说明当前状态不能操作 |
| 429 | RATE_LIMITED | 按服务端提示稍后重试 |
| 503 | SERVICE_UNAVAILABLE | 保留草稿，允许稍后重试 |

### 2.3 版本和幂等

1. 改变办件事实的请求携带`expected_revision`；事务中校验并更新`applications.content_revision`。同一逻辑操作只增加一次。
2. 问卷、参与人、有效材料版本、字段确认/纠正、准备声明都属于事实变化。消息已读、备注追加、任务领取不增加办件内容修订。
3. 创建办件、上传新版本、发起解析/核验/复核、提交复核使用`Idempotency-Key`请求头。相同账号、相同路由、相同键和相同请求返回原结果；键相同但请求不同返回409。
4. `check_runs.idempotency_key`支持核验幂等，其余接口用新增`api_idempotency_records`。内容摘要不在响应中暴露。
5. 草稿配置使用`expected_config_revision`；复核任务操作使用`expected_task_revision`，两者分别独立计数。
6. 幂等重放先验证请求摘要、再返回已提交结果，不能因为旧`expected_revision`而把成功重试误判为冲突。其他新请求仍按当前修订校验。
7. 已发布事项版本冻结。P0不支持原地换版本；需要改用新指南时明确创建新的准备办件。

### 2.4 权限与字段可见性

私有办件、字段、文件、报告、复核记录每个端点都校验对象所属关系。先校验路径中的办件，再检查下级ID同属该办件。跨办件ID存在也不能使用。

列表默认脱敏，查看本人必要材料或已授权复核原图使用单独访问接口并记审计。队列摘要不返回全文或证件号码。管理员配置接口拒绝居民材料ID。

## 3. 前端功能到数据库的总映射

| 前端功能 | 核心读取 | 核心写入 | 是否使用模型 |
| --- | --- | --- | --- |
| 登录与个人信息 | users、user_roles | users；认证扩展按现有机制 | 否 |
| 事项查询与详情 | service_matters、matter_versions、material_requirements、policy_sources、地点与渠道表 | 无 | P0否 |
| 创建与继续办件 | applications、matter_versions | applications、application_events | 否 |
| 参与人 | application_participants | application_participants、applications修订 | 否 |
| 情形问卷 | matter_questions、applications.scenario_answers | scenario_answers与修订 | 否 |
| 个性化清单 | 材料要求、参与人、问卷、材料及最新检查 | 准备声明表（新增） | 否，条件求值器 |
| 上传与补传 | application_documents、document_versions、文件表 | 逻辑材料、版本、文件、修订 | 可触发后台解析 |
| 字段确认 | extraction_runs、extracted_fields、field_corrections | field_corrections、修订 | 已有模型输出 |
| 检查进度与报告 | check_runs、输入快照、结果、问题、证据 | 后台写各检查表 | 抽取/解释可用模型；规则判断使用引擎 |
| 用户请求复核 | review_tasks、review_records | review_tasks、补充说明表（新增） | 否 |
| 工作人员复核 | 问题、证据、任务、授权 | review_records、纠正记录、任务状态 | 可生成回复草稿 |
| 线下准备与打印 | 当前清单、固定报告、地点、准备声明 | P0无 | 否 |
| 消息 | notifications（新增） | notifications已读状态 | 否 |
| 配置与发布 | 版本及配置子表 | 草稿配置、发布审计 | 模型仅辅助草稿 |
| 统计与审计 | runs、tasks、records、events、audit_logs | 一般无 | 否 |

**问卷唯一事实来源**：本文P0固定使用`applications.scenario_answers`，动态题目定义使用`matter_questions`。若后续启用`application_answers`，通过迁移改为明细唯一来源，现有API可保持不变；禁止两个来源各自编辑。

## 4. 为完整前端补充的数据库设计

下表均为新增建议，需要模型与迁移，未修改原数据库文档。一般字段`created_at`/`updated_at`采用TIMESTAMPTZ；UUID由服务端生成。

### 4.1 P0需要的补充

| 表/字段 | 定义 | 约束与用途 |
| --- | --- | --- |
| matter_versions.config_revision | INTEGER NOT NULL DEFAULT 1 | >0；任何草稿子配置变化均增加，用于发布与编辑冲突校验 |
| material_requirements.alternative_group_code | VARCHAR(80) NULL | 相同版本内同组为“任选一”；P0只支持至少一项，不开放任意复杂组合 |
| applications.questionnaire_status | VARCHAR(16)，默认draft | draft/submitted；区分自动保存和情形提交 |
| check_runs.coverage | VARCHAR(16)，默认full | full/partial；部分检查不能生成整体prepared结论 |
| check_runs.input_preparation_snapshot | JSONB，默认[] | 冻结现场材料准备声明，不使用后来可变记录 |
| extraction_runs.input_schema_snapshot | JSONB，默认{} | 冻结本次字段定义、材料归类与人员映射，成功结果必须匹配当前配置才可选作当前有效字段 |
| review_tasks.task_revision | INTEGER，默认1 | >0；领取、补充说明、提交反馈均递增 |
| review_records.details | JSONB，默认{} | 结构化补充项、来源、线下地点及输入版本；不能把评论当作规则事实 |
| application_preparation_items | id、application_id、matter_version_id、requirement_id、participant_id?、declaration=not_ready/ready/unknown、declared_by、updated_at | FK限定要求同版本、人员同办件；非空人员唯一(application_id,requirement_id,participant_id)，空人员使用单独部分唯一索引；用户声明不等于核验通过 |
| review_task_messages | id、task_id、message_no、actor_user_id、sender_kind=user/staff、body、created_at | UNIQUE(task_id,message_no)；追加式，用于双方补充说明；正式复核意见仍写review_records |
| api_idempotency_records | id、user_id、operation、key、request_hash、state=in_progress/completed、resource_id?、response_status?、response_json?、expires_at、created_at | UNIQUE(user_id,operation,key)；保存最少响应标识，不缓存完整证件；租约超时需结合实际资源核对，不能直接重复执行 |

准备声明、复核消息的外键均使用RESTRICT，删除走受控清理；消息限制长度并禁止包含未授权办件文件引用。替代组成员必须同版本、同人员角色、同提交语义，发布时校验。复杂“N选M”留到后续独立组表。

### 4.2 P1/P2扩展

| 新增表 | 核心字段 | 约束与范围 |
| --- | --- | --- |
| notifications | id、recipient_user_id、application_id?、task_id?、type、title、body、read_at?、event_key、created_at | UNIQUE(recipient_user_id,event_key)；recipient索引；任务与办件关联由服务层检查；正文不存敏感全文 |
| admin_assistance_jobs | id、matter_version_id、requested_by、status、expected_config_revision、input_source_ids JSONB、proposal JSONB、model_info JSONB、review_status、started_at?、finished_at?、error_code? | 模型草稿任务；proposal不可自动发布，采纳时重新检查配置修订与来源 |
| report_exports | id、application_id、check_run_id、input_revision、status、storage_key?、template_version、created_at、expires_at? | 同范围复合FK；导出仍需鉴权，文件删除同样清理 |
| file_cleanup_requests | id、application_id、requested_by、status、reason、created_at、finished_at? | 服务端检查保留与关联任务，按策略实际清理文件与派生数据 |
| applications.user_handling_note | JSONB，默认{} | P1个人记录：state=not_recorded/reported_handled、recorded_at、note；仅用户自述，不改准备服务为正式审批状态 |
| assistance_questions | id、user_id、application_id?、matter_version_id、check_run_id?、question、answer?、status、source_refs JSONB、model_info JSONB、created_at、finished_at?、expires_at | P1辅助问答任务；引用同范围、最少保存、限额与清理；不将回答作为核验事实 |

P0任务进度可以由已有解析/检查任务组合计算。若需要保存阶段完成计数，再新增结构化进度字段并由后台更新；API返回阶段不代表数据库已有同名列。P0不承诺真实预约、短信或微信能力。

认证会话表是否新增由现有登录机制决定，不能重复建立另一套登录。采用服务端会话才需要会话存储；JWT退出是否即时失效取决于撤销机制，不作虚假承诺。

## 5. 居民端接口

以下每个接口均遵守第2章约定。`R`表示读表，`W`表示写表；事件/审计写入按操作需要追加。

### 5.1 登录、个人信息和消息

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与校验 |
| --- | --- | --- | --- | --- |
| U01 登录 | POST `/login/access-token` | 表单username、password；沿用模板实际认证格式 | access_token、token_type | R users；账号可用、密码验证；认证响应沿用模板，不强制改包装 |
| U02 当前账号 | GET `/users/me` | 无 | id、display_name、roles、is_demo | R users、user_roles；is_demo为环境计算值 |
| U03 修改个人信息 | PATCH `/users/me` | display_name | 个人展示信息 | W users；不允许写角色或is_superuser |
| U04 退出 | POST `/auth/logout`（如服务支持） | 会话/令牌由认证机制识别 | 204 | 服务端撤销按现有机制；没有撤销能力时前端仅清除令牌并说明语义 |
| U05 消息列表 P1 | GET `/notifications` | page、page_size、unread_only? | 分页通知、unread_count | R notifications；只读当前用户，链接目标访问再次鉴权 |
| U06 标记已读 P1 | PATCH `/notifications/{notification_id}` | read=true | id、read_at | W notifications；重复操作幂等，不能改正文 |

前端若已有`/users/me`等接口，优先适配已有名称与字段。密码变更、注册、找回密码沿用现有认证模块，本文不假定其具体实现。

### 5.2 事项查询、详情和公开来源

| 编号/功能 | 方法与路径 | 请求 | 响应data | R表与校验 |
| --- | --- | --- | --- | --- |
| M01 事项搜索 | GET `/matters` | q?、region_code?、page、page_size | id、name、region_name、description、published_version_id、supports_precheck、source_checked_at | service_matters、matter_versions；只公开有效目录及可用发布版本；P0无分类字段，不实现category筛选 |
| M02 事项详情 | GET `/matters/{matter_id}` | 无 | matter、version、requirements、questions_summary、handling_locations、sources | 版本、材料、地点、问卷、来源关联；已发布配置，未知地址留空 |
| M03 获取材料办法 | GET `/matter-versions/{version_id}/requirements/{requirement_id}/acquisition-methods` | 无 | methods：steps、entry_url、location、source、verification_status | material_acquisition_methods、service_locations、policy_sources；公开已核对渠道，条件渠道标明适用条件 |
| M04 官方来源 | GET `/policy-sources/{source_id}` | 无 | title、url、publisher、published_date、verified_at、引用片段 | policy_sources及已发布引用关系；不能凭ID公开管理员草稿和内部全文 |

`supports_precheck`由发布配置完整性和服务启用状态推导；不虚构原表中的同名字段。选择公开版本使用稳定策略：已发布且当前业务日期适用的版本，按已确定的版本序号选择；出现冲突配置时不随意选取。

### 5.3 办件、问卷和参与人

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库读写及校验 |
| --- | --- | --- | --- | --- |
| A01 新建办件 | POST `/applications` | matter_id、matter_version_id；Idempotency-Key | id、application_no、matter_version_id、status=draft、content_revision=1 | R matter_versions；W applications；归属当前账号，版本已发布且可用于新办件；data_origin由运行环境确定 |
| A02 我的办件 | GET `/applications` | status?、matter_id?、page、page_size | 分页卡片、latest_check、next_actions | R applications与相关任务；固定owner过滤，不接受任意owner_user_id |
| A03 办件详情 | GET `/applications/{app_id}` | 无 | 概况、version、participants、状态、修订、actions | R applications及汇总；owner/授权范围检查 |
| A04 归档/取消 | POST `/applications/{app_id}/lifecycle-actions` | action=close/cancel、expected_revision | status、closed_at、content_revision | W applications、任务取消、事件；关闭不代表政府已办结；拒绝仍需处理的关闭请求 |
| A05 过程历史 | GET `/applications/{app_id}/events` | page、page_size | 用户可见事件分页 | R application_events；不返回内部审计细节 |
| Q01 获取问卷 | GET `/applications/{app_id}/questionnaire` | 无 | questions、answers、visible_codes、unknown_codes、questionnaire_status、content_revision | R matter_questions、scenario_answers、版本；按锁定版本返回 |
| Q02 保存/提交问卷 | PUT `/applications/{app_id}/scenario` | answers、mode=draft/submit、expected_revision | answers、可见题、校验提示、清单差异、content_revision | W scenario_answers、questionnaire_status、修订；校验类型/选项；submit检查当前可见必填 |
| P01 参与人列表 | GET `/applications/{app_id}/participants` | 无 | id、participant_code、role_code、display_name、必要事实 | R application_participants；敏感内容按权限脱敏 |
| P02 新增参与人 | POST `/applications/{app_id}/participants` | role_code、display_name?、identity_payload?、expected_revision | participant、content_revision | W participants、修订；code由后端生成；事项允许角色与字段白名单 |
| P03 修改参与人 | PATCH `/applications/{app_id}/participants/{participant_id}` | display_name?、identity_payload?、expected_revision | participant、content_revision | W participants、修订；P0不允许更改role_code以免旧字段角色失真 |
| P04 删除空参与人 | DELETE `/applications/{app_id}/participants/{participant_id}` | expected_revision查询参数 | 204 | W participants、修订；有材料/快照/纠正关联时409，不能级联删证据 |

`answers`是当前答案完整替换；前端先取得当前问卷再提交，避免遗漏导致意外删除。`draft`允许未完成，`submit`表示完成情形确认；允许“不确定”的问题须定义明确选项，例如`unknown`，不得把它当成false。隐藏题可保留但不参与当前计算；每次运行固定实际使用的答案与可见性。

### 5.4 清单与准备状态

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与校验 |
| --- | --- | --- | --- | --- |
| C01 个性化清单 | GET `/applications/{app_id}/checklist` | 无 | items、alternative_groups、unknown_conditions、content_revision | R requirements、答案、participants、documents、preparation_items、最新有效检查；服务层计算 |
| C02 个人材料获取渠道 | GET `/applications/{app_id}/requirements/{requirement_id}/acquisition-methods` | participant_id? | 当前情形适用渠道、取材料地点、来源 | R 已发布渠道与情形；unknown渠道保留待确认 |
| C03 标记现场材料已准备 | PUT `/applications/{app_id}/preparation-items` | requirement_id、participant_id?、declaration、expected_revision | 声明、content_revision | W preparation_items、修订；user_upload项目不能通过声明替代文件；部门是否实际取得不由用户声明 |

**清单项DTO**：requirement_id、requirement_code、material_type_id、name、participant_id、provider_role、applicability=true/false/unknown、requirement_level、submission_mode、alternative_group_code、original_required、copy_count、min_pages、format_requirements、preparation_state、document_ids、latest_check_status、source_refs、available_actions。

`preparation_state`为组合展示值，不直接写回材料表。未知适用性不能隐藏必要材料；清单差异包含added、removed_from_current_scope和pending_confirmation，旧材料不物理删除。

### 5.5 材料上传、补传、预览与解析

P0采用“创建逻辑材料 → multipart一次提交完整版本 → 后台解析”，不必先实现直传对象存储。移动端先在本地预览和排序；只有完整上传成功后，新版本才成为active。

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与校验 |
| --- | --- | --- | --- | --- |
| D01 上传限制 | GET `/upload-policy` | 已登录；app_id? | allowed_mime_types、max_file_bytes、max_files_per_version、总容量限制 | R 服务配置；不伪称业务表已有字段 |
| D02 材料列表 | GET `/applications/{app_id}/documents` | 无 | 逻辑材料、当前版本、文件摘要、解析状态 | R documents、versions、files、extraction_runs；不返回storage_key |
| D03 创建逻辑材料 | POST `/applications/{app_id}/documents` | requirement_id?、material_type_id、participant_id?、expected_revision | document、content_revision | W application_documents、修订；code由后端生成；所属要求同版本、人员同办件 |
| D04 上传完整新版本 | POST `/applications/{app_id}/documents/{document_id}/versions` | multipart files[]按顺序、expected_revision；Idempotency-Key | document_version_id、version_no、files、content_revision | W versions、files、旧active状态、修订；检测实际类型、大小、权限；201，不等于OCR完成 |
| D05 材料版本历史 | GET `/applications/{app_id}/documents/{document_id}/versions` | page、page_size | versions、文件信息、解析摘要 | R versions、files、runs；保留旧报告对应版本 |
| D06 受控预览/下载 | GET `/applications/{app_id}/files/{file_id}/content` | download? | 文件流；不使用JSON包装 | R files与所属关系；审计访问；purged返回410，按授权处理Range请求 |
| D07 确认材料归类 | PATCH `/applications/{app_id}/documents/{document_id}/classification` | material_type_id、requirement_id?、participant_id?、expected_revision | 分类、content_revision、needs_reextract | W documents、修订；变更字段配置需新解析；历史报告用快照不读新归类 |
| D08 撤回当前版本 | POST `/applications/{app_id}/documents/{document_id}/withdrawal` | document_version_id、expected_revision、reason? | status=withdrawn、content_revision | W versions、修订；不自动恢复旧版本，不删除历史文件 |
| D09 发起/重试解析 | POST `/applications/{app_id}/document-versions/{version_id}/extractions` | expected_revision；Idempotency-Key | extraction_run_id、status=pending | W extraction_runs；202；同版本活动任务去重，拒绝已撤回或被替换版本用于当前解析 |
| D10 解析进度 | GET `/applications/{app_id}/extractions/{extraction_id}` | 无 | status、stage、processed_files、total_files、error_code | R extraction_runs、后端任务元数据；旧尝试仍可查看 |
| D11 识别字段 | GET `/applications/{app_id}/extractions/{extraction_id}/fields` | page、page_size | fields：原值、有效值、人员、页码、bbox、确认状态 | R extracted_fields、corrections、files；只使用指定解析尝试 |
| D12 确认/纠正字段 | POST `/applications/{app_id}/fields/{field_id}/corrections` | action=confirm/correct、corrected_value?、corrected_participant_id?、reason?、expected_revision | correction_id、effective_value、value_status、content_revision | W field_corrections、修订；检查字段属当前可用版本与尝试；原值不可覆盖 |

**上传事务**：先暂存并验证全部文件 → 短事务锁定办件/材料与校验修订 → 旧active变superseded → 插入版本和文件 → 修订加1 → 提交。失败清理临时对象；提交成功后文件已可用。对象存储与数据库不是同一事务，须有孤儿清理与补偿。

**部分失败**：P0一个版本上传失败则不发布新版本，前端保留本地选中页并重试请求。旧版本不受影响。若必须只重传失败页，需要P1新增上传会话与临时文件表；不能将未完成版本当active。多页追加/排序形成新完整版本，不能就地修改旧files。

**归类历史**：创建check时将要求、人员、材料类型映射纳入`config_snapshot`或输入文档快照，避免修改document归类后旧报告改变。

**有效字段选择**：使用当前文件版本、与当前字段配置匹配的成功解析尝试；按attempt_no选择，排除旧模型尝试；有效值采用最新有效correction_no。选择发生变化时后端增加content_revision，让旧检查失效。解析完成写字段与更新修订在同一短事务，核验不读取未完成的半批字段。

`corrected_value=null`表示无法确认，value_status=unknown；confirm时服务复制原值。纠正人员字段需区分不改人员和显式清空。用户纠正只是识别信息，不改变原文件；材料确实填写错误时应补传而非改字段掩盖。

### 5.6 预审、报告与历史

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与校验 |
| --- | --- | --- | --- | --- |
| K01 开始材料检查 | POST `/applications/{app_id}/checks` | expected_revision、coverage=full/partial；Idempotency-Key | check_run_id、run_no、input_revision、status=pending | W check_runs、check_run_documents、check_run_fields及准备快照；202；情形已提交、使用的解析已可用 |
| K02 查询进度 | GET `/applications/{app_id}/checks/{run_id}` | 无 | status、stage、input_revision、is_current、error_code、可测算计数 | R check_runs、输入任务；无依据不返回虚假百分比 |
| K03 查看报告 | GET `/applications/{app_id}/checks/{run_id}/report` | 无 | report、results_summary、issues、review_summary、actions | R runs/results/issues/evidence/复核；未完成409，失败可返回部分结果并明确不完整 |
| K04 报告历史 | GET `/applications/{app_id}/checks` | page、page_size | 运行分页、版本、汇总、is_current | R check_runs；run_no降序 |
| K05 问题证据详情 | GET `/applications/{app_id}/checks/{run_id}/issues/{issue_id}` | 无 | issue、evidence、rule_source、available_actions | R issues、evidence、输入快照、来源；问题必须属于run且证据被纳入本次输入 |

K01重复点击不重复运行。还有未完成的同输入检查时返回已有任务；解析未完成返回`EXTRACTION_NOT_READY`，前端等待解析再发检查，不在数据库锁中等待模型。P0部分检查使用当前已就绪材料，列出未检查范围。

**完整性汇总**：规则结果保持pass/fail/unknown/not_applicable/error；任何error不能汇总为no_issue。资格检查未实现返回not_evaluated。full表示检查完整范围，不表示材料齐全；缺失材料仍产生问题。partial即使已上传部分无问题，也不能让整个办件进入prepared。

**输入快照**：问卷、参与人必要事实、材料映射、文件版本、有效字段与人员、纠正ID、准备声明、规则、来源展示内容、地点信息均冻结或引用不可变记录。若采用简化check_run_fields方案，则增加等价`input_fields_snapshot`，不可删除快照后仍声称可追溯。

**后台完成**：保存结果与证据；检查input_revision仍等于content_revision，且该运行是当前有效请求，才更新主状态。旧任务结果保存为历史，不覆盖新状态。用户请求不能传pass/fail或直接修改问题“已解决”。

### 5.7 申请复核、查看反馈与补充说明

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与校验 |
| --- | --- | --- | --- | --- |
| R01 请求复核 | POST `/applications/{app_id}/review-tasks` | check_run_id、scope、issue_id?、request_note?、expected_revision；Idempotency-Key | task_id、status、task_revision、is_demo | W review_tasks；202；只能请求可用的当前报告，具体问题同run |
| R02 复核列表 | GET `/applications/{app_id}/review-tasks` | page、page_size、status? | tasks、过期提示、反馈摘要 | R tasks、records；只读授权办件 |
| R03 复核详情 | GET `/applications/{app_id}/review-tasks/{task_id}` | 无 | scope、固定报告、records、messages、task_revision、is_stale | R tasks、records、messages、runs；反馈不是审批结论 |
| R04 补充说明 | POST `/applications/{app_id}/review-tasks/{task_id}/messages` | body、expected_task_revision；Idempotency-Key | message、task_revision | W messages、task修订；不覆盖request_note；已完成任务拒绝追加或引导新任务 |
| R05 撤回复核 | POST `/applications/{app_id}/review-tasks/{task_id}/cancellation` | reason?、expected_task_revision | task、task_revision | W task与withdrawn处理记录；保留历史，取消后工作人员不可继续提交 |

一条review_tasks只支持一个issue或整体scope，不接受issue_ids数组写入同一行。前端选择多个问题时逐项创建，或明确选择整体复核。活动重复任务返回409与已有task_id。补传后旧任务仍对应旧run；P0先完成旧任务或取消，再用新run创建任务，不悄悄换task.check_run_id。

### 5.8 线下准备、打印与文件清理

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与校验 |
| --- | --- | --- | --- | --- |
| L01 当前线下准备 | GET `/applications/{app_id}/preparation` | check_run_id? | checklist、locations、unresolved_items、report_date、is_current、guidance_update_available | R 固定报告配置与当前状态；旧run明确旧版本，不混入新要求 |
| L02 页面打印 | 无独立写API | 使用L01返回数据 | 浏览器打印视图 | P0不落新报告表；绑定run_id和版本，不能打印个人材料公开链接 |
| L03 导出PDF P1 | POST `/applications/{app_id}/report-exports` | check_run_id；Idempotency-Key | export_id、status | W report_exports；202；引用授权run |
| L04 导出下载 P1 | GET `/applications/{app_id}/report-exports/{export_id}/content` | 无 | PDF文件流或未完成错误 | R exports；权限与有效期校验 |
| L05 请求清理 P1 | POST `/applications/{app_id}/cleanup-requests` | reason?；Idempotency-Key | request_id、status、预计处理说明 | W cleanup_requests；202；不等于立刻删除，实际处理按保留策略 |
| L06 个人办理记录 P1 | PUT `/applications/{app_id}/user-handling-note` | state、note? | user_handling_note | W applications.user_handling_note；只保存当前owner自述、后端时间；不修改prepared、资格或政府审批结论 |

地点来自锁定版本的已核对配置；发现新指南仅提示，P0不自动改旧办件版本。若有线上未解决问题，准备页优先提供咨询准备，不显示“材料全部无误”。

### 5.9 当前事项与报告辅助问答 P1

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与校验 |
| --- | --- | --- | --- | --- |
| H01 事项辅助提问 | POST `/matter-versions/{version_id}/assistance-questions` | question；Idempotency-Key | question_id、status=pending | W assistance_questions；202；已登录，公开发布版本，仅检索已核对公开资料 |
| H02 报告辅助提问 | POST `/applications/{app_id}/checks/{run_id}/assistance-questions` | question；Idempotency-Key | question_id、status=pending | R 固定报告/已授权证据，W assistance_questions；不能根据问题读取其他办件 |
| H03 查看回答 | GET `/assistance-questions/{question_id}` | 无 | status、answer、source_refs、is_supported、error_code | R assistance_questions；仅请求者或明确授权范围；无充分依据明确无法回答 |

第一版不必保存无限会话。每次问题绑定版本与报告，服务端限制输入、检索范围、耗时与配额，答案引用已核对来源。回答不能自动追加材料要求、修改问卷、触发审批或执行模型生成的SQL。上传材料和政策正文只是待处理数据，不作为新的系统指令。是否向外部模型发送个人信息按既定数据处理方式执行。

## 6. 工作人员端接口

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库、权限与状态 |
| --- | --- | --- | --- | --- |
| S01 待领取任务 | GET `/staff/review-tasks` | status?、matter_id?、mine?、page、page_size | 脱敏摘要、等待时长、priority、task_revision | R review_tasks、runs、matters；限定配置的工作范围，P0演示单范围 |
| S02 领取任务 | POST `/staff/review-tasks/{task_id}/claim` | expected_task_revision；Idempotency-Key | assigned_to、status=in_progress、task_revision | 条件W tasks；必要时W access_grants；只有pending未分配且符合范围成功 |
| S03 复核工作台 | GET `/staff/review-tasks/{task_id}/workspace` | 无 | 任务、问题、固定字段证据、当前修订、来源、历史、actions | R task/run/输入/issues/evidence/files/fields/corrections；assigned_to或明确grant |
| S04 工作人员材料访问 | GET `/staff/review-tasks/{task_id}/files/{file_id}/content` | download? | 授权文件流 | R files及固定输入集合；不允许借task访问其他办件文件；写审计 |
| S05 回复补充说明 | POST `/staff/review-tasks/{task_id}/messages` | body、expected_task_revision；Idempotency-Key | message、task_revision | W messages、task修订；领取人可写，不能代替正式结论 |
| S06 提交复核处理 | POST `/staff/review-tasks/{task_id}/records` | expected_task_revision、expected_revision、outcome、comment、details、field_correction?；Idempotency-Key | record、task、content_revision、needs_recheck | W records/tasks、可选correction与办件修订；短事务提交，详见下文 |
| S07 历史处理 | GET `/staff/review-records` | mine=true、matter_id?、from?、to?、page、page_size | 处理记录分页 | R records、tasks；默认本人，扩大范围需额外管理权限 |
| S08 工作统计 P1 | GET `/staff/metrics` | from、to、matter_id?、data_origin | 数量、耗时、补正/线下比例、定义与样本量 | R tasks、records、events；按授权范围聚合，合成/真实分开 |
| S09 转交任务 P1 | POST `/staff/review-tasks/{task_id}/transfer` | target_reviewer_id、reason、expected_task_revision | task、task_revision | W tasks、授权与审计；仅受理负责人/获授权主管，不能任何reviewer任意转交 |

### 6.1 复核提交规则

| outcome | 必需内容 | 任务状态 | 后续处理 |
| --- | --- | --- | --- |
| confirmed | 评论/依据；若涉及识别错误可附字段纠正 | completed | 如字段事实改变则修订加1、需重新检查；仅人工意见不擅改规则结果 |
| supplement_required | details.supplement_items与说明 | waiting_user | 提示用户补传；旧task固定旧run，新输入需新run重新提交 |
| offline_required | 原因及核对过的location_id或官方咨询方式 | completed | 提供线下咨询准备，不汇总为材料无误 |
| system_error | 可理解的错误说明 | completed | 保留未确认问题，允许重试或另建任务 |

withdrawn由撤回接口产生，不作为一般工作人员确认结果。`details`固定存本任务的run_id/input_revision及来源ID，不接受任意任务或办件引用。

提交前验证领取人、task_revision、办件revision、字段归属。过期输入默认409；P0不允许绕过。一个提交最多附一条field_correction，适配原review_records的单外键；多字段纠正可分步骤追加，随后针对更新的输入重检，未来批量能力需新增关联表。

工作人员不能POST一段评论就把资格unknown改为supported。人工事实若需要参与规则，必须设计独立结构化事实与输入快照；P0只保留意见和待确认状态。

任务completed或cancelled后撤销任务授予的原图访问能力，历史意见保留；既有独立grant按其权限与有效期管理。队列、历史页、文件读取使用相同服务端权限规则。

## 7. 管理端接口

所有接口要求config_admin。仅草稿可编辑；每个子配置写操作持有该版本的短事务锁、检查并增加config_revision。公开版本与历史来源不得就地覆盖。

### 7.1 事项与版本

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库及约束 |
| --- | --- | --- | --- | --- |
| B01 事项目录 | GET `/admin/matters` | q?、region_code?、page、page_size | matters、版本摘要 | R service_matters、versions |
| B02 创建事项 | POST `/admin/matters` | code、name、region_code、region_name、official_code?、description? | matter | W service_matters；code唯一，官方码未核实不填 |
| B03 编辑/停用目录 | PATCH `/admin/matters/{matter_id}` | name?、description?、is_active? | matter | W service_matters；涉及发布展示时需建立新版本快照，停用只阻止新办件 |
| B04 创建草稿版本 | POST `/admin/matters/{matter_id}/versions` | based_on_version_id?、change_summary? | version_id、version_no、config_revision | W versions与复制子配置；重建内部ID映射，不能让新规则引用旧requirement_id |
| B05 版本详情 | GET `/admin/matter-versions/{version_id}` | 无 | version、requirements、questions、rules、locations | R 版本配置 |
| B06 修改版本元信息 | PATCH `/admin/matter-versions/{version_id}` | valid_from?、valid_to?、change_summary?、expected_config_revision | version、config_revision | W draft version；日期边界校验 |
| B07 废弃草稿 | DELETE `/admin/matter-versions/{version_id}` | expected_config_revision查询参数 | 204 | 按依赖逆序删除无办件草稿；已发布/被引用返回409 |
| B08 停用发布版本 | POST `/admin/matter-versions/{version_id}/retirement` | reason、expected_config_revision | status=retired | W versions与审计；不改历史数据，不中断旧办件读取 |

目录名称等可变值若被报告使用，必须在run配置快照保存，不依赖当前目录行生成旧报告。并发创建version_no使用事项锁或唯一约束重试。

### 7.2 配置CRUD接口族

每行是一组明确的集合/单项接口：`GET collection`、`POST collection`、`PATCH collection/{id}`、`DELETE collection/{id}`。POST/PATCH/DELETE携带expected_config_revision；DELETE使用查询参数。GET返回items和config_revision；写返回资源及新config_revision；DELETE返回204，前端随后刷新。适用范围均为指定草稿版本。

| 编号/配置 | collection路径 | POST必需字段（PATCH只接受其可改子集） | R/W表与特殊校验 |
| --- | --- | --- | --- |
| B09 材料要求 | `/admin/matter-versions/{version_id}/requirements` | material_type_id、requirement_code、name、applicability_expr、provider_role?、submission_mode、field_schema | material_requirements；可选份数/页数/原件/替代组/排序；类型存在、字段schema和角色合法 |
| B10 问卷 | `/admin/matter-versions/{version_id}/questions` | question_code、label、answer_type、options、required、show_when | matter_questions；选项类型、问题码唯一；删除被条件引用的问题时409 |
| B11 规则 | `/admin/matter-versions/{version_id}/rules` | rule_code、name、rule_type、operator_code、input_spec、parameters、applicability_expr、message_template | verification_rules；可选severity/on_missing/remedy/source；操作符白名单；字段与要求引用同版本 |
| B12 获取方式 | `/admin/matter-versions/{version_id}/requirements/{requirement_id}/acquisition-methods` | method_code、method_type、title、applicability_expr、source_id?、location_id?、steps?、entry_url? | material_acquisition_methods；要求属于版本，展示前核实来源及渠道 |

材料类型是全局目录，另提供`GET/POST /admin/material-types`和`PATCH /admin/material-types/{id}`，字段为code、name、description、is_active；不物理删已被引用类型。管理员改全局名称时，已发布材料要求name与历史快照不随之改写。

### 7.3 地点、来源与配置关联

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与约束 |
| --- | --- | --- | --- | --- |
| B13 来源列表 | GET `/admin/policy-sources` | verification_status?、q?、page、page_size | 来源分页 | R policy_sources |
| B14 创建来源版本 | POST `/admin/policy-sources` | title、source_kind、url、publisher?、published_date?、content_text? | source_id、verification_status=pending | W policy_sources；摘要由后端计算，更新时间新建版本 |
| B15 核对来源 | POST `/admin/policy-sources/{source_id}/verification` | verification_status=verified/unavailable、说明 | source状态、verified_by、verified_at | W source与audit；关联已发布版本的内容不可重写；说明保存在审计metadata |
| B16 来源详情 | GET `/admin/policy-sources/{source_id}` | 无 | 来源文本、核对信息、反向引用 | R source及关联；仅管理员 |
| B17 地点列表/新建 | GET/POST `/admin/locations` | GET筛选；POST name、region_code、address?、phone?、opening_hours?、official_entry_url?、source_id | 分页或新location | R/W service_locations；地址变化创建新记录 |
| B18 核对地点 | POST `/admin/locations/{location_id}/verification` | verification_status、说明 | 地点核实状态、checked_at | W location与audit；必要来源验证 |
| B19 关联办理地点 | PUT `/admin/matter-versions/{version_id}/locations` | items[{location_id,applicability_expr,sort_order,instructions}]、expected_config_revision | items、config_revision | 替换W matter_locations；同版本锁，发布前所有地点已核对 |
| B20 材料依据 | PUT `/admin/matter-versions/{version_id}/requirements/{requirement_id}/sources` | items[{source_id,excerpt,locator}]、expected_config_revision | 引用、config_revision | W requirement_sources；同版本范围校验 |
| B21 规则依据 | PUT `/admin/matter-versions/{version_id}/rules/{rule_id}/sources` | primary_source_id、items[{source_id,excerpt,locator}]、expected_config_revision | 引用、config_revision | W rule_sources与rule主来源；两者一致，删除主来源要显式替换 |

来源、地点核对接口只确认状态，不修改正文与地址。若要改内容，新增记录并更新草稿引用。通过URL抓取官方内容为后续能力：服务端限制网络目标、响应大小和文件类型，不开放任意内网地址访问。

### 7.4 预览、测试、模型草稿与发布

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与约束 |
| --- | --- | --- | --- | --- |
| B22 配置预览 | POST `/admin/matter-versions/{version_id}/preview` | answers、participants模拟、expected_config_revision | 清单、条件判定、地点、配置错误 | R draft配置；不创建居民办件 |
| B23 规则测试 | POST `/admin/matter-versions/{version_id}/rule-tests` | synthetic_facts、answers、expected_config_revision | 各规则结果与缺失输入 | R 配置；P0不写正式check_results，测试标准答案独立维护 |
| B24 模型整理草稿 P1 | POST `/admin/matter-versions/{version_id}/assistance-jobs` | source_ids、expected_config_revision；Idempotency-Key | job_id、status=pending | W admin_assistance_jobs；202；仅使用已允许来源 |
| B25 查询候选 P1 | GET `/admin/assistance-jobs/{job_id}` | 无 | status、proposal、证据、review_status | R assistance_jobs；不公开给居民 |
| B26 采纳草稿 P1 | POST `/admin/assistance-jobs/{job_id}/apply` | selected_proposals、expected_config_revision | 新草稿配置、config_revision | 人工确认后W配置与job审核状态；引用映射/结构验证，仍非发布 |
| B27 发布校验 | POST `/admin/matter-versions/{version_id}/validation` | expected_config_revision | errors、warnings、can_publish | R 所有配置，白名单、来源、边界、循环、替代组验证 |
| B28 发布版本 | POST `/admin/matter-versions/{version_id}/publication` | expected_config_revision、change_summary?；Idempotency-Key | status=published、approved_by、published_at | 事务重做校验、冻结配置并W版本/audit；未校验通过409或422 |

发布不是先调用validation后无条件改status。publication在同一配置修订下重新验证。更新页面不得让用户填写approved_by；审核者由服务端确定，项目角色为内部配置确认，不冒充政府审核。

### 7.5 角色、授权、审计和统计

| 编号/功能 | 方法与路径 | 请求 | 响应data | 数据库与约束 |
| --- | --- | --- | --- | --- |
| B29 账号角色 P1 | GET `/admin/users/{user_id}/roles` | 无 | roles | R user_roles；须额外access_admin能力或受控系统管理员，config_admin本身不足 |
| B30 修改角色 P1 | PUT `/admin/users/{user_id}/roles` | roles | roles | W user_roles与audit；防止自行越权或取消唯一管理入口 |
| B31 办件授权 P1 | PUT `/admin/applications/{app_id}/grants/{user_id}` | permission、expires_at? | grant | W application_access_grants与audit；额外grant_admin能力，默认配置管理员无权 |
| B32 撤销授权 P1 | DELETE `/admin/applications/{app_id}/grants/{user_id}` | 无 | 204 | W grant与audit；不改变历史处理记录 |
| B33 审计查询 P1 | GET `/admin/audit-logs` | action?、entity_type?、from?、to?、page、page_size | 脱敏审计分页 | R audit_logs；额外audit_read权限，不公开全文 |
| B34 运行统计 P1 | GET `/admin/metrics` | from、to、matter_id?、data_origin | 运行成功率、延迟、人工比例、分母定义 | R tasks/runs/events；允许聚合范围，不提供居民详情 |

access_admin等是建议的能力名，原user_roles只有三个角色；P0可映射已有受控is_superuser，P1需明确能力配置或扩展角色表，不能写不存在的角色并假定鉴权完成。

## 8. 核心请求与响应示例

以下均为虚构事项，编号为UUID占位符。未出现的字段不表示允许自由扩展；具体DTO应通过服务端类型模型验证。

### 8.1 创建办件与问卷提交

```http
POST /api/v1/applications
Authorization: Bearer <token>
Idempotency-Key: create-case-demo-01
Content-Type: application/json
```

```json
{"matter_id":"M1","matter_version_id":"MV1"}
```

```json
{"data":{"id":"A1","application_no":"DEMO-001","status":"draft","content_revision":1},"request_id":"req-01"}
```

```http
PUT /api/v1/applications/A1/scenario
```

```json
{
  "expected_revision": 2,
  "mode": "submit",
  "answers": {"handling_mode":"agent","application_kind":"first_time"}
}
```

```json
{
  "data": {
    "questionnaire_status":"submitted",
    "content_revision":3,
    "checklist_changes":{"added":["RQ3"],"removed_from_current_scope":[],"pending_confirmation":[]},
    "needs_recheck":true
  },
  "request_id":"req-02"
}
```

参与人新增等操作也会增加修订，示例数字不是固定流程次数。

### 8.2 材料版本与字段纠正

```http
POST /api/v1/applications/A1/documents/D1/versions
Content-Type: multipart/form-data; boundary=<generated>
Idempotency-Key: upload-demo-01
```

表单字段：`expected_revision=3`，`files`重复两次分别为正面和反面。boundary由请求库生成，前端不要手工写错。文件顺序即file_order。

```json
{
  "data": {
    "document_version_id":"DV2","version_no":2,"status":"active",
    "files":[{"id":"F1","file_order":1},{"id":"F2","file_order":2}],
    "content_revision":4,"needs_extraction":true
  },
  "request_id":"req-03"
}
```

```http
POST /api/v1/applications/A1/fields/EF1/corrections
```

```json
{"action":"correct","corrected_value":"张甲","reason":"对照原图纠正识别错误","expected_revision":5}
```

```json
{"data":{"correction_id":"FC1","effective_value":"张甲","value_status":"user_confirmed","content_revision":6},"request_id":"req-04"}
```

解析成功选用新字段导致修订增加，故这里从5开始。归属人员沿用原字段；显式调整人员须单独传corrected_participant_id并验证范围。

### 8.3 开始检查与报告

```http
POST /api/v1/applications/A1/checks
Idempotency-Key: check-demo-01
```

```json
{"expected_revision":6,"coverage":"full"}
```

```json
{"data":{"check_run_id":"CR1","run_no":1,"input_revision":6,"status":"pending"},"request_id":"req-05"}
```

```json
{
  "data": {
    "check_run_id":"CR1","input_revision":6,"current_revision":6,
    "is_current":true,"coverage":"full","status":"succeeded",
    "material_summary":"issues_found","eligibility_summary":"not_evaluated",
    "results_summary":{"pass":2,"fail":1,"unknown":0,"not_applicable":1,"error":0},
    "issues":[{
      "id":"I1","issue_type":"conflict","title":"申请人姓名待核对",
      "next_action":"confirm","remedy_text":"请先对照两份材料原图确认。",
      "evidence":[
        {"evidence_kind":"field","field_id":"EF1","file_id_for_preview":"F1","page_number":1,"bbox":[0.1,0.2,0.4,0.3],"snapshot_value":"张甲"},
        {"evidence_kind":"field","field_id":"EF2","file_id_for_preview":"F3","page_number":1,"bbox":[0.2,0.2,0.5,0.3],"snapshot_value":"张乙"}
      ],
      "source_refs":[{"source_id":"PS1","quote_text":"测试条款占位，不是真实政策"}]
    }],
    "available_actions":["correct_fields","request_review"]
  },
  "request_id":"req-06"
}
```

`file_id_for_preview`是DTO关联展示字段，不是issue_evidence的第二目标。数据库field证据仅field_id非空，文件ID通过字段归属计算，仍满足“目标恰一个”约束。报告snapshot_value来自本次输入，而非当前纠正值。

### 8.4 请求复核、领取与提交意见

```json
{
  "check_run_id":"CR1","scope":"issue","issue_id":"I1",
  "request_note":"原图仍不能确认，请帮助核对。","expected_revision":6
}
```

创建返回task_id=T1、status=pending、task_revision=1。领取：

```http
POST /api/v1/staff/review-tasks/T1/claim
```

```json
{"expected_task_revision":1}
```

返回status=in_progress、assigned_to=current_user、task_revision=2。提交：

```json
{
  "expected_task_revision":2,"expected_revision":6,
  "outcome":"supplement_required",
  "comment":"照片裁切了关键区域，请重拍完整页面。",
  "details":{
    "supplement_items":[{"requirement_id":"RQ1","participant_id":"P1","instruction":"补传完整第一页"}],
    "source_ids":["PS1"]
  }
}
```

返回record_id、task.status=waiting_user、task_revision=3；没有事实修改时content_revision仍为6。用户补传增加revision，再解析和新检查；旧记录始终保留。来源ID、补传要求必须来自当前任务范围。

### 8.5 草稿发布

```http
POST /api/v1/admin/matter-versions/MV1/publication
Idempotency-Key: publish-demo-01
```

```json
{"expected_config_revision":12,"change_summary":"首次发布测试配置"}
```

服务端锁定草稿、验证引用和来源，再设置approved_by、published_at及status。失败返回结构化errors，例如`RULE_FIELD_NOT_FOUND`，不创建半发布配置。

## 9. 状态与事务实现要求

### 9.1 办件主状态由服务计算

| 状态 | 含义 | 触发条件 |
| --- | --- | --- |
| draft | 情形尚未提交 | 新建办件、问卷草稿 |
| preparing | 准备材料或事实已变化 | 情形提交、上传/纠正后等待检查 |
| checking | 当前输入正在检查 | 创建当前run |
| needs_action | 当前检查/复核需要用户行动 | 缺件、冲突、重拍、补传或线下核实 |
| review_pending | 当前疑问有人工任务待处理 | 创建复核且没有更优先的补正动作 |
| prepared | 完整检查范围未发现待处理问题 | 当前full运行及必要准备声明，无未完成检查和疑问 |
| closed/cancelled | 准备服务归档/取消 | 生命周期操作 |

同一办件可同时有补正与复核，前端同时展示子状态。主状态按后端统一优先级重算，不靠最后一个任务写入决定。Prepared不表示资格或真实性已被政府核实；无资格检查时明确展示not_evaluated。

### 9.2 后台模型任务可靠性

解析与核验先提交pending任务，再交后台处理，不在数据库事务中等待OCR/大模型。P0可使用数据库任务轮询作为可靠分发方式；若队列推送失败，扫描pending任务恢复，不能丢失已返回202的任务。

worker使用条件领取，处理结果按attempt/run写入。客户端不调用写check_results等内部结果端点。后台重试不覆盖成功尝试；失败有脱敏错误码和结束时间。

运行完成后检查最新修订与数据来源；状态写入与结果提交同事务。材料切换/撤回使旧解析结果成为历史，不能重新激活旧版本或覆盖当前字段。

### 9.3 复核与当前状态

复核record追加保存，task状态和task_revision同事务更新。字段纠正同时更新办件修订；其他意见不改原rule结果。任务完成只是完成该任务，整体prepared由新检查和明确汇总策略决定。

历史问题不更新“已解决”字段。当前页可以提供计算的review_summary与latest_check摘要，分别标明历史发现、工作人员反馈和新运行结论。

### 9.4 存储清理

撤回、归档、删除声明与实际文件清理分开。文件清理同步处理原图、缩略图、OCR原输出、导出件和相关缓存；数据库文件availability记录purged。审计保留最少描述，不能把全文复制进审计绕过删除。

## 10. 索引与数据库约束检查

| 常见查询/冲突 | 索引或约束 |
| --- | --- |
| 居民办件列表 | applications(owner_user_id,created_at,id) |
| 当前情形材料要求 | material_requirements(matter_version_id,sort_order) |
| 问卷问题 | UNIQUE(matter_version_id,question_code) |
| 参与人范围 | UNIQUE(id,application_id)及同范围复合FK |
| 同材料当前版本 | document_versions(document_id) WHERE status='active'部分唯一 |
| 解析尝试 | UNIQUE(document_version_id,attempt_no)；活动尝试可增加部分唯一 |
| 字段及纠正顺序 | extracted_fields(extraction_run_id,field_key)；UNIQUE(field_id,correction_no) |
| 运行历史/幂等 | UNIQUE(application_id,run_no)；UNIQUE(application_id,idempotency_key) |
| 活动复核去重 | issue/application两种scope分别部分唯一，与原设计一致 |
| 队列 | review_tasks(status,priority,created_at,id) |
| 消息顺序 | UNIQUE(task_id,message_no) |
| 通知列表 | notifications(recipient_user_id,created_at,id) |
| 幂等通用记录 | UNIQUE(user_id,operation,key)及expires_at索引 |

FK只校验直接关系，仍需服务层验证字段是否属于本次run选定版本、来源是否为该规则依据、材料type是否匹配requirement等跨表路径。发布冻结需由受控写服务及数据库约束策略共同执行。

## 11. 第一版开发与接口验收顺序

1. **公开配置与账号**：U01/U02、M01—M04；能查询真实核对过的指南。
2. **办件和问卷**：A01—A03、Q01/Q02、P01—P03、C01；清单随情形变化。
3. **上传和识别**：D01—D06、D09—D12；多页版本、字段确认与证据定位。
4. **预审**：K01—K05；正常、缺失、冲突、模糊材料能产生不同结果。
5. **人工复核**：R01—R04、S01—S06；两个账户完成领取、反馈、补传和重检。
6. **线下准备**：L01/L02；完整携带清单和独立地点展示。
7. **配置复用**：B01—B06、B09—B23、B27/B28；第二情形或事项读取同一流程。
8. **扩展**：消息、PDF、模型整理草稿、统计、授权管理等P1。

管理员P0可先用简单表单/配置导入，但导入仍通过同样的范围校验与发布服务，不能绕过版本约束。

### 11.1 必须验证的接口场景

- [ ] 不登录可看公开指南，但不能看任何居民文件。
- [ ] 用户B换成用户A的app_id/file_id/run_id/task_id仍被拒绝。
- [ ] 请求传入owner_user_id、assigned_to、pass等非法写字段被拒绝。
- [ ] 问卷缺失与unknown不会被当成false漏掉条件材料。
- [ ] 代理人与申请人字段分别关联，不把不同人员差异误报冲突。
- [ ] 同一幂等键重试创建办件/上传/检查只产生一次提交；不同内容409。
- [ ] 上传中途失败旧active不变，无半完整新版本；孤儿临时文件可清理。
- [ ] 材料替换后旧报告仍引用旧文件、旧字段有效值。
- [ ] 解析换模型成功后选用新尝试并增加修订，旧检查显示过期。
- [ ] 检查期间问卷或材料变化，旧任务不覆盖新prepared状态。
- [ ] partial检查、技术错误、unknown不会显示整体材料无误。
- [ ] 两人同时领取任务只有一人成功，未领取者不能读原图。
- [ ] 材料更新或任务被取消后，旧版本提交复核返回冲突。
- [ ] 字段修正、复核评论和材料真实内容变更区别明确。
- [ ] 已发布配置不能PATCH，草稿发布过程中编辑冲突被发现。
- [ ] 未启用真实人工、预约或部门接口时不承诺官方服务结果。

## 12. 开发成果与边界

这份文档可以转为FastAPI路由、请求/响应类型、权限依赖、业务服务、数据模型与迁移，再由接口规范生成前端类型。应先对照本地现有项目实际路径和账号模型进行适配，不重建已有认证表。

本文尚未生成可执行OpenAPI、SQL迁移或后端代码，也没有在真实数据库执行测试。新增表字段、接口DTO和状态策略应作为实现时的统一契约，先完成一个事项闭环，再按测试和业务需要扩展。
