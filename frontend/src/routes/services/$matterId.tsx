import { Link, createFileRoute, notFound } from "@tanstack/react-router"
import { Building2, FileText, MapPin, ShieldCheck } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { getMatter } from "@/lib/matters-api"

export const Route = createFileRoute("/services/$matterId")({
  component: MatterDetail,
  loader: async ({ params }) => {
    const matter = await getMatter(params.matterId)
    if (!matter) throw notFound()
    return matter
  },
})

function MatterDetail() {
  const matter = Route.useLoaderData()
  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6 md:p-10">
      <Link to="/services" className="text-sm text-muted-foreground hover:underline">← 返回事项查询</Link>
      <header className="rounded-xl border bg-card p-6">
        <Badge className="mb-3">{matter.region_name}</Badge>
        <h1 className="text-3xl font-bold">{matter.name}</h1>
        <p className="mt-3 text-muted-foreground">{matter.description}</p>
        <p className="mt-4 text-sm text-muted-foreground">事项版本：第 {matter.version_no} 版</p>
      </header>
      <section className="grid gap-4 md:grid-cols-2">
        <InfoCard icon={<FileText />} title="材料清单" content={matter.requirements.length ? matter.requirements.map((item) => `${item.name}（${item.requirement_level === "required" ? "必要" : "可选"}）`).join("、") : "当前版本尚未配置材料要求。"} />
        <InfoCard icon={<Building2 />} title="材料获取方式" content="请进入具体材料要求查看已核验的获取渠道、办理步骤及依据。" />
        <InfoCard icon={<MapPin />} title="线下办理地点" content={matter.location_name ? `${matter.location_name}${matter.address ? `：${matter.address}` : ""}${matter.opening_hours ? `；${matter.opening_hours}` : ""}` : "当前版本暂未配置办理地点。"} />
        <InfoCard icon={<ShieldCheck />} title="信息依据" content="本页面展示已发布事项版本；材料预审建议不等同于正式受理或审批结果。" />
      </section>
      <Button asChild size="lg"><Link to="/login">登录后开始准备材料</Link></Button>
    </main>
  )
}

function InfoCard({ icon, title, content }: { icon: React.ReactNode; title: string; content: string }) {
  return <article className="rounded-xl border p-5"><div className="mb-3 text-primary">{icon}</div><h2 className="font-semibold">{title}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{content}</p></article>
}
