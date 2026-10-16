<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app"
import { ref } from "vue"
import { request } from "../../utils/request"

type Matter = { id: string; name: string; region: string; description: string | null; location: string; material_count: number; supported: boolean }
const keyword = ref("")
const matters = ref<Matter[]>([])
const loading = ref(false)

async function search() {
  loading.value = true
  try {
    const data = await request<{ items: Matter[] }>(`/matters/search?q=${encodeURIComponent(keyword.value.trim())}`)
    matters.value = data.items
  } catch (error) { uni.showToast({ title: error instanceof Error ? error.message : "查询失败", icon: "none" }) }
  finally { loading.value = false }
}
function openMatter(id: string) { uni.navigateTo({ url: `/pages/matter/detail?id=${id}` }) }
onShow(search)
</script>

<template>
  <view class="hero"><text class="title">办事材料，先查清再出发</text><text class="subtitle">查询材料清单、办理地点与服务指南</text></view>
  <view class="search-row"><input v-model="keyword" confirm-type="search" placeholder="输入事项名称或服务区域" @confirm="search" /><button class="search-button" @click="search">查询</button></view>
  <view v-if="loading" class="empty">正在查询事项…</view>
  <view v-else-if="matters.length === 0" class="empty">未找到已发布事项，请调整关键词后重试。</view>
  <view v-for="matter in matters" :key="matter.id" class="card" @click="openMatter(matter.id)">
    <view class="row"><text class="matter-name">{{ matter.name }}</text><text class="tag">{{ matter.supported ? "支持预审" : "办理指南" }}</text></view>
    <text class="muted line">{{ matter.description || "查看事项办理材料与线下服务信息" }}</text>
    <text class="muted">{{ matter.region }} · {{ matter.location || "地点待确认" }}</text>
    <text class="count">材料 {{ matter.material_count }} 项　查看详情 ›</text>
  </view>
</template>

<style scoped>
.hero { padding: 56rpx 32rpx 42rpx; background: linear-gradient(135deg,#1677ff,#4f8cff); color:#fff; }
.title { display:block; font-size:42rpx; font-weight:700; }.subtitle { display:block; margin-top:16rpx; opacity:.88; }
.search-row { display:flex; gap:16rpx; margin:24rpx; }.search-row input { flex:1; height:80rpx; border-radius:14rpx; background:#fff; padding:0 24rpx; }.search-button { margin:0; background:#1677ff; color:#fff; font-size:28rpx; line-height:80rpx; }
.row { display:flex; justify-content:space-between; gap:16rpx; }.matter-name { font-size:32rpx; font-weight:600; }.tag { padding:5rpx 12rpx; border-radius:10rpx; background:#e8f2ff; color:#1677ff; font-size:23rpx; }.line { display:block; margin:18rpx 0; line-height:1.55; }.count { display:block; margin-top:20rpx; color:#1677ff; font-size:25rpx; }.empty { padding:90rpx 36rpx; text-align:center; color:#64748b; }
</style>
