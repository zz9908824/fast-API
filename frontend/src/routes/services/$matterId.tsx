import { useMutation } from "@tanstack/react-query"
import { Link, createFileRoute, notFound, useNavigate } from "@tanstack/react-router"
import { Building2, ChevronDown, FileText, MapPin, ShieldCheck } from "lucide-react"

import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { createApplication } from "@/lib/applications-api"
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
  const navigate = useNavigate()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const createApplicationMutation = useMutation({
    mutationFn: () => createApplication({ matterId: matter.id, matterVersionId: matter.version_id }),
    onSuccess: (application) => {
      showSuccessToast("已创建办件，可以开始填写材料信息")
      navigate({ to: "/applications/$applicationId", params: { applicationId: application.id } })
    },
    onError: (error: Error) => showErrorToast(error.message),
  })

  const acceptanceCondition = textValue(matter.metadata_json.acceptance_condition_raw)
  const channels = listValue(matter.metadata_json.channels)

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center gap-2 border-b bg-background px-4">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
        </header>
        <main className="flex-1 p-6 md:p-8">
          <div className="mx-auto max-w-5xl space-y-6">
            <Link to="/services" className="text-sm text-muted-foreground hover:underline">← 返回事项查询</Link>

            <header className="rounded-xl border bg-card p-6 shadow-sm">
              <Badge className="mb-3">{matter.region_name}</Badge>
              <h1 className="text-3xl font-bold tracking-tight">{matter.name}</h1>
              {matter.description && <p className="mt-3 text-muted-foreground">{matter.description}</p>}
              <p className="mt-4 text-sm text-muted-foreground">事项版本：第 {matter.version_no} 版</p>
            </header>

            <section className="space-y-3" aria-label="事项详情">
              <DetailSection icon={<FileText className="size-5" />} title="材料要求">
                {matter.requirements.length > 0 ? (
                  <div className="space-y-2">
                    {matter.requirements.map((item, index) => (
                      <details key={item.id} className="group rounded-lg border bg-background">
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 font-medium">
                          <span>{index + 1}. {item.name}</span>
                          <span className="flex items-center gap-2">
                            <Badge variant={item.requirement_level === "required" ? "default" : "secondary"}>
                              {item.requirement_level === "required" ? "必要材料" : "可选材料"}
                            </Badge>
                            <ChevronDown className="size-4 transition-transform group-open:rotate-180" />
                          </span>
                        </summary>
                        <div className="border-t px-4 py-3 text-sm leading-6 text-muted-foreground">
                          <p>材料类别：{item.material_type_name}</p>
                          <p>提交方式：{item.submission_mode || "以办理窗口要求为准"}</p>
                        </div>
                      </details>
                    ))}
                  </div>
                ) : <EmptyContent text="当前事项尚未配置材料要求。" />}
              </DetailSection>

              <DetailSection icon={<ShieldCheck className="size-5" />} title="受理条件与办理渠道">
                <div className="space-y-3 text-sm leading-6 text-muted-foreground">
                  <div><p className="font-medium text-foreground">受理条件</p><p>{acceptanceCondition || "请以线下办理窗口的最新要求为准。"}</p></div>
                  <div><p className="font-medium text-foreground">办理渠道</p>{channels.length > 0 ? <ul className="list-disc space-y-1 pl-5">{channels.map((channel) => <li key={channel}>{channel}</li>)}</ul> : <p>当前版本暂未公开线上办理渠道，请咨询办理地点。</p>}</div>
                </div>
              </DetailSection>

              <DetailSection icon={<MapPin className="size-5" />} title="办理地点与联系电话">
                {matter.location_name ? (
                  <div className="space-y-1 text-sm leading-6 text-muted-foreground">
                    <p className="font-medium text-foreground">{matter.location_name}</p>
                    {matter.address && <p>地址：{matter.address}</p>}
                    {matter.phone && <p>联系电话：{matter.phone}</p>}
                    {matter.opening_hours && <p>工作时间：{matter.opening_hours}</p>}
                  </div>
                ) : <EmptyContent text="当前事项暂未配置线下办理地点。" />}
              </DetailSection>

              <DetailSection icon={<Building2 className="size-5" />} title="信息依据与提示">
                <p className="text-sm leading-6 text-muted-foreground">本页面展示已发布事项版本。材料预审结果仅用于辅助准备材料，不等同于正式受理或审批结论；办理前请结合线下窗口的最新要求核对。</p>
              </DetailSection>
            </section>

            <section className="rounded-xl border bg-card p-5">
              <h2 className="text-lg font-semibold">准备好材料后，立即办件</h2>
              <p className="mt-2 text-sm text-muted-foreground">创建办件后可保存材料准备进度、上传材料并申请工作人员复核。</p>
              <div className="mt-4">
                {isLoggedIn() ? (
                  <Button size="lg" onClick={() => createApplicationMutation.mutate()} disabled={createApplicationMutation.isPending}>
                    {createApplicationMutation.isPending ? "正在创建办件…" : "立即办件"}
                  </Button>
                ) : (
                  <Button asChild size="lg"><Link to="/login">登录后立即办件</Link></Button>
                )}
              </div>
            </section>
          </div>
        </main>
        <Footer />
      </SidebarInset>
    </SidebarProvider>
  )
}

function DetailSection({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <details className="group rounded-xl border bg-card shadow-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5">
        <span className="flex items-center gap-3 font-semibold"><span className="text-primary">{icon}</span>{title}</span>
        <ChevronDown className="size-5 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t px-5 py-4">{children}</div>
    </details>
  )
}

function EmptyContent({ text }: { text: string }) {
  return <p className="text-sm text-muted-foreground">{text}</p>
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null
}

function listValue(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : []
}
