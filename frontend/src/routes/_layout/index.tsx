import { createFileRoute } from "@tanstack/react-router"
import { ExternalLink, Landmark } from "lucide-react"

import { Button } from "@/components/ui/button"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [{ title: "控制台 - 政务材料预审系统" }],
  }),
})

const governmentLinks = [
  {
    name: "黑龙江政务服务网",
    description: "查询黑龙江省政务服务事项、办事指南和在线服务。",
    href: "https://www.zwfw.hlj.gov.cn",
  },
  {
    name: "哈尔滨政务服务网",
    description: "查询哈尔滨市政务服务事项及本地办理信息。",
    href: "https://hrb.zwfw.hlj.gov.cn",
  },
  {
    name: "黑龙江省人民政府",
    description: "访问黑龙江省人民政府官方网站，查看政策和政务公开信息。",
    href: "https://www.hlj.gov.cn/",
  },
]

function Dashboard() {
  const { user: currentUser } = useAuth()

  return (
    <div className="space-y-8">
      <section>
        <h1 className="max-w-sm truncate text-2xl font-semibold">
          你好，{currentUser?.full_name || currentUser?.email} 👋
        </h1>
        <p className="mt-2 text-muted-foreground">欢迎回来。可从下方进入政务服务官方网站查询最新办事信息。</p>
      </section>

      <section aria-labelledby="government-links-title">
        <div className="mb-4 flex items-center gap-2">
          <Landmark className="size-5 text-primary" />
          <h2 id="government-links-title" className="text-xl font-semibold">网址导航</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {governmentLinks.map((link) => (
            <article key={link.href} className="rounded-xl border bg-card p-5 shadow-sm">
              <h3 className="text-lg font-semibold">{link.name}</h3>
              <p className="mt-2 min-h-12 text-sm leading-6 text-muted-foreground">{link.description}</p>
              <Button asChild className="mt-5" variant="outline">
                <a href={link.href} target="_blank" rel="noreferrer">
                  访问官网 <ExternalLink className="ml-2 size-4" />
                </a>
              </Button>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
