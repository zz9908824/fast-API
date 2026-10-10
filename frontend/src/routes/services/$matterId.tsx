import { Link, createFileRoute, notFound } from "@tanstack/react-router"
import { Building2, FileText, MapPin, ShieldCheck } from "lucide-react"

import { DemoNotice } from "@/components/Precheck/DemoNotice"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { matters } from "@/lib/precheck-demo"

export const Route = createFileRoute("/services/$matterId")({
  component: MatterDetail,
  loader: ({ params }) => {
    const matter = matters.find((item) => item.id === params.matterId)
    if (!matter) throw notFound()
    return matter
  },
})

function MatterDetail() {
  const matter = Route.useLoaderData()
  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6 md:p-10">
      <Link to="/services" className="text-sm text-muted-foreground hover:underline">← 返回事项查询</Link>
      <DemoNotice />
      <header className="rounded-xl border bg-card p-6">
        <Badge className="mb-3">{matter.region}</Badge>
        <h1 className="text-3xl font-bold">{matter.name}</h1>
        <p className="mt-3 text-muted-foreground">{matter.description}</p>
        <p className="mt-4 text-sm text-muted-foreground">信息核对日期：{matter.checkedAt}</p>
      </header>
      <section className="grid gap-4 md:grid-cols-2">
        <InfoCard icon={<FileText />} title="通用材料说明" content="申请表、身份证明及事项要求的情况说明材料。填写个人情形后，系统会生成个性化清单。" />
        <InfoCard icon={<Building2 />} title="材料获取方式" content="优先查看已核对的官方指南、下载入口或现场窗口说明；不同材料的渠道可能不同。" />
        <InfoCard icon={<MapPin />} title="线下办理地点" content={`${matter.location}。请以实际受理部门公布信息为准。`} />
        <InfoCard icon={<ShieldCheck />} title="信息依据" content="本页面仅展示已配置的演示来源与版本。材料预审建议不等同于正式审批结果。" />
      </section>
      {matter.supported ? <Button asChild size="lg"><Link to="/login">登录后开始准备材料</Link></Button> : <Button disabled size="lg">该事项暂未开放线上预审</Button>}
    </main>
  )
}

function InfoCard({ icon, title, content }: { icon: React.ReactNode; title: string; content: string }) {
  return <article className="rounded-xl border p-5"><div className="mb-3 text-primary">{icon}</div><h2 className="font-semibold">{title}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{content}</p></article>
}
