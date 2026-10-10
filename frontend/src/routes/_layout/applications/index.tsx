import { Link, createFileRoute } from "@tanstack/react-router"
import { ArrowRight, ClipboardList, Plus } from "lucide-react"

import { DemoNotice } from "@/components/Precheck/DemoNotice"
import { StatusBadge } from "@/components/Precheck/StatusBadge"
import { Button } from "@/components/ui/button"
import { demoApplication } from "@/lib/precheck-demo"

export const Route = createFileRoute("/_layout/applications/")({ component: Applications })

function Applications() {
  return <div className="space-y-6">
    <DemoNotice />
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-bold">我的办件</h1><p className="mt-1 text-muted-foreground">查看自己的材料准备进度、预审报告和复核反馈。</p></div><Button asChild><Link to="/services"><Plus className="mr-2 size-4" />新建办件</Link></Button></div>
    <article className="rounded-xl border bg-card p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-sm text-muted-foreground">{demoApplication.version}</p><h2 className="mt-1 text-lg font-semibold">{demoApplication.matterName}</h2><p className="mt-2 text-sm text-muted-foreground">{demoApplication.applicant} · 最近更新：{demoApplication.updatedAt}</p></div><StatusBadge status={demoApplication.status} /></div><div className="mt-5 flex flex-wrap gap-2"><Button asChild><Link to="/applications/$applicationId" params={{ applicationId: demoApplication.id }}>继续准备 <ArrowRight className="ml-2 size-4" /></Link></Button><Button asChild variant="outline"><Link to="/applications/$applicationId/checks/$runId/report" params={{ applicationId: demoApplication.id, runId: "demo-run-001" }}>查看最新报告</Link></Button></div></article>
    <div className="rounded-xl border border-dashed p-8 text-center text-muted-foreground"><ClipboardList className="mx-auto mb-3 size-7" />办件状态由后端根据材料、检查和复核任务计算；此处为演示展示。</div>
  </div>
}
