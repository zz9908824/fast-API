export type Matter = {
  id: string
  name: string
  region: string
  description: string
  location: string
  checkedAt: string
  supported: boolean
}

export const matters: Matter[] = [
  {
    id: "living-assistance-demo",
    name: "社区困难家庭帮扶申请（演示）",
    region: "示例社区",
    description: "用于演示材料清单、上传、预审与人工复核的完整流程。",
    location: "示例社区便民服务中心",
    checkedAt: "2026-10-10",
    supported: true,
  },
  {
    id: "senior-service-demo",
    name: "老年人服务申请指南（演示）",
    region: "示例社区",
    description: "公开办理指南示例，暂未开放线上材料预审。",
    location: "示例社区便民服务中心",
    checkedAt: "2026-10-08",
    supported: false,
  },
]

export const demoApplication = {
  id: "demo-application-001",
  matterName: matters[0].name,
  applicant: "张先生（申请人）",
  status: "待补正",
  updatedAt: "刚刚",
  version: "事项配置第 1 版",
}

export const checklist = [
  { name: "申请表", status: "已上传", action: "查看材料", note: "请确认申请人签名完整。" },
  { name: "身份证明", status: "待补充", action: "补传材料", note: "需上传正反面清晰照片。" },
  { name: "情况说明材料", status: "待准备", action: "查看获取方式", note: "可按指南准备纸质材料。" },
  { name: "原件核验", status: "现场出示", action: "查看线下要求", note: "线上无需上传，线下请携带原件。" },
]

export const issues = [
  {
    title: "身份证明材料缺少反面",
    type: "明确缺失",
    action: "补传材料",
    detail: "当前仅收到身份证明正面，请补充反面清晰照片后重新检查。",
    source: "材料要求：身份证明需包含正反面",
  },
  {
    title: "申请人姓名待核对",
    type: "字段冲突",
    action: "核对识别信息",
    detail: "申请表识别为“张三”，身份证明识别为“张山”。请对照原图确认。",
    source: "核验规则：同一申请人姓名一致性检查",
  },
]

export const reviewTasks = [
  { id: "review-001", matter: matters[0].name, issue: "申请人姓名待核对", status: "待领取", createdAt: "10 分钟前", priority: "普通" },
  { id: "review-002", matter: matters[0].name, issue: "材料清晰度待确认", status: "处理中", createdAt: "35 分钟前", priority: "较高" },
]
