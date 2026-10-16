# 哈哈快办居民端（UniApp）

这是独立于现有 React 管理网页的居民端 UniApp 工程，目标平台是微信小程序，复用现有 FastAPI 的 `/api/v1` 接口。

## 已实现页面

- 公开事项查询与关键词搜索
- 事项详情、材料要求与办理地点展示
- 账号登录（JWT 保存至小程序本地存储）
- 我的材料准备记录
- 办件材料清单、单项上传、本地/云端模型检查
- 生成办理准备包与查看当前状态

管理员的用户管理、事项配置、办件人工复核保留在现有网页管理端，不放入居民端小程序。

## 启动

1. 用 HBuilderX 导入 `miniapp-user` 目录，选择“运行到微信开发者工具”；或安装依赖后执行 `npm run dev:mp-weixin`。不要把源码目录直接导入微信开发者工具。
2. 在 `src/config.ts` 设置后端的 HTTPS 域名，例如 `https://api.example.com/api/v1`。
3. 在微信公众平台的“开发管理 → 开发设置 → 服务器域名”添加该 HTTPS 域名的 request、uploadFile、downloadFile 合法域名。

`localhost` 只在电脑本机浏览器中有效，真机和微信开发者工具不能把它当作手机上的后端地址。调试时可临时使用同一局域网的电脑 IP；正式小程序必须配置公网 HTTPS 域名。

微信开发者工具需要导入的是 UniApp 编译后输出目录（其中包含自动生成的 `app.json`）：HBuilderX 通常输出到 `unpackage/dist/dev/mp-weixin`，CLI 通常输出到 `dist/dev/mp-weixin`。

## 后端接口

小程序使用已有接口，不新增数据库表：

- `GET /matters/search`、`GET /matters/{id}`
- `POST /login/access-token`
- `GET/POST /applications`、`GET /applications/{id}`
- `GET /applications/{id}/checklist`
- `POST /applications/{id}/materials/{materialId}/documents`
- `POST /applications/{id}/material-review`
- `POST /applications/{id}/preparation-packages`

上传的材料仍由 FastAPI 保存到 Docker `application-document-storage` volume，模型检查仍走当前 OCR/本地模型或云端模型服务。
