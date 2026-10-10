import { Link, createFileRoute } from "@tanstack/react-router"
import { AlertTriangle, FilePlus2, MessageSquareText, Printer } from "lucide-react"

import { DemoNotice } from "@/components/Precheck/DemoNotice"
import { StatusBadge } from "@/components/Precheck/StatusBadge"
import { Button } from "@/components/ui/button"
import { demoApplication, issues } from "@/lib/precheck-demo"

export const Route = createFileRoute("/_layout/applications/$applicationId/checks/$runId/report")({ component: Report })

function Report() {
  const { applicationId, runId } = Route.useParams()
  return <div className="space-y-6"><DemoNotice /><header className="rounded-xl border bg-card p-6"><p className="text-sm text-muted-foreground">报告编号：{runId} · 对应办件：{applicationId}</p><h1 className="mt-2 text-2xl font-bold">材料预审报告</h1><p className="mt-2 text-sm text-muted-foreground">事项：{demoApplication.matterName} · 申请人：{demoApplication.applicant} · 材料版本：演示 v1</p><div className="mt-4 rounded-lg bg-muted p-3 text-sm">本报告是材料预审建议，正式办理以受理部门核验为准。</div></header><section><div className="mb-3 flex items-center gap-2"><AlertTriangle className="size-5 text-destructive" /><h2 className="text-lg font-semibold">需要处理的问题</h2></div><div className="space-y-4">{issues.map((issue) => <article key={issue.title} className="rounded-xl border border-destructive/30 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><StatusBadge status={issue.type} /><h3 className="mt-3 font-semibold">{issue.title}</h3></div><Button size="sm" variant="outline">{issue.action}</Button></div><p className="mt-3 text-sm leading-6 text-muted-foreground">{issue.detail}</p><p className="mt-3 rounded-md bg-muted p-3 text-xs">依据：{issue.source}</p></article>)}</div></section><div className="flex flex-wrap gap-3"><Button><FilePlus2 className="mr-2 size-4" />补充材料</Button><Button variant="outline"><MessageSquareText className="mr-2 size-4" />申请人工复核</Button><Button variant="outline" onClick={() => window.print()}><Printer className="mr-2 size-4" />打印线下准备清单</Button><Button asChild variant="ghost"><Link to="/applications/$applicationId" params={{ applicationId }}>返回办件</Link></Button></div></div>
}
