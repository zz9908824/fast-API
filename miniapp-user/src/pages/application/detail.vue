<script setup lang="ts">
import { onLoad, onShow } from "@dcloudio/uni-app"
import { computed, ref } from "vue"
import { API_BASE_URL } from "../../config"
import { authHeaders, request, requireLogin } from "../../utils/request"

type AppDetail = { id: string; application_no: string; status: string; content_revision: number; matter: { matter_name: string; region_name: string | null } }
type ChecklistItem = { item_kind: "requirement" | "extra"; requirement_id: string; name: string; requirement_level: "required" | "optional"; uploaded_file_count: number; review_decision: "pass" | "model_pass" | "reupload" | null; review_note: string | null; reupload_file_saved: boolean; review_result: { decision?: string; summary?: string } | null }
const appId = ref("")
const app = ref<AppDetail | null>(null)
const checklist = ref<ChecklistItem[]>([])
const loading = ref(true)
const busyMaterial = ref("")
const packageInfo = ref<{ id: string; package_no: number; is_current: boolean } | null>(null)
const statusLabels: Record<string, string> = { draft: "待确认情形", preparing: "准备中", needs_action: "待补传材料", review_pending: "人工复核中", prepared: "准备包已生成（待线下办理）" }
const canGenerate = computed(() => checklist.value.length > 0 && checklist.value.every((item) => item.review_decision === "pass" || item.review_decision === "model_pass"))

async function load() {
  if (!appId.value || !requireLogin(`/pages/application/detail?id=${appId.value}`)) return
  loading.value = true
  try {
    const [detail, items, pkg] = await Promise.all([
      request<AppDetail>(`/applications/${appId.value}`),
      request<{ items: ChecklistItem[] }>(`/applications/${appId.value}/checklist`),
      request<{ id: string; package_no: number; is_current: boolean } | null>(`/applications/${appId.value}/preparation-packages/latest`),
    ])
    app.value = detail; checklist.value = items.items; packageInfo.value = pkg
  } catch (error) { uni.showToast({ title: error instanceof Error ? error.message : "加载失败", icon: "none" }) }
  finally { loading.value = false }
}

function upload(item: ChecklistItem) {
  if (!app.value) return
  uni.chooseMessageFile({ count: 1, type: "file", success: async (chosen) => {
    const file = chosen.tempFiles[0]
    busyMaterial.value = item.requirement_id
    try {
      const result = await uni.uploadFile({
        url: `${API_BASE_URL}/applications/${appId.value}/materials/${item.requirement_id}/documents`,
        filePath: file.path, name: "files", header: authHeaders(),
        formData: { item_kind: item.item_kind, expected_revision: String(app.value!.content_revision) },
      })
      const body = JSON.parse(result.data || "{}") as { detail?: string }
      if (result.statusCode < 200 || result.statusCode >= 300) throw new Error(body.detail || "上传失败")
      uni.showToast({ title: "材料已上传", icon: "success" }); await load()
    } catch (error) { uni.showToast({ title: error instanceof Error ? error.message : "上传失败", icon: "none" }) }
    finally { busyMaterial.value = "" }
  } })
}

async function review(item: ChecklistItem, provider: "local" | "cloud") {
  if (!app.value) return
  busyMaterial.value = item.requirement_id
  try {
    const result = await request<{ decision: "pass" | "manual_review" }>(`/applications/${appId.value}/material-review`, {
      method: "POST", header: { "Content-Type": "application/json" },
      data: { provider, expected_revision: app.value.content_revision, material_id: item.requirement_id, item_kind: item.item_kind },
    })
    uni.showToast({ title: result.decision === "pass" ? "模型检查通过" : "已进入人工复核", icon: "none" }); await load()
  } catch (error) { uni.showToast({ title: error instanceof Error ? error.message : "检查失败", icon: "none" }) }
  finally { busyMaterial.value = "" }
}

async function generatePackage() {
  try {
    await request(`/applications/${appId.value}/preparation-packages`, { method: "POST" })
    uni.showToast({ title: "准备包已生成", icon: "success" }); await load()
  } catch (error) { uni.showToast({ title: error instanceof Error ? error.message : "暂不能生成", icon: "none" }) }
}
onLoad((options) => { appId.value = options.id || ""; load() })
onShow(() => { if (appId.value) load() })
</script>

<template>
  <view v-if="loading" class="empty">正在加载办件…</view>
  <view v-else-if="app">
    <view class="card"><text class="muted">材料准备记录：{{ app.application_no }}</text><text class="title">{{ app.matter.matter_name }}</text><text class="region">{{ app.matter.region_name || '适用地区待确认' }}</text><text class="status">{{ statusLabels[app.status] || app.status }}</text></view>
    <view class="card"><text class="section-title">材料清单与材料审核</text><text class="muted">每项材料独立上传与检查。模型检查仅辅助准备，人工复核或线下窗口核验才是最终依据。</text><view v-for="item in checklist" :key="item.requirement_id" class="material"><view class="row"><view><text class="name">{{ item.name }}</text><text class="muted block">{{ item.requirement_level === 'required' ? '必要材料' : '可选材料' }} · 已上传 {{ item.uploaded_file_count }} 个文件</text></view><text class="state">{{ item.review_decision === 'pass' ? '人工通过' : item.review_decision === 'model_pass' ? '模型通过' : item.review_decision === 'reupload' ? '待重传' : item.uploaded_file_count ? '待检查' : '未准备' }}</text></view><text v-if="item.review_note" class="feedback">工作人员反馈：{{ item.review_note }}</text><text v-if="item.review_result?.summary" class="result">检查结果：{{ item.review_result.summary }}</text><view v-if="item.review_decision !== 'pass'" class="actions"><button size="mini" :loading="busyMaterial === item.requirement_id" @click="upload(item)">{{ item.review_decision === 'reupload' ? '重传文件' : '上传文件' }}</button><button v-if="item.uploaded_file_count > 0 && (!item.review_decision || item.review_decision === 'reupload')" size="mini" :disabled="busyMaterial === item.requirement_id" @click="review(item, 'local')">本地模型检查</button><button v-if="item.uploaded_file_count > 0 && (!item.review_decision || item.review_decision === 'reupload')" size="mini" :disabled="busyMaterial === item.requirement_id" @click="review(item, 'cloud')">云端模型检查</button></view></view></view>
    <view class="card"><text class="section-title">线下办理提示与办理准备包</text><text class="muted">准备包汇总当前材料与办理信息。正式受理、审批和办理结论仍以线下窗口核验为准。</text><view v-if="packageInfo" class="package"><text>准备包 #{{ packageInfo.package_no }} {{ packageInfo.is_current ? '（当前版本）' : '（已过期）' }}</text><text class="muted block">当前办件状态：{{ statusLabels[app.status] || app.status }}</text></view><button class="primary" :disabled="!canGenerate" @click="generatePackage">{{ packageInfo ? '重新生成当前准备包' : '生成办理准备包' }}</button><text v-if="!canGenerate" class="hint">所有适用材料上传并通过模型或人工复核后，才能生成准备包。</text></view>
  </view>
</template>

<style scoped>
.empty { padding:120rpx 0; text-align:center; color:#64748b; }.title { display:block; margin-top:14rpx; font-size:38rpx; font-weight:700; }.region,.block { display:block; margin-top:12rpx; }.region { color:#64748b; }.status { display:inline-block; margin-top:20rpx; padding:6rpx 14rpx; border-radius:8rpx; background:#e8f2ff; color:#1677ff; font-size:24rpx; }.section-title { display:block; margin-bottom:15rpx; font-size:32rpx; font-weight:600; }.material { padding:26rpx 0; border-top:1rpx solid #edf1f5; }.row { display:flex; justify-content:space-between; gap:16rpx; }.name { font-weight:600; }.state { height:max-content; padding:5rpx 10rpx; border-radius:8rpx; background:#f1f5f9; color:#475569; font-size:22rpx; }.actions { display:flex; flex-wrap:wrap; gap:12rpx; margin-top:20rpx; }.actions button { margin:0; font-size:24rpx; }.feedback,.result { display:block; margin-top:16rpx; padding:14rpx; border-radius:10rpx; font-size:24rpx; line-height:1.5; }.feedback { background:#fff7e6; color:#9a6700; }.result { background:#eef6ff; color:#285a94; }.package { margin:22rpx 0; padding:20rpx; border-radius:12rpx; background:#f5f9ff; }.hint { display:block; margin-top:16rpx; color:#64748b; font-size:23rpx; line-height:1.5; }
</style>
