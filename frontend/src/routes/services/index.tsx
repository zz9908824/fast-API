import { Link, createFileRoute } from "@tanstack/react-router"
import { ArrowRight, MapPin, Search } from "lucide-react"
import { useMemo, useState } from "react"

import { DemoNotice } from "@/components/Precheck/DemoNotice"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { matters } from "@/lib/precheck-demo"

export const Route = createFileRoute("/services/")({ component: Services })

function Services() {
  const [keyword, setKeyword] = useState("")
  const results = useMemo(
    () => matters.filter((matter) => `${matter.name}${matter.region}`.includes(keyword.trim())),
    [keyword],
  )

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 p-6 md:p-10">
      <section className="space-y-3">
        <Badge variant="outline">公开事项查询</Badge>
        <h1 className="text-3xl font-bold tracking-tight">查询办事材料与办理指南</h1>
        <p className="max-w-2xl text-muted-foreground">先查看公开事项说明；保存办件、上传材料和申请复核时再登录。</p>
      </section>
      <DemoNotice />
      <div className="relative max-w-xl">
        <Search className="absolute left-3 top-3 size-4 text-muted-foreground" />
        <Input className="pl-9" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="输入事项名称或服务区域" />
      </div>
      <section className="grid gap-4 md:grid-cols-2">
        {results.map((matter) => (
          <article key={matter.id} className="rounded-xl border bg-card p-5 shadow-sm">
            <div className="mb-3 flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold">{matter.name}</h2>
              <Badge variant={matter.supported ? "default" : "secondary"}>{matter.supported ? "支持预审" : "仅提供指南"}</Badge>
            </div>
            <p className="mb-4 text-sm text-muted-foreground">{matter.description}</p>
            <p className="mb-5 flex items-center gap-1 text-sm"><MapPin className="size-4" />{matter.region} · {matter.location}</p>
            <Button asChild className="w-full"><Link to="/services/$matterId" params={{ matterId: matter.id }}>查看事项详情 <ArrowRight className="ml-2 size-4" /></Link></Button>
          </article>
        ))}
      </section>
      {results.length === 0 && <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">未找到匹配事项，请调整关键词或服务区域。</div>}
    </main>
  )
}
