<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app"
import { ref } from "vue"
import { isLoggedIn, request, requireLogin } from "../../utils/request"

type Application = { id: string; application_no: string; matter_name: string; region_name: string | null; status: string; is_delegated: boolean; updated_at: string }
const applications = ref<Application[]>([])
const loading = ref(false)
const labels: Record<string, string> = { draft: "待确认情形", preparing: "准备中", checking: "材料检查中", needs_action: "待补传材料", review_pending: "人工复核中", prepared: "准备包已生成（待线下办理）", cancelled: "已取消" }
async function load() {
  if (!requireLogin("/pages/applications/index")) return
  loading.value = true
  try { applications.value = (await request<{ items: Application[] }>("/applications")).items.filter((item) => item.status !== "cancelled") }
  catch (error) { uni.showToast({ title: error instanceof Error ? error.message : "加载失败", icon: "none" }) }
  finally { loading.value = false }
}
function open(id: string) { uni.navigateTo({ url: `/pages/application/detail?id=${id}` }) }
onShow(load)
</script>

<template>
  <view v-if="!isLoggedIn()" class="empty">请先登录后查看材料准备记录。</view>
  <view v-else><view class="top"><text class="title">我的办件</text><text>保存材料准备、检查与复核进度</text></view><view v-if="loading" class="empty">正在加载…</view><view v-else-if="applications.length === 0" class="empty">暂无材料准备记录，请从事项查询开始。</view><view v-for="app in applications" :key="app.id" class="card" @click="open(app.id)"><view class="row"><text class="matter">{{ app.matter_name }}</text><text class="status">{{ labels[app.status] || app.status }}</text></view><text class="muted block">{{ app.region_name || '适用地区待确认' }} · {{ app.application_no }}</text><text class="muted block">最近更新：{{ new Date(app.updated_at).toLocaleString('zh-CN') }}</text><text v-if="app.is_delegated" class="delegate">他人代办</text></view></view>
</template>

<style scoped>
.top { padding:38rpx 32rpx 18rpx; }.title { display:block; font-size:40rpx; font-weight:700; }.top text:last-child { display:block; margin-top:10rpx; color:#64748b; }.empty { padding:110rpx 36rpx; text-align:center; color:#64748b; }.row { display:flex; justify-content:space-between; gap:18rpx; }.matter { font-size:32rpx; font-weight:600; }.status { padding:5rpx 12rpx; border-radius:8rpx; background:#e8f2ff; color:#1677ff; font-size:22rpx; }.block { display:block; margin-top:16rpx; }.delegate { display:inline-block; margin-top:18rpx; padding:5rpx 12rpx; border:1rpx solid #94a3b8; border-radius:8rpx; color:#475569; font-size:22rpx; }
</style>
