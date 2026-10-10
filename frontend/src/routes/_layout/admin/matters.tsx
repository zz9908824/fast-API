import { createFileRoute } from "@tanstack/react-router"
import { FileText, MapPin, Plus, ShieldCheck } from "lucide-react"

import { DemoNotice } from "@/components/Precheck/DemoNotice"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { matters } from "@/lib/precheck-demo"

export const Route = createFileRoute("/_layout/admin/matters")({ component: MatterAdmin })

function MatterAdmin() { return <div className="space-y-6"><DemoNotice /><div className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-bold">事项与版本管理</h1><p className="mt-1 text-muted-foreground">已发布版本不可原地修改；更新应创建新的草稿版本。</p></div><Button><Plus className="mr-2 size-4" />新建事项</Button></div><div className="grid gap-4 md:grid-cols-2">{matters.map((matter) => <article className="rounded-xl border p-5" key={matter.id}><div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{matter.name}</h2><p className="mt-1 text-sm text-muted-foreground">{matter.region} · {matter.checkedAt}</p></div><Badge>{matter.supported ? "已发布" : "草稿"}</Badge></div><div className="mt-5 grid grid-cols-3 gap-2 text-center text-xs"><AdminAction icon={<FileText />} text="材料要求" /><AdminAction icon={<ShieldCheck />} text="核验规则" /><AdminAction icon={<MapPin />} text="来源与地点" /></div></article>)}</div></div> }
function AdminAction({ icon, text }: { icon: React.ReactNode; text: string }) { return <button className="flex flex-col items-center gap-2 rounded-lg border p-3 hover:bg-muted"><span className="text-primary">{icon}</span>{text}</button> }
