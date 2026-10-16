<script setup lang="ts">
import { onLaunch } from "@dcloudio/uni-app"

onLaunch(() => {
  // Keep the token in one well-known location.  Every protected request adds it.
  const token = uni.getStorageSync("access_token")
  if (token) uni.setStorageSync("access_token", token)
})
</script>

<style>
page { background: #f5f7fb; color: #1f2937; font-size: 28rpx; }
button::after { border: 0; }
.card { margin: 24rpx; padding: 28rpx; border-radius: 18rpx; background: #fff; box-shadow: 0 4rpx 18rpx rgba(15, 23, 42, .06); }
.primary { background: #1677ff; color: #fff; }
.muted { color: #64748b; }
.danger { color: #dc2626; }
</style>
