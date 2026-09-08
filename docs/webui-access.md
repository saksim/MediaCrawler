# WebUI 访问与凭据

默认运行 `uv run python -m api.main`，仅监听 `127.0.0.1:8080`。
浏览器通过 `http://localhost:8080` 或 `http://127.0.0.1:8080` 使用 WebUI，无需额外配置。
API 校验回环客户端、Host 与浏览器 Origin；本机 Vite 3000/5173 端口仍可访问。
HTTP 与 WebSocket 使用同一个访问边界，CORS 不是身份验证。

需要远程 API 时，在服务进程环境中设置随机的 `MEDIACRAWLER_API_TOKEN`，
并在每个 HTTP 请求和 WebSocket 握手中发送 `Authorization: Bearer <token>`。
设置 token 后，本机客户端也必须携带它。请在可信 TLS 反向代理后暴露服务，
不要把 token 放入 URL 查询参数或源码。当前 WebUI 没有 token 输入功能；
远程使用浏览器界面可通过 SSH 本地端口转发访问默认回环服务。

命令行自行使用 `uvicorn --host ...` 不会移除 API 的访问检查。反向代理必须可靠地
覆盖转发头；不能通过伪造 Host 或 X-Forwarded-For 将远程匿名请求当成本机请求。
没有 token 时不要把一个把全部用户代理为回环客户端的服务暴露到公网。

WebUI 传入的社交平台 Cookie 通过子进程专用环境变量 `MEDIACRAWLER_COOKIES` 传递。
日志对该次启动的 Cookie/值进行脱敏，配置对象 repr 也不显示 Cookie。
CLI 仍支持 `--cookies`；自动化脚本应使用环境变量，避免命令历史或进程列表留存凭据。
同一系统账号/管理员仍可能检查子进程环境，因此环境变量不是对本机高权限用户的加密存储。

JSONL 结果现在支持文件列表、统计、预览和下载，预览限制 1–1000 条。
文件按行解析，空行跳过；损坏行返回 400。读取总数仍需扫描文件，但不保留全部记录对象。
