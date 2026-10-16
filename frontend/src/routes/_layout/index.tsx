import { Link, createFileRoute } from "@tanstack/react-router"
import { ArrowRight, BookOpen, Building2, ClipboardCheck, ClipboardList, ExternalLink, FileCog, Landmark, MapPin, Search, Settings, ShieldCheck, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({ meta: [{ title: "首页 - 哈哈快办" }] }),
})

const governmentLinks = [
  { name: "黑龙江政务服务网", description: "查询全省政务服务事项、办事指南和在线服务。", href: "https://www.zwfw.hlj.gov.cn", domain: "zwfw.hlj.gov.cn", icon: Landmark, category: "省级政务服务" },
  { name: "哈尔滨政务服务网", description: "查询哈尔滨本地事项与办理信息。", href: "https://hrb.zwfw.hlj.gov.cn", domain: "hrb.zwfw.hlj.gov.cn", icon: Building2, category: "市级政务服务" },
  { name: "黑龙江省人民政府", description: "查看政策文件和政务公开信息。", href: "https://www.hlj.gov.cn/", domain: "hlj.gov.cn", icon: BookOpen, category: "政策与公开" },
  { name: "松北新区 AI 政务问答北北", description: "获取松北新区办事咨询帮助。", href: "https://www.songbei.gov.cn/aiqa/#/", domain: "songbei.gov.cn", icon: Sparkles, category: "智能问答" },
]

function Dashboard() {
  const { user } = useAuth()
  const isAdmin = Boolean(user?.is_superuser)
  const quickLinks = isAdmin
    ? [{ title: "事项查询", text: "查询已发布事项与材料清单", to: "/services" as const, icon: Search }, { title: "事项配置", text: "维护已发布事项与版本", to: "/admin/matters" as const, icon: FileCog }, { title: "事项状态复核", text: "核验草稿事项后发布", to: "/admin/matter-reviews" as const, icon: ClipboardCheck }]
    : [{ title: "事项查询", text: "查询材料、地点与办理指南", to: "/services" as const, icon: Search }, { title: "我的办件", text: "继续准备材料并查看反馈", to: "/applications" as const, icon: ClipboardList }, { title: "账户设置", text: "管理账户信息与安全设置", to: "/settings" as const, icon: Settings }]

  return <div className="dashboard-page space-y-8">
    <section className="dashboard-hero">
      <div className="dashboard-hero-content"><span className="dashboard-kicker"><Sparkles className="size-4" />哈哈快办</span><h1>你好，{user?.full_name || user?.email || "用户"} 👋</h1><p>从查询事项开始，把材料准备、智能检查和线下办理指引安排得更清楚。</p><Button asChild size="lg" className="dashboard-hero-button"><Link to="/services">查询办事事项 <ArrowRight className="ml-2 size-4" /></Link></Button></div>
      <div className="dashboard-illustration" aria-hidden="true"><div className="dashboard-paper"><div className="dashboard-paper-top"><span /><div><b>办事准备清单</b><small>从查询到线下办理</small></div></div>{["确认事项与办理地点", "查看所需材料", "准备并上传材料"].map((text, index) => <div className="dashboard-paper-row" key={text}><i>✓</i><span>{text}</span><em>0{index + 1}</em></div>)}<div className="dashboard-paper-foot"><MapPin className="size-4" />准备充分，再去办理</div></div></div>
    </section>

    <section><div className="section-heading"><div><p className="section-eyebrow">快速开始</p><h2>常用入口</h2></div><span>{isAdmin ? "管理工作台" : "居民服务"}</span></div><div className="dashboard-quick-grid">{quickLinks.map(({ title, text, to, icon: Icon }) => <Link key={to} to={to} className="dashboard-quick-card"><span className="dashboard-quick-icon"><Icon className="size-5" /></span><div><h3>{title}</h3><p>{text}</p></div><ArrowRight className="dashboard-quick-arrow size-4" /></Link>)}</div></section>

    <section aria-labelledby="government-links-title"><div className="section-heading"><div><p className="section-eyebrow">政务网址导航</p><h2 id="government-links-title">官方服务入口</h2></div><span>外部官方网站</span></div><div className="dashboard-link-grid">{governmentLinks.map(({ name, description, href, domain, icon: Icon, category }) => <article key={href} className="dashboard-link-card"><div className="flex items-start justify-between gap-3"><span className="dashboard-link-icon"><Icon className="size-5" /></span><span className="dashboard-link-category">{category}</span></div><h3>{name}</h3><p>{description}</p><div className="dashboard-link-bottom"><span>{domain}</span><a href={href} target="_blank" rel="noreferrer">访问官网 <ExternalLink className="size-3.5" /></a></div></article>)}</div></section>

    <section className="dashboard-tip"><ShieldCheck className="size-5" /><div><h2>出发前小提示</h2><p>线上材料检查和人工复核用于辅助准备；正式受理、材料要求及办理结论以线下受理部门核验为准。</p></div></section>
  </div>
}
