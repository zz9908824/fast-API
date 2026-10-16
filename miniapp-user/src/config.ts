// Replace before real-device testing and release.  A real WeChat mini-program
// must use an HTTPS domain registered in the WeChat console, not localhost.
// 微信开发者工具在此电脑上运行时，应直接访问本机映射的 Docker 后端端口。
// 真机调试时改为电脑在同一局域网中的 IPv4 地址；正式发布必须使用已备案的 HTTPS 域名。
export const API_BASE_URL = "http://127.0.0.1:8000/api/v1"
