import { createFileRoute } from "@tanstack/react-router"
import { FileImage, FileText, Send } from "lucide-react"

import { DemoNotice } from "@/components/Precheck/DemoNotice"
import { Button } from "@/components/ui/button"
import { issues } from "@/lib/precheck-demo"

export const Route = createFileRoute("/_layout/staff/tasks/$taskId")({ component: TaskWorkbench })

function TaskWorkbench() { const { taskId } = Route.useParams(); return <div className="space-y-6"><DemoNotice /><div><p className="text-sm text-muted-foreground">复核任务：{taskId}</p><h1 className="text-2xl font-bold">复核工作台</h1></div><div className="grid gap-4 xl:grid-cols-3"><section className="rounded-xl border p-5"><h2 className="font-semibold">任务与问题</h2>{issues.map((issue) => <button className="mt-3 w-full rounded-lg border p-3 text-left hover:bg-muted" key={issue.title}><p className="font-medium">{issue.title}</p><p className="mt-1 text-xs text-muted-foreground">{issue.type}</p></button>)}</section><section className="rounded-xl border p-5"><div className="flex items-center gap-2"><FileImage className="size-4" /><h2 className="font-semibold">材料证据</h2></div><div className="mt-4 flex min-h-64 items-center justify-center rounded-lg bg-muted text-sm text-muted-foreground">受控原图 / PDF 预览区域<br />后端授权后才加载文件</div><p className="mt-3 text-sm text-muted-foreground">定位：身份证明，第 1 页；字段“申请人姓名”。</p></section><section className="rounded-xl border p-5"><div className="flex items-center gap-2"><FileText className="size-4" /><h2 className="font-semibold">依据与处理</h2></div><p className="mt-3 text-sm text-muted-foreground">规则依据：同一申请人姓名一致性检查。</p><textarea className="mt-4 min-h-28 w-full rounded-md border bg-background p-3 text-sm" placeholder="填写经确认的复核意见与下一步建议" /><div className="mt-4 flex gap-2"><Button>请求补充材料</Button><Button variant="outline"><Send className="mr-2 size-4" />提交复核意见</Button></div></section></div></div> }
