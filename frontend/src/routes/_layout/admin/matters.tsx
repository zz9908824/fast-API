import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { Ban, FileText, MapPin, Pencil, Plus, RefreshCw, ShieldCheck, Sparkles } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { applyMatterImport, startMatterImport, uploadMatterImport, type MatterImportInput } from "@/lib/matter-import-api"
import { createDraftFromFinishedVersion, disableMatter, getFinishedMatterVersions, type FinishedMatterVersion } from "@/lib/admin-matters-api"
import { MATTER_CATALOG_SECTIONS, categoriesForMatter, categoryById } from "@/lib/matter-catalog"

export const Route = createFileRoute("/_layout/admin/matters")({ component: MatterAdmin })

const initialImport: MatterImportInput = {
  region_code: "",
  region_name: "",
  source_url: "",
  source_kind: "guide",
  model_provider: "local",
  pasted_text: "",
  source_title_override: "",
  import_note: "",
}

function MatterAdmin() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [isImportOpen, setImportOpen] = useState(false)
  const [importForm, setImportForm] = useState<MatterImportInput>(initialImport)
  const [importFiles, setImportFiles] = useState<File[]>([])
  const [importResult, setImportResult] = useState<Awaited<ReturnType<typeof startMatterImport>> | null>(null)
  const [keyword, setKeyword] = useState("")
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const { data: matters = [], isLoading, isError, error, isFetching, refetch } = useQuery({
    queryKey: ["finished-matter-versions", keyword], queryFn: () => getFinishedMatterVersions(keyword),
  })
  const createDraft = useMutation({
    mutationFn: createDraftFromFinishedVersion,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["finished-matter-versions"] })
      queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] })
    },
  })
  const disableCurrentMatter = useMutation({
    mutationFn: disableMatter,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["finished-matter-versions"] }),
  })
  const startImport = useMutation({
    mutationFn: () => importFiles.length ? uploadMatterImport(importForm, importFiles) : startMatterImport(importForm),
    onSuccess: setImportResult,
  })
  const applyImport = useMutation({
    mutationFn: applyMatterImport,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["draft-matter-versions"] })
      setImportOpen(false)
      setImportResult(null)
      setImportForm(initialImport)
      setImportFiles([])
      navigate({ to: "/admin/matter-reviews" })
    },
  })

  const copyToDraft = (matter: FinishedMatterVersion) => {
    if (window.confirm(`确认基于“${matter.name}”第 ${matter.version_no} 版创建新的草稿版本吗？已发布版本会被保留，草稿中的信息需要重新核验。`)) createDraft.mutate(matter)
  }
  const openImport = () => {
    setImportResult(null)
    setImportOpen(true)
  }
  const disableMatterItem = (matter: FinishedMatterVersion) => {
    if (window.confirm(`确认禁用事项“${matter.name}”吗？禁用后不会出现在公开事项查询中，也不能新建办件；已有历史办件不受影响。`)) {
      disableCurrentMatter.mutate(matter)
    }
  }
  const selectedCategory = categoryById(categoryId)
  const visibleMatters = categoryId
    ? matters.filter((matter) => categoriesForMatter(matter).some((category) => category.id === categoryId))
    : matters

  return <div className="space-y-6">
    <header><h1 className="text-2xl font-bold">事项配置</h1><p className="mt-1 text-muted-foreground">展示已完成核验并发布的事项版本；可智能导入官方资料生成待复核草稿，或基于已发布版本创建修订草稿。</p></header>
    <div className="flex flex-wrap items-center gap-2"><Input className="w-full sm:w-80" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索事项名称、事项编码、地区或办理地点" /><Button variant="outline" disabled={isFetching} onClick={() => refetch()}>查询</Button><Button variant="outline" disabled={isFetching} onClick={() => refetch()}><RefreshCw className={`mr-2 size-4 ${isFetching ? "animate-spin" : ""}`} />{isFetching ? "正在刷新…" : "刷新事项"}</Button><Button onClick={openImport}><Plus className="mr-2 size-4" />新增事项</Button></div>
    <section className="rounded-xl border bg-muted/20 p-4"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div><h2 className="font-semibold">事项服务分类</h2><p className="mt-1 text-sm text-muted-foreground">按图片中的热门服务、个人生命周期和群体服务分类浏览已发布事项。分类根据事项名称与说明自动匹配。</p></div>{categoryId && <Button size="sm" variant="ghost" onClick={() => setCategoryId(null)}>清除分类</Button>}</div><div className="space-y-3">{MATTER_CATALOG_SECTIONS.map((section) => <div className="flex flex-wrap items-center gap-2" key={section.id}><span className="w-28 text-sm font-medium text-muted-foreground">{section.title}</span>{section.categories.map((category) => { const count = matters.filter((matter) => categoriesForMatter(matter).some((item) => item.id === category.id)).length; return <Button key={category.id} size="sm" variant={category.id === categoryId ? "default" : "outline"} onClick={() => setCategoryId(category.id === categoryId ? null : category.id)}>{category.label}<span className="ml-1 opacity-70">{count}</span></Button> })}</div>)}</div></section>
    {isLoading && <p className="text-muted-foreground">正在加载已发布事项…</p>}
    {isError && <p className="text-destructive">{error instanceof Error ? error.message : "已发布事项加载失败，请确认管理员登录状态和后端服务。"}</p>}
    {!isLoading && !isError && visibleMatters.length === 0 && <div className="rounded-xl border border-dashed p-10 text-center text-muted-foreground">{selectedCategory ? `“${selectedCategory.label}”分类暂未找到已发布事项。` : keyword.trim() ? "未找到匹配的已发布事项。" : "当前没有状态为 finished 的已发布事项。"}</div>}
    {!isLoading && !isError && visibleMatters.length > 0 && <div className="grid gap-4 md:grid-cols-2">{visibleMatters.map((matter) => <article className="rounded-xl border p-5" key={matter.version_id}>
      <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{matter.name}</h2><p className="mt-1 text-sm text-muted-foreground">{matter.region_name} · 第 {matter.version_no} 版</p></div><Badge variant={matter.is_active ? "default" : "secondary"}>{matter.is_active ? "已发布 finished" : "已禁用"}</Badge></div>
      {categoriesForMatter(matter).length > 0 && <div className="mt-3 flex flex-wrap gap-1">{categoriesForMatter(matter).map((category) => <Badge key={category.id} variant="outline" className="font-normal">{category.label}</Badge>)}</div>}
      <p className="mt-3 text-sm text-muted-foreground">{matter.description ?? "未填写事项说明"}</p>
      <div className="mt-4 space-y-1 text-sm text-muted-foreground"><p>事项编码：{matter.official_code ?? matter.code}</p><p>办理地点：{matter.location_name ?? "未配置"}</p><p>发布日期：{formatDate(matter.published_at)}</p></div>
      <div className="mt-5 grid grid-cols-3 gap-2 text-center text-xs"><MatterInfo icon={<FileText />} text={`材料要求 ${matter.material_count} 项`} /><MatterInfo icon={<ShieldCheck />} text={`获取方式 ${matter.acquisition_method_count} 项`} /><MatterInfo icon={<MapPin />} text={matter.location_name ? "已配置地点" : "未配置地点"} /></div>
      <div className="mt-4 flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={createDraft.isPending} onClick={() => copyToDraft(matter)}><Pencil className="mr-1 size-3" />{createDraft.isPending ? "正在创建草稿…" : "编辑（创建草稿版本）"}</Button>{matter.is_active && <Button size="sm" variant="destructive" disabled={disableCurrentMatter.isPending} onClick={() => disableMatterItem(matter)}><Ban className="mr-1 size-3" />禁用当前事项</Button>}{(createDraft.error instanceof Error || disableCurrentMatter.error instanceof Error) && <p className="w-full text-sm text-destructive">{createDraft.error instanceof Error ? createDraft.error.message : disableCurrentMatter.error instanceof Error ? disableCurrentMatter.error.message : ""}</p>}</div>
    </article>)}</div>}
    <MatterImportDialog open={isImportOpen} form={importForm} files={importFiles} result={importResult} isExtracting={startImport.isPending} isApplying={applyImport.isPending} error={startImport.error ?? applyImport.error} onOpenChange={setImportOpen} onChange={setImportForm} onFilesChange={setImportFiles} onExtract={() => startImport.mutate()} onApply={() => importResult && applyImport.mutate(importResult.id)} />
  </div>
}

function MatterImportDialog({ open, form, files, result, isExtracting, isApplying, error, onOpenChange, onChange, onFilesChange, onExtract, onApply }: {
  open: boolean; form: MatterImportInput; files: File[]; result: Awaited<ReturnType<typeof startMatterImport>> | null; isExtracting: boolean; isApplying: boolean; error: unknown
  onOpenChange: (open: boolean) => void; onChange: (value: MatterImportInput) => void; onFilesChange: (files: File[]) => void; onExtract: () => void; onApply: () => void
}) {
  const canExtract = form.region_code.trim() && form.region_name.trim() && form.source_url.trim() && (form.pasted_text.trim().length >= 20 || files.length > 0)
  const errorMessage = error instanceof Error ? error.message : null
  const appendFiles = (selected: File[]) => {
    const merged = [...files, ...selected]
    const uniqueFiles = merged.filter((file, index) => merged.findIndex((candidate) =>
      candidate.name === file.name && candidate.size === file.size && candidate.lastModified === file.lastModified,
    ) === index)
    onFilesChange(uniqueFiles)
  }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
    <DialogHeader><DialogTitle className="flex items-center gap-2"><Sparkles className="size-5 text-primary" />新增事项：智能导入资料</DialogTitle></DialogHeader>
    {!result ? <div className="space-y-4 py-2">
      <div className="grid gap-4 md:grid-cols-2"><Field label="地区编码 *"><Input value={form.region_code} onChange={(e) => onChange({ ...form, region_code: e.target.value })} placeholder="例如：230109" /></Field><Field label="地区名称 *"><Input value={form.region_name} onChange={(e) => onChange({ ...form, region_name: e.target.value })} placeholder="例如：哈尔滨市松北区" /></Field></div>
      <Field label="官方来源链接 *"><Input type="url" value={form.source_url} onChange={(e) => onChange({ ...form, source_url: e.target.value })} placeholder="https://..." /></Field>
      <Field label="字段提取模型 *"><div className="grid gap-3 md:grid-cols-2"><label className={`cursor-pointer rounded-lg border p-3 ${form.model_provider === "local" ? "border-primary bg-primary/5" : ""}`}><input className="mr-2" type="radio" name="model-provider" checked={form.model_provider === "local"} onChange={() => onChange({ ...form, model_provider: "local" })} />本地模型<p className="mt-1 text-xs text-muted-foreground">文件先由本机 OCR 识别，文字仅在本机处理；速度较慢，适合敏感材料。</p></label><label className={`cursor-pointer rounded-lg border p-3 ${form.model_provider === "cloud" ? "border-primary bg-primary/5" : ""}`}><input className="mr-2" type="radio" name="model-provider" checked={form.model_provider === "cloud"} onChange={() => onChange({ ...form, model_provider: "cloud" })} />云端模型<p className="mt-1 text-xs text-muted-foreground">PDF 和图片原文件会直接发送至百炼 Qwen 识别；Word/TXT 会发送其文本内容。请勿上传不应出境的敏感材料。</p></label></div></Field>
      <div className="grid gap-4 md:grid-cols-2"><Field label="资料类型"><select className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm" value={form.source_kind} onChange={(e) => onChange({ ...form, source_kind: e.target.value as MatterImportInput["source_kind"] })}><option value="guide">办事指南</option><option value="policy">政策文件</option><option value="template">表单模板</option><option value="faq">常见问题</option><option value="contact">联系方式</option></select></Field><Field label="来源标题（可选）"><Input value={form.source_title_override ?? ""} onChange={(e) => onChange({ ...form, source_title_override: e.target.value })} /></Field></div>
      <Field label="上传官方资料（可选）"><Input type="file" multiple accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,.webp" onChange={(event) => { appendFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = "" }} /><p className="text-xs text-muted-foreground">支持 PDF、Word（.docx）、TXT、JPG、PNG、WEBP；可一次选择多个文件，也可重复选择追加。单个文件不超过 10MB，总计不超过 30MB。</p>{files.length > 0 && <ul className="space-y-1 text-sm">{files.map((file, index) => <li className="flex items-center justify-between gap-2 rounded border px-2 py-1" key={`${file.name}-${file.lastModified}-${index}`}><span className="truncate">{file.name}（{Math.ceil(file.size / 1024)} KB）</span><Button type="button" size="sm" variant="ghost" onClick={() => onFilesChange(files.filter((_, fileIndex) => fileIndex !== index))}>移除</Button></li>)}</ul>}</Field>
      <Field label="可粘贴补充正文"><textarea className="min-h-40 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm" value={form.pasted_text} onChange={(e) => onChange({ ...form, pasted_text: e.target.value })} placeholder="至少上传一个文件或填写不少于 20 个字符的正文。" /></Field>
      <Field label="导入备注（可选）"><Input value={form.import_note ?? ""} onChange={(e) => onChange({ ...form, import_note: e.target.value })} placeholder="例如：2026-10-13 从官网页面人工整理" /></Field>
    </div> : <ImportPreview result={result} />}
    {errorMessage && <p className="text-sm text-destructive">{errorMessage}</p>}
    <DialogFooter>{result ? <><Button variant="outline" onClick={() => onOpenChange(false)}>稍后处理</Button><Button disabled={isApplying} onClick={onApply}>{isApplying ? "正在生成草稿…" : "生成 draft 待复核事项"}</Button></> : <Button disabled={!canExtract || isExtracting} onClick={onExtract}>{isExtracting ? "模型正在提取…" : "开始提取"}</Button>}</DialogFooter>
  </DialogContent></Dialog>
}

function ImportPreview({ result }: { result: Awaited<ReturnType<typeof startMatterImport>> }) {
  const { candidate } = result
  return <div className="space-y-4 rounded-lg border bg-muted/30 p-4 text-sm"><div><p className="font-semibold">候选事项：{candidate.matter.name ?? "未提取到"}</p><p className="mt-1 text-muted-foreground">来源：{candidate.source.title ?? "未提取到"}；材料 {candidate.materials.length} 项</p></div><div><p className="font-medium">材料候选</p><ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">{candidate.materials.length ? candidate.materials.map((item) => <li key={item.local_key}>{item.name ?? "未命名材料"}（{item.requirement_level === "required" ? "必要" : item.requirement_level === "optional" ? "可选" : "必要性待确认"}）</li>) : <li>未提取到材料</li>}</ul></div><div><p className="font-medium">代办候选</p><p className="mt-2 text-muted-foreground">是否允许代办：{candidate.delegation.delegation_allowed === true ? "允许（待人工核验）" : candidate.delegation.delegation_allowed === false ? "不允许（待人工核验）" : "未从资料中确认"}</p>{candidate.delegation.materials.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">{candidate.delegation.materials.map((item) => <li key={item.local_key}>{item.name ?? "未命名代办材料"}（{item.requirement_level === "optional" ? "可选" : "必要"}）</li>)}</ul>}</div>{candidate.uncertainties.length > 0 && <div><p className="font-medium">待进一步确认</p><ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">{candidate.uncertainties.map((item, index) => <li key={`${item.field_path}-${index}`}>{item.message}</li>)}</ul></div>}<p className="text-muted-foreground">生成后会创建 `draft`，代办结论和材料同样为 `pending`，请前往事项状态复核完成核验。</p></div>
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="space-y-2"><Label>{label}</Label>{children}</div> }
function MatterInfo({ icon, text }: { icon: React.ReactNode; text: string }) { return <div className="flex flex-col items-center gap-2 rounded-lg border p-3"><span className="text-primary">{icon}</span>{text}</div> }
function formatDate(value: string | null): string { return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "未记录" }
