import { Link, Outlet, createFileRoute } from "@tanstack/react-router"
import { CheckCircle2, FileUp, ListChecks, ScanText, Users } from "lucide-react"

import { DemoNotice } from "@/components/Precheck/DemoNotice"
import { StatusBadge } from "@/components/Precheck/StatusBadge"
import { Button } from "@/components/ui/button"
import { checklist, demoApplication } from "@/lib/precheck-demo"

export const Route = createFileRoute("/_layout/applications/$applicationId")({ component: ApplicationWorkspace })

function ApplicationWorkspace() {
  const { applicationId } = Route.useParams()
  return <div className="space-y-6">
    <DemoNotice />
    <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm text-muted-foreground">办件编号：{applicationId}</p><h1 className="mt-1 text-2xl font-bold">{demoApplication.matterName}</h1><p className="mt-1 text-muted-foreground">账户创建人、申请人和代办人可能不同，请在情形确认中核对。</p></div><StatusBadge status={demoApplication.status} /></div>
    <nav className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      <Step icon={<Users />} title="情形与参与人" text="确认申请人、代办人和办理情形" />
      <Step icon={<ListChecks />} title="材料清单" text="按当前情形显示适用材料" />
      <Step icon={<FileUp />} title="上传与确认" text="上传文件并核对关键识别字段" />
      <Step icon={<ScanText />} title="检查与补正" text="发起预审并按问题处理" />
    </nav>
    <section className="rounded-xl border bg-card p-5"><div className="mb-4 flex items-center justify-between"><div><h2 className="font-semibold">个性化材料清单</h2><p className="text-sm text-muted-foreground">填写情形后生成；“已上传”不代表材料已通过检查。</p></div><Button asChild variant="outline"><Link to="/applications/$applicationId/checks/$runId/report" params={{ applicationId, runId: "demo-run-001" }}>查看检查报告</Link></Button></div><div className="space-y-3">{checklist.map((item) => <div key={item.name} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4"><div><h3 className="font-medium">{item.name}</h3><p className="mt-1 text-sm text-muted-foreground">{item.note}</p></div><div className="flex items-center gap-2"><StatusBadge status={item.status} /><Button size="sm" variant="outline">{item.action}</Button></div></div>)}</div></section>
    <section className="rounded-xl border border-primary/30 bg-primary/5 p-5"><CheckCircle2 className="mb-2 size-5 text-primary" /><h2 className="font-semibold">开始材料检查</h2><p className="mt-1 text-sm text-muted-foreground">检查会固定本次情形、材料版本和规则版本。上传或修改后需重新检查。</p><Button asChild className="mt-4"><Link to="/applications/$applicationId/checks/$runId/report" params={{ applicationId, runId: "demo-run-001" }}>查看演示检查结果</Link></Button></section>
    <Outlet />
  </div>
}

function Step({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) { return <div className="rounded-lg border p-4"><div className="mb-2 text-primary">{icon}</div><h2 className="font-medium">{title}</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">{text}</p></div> }
