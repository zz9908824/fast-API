<script setup lang="ts">
import { onLoad } from "@dcloudio/uni-app"
import { ref } from "vue"
import { isLoggedIn, request, requireLogin } from "../../utils/request"

type MatterDetail = {
  id: string; name: string; region_name: string; description: string | null; version_id: string; version_no: number
  location_name: string | null; address: string | null; phone: string | null; opening_hours: string | null
  requirements: Array<{ id: string; name: string; requirement_level: "required" | "optional"; submission_mode: string }>
}
const matter = ref<MatterDetail | null>(null)
const loading = ref(true)
async function load(id: string) {
  try { matter.value = await request<MatterDetail>(`/matters/${id}`) }
  catch (error) { uni.showToast({ title: error instanceof Error ? error.message : "加载失败", icon: "none" }) }
  finally { loading.value = false }
}
async function startPreparation() {
  if (!matter.value) return
  if (!requireLogin(`/pages/matter/detail?id=${matter.value.id}`)) return
  try {
    const result = await request<{ id: string }>("/applications", { method: "POST", header: { "Content-Type": "application/json", "Idempotency-Key": `${Date.now()}-${Math.random()}` }, data: { matter_id: matter.value.id, matter_version_id: matter.value.version_id, create_new: false } })
    uni.navigateTo({ url: `/pages/application/detail?id=${result.id}` })
  } catch (error) { uni.showToast({ title: error instanceof Error ? error.message : "创建办件失败", icon: "none" }) }
}
onLoad((options) => { if (options.id) load(options.id) })
</script>

<template>
  <view v-if="loading" class="empty">正在加载事项…</view>
  <view v-else-if="matter">
    <view class="card hero"><text class="region">{{ matter.region_name }}</text><text class="name">{{ matter.name }}</text><text class="muted">{{ matter.description || "政务服务事项办理指南" }}</text><text class="version">当前发布版本：第 {{ matter.version_no }} 版</text></view>
    <view class="card"><text class="section-title">材料要求</text><view v-for="(item, index) in matter.requirements" :key="item.id" class="material"><view><text>{{ index + 1 }}. {{ item.name }}</text><text class="muted block">提交方式：{{ item.submission_mode || "以窗口要求为准" }}</text></view><text :class="item.requirement_level === 'required' ? 'required' : 'optional'">{{ item.requirement_level === 'required' ? '必要' : '可选' }}</text></view><text v-if="matter.requirements.length === 0" class="muted">暂未配置材料清单。</text></view>
    <view class="card"><text class="section-title">办理地点与联系电话</text><text class="block">{{ matter.location_name || "地点待确认" }}</text><text v-if="matter.address" class="muted block">地址：{{ matter.address }}</text><text v-if="matter.phone" class="muted block">电话：{{ matter.phone }}</text><text v-if="matter.opening_hours" class="muted block">工作时间：{{ matter.opening_hours }}</text></view>
    <view class="footer-action"><button class="primary" @click="startPreparation">{{ isLoggedIn() ? '开始准备材料' : '登录后开始准备' }}</button><text>建立材料准备记录后可上传材料并查看检查反馈。</text></view>
  </view>
</template>

<style scoped>
.empty { padding:120rpx 0; text-align:center; color:#64748b; }.hero { display:flex; flex-direction:column; gap:16rpx; }.region { color:#1677ff; font-size:25rpx; }.name { font-size:40rpx; font-weight:700; }.version { color:#64748b; font-size:24rpx; }.section-title { display:block; margin-bottom:24rpx; font-size:32rpx; font-weight:600; }.material { display:flex; justify-content:space-between; gap:20rpx; padding:22rpx 0; border-top:1rpx solid #edf1f5; }.block { display:block; margin-top:10rpx; line-height:1.55; }.required,.optional { align-self:flex-start; padding:5rpx 12rpx; border-radius:8rpx; font-size:22rpx; }.required { background:#e8f2ff; color:#1677ff; }.optional { background:#f1f5f9; color:#64748b; }.footer-action { position:sticky; bottom:0; padding:24rpx; background:#fff; box-shadow:0 -4rpx 16rpx rgba(0,0,0,.06); }.footer-action text { display:block; margin-top:14rpx; text-align:center; color:#64748b; font-size:23rpx; }
</style>
