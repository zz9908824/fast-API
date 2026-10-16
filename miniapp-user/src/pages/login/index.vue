<script setup lang="ts">
import { ref } from "vue"
import { API_BASE_URL } from "../../config"

const email = ref("")
const password = ref("")
const submitting = ref(false)
const pages = getCurrentPages()
const current = pages[pages.length - 1] as unknown as { options?: { returnUrl?: string } }
const returnUrl = current.options?.returnUrl ? decodeURIComponent(current.options.returnUrl) : "/pages/applications/index"

async function login() {
  if (!email.value || !password.value) return uni.showToast({ title: "请输入邮箱和密码", icon: "none" })
  submitting.value = true
  try {
    const result = await uni.request({ url: `${API_BASE_URL}/login/access-token`, method: "POST", header: { "Content-Type": "application/x-www-form-urlencoded" }, data: `username=${encodeURIComponent(email.value)}&password=${encodeURIComponent(password.value)}` })
    const body = result.data as { access_token?: string; detail?: string }
    if (result.statusCode < 200 || result.statusCode >= 300 || !body.access_token) throw new Error(body.detail || "登录失败")
    uni.setStorageSync("access_token", body.access_token)
    uni.showToast({ title: "登录成功", icon: "success" })
    uni.reLaunch({ url: returnUrl })
  } catch (error) { uni.showToast({ title: error instanceof Error ? error.message : "登录失败", icon: "none" }) }
  finally { submitting.value = false }
}
</script>

<template>
  <view class="page"><view class="brand"><text>哈哈快办</text><text>登录后保存材料准备进度</text></view><view class="card form"><text>邮箱</text><input v-model="email" placeholder="请输入注册邮箱" /><text>密码</text><input v-model="password" password placeholder="请输入密码" /><button class="primary" :loading="submitting" @click="login">登录</button><text class="tip">材料预审仅辅助准备，正式办理以线下窗口核验为准。</text></view></view>
</template>

<style scoped>
.page { min-height:100vh; padding-top:100rpx; }.brand { padding:0 60rpx 48rpx; color:#1677ff; }.brand text:first-child { display:block; font-size:52rpx; font-weight:700; }.brand text:last-child { display:block; margin-top:14rpx; color:#64748b; }.form { display:flex; flex-direction:column; gap:16rpx; margin:24rpx 40rpx; }.form input { height:84rpx; border:1rpx solid #dbe3ef; border-radius:12rpx; padding:0 20rpx; }.primary { margin-top:20rpx; }.tip { margin-top:18rpx; color:#64748b; font-size:24rpx; line-height:1.6; }
</style>
